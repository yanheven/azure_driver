import math
import os
import socket

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import importutils
from oslo_utils import units
import six

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
        return volume.name + '.vhd'

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
        vhd_uri += '.vhd'
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
        azure_snapshot_id = self.storage.snapshot_blob(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name']
        )
        LOG.debug('Created Snapshot: {} in Azure.'.format(azure_snapshot_id))
        metadata = snapshot['meta']
        metadata['azure_snapshot_id'] = azure_snapshot_id
        return dict(metadata=metadata)

    def delete_snapshot(self, snapshot):
        azure_snapshot_id = snapshot['metadata']['azure_snapshot_id']
        self.storage.delete_blob(
            self.configuration.azure_storage_container_name,
            snapshot['volume_name'],
            snapshot=azure_snapshot_id
        )
        LOG.debug('Deleted Snapshot: {} in Azure.'.format(azure_snapshot_id))

    def create_volume_from_snapshot(self, volume, snapshot):
        blob_name = self._get_blob_name(volume)
        azure_snapshot_id = snapshot['metadata']['azure_snapshot_id']
        old_blob_uri = self.storage.make_blob_url(
            self.configuration.azure_storage_container_name, blob_name)
        snapshot_uri = old_blob_uri + '?snapshot=' + azure_snapshot_id
        self.storage.copy_blob(
            self.configuration.azure_storage_container_name,
            blob_name, snapshot_uri)
        LOG.debug('Create Volume from Snapshot: {} in '
                  'Azure.'.format(azure_snapshot_id))
