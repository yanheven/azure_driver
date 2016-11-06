
"""
Driver base-classes:

    (Beginning of) the contract that compute drivers must follow, and shared
    types that support that contract
"""

import sys
import uuid
import json

from oslo_log import log as logging
from oslo_utils import importutils
import six

import nova.conf
from nova.i18n import _, _LE, _LI
from nova import utils
from nova.virt import event as virtevent
from nova.virt import driver
from nova.virt.azureapi.adapter import Azure
from nova.virt.azureapi import constant
from nova.virt.azureapi import exception
from nova.compute import power_state
from nova.virt.hardware import InstanceInfo
from nova.compute import arch
from nova.compute import hv_type
from nova.compute import vm_mode

CONF = nova.conf.CONF
LOG = logging.getLogger(__name__)

LIMIT = {
    'vcpus': 100,
    'memory_mb': 88192,
    'local_gb': 500,
    'vcpus_used': 0,
    'memory_mb_used': 0,
    'local_gb_used': 0,
    'cpu_info': 'azure_basic',
    'numa_topology': None
}


class AzureDriver(driver.ComputeDriver):
    capabilities = {
        "has_imagecache": False,
        "supports_recreate": False,
        "supports_migrate_to_same_host": False,
        "supports_attach_interface": False,
        "supports_device_tagging": False,
    }

    def __init__(self, virtapi):
        super(AzureDriver, self).__init__(virtapi)
        self.azure = Azure()
        self.compute = self.azure.compute
        self.network = self.azure.network
        self.storage = self.azure.storage
        self.resource = self.azure.resource

    def _precreate_network(self):
        """Pre Create Network info in Azure.
        """
        # Creaet Network
        # Create Subnet
        net_info = self.network.virtual_networks.get(
            CONF.azure.resource_group,
            CONF.azure.vnet_name)
        LOG.debug('#####Get vnet info:{}'.format(net_info))
        if not net_info:
            async_vnet_creation = self.network.virtual_networks.create_or_update(
                CONF.azure.resource_group,
                CONF.azure.vnet_name,
                {
                    'location': CONF.azure.location,
                    'address_space': {
                        'address_prefixes': ['10.0.0.0/16']
                    }
                }
            )
            async_vnet_creation.wait()
            LOG.debug("Create Network")

        # Create Subnet
        subnet_info = self.network.subnets.get(
            CONF.azure.resource_group,
            CONF.azure.vnet_name,
            CONF.azure.vsubnet_name,)
        LOG.debug('#####Get subnet info:{}'.format(subnet_info))
        if not subnet_info:
            # subnet can't recreate, check existing before create.
            async_subnet_creation = self.network.subnets.create_or_update(
                CONF.azure.resource_group,
                CONF.azure.vnet_name,
                CONF.azure.vsubnet_name,
                {'address_prefix': '10.0.0.0/16'}
            )
            subnet_info = async_subnet_creation.result()
        CONF.set_override('vsubnet_id', subnet_info.id, 'azure')
        LOG.debug("Create/Update Subnet:{}".format(CONF.azure.vsubnet_id))

    def init_host(self, host):
        self.resource.providers.register('Microsoft.Network')
        LOG.debug("Register Microsoft.Network")
        self.resource.providers.register('Microsoft.Compute')
        LOG.debug("Register Microsoft.Compute")
        self.resource.providers.register('Microsoft.Storage')
        LOG.debug("Register Microsoft.Storage")

        self.resource.resource_groups.create_or_update(
            CONF.azure.resource_group, {'location': CONF.azure.location})
        LOG.debug("Create/Update Resource Group")
        storage_async_operation = self.storage.storage_accounts.create(
            CONF.azure.resource_group,
            CONF.azure.storage_account,
            {
                'sku': {'name': 'standard_lrs'},
                'kind': 'storage',
                'location': CONF.azure.location
            }
        )
        storage_async_operation.wait()
        LOG.debug("Create/Update Storage Account")

        self._precreate_network()
        LOG.debug("Create/Update Ntwork and Subnet, Done.")

    def get_available_nodes(self, refresh=False):
        return 'azure-{}'.format(CONF.azure.location)

    def list_instances(self):
        """Return the names of all the instances known to the virtualization
        layer, as a list.
        """
        instances = []
        pages = self.compute.virtual_machines.list(CONF.azure.resource_group)
        for i in pages:
            instances.append(i)
        return instances

    def list_instance_uuids(self):
        """Return the UUIDS of all the instances known to the virtualization
        layer, as a list. azure vm.name is vm.uuid in openstack.
        """
        uuids = []
        instances = self.list_instances()
        for i in instances:
            uuids.append(i.name)
        return uuids

    def get_info(self, instance):
        """Get the current status of an instance

        :param instance: nova.objects.instance.Instance object

        Returns a InstanceInfo object
        """
        instance_id = instance.uuid
        LOG.debug('Virtual Machine id is {}'.format(instance_id))

        vm = self.compute.virtual_machines.get(
            CONF.azure.resource_group, instance_id)
        LOG.debug('vm info is: {}'.format(vm))

        state = power_state.NOSTATE

        # TODO
        return InstanceInfo(
            state=state,
            max_mem_kb=2048,
            mem_kb=1024,
            num_cpu=2,
            cpu_time_ns=0,
            id=instance_id)

    def get_available_resource(self, nodename):
        """Retrieve resource information.

        This method is called when nova-compute launches, and
        as part of a periodic task that records the results in the DB.

        :param nodename: unused in this driver
        :returns: dictionary containing resource info
        "vcpus", "memory_mb", "local_gb", "cpu_info","vcpus_used",
        "memory_mb_used", "local_gb_used","numa_topology"
        """
        return {'vcpus': 10000,
                'memory_mb': 100000000,
                'local_gb': 100000000,
                'vcpus_used': 0,
                'memory_mb_used': 1000,
                'local_gb_used': 1000,
                'hypervisor_type': 'aws',
                'hypervisor_version': 5005000,
                'hypervisor_hostname': nodename,
                'cpu_info': '{"model": ["Intel(R) Xeon(R) CPU E5-2670 0 @ 2.60GHz"], \
                "topology": {"cores": 16, "threads": 32}}',
                'supported_instances':[(arch.I686, hv_type.HYPERV, vm_mode.HVM),
                    (arch.X86_64, hv_type.HYPERV, vm_mode.HVM)],
                'numa_topology': None
                }

    def _create_nic(self, instance_uuid):
        """Create a Network Interface for a VM.
        """
        async_nic_creation = self.network.network_interfaces.create_or_update(
            CONF.azure.resource_group,
            instance_uuid,
            {
                'location': CONF.azure.location,
                'ip_configurations': [{
                    'name': instance_uuid,
                    'subnet': {
                        'id': CONF.azure.vsubnet_id
                    }
                }]
            }
        )
        nic = async_nic_creation.result()
        LOG.debug("Create a Nic:{}".format(nic.id))
        return nic.id

    def _get_image_from_mapping(self, image_meta):
        image_name = image_meta.name
        image_ref = constant.IMAGE_MAPPING.get(image_name, None)
        if not image_ref:
            raise exception.ImageAzureMappingNotFound(image_name=image_name)
        LOG.debug("Get image mapping:{}".format(image_ref))
        return image_ref

    def _get_instance_size(self, instance):
        flavor = instance.get_flavor()
        flavor_name = flavor.get('name')
        vm_size = constant.FLAVOR_MAPPING.get(flavor_name, None)
        if not vm_size:
            raise exception.FlavorAzureMappingNotFound(flavor_name=flavor_name)
        LOG.debug("Get size mapping:{}".format(vm_size))
        return vm_size

    def _create_vm_parameters(self, instance_uuid, image_reference, vm_size,
                              nic_id, admin_password):
        """Create the VM parameters structure.
        """
        vm_parameters = {
            'location': CONF.azure.location,
            'os_profile': {
                'computer_name': instance_uuid,
                'admin_username': 'azureadmin',
                'admin_password': admin_password
            },
            'hardware_profile': {
                'vm_size': 'Standard_DS1'
            },
            'storage_profile': {
                'image_reference': image_reference,
                'os_disk': {
                    'name': instance_uuid,
                    'caching': 'None',
                    'create_option': 'fromImage',
                    'vhd': {
                        'uri': 'https://{}.blob.core.windows.net/vhds/{}.vhd'.format(
                            CONF.azure.storage_account, instance_uuid)
                    }
                },
            },
            'network_profile': {
                'network_interfaces': [{
                    'id': nic_id,
                }]
            },
        }
        LOG.debug("Create vm parameters:{}".format(vm_parameters))
        return vm_parameters

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None):
        instance_uuid = instance.uuid
        image_reference = self._get_image_from_mapping(image_meta) or None
        vm_size = self._get_instance_size(instance) or None
        nic_id = self._create_nic(instance_uuid)
        vm_parameters = self._create_vm_parameters(
            instance_uuid, image_reference, vm_size, nic_id, admin_password)

        async_vm_creation = self.compute.virtual_machines.create_or_update(
            CONF.azure.resource_group, instance_uuid, vm_parameters)

        LOG.debug("Calling Create Instance in Azure ...", instance=instance)

        async_vm_creation.wait()

        LOG.debug("Create Instance in Azure Called.", instance=instance)

        # def _wait_for_boot():
        #     """Called at an interval until the VM is running."""
        #     state = self.get_info(instance).state
        #
        #     if state == power_state.RUNNING:
        #         LOG.info(_LI("Instance spawned successfully."),
        #                  instance=instance)
        #         raise loopingcall.LoopingCallDone()
        #
        # timer = loopingcall.FixedIntervalLoopingCall(_wait_for_boot)
        # timer.start(interval=0.5).wait()

    def cleanup(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None, destroy_vifs=True):
        """Cleanup the instance resources .

        Instance should have been destroyed from the Hypervisor before calling
        this method.

        :param context: security context
        :param instance: Instance object as returned by DB layer.
        :param network_info: instance network information
        :param block_device_info: Information about block devices that should
                                  be detached from the instance.
        :param destroy_disks: Indicates if disks should be destroyed
        :param migrate_data: implementation specific params
        """
        # clean vhd
        # clean nic
        pass

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        """Destroy the specified instance from the Hypervisor.

        If the instance is not found (for example if networking failed), this
        function should still succeed.  It's probably a good idea to log a
        warning in that case.

        :param context: security context
        :param instance: Instance object as returned by DB layer.
        :param network_info: instance network information
        :param block_device_info: Information about block devices that should
                                  be detached from the instance.
        :param destroy_disks: Indicates if disks should be destroyed
        :param migrate_data: implementation specific params
        """
        LOG.debug("Calling Delete Instance in Azure ...", instance=instance)
        result = self.compute.virtual_machines.delete(
            CONF.azure.resource_group, instance.uuid)
        result.wait()
        LOG.debug("Delete Instance in Azure Called.", instance=instance)
        self.cleanup(context, instance, network_info, block_device_info,
                     destroy_disks, migrate_data)

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        """Reboot the specified instance.

        After this is called successfully, the instance's state
        goes back to power_state.RUNNING. The virtualization
        platform should ensure that the reboot action has completed
        successfully even in cases in which the underlying domain/vm
        is paused or halted/stopped.

        :param instance: nova.objects.instance.Instance
        :param network_info: instance network information
        :param reboot_type: Either a HARD or SOFT reboot
        :param block_device_info: Info pertaining to attached volumes
        :param bad_volumes_callback: Function to handle any bad volumes
            encountered
        """
        raise NotImplementedError()

    def attach_volume(self, context, connection_info, instance, mountpoint,
                      disk_bus=None, device_type=None, encryption=None):
        """Attach the disk to the instance at mountpoint using info."""
        raise NotImplementedError()

    def detach_volume(self, connection_info, instance, mountpoint,
                      encryption=None):
        """Detach the disk attached to the instance."""
        raise NotImplementedError()

    def attach_interface(self, instance, image_meta, vif):
        """Use hotplug to add a network interface to a running instance.

        The counter action to this is :func:`detach_interface`.

        :param nova.objects.instance.Instance instance:
            The instance which will get an additional network interface.
        :param nova.objects.ImageMeta image_meta:
            The metadata of the image of the instance.
        :param nova.network.model.NetworkInfo vif:
            The object which has the information about the interface to attach.

        :raise nova.exception.NovaException: If the attach fails.

        :return: None
        """
        raise NotImplementedError()

    def detach_interface(self, instance, vif):
        """Use hotunplug to remove a network interface from a running instance.

        The counter action to this is :func:`attach_interface`.

        :param nova.objects.instance.Instance instance:
            The instance which gets a network interface removed.
        :param nova.network.model.NetworkInfo vif:
            The object which has the information about the interface to detach.

        :raise nova.exception.NovaException: If the detach fails.

        :return: None
        """
        raise NotImplementedError()

    def snapshot(self, context, instance, image_id, update_task_state):
        """Snapshots the specified instance.

        :param context: security context
        :param instance: nova.objects.instance.Instance
        :param image_id: Reference to a pre-created image that will
                         hold the snapshot.
        :param update_task_state: Callback function to update the task_state
            on the instance while the snapshot operation progresses. The
            function takes a task_state argument and an optional
            expected_task_state kwarg which defaults to
            nova.compute.task_states.IMAGE_SNAPSHOT. See
            nova.objects.instance.Instance.save for expected_task_state usage.
        """
        raise NotImplementedError()

    def power_off(self, instance, timeout=0, retry_interval=0):
        """Power off the specified instance.

        :param instance: nova.objects.instance.Instance
        :param timeout: time to wait for GuestOS to shutdown
        :param retry_interval: How often to signal guest while
                               waiting for it to shutdown
        """
        raise NotImplementedError()

    def power_on(self, context, instance, network_info,
                 block_device_info=None):
        """Power on the specified instance.

        :param instance: nova.objects.instance.Instance
        """
        raise NotImplementedError()
