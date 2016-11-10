import math
import os
import socket

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import importutils
from oslo_utils import units
from oslo_service import loopingcall

from cinder.brick.local_dev import lvm as lvm
from cinder import exception
from cinder.i18n import _, _LE, _LI, _LW
from cinder.image import image_utils
from cinder import interface
from cinder import objects
from cinder import utils
from cinder.volume import driver
from cinder.volume import utils as volutils
from azure.storage import CloudStorageAccount
from cinder.volume.drivers.azure import vhd_utils as azutils
from azure.storage.blob.models import  Include
from cinder import exception

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

]

CONF = cfg.CONF
CONF.register_opts(volume_opts)
VHD = '.vhd'


@interface.volumedriver
class AzureDriver(driver.VolumeDriver):
    """Executes commands relating to Volumes."""

    VERSION = '0.33.0'

    def __init__(self, vg_obj=None, *args, **kwargs):
        # Parent sets db, host, _execute and base config
        super(AzureDriver, self).__init__(*args, **kwargs)

        self.configuration.append_config_values(volume_opts)
        self.account = CloudStorageAccount(
            account_name=self.configuration.azure_storage_account,
            account_key=self.configuration.azure_storage_account_key)
        self.storage = self.account.create_page_blob_service()
        self.storage.create_container(self.configuration.azure_storage_container_name)

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
            data = {'volume_backend_name': backend_name,
                    'vendor_name': 'Azure',
                    'driver_version': self.VERSION,
                    'storage_protocol': 'vhd',
                    'reserved_percentage': 0,
                    'total_capacity_gb': 'unknown',
                    'free_capacity_gb': 'unknown'}
            self._stats = data
        return self._stats

    def _get_blob_name(self, volume):
        """Get blob name from volume name
        """
        return volume.name + VHD

    def create_volume(self, volume):
        size = volume.size * units.Gi
        blob_size = size + 512
        blob_name = self._get_blob_name(volume)
        LOG.debug("Calling Create Volume '%s' in Azure ...", volume.name)
        vhd_footer = azutils.generate_vhd_footer(size)
        self.storage.create_blob(
            self.configuration.azure_storage_container_name,
            blob_name, blob_size)
        
        self.storage.update_page(
            self.configuration.azure_storage_container_name,
            blob_name, vhd_footer, start_range=size, end_range=blob_size-1)
        LOG.debug("Calling Create Volume '%s' in Azure finish.", volume.name)

    def delete_volume(self, volume):
        blob_name = self._get_blob_name(volume)
        exists = self.storage.exists(
            self.configuration.azure_storage_container_name,
            blob_name
        )

        if not exists:
            LOG.warn('Delete an Inexistent Volume: {} in Azure.'.
                     format(blob_name))
            return

        # Delete exist snapshots in Azure before Volume,
        # if thers are snapshots managed by cinder, can't go here.
        # if go here, and snapshots in Azure exists, these snapshots
        # are zombie snapshots in Azure.
        blob_pages = self.storage.list_blobs(
            self.configuration.azure_storage_container_name,
            include=Include(snapshots=True)
        )
        for i in blob_pages:
            if blob_name == i.name and i.snapshot:
                self.storage.delete_blob(
                    self.configuration.azure_storage_container_name,
                    blob_name, snapshot=i.snapshot
                )
                LOG.info("Delete Zombie Snapshot {} of Volume {} in Azure "
                         "...".format(i.snapshot, volume.name))

        LOG.debug("Calling Delete Volume '%s' in Azure ...", volume.name)
        self.storage.delete_blob(
            self.configuration.azure_storage_container_name,  blob_name)
        LOG.debug("Calling Delete Volume '%s' in Azure finish.", volume.name)

    def remove_export(self, context, volume):
        pass

    def ensure_export(self, context, volume):
        pass

    def create_export(self, context, volume, connector, vg=None):
        # nothing to do in azure.
        pass

    def initialize_connection(self, volume, connector):
        vhd_uri = self.storage.make_blob_url(
            self.configuration.azure_storage_container_name, volume.name)
        vhd_uri += VHD
        connection_info = {
            'driver_volume_type': 'vmdk',
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
        snapshot_blob = self.storage.snapshot_blob(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name'] + VHD
        )
        azure_snapshot_id = snapshot_blob.snapshot
        LOG.debug('Created Snapshot: {} in Azure.'.format(azure_snapshot_id))
        metadata = snapshot['metadata']
        metadata['azure_snapshot_id'] = azure_snapshot_id
        return dict(metadata=metadata)

    def delete_snapshot(self, snapshot):
        azure_snapshot_id = snapshot['metadata']['azure_snapshot_id']
        exists = self.storage.exists(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name'] + VHD,
            snapshot=azure_snapshot_id
        )
        if not exists:
            LOG.warn('Delete an Inexistent Snapshot: {} in Azure.'.
                     format(azure_snapshot_id))
            return

        self.storage.delete_blob(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name'] + VHD,
            snapshot=azure_snapshot_id
        )
        LOG.debug('Deleted Snapshot: {} in Azure.'.format(azure_snapshot_id))

    def create_volume_from_snapshot(self, volume, snapshot):
        blob_name = self._get_blob_name(volume)
        azure_snapshot_id = snapshot['metadata']['azure_snapshot_id']
        old_blob_uri = self.storage.make_blob_url(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name'] + VHD)
        snapshot_uri = old_blob_uri + '?snapshot=' + azure_snapshot_id
        exists = self.storage.exists(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name'] + VHD,
            snapshot=azure_snapshot_id
        )
        if not exists:
            LOG.warn('Copy an Inexistent Snapshot: {} in Azure.'.
                     format(azure_snapshot_id))
            raise exception.SnapshotNotFound(snapshot_id=snapshot['id'])
        self.storage.copy_blob(
            self.configuration.azure_storage_container_name,
            blob_name, snapshot_uri)

        def _wait_for_copy():
            """Called at an copy until finish."""
            copy = self.storage.get_blob_properties(
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
        LOG.debug('Create Volume from Snapshot: {} in '
                  'Azure.'.format(azure_snapshot_id))

    def create_cloned_volume(self, volume, src_vref):
        src_blob_name = src_vref['name'] + VHD
        exists = self.storage.exists(
            self.configuration.azure_storage_container_name, src_blob_name)
        if not exists:
            LOG.warn('Copy an Inexistent Volume: {} in Azure.'.
                     format(src_blob_name))
            raise exception.VolumeNotFound(volume_id=src_vref['id'])

        blob_name = self._get_blob_name(volume)
        src_blob_uri = self.storage.make_blob_url(
            self.configuration.azure_storage_container_name, src_blob_name)
        self.storage.copy_blob(
            self.configuration.azure_storage_container_name,
            blob_name, src_blob_uri)

        def _wait_for_copy():
            """Called at an copy until finish."""
            copy = self.storage.get_blob_properties(
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
        LOG.debug('Create Volume from Snapshot: {} in '
                  'Azure.'.format(blob_name))
