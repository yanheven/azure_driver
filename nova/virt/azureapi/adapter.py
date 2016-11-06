import sys

from oslo_log import log as logging
from oslo_utils import importutils
import six

import nova.conf
from nova.i18n import _, _LE, _LI
from nova import utils
from nova.virt import event as virtevent
from oslo_config import cfg
from azure.common.credentials import UserPassCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient

CONF = nova.conf.CONF
LOG = logging.getLogger(__name__)

compute_opts = [
    cfg.StrOpt('location',
               default='westus',
               help='Azure Datacenter Location'),
    cfg.StrOpt('resource_group',
               default='openstack_resource_group',
               help='Azure Resource Group Name'),
    cfg.StrOpt('storage_account',
               default='openstack_storage_account',
               help='Azure Storage Account Name, '
                    'should be unique in Azure'),
    cfg.StrOpt('subscription_id',
               help='Azure subscription ID'),
    cfg.StrOpt('username',
               help='Auzre username of subscription'),
    cfg.StrOpt('password',
               help='Auzre password of user of subscription'),
    cfg.StrOpt('vnet_name',
               help='Auzre Virtual Network Name'),
    cfg.StrOpt('vsubnet_id',
               help='Auzre Virtual Subnte ID'),
    cfg.StrOpt('password',
               help='Auzre password of user of subscription'),
]

CONF.register_opts(compute_opts, 'azure')
# CONF.import_opt('my_ip', 'nova.netconf')


class Azure(object):

    def __init__(self):

        credentials = UserPassCredentials(CONF.azure.username,
                                          CONF.azure.password)
        self.resource = ResourceManagementClient(credentials,
                                                 CONF.azure.subscription_id)
        self.compute = ComputeManagementClient(credentials,
                                               CONF.azure.subscription_id)
        self.storage = StorageManagementClient(credentials,
                                               CONF.azure.subscription_id)
        self.network = NetworkManagementClient(credentials,
                                               CONF.azure.subscription_id)
