from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import units
from oslo_service import loopingcall

from cinder.i18n import _, _LE, _LI, _LW
from cinder import interface
from cinder.volume import driver
from cinder import exception
from cinder.volume.drivers.azure import vhd_utils as azutils
from cinder.volume.drivers.azure.adapter import Azure
from azure.common import AzureMissingResourceHttpError
from azure.common import AzureConflictHttpError

LOG = logging.getLogger(__name__)

volume_opts = [
    cfg.StrOpt('azure_storage_account',
               default='ops0storage0account',
               help="""Azure Storage Account Name, should be unique in Azure,
Storage account name must be between 3 and 24 characters in length
and use numbers and lower-case letters only."""),
    cfg.StrOpt('azure_storage_account_key',
               help='Azure Storage Account Key'),
    cfg.StrOpt('azure_storage_container_name',
               default='volumes',
               help='Azure Storage Container Name'),
    cfg.IntOpt('azure_total_capacity_gb',
               help='Total capacity in Azuer, in GB',
               default=500000)
]

CONF = cfg.CONF
CONF.register_opts(volume_opts)
VHD_EXT = '.vhd'


@interface.volumedriver
class AzureDriver(driver.VolumeDriver):
    """Executes commands relating to Volumes."""

    VERSION = '0.33.0'

    def __init__(self, vg_obj=None, *args, **kwargs):
        # Parent sets db, host, _execute and base config
        super(AzureDriver, self).__init__(*args, **kwargs)

        self.configuration.append_config_values(volume_opts)

        self.azure = Azure()
        self.blob = self.azure.blob
        self.blob.create_container(self.configuration.azure_storage_container_name)

    def check_for_setup_error(self):
        pass

    def get_volume_stats(self, refresh=False):
        """Obtain status of the volume service.

        :param refresh: Whether to get refreshed information
        """

        if not self._stats:
            backend_name = self.configuration.safe_get('volume_backend_name')
            if not backend_name:
                backend_name = self.__class__.__name__
            # TODO free capacity need to refresh
            data = {'volume_backend_name': backend_name,
                    'vendor_name': 'Azure',
                    'driver_version': self.VERSION,
                    'storage_protocol': 'vhd',
                    'reserved_percentage': 0,
                    'total_capacity_gb':
                        self.configuration.azure_total_capacity_gb,
                    'free_capacity_gb':
                        self.configuration.azure_total_capacity_gb}
            self._stats = data
        return self._stats

    def _get_blob_name(self, name):
        """Get blob name from volume name
        """
        return '{}{}'.format(name, VHD_EXT)

    def create_volume(self, volume):
        size = volume.size * units.Gi
        blob_size = size + 512
        blob_name = self._get_blob_name(volume.name)
        LOG.debug("Calling Create Volume '{}' in Azure ..."
                  .format(volume.name))
        vhd_footer = azutils.generate_vhd_footer(size)
        self.blob.create_blob(
            self.configuration.azure_storage_container_name,
            blob_name, blob_size)
        try:
            self.blob.update_page(
                self.configuration.azure_storage_container_name,
                blob_name, vhd_footer,
                start_range=size, end_range=blob_size-1)
        except Exception:
            self.blob.delete_blob(
                self.configuration.azure_storage_container_name,
                blob_name
            )
            raise Exception("Create Volume '{}' in Azure failed."
                            .format(volume.name))
        else:
            LOG.info("Created Volume '{}' in Azure."
                      .format(volume.name))

    def delete_volume(self, volume):
        blob_name = self._get_blob_name(volume.name)
        LOG.debug("Calling Delete Volume '{}' in Azure ..."
                  .format(volume.name))
        try:
            self.blob.delete_blob(
                self.configuration.azure_storage_container_name,
                blob_name, delete_snapshots='include')
        except AzureMissingResourceHttpError:
            LOG.info('Volume blob: {} does not exist.'.format(volume.name))
        else:
            LOG.info("Delete Volume '{}' in Azure finish."
                      .format(volume.name))

    def remove_export(self, context, volume):
        pass

    def ensure_export(self, context, volume):
        pass

    def create_export(self, context, volume, connector, vg=None):
        # nothing to do in azure.
        pass

    def initialize_connection(self, volume, connector, **kwargs):
        blob_name = self._get_blob_name(volume.name)
        vhd_uri = self.blob.make_blob_url(
            self.configuration.azure_storage_container_name, blob_name)
        connection_info = {
            'driver_volume_type': 'vhd',
            'data': {'volume_name': volume.name,
                     'volume_id': volume.id,
                     'vhd_uri': vhd_uri,
                     'vhd_size_gb': volume.size,
                     'vhd_name': volume.name
                     }
            }
        return connection_info

    def validate_connector(self, connector):
        pass

    def terminate_connection(self, volume, connector, **kwargs):
        pass

    def create_snapshot(self, snapshot):
        snapshot_blob = self.blob.snapshot_blob(
            self.configuration.azure_storage_container_name,
            self._get_blob_name(snapshot['volume_name'])
        )
        azure_snapshot_id = snapshot_blob.snapshot
        LOG.info('Created Snapshot: {} in Azure.'.format(azure_snapshot_id))
        metadata = snapshot['metadata']
        metadata['azure_snapshot_id'] = azure_snapshot_id
        return dict(metadata=metadata)

    def delete_snapshot(self, snapshot):
        azure_snapshot_id = snapshot['metadata']['azure_snapshot_id']
        LOG.debug("Calling Delete Snapshot: {} in Azure."
                  .format(azure_snapshot_id))
        try:
            self.blob.delete_blob(
                self.configuration.azure_storage_container_name,
                self._get_blob_name(snapshot['volume_name']),
                snapshot=azure_snapshot_id
            )
        except AzureMissingResourceHttpError:
            LOG.info('Snapshot blob: {} does not exist.'
                     .format(azure_snapshot_id))
        else:
            LOG.info('Deleted Snapshot: {} in Azure.'
                      .format(azure_snapshot_id))

    def create_volume_from_snapshot(self, volume, snapshot):
        blob_name = self._get_blob_name(volume.name)
        azure_snapshot_id = snapshot['metadata']['azure_snapshot_id']
        old_blob_uri = self.blob.make_blob_url(
            self.configuration.azure_storage_container_name,
            self._get_blob_name(snapshot['volume_name']))
        snapshot_uri = '{}?snapshot={}'.format(old_blob_uri,
                                               azure_snapshot_id)
        exists = self.blob.exists(
            self.configuration.azure_storage_container_name,
            self._get_blob_name(snapshot['volume_name']),
            snapshot=azure_snapshot_id
        )
        if not exists:
            LOG.warn('Copy an Inexistent Snapshot: {} in Azure.'.
                     format(azure_snapshot_id))
            raise exception.SnapshotNotFound(snapshot_id=snapshot['id'])
        self.blob.copy_blob(
            self.configuration.azure_storage_container_name,
            blob_name, snapshot_uri)

        def _wait_for_copy():
            """Called at an copy until finish."""
            copy = self.blob.get_blob_properties(
                self.configuration.azure_storage_container_name,
                blob_name)
            state = copy.properties.copy.status

            if state == 'success':
                LOG.info(_LI("Created Volume from Snapshot: {} in Azure.".
                             format(azure_snapshot_id)))
                raise loopingcall.LoopingCallDone()
            else:
                LOG.debug(
                    'Create Volume from Snapshot: {} in Azure Progress '
                    '{}'.format(
                        azure_snapshot_id, copy.properties.copy.progress))

        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_copy)
        timer.start(interval=0.5).wait()
        if volume['size'] != snapshot['volume_size']:
            LOG.warn(_LW("Created Volume from Snapshot: {} in Azure can't be "
                         "resized, use Snapshot size {} GB for new Volume.".
                         format(blob_name, snapshot['volume_size'])))
            volume.update(dict(size=snapshot['volume_size']))
            volume.save()
        LOG.info('Create Volume from Snapshot: {} in '
                  'Azure.'.format(azure_snapshot_id))

    def create_cloned_volume(self, volume, src_vref):
        src_blob_name = self._get_blob_name(src_vref['name'])
        exists = self.blob.exists(
            self.configuration.azure_storage_container_name, src_blob_name)
        if not exists:
            LOG.warn('Copy an Inexistent Volume: {} in Azure.'.
                     format(src_blob_name))
            raise exception.VolumeNotFound(volume_id=src_vref['id'])

        blob_name = self._get_blob_name(volume.name)
        src_blob_uri = self.blob.make_blob_url(
            self.configuration.azure_storage_container_name, src_blob_name)
        self.blob.copy_blob(
            self.configuration.azure_storage_container_name,
            blob_name, src_blob_uri)

        def _wait_for_copy():
            """Called at an copy until finish."""
            copy = self.blob.get_blob_properties(
                self.configuration.azure_storage_container_name,
                blob_name)
            state = copy.properties.copy.status

            if state == 'success':
                LOG.info(_LI("Created Clone Volume: {} in Azure.".
                             format(blob_name)))
                raise loopingcall.LoopingCallDone()
            else:
                LOG.debug(
                    'Create Clone Volume: {} in Azure Progress '
                    '{}'.format(blob_name, copy.properties.copy.progress))

        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_copy)
        timer.start(interval=0.5).wait()
        if volume['size'] != src_vref['size']:
            LOG.warn(_LW("Clone Volume: {} in Azure can't be resized,"
                         "use source size {} GB for new Volume.".
                         format(blob_name, src_vref['size'])))
            volume.update(dict(size=src_vref['size']))
            volume.save()
        LOG.info('Create Volume from Snapshot: {} in '
                  'Azure.'.format(blob_name))
