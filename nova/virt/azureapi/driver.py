import re

from oslo_log import log as logging
from oslo_service import loopingcall

import nova.conf
from nova.i18n import _, _LE, _LI
from nova.virt import driver
from nova.virt.azureapi.adapter import Azure
from nova.virt.azureapi import constant
from nova.virt.azureapi import exception
from nova.compute import power_state
from nova.virt.hardware import InstanceInfo
from nova.compute import arch
from nova.compute import hv_type
from nova.compute import vm_mode
from nova.compute import task_states
from nova.volume import cinder
from nova import image

CONF = nova.conf.CONF
LOG = logging.getLogger(__name__)
VOLUME_CONTAINER = 'volume'
VHDS_CONTAINER = 'vhds'
AZURE = 'azure'
USER_NAME = 'azureuser'
VHD_EXT = '.vhd'

# TODO need complete according to image mapping.
LINUX_OFFER = ['UbuntuServer', 'RedhatServer']
WINDOWS_OFFER = ['WindowsServerEssentials']


class AzureDriver(driver.ComputeDriver):
    capabilities = {
        "has_imagecache": False,
        "supports_recreate": True,
        "supports_migrate_to_same_host": True,
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
        self.blob = self.azure.blob

        self._volume_api = cinder.API()
        self._image_api = image.API()

    def _precreate_network(self):
        """Pre Create Network info in Azure.
        """
        # Creaet Network
        # Create Subnet
        net_info = self.network.virtual_networks.get(
            CONF.azure.resource_group,
            CONF.azure.vnet_name)
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

    def get_host_ip_addr(self):
        return CONF.my_ip

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
        state for azure:running, deallocating, deallocated,
        stopping , stopped
        """
        shutdown_staues = ['deallocating', 'deallocated',
                           'stopping', 'stopped']
        instance_id = instance.uuid
        vm = self.compute.virtual_machines.get(
            CONF.azure.resource_group, instance_id, expand='instanceView')
        LOG.debug('vm info is: {}'.format(vm))
        state = power_state.NOSTATE
        status = 'Unkown'
        if vm and vm.instance_view and vm.instance_view.statuses:
            for i in vm.instance_view.statuses:
                if 'PowerState' in i.code:
                    status = i.code.split('/')[1]
                    if 'running' == status:
                        state = power_state.RUNNING
                    elif status in shutdown_staues:
                        state = power_state.SHUTDOWN
                    break
        LOG.debug('vm: {} state is : {}'.format(instance_id, status))
        return InstanceInfo(state=state, id=instance_id)

    def get_available_resource(self, nodename):
        usage_family = 'basicAFamily'
        page = self.compute.usage.list(CONF.azure.location)
        usages = [i for i in page]
        cores = 0
        cores_by_family = 0
        cores_used = 0
        cores_used_by_family = 0
        for i in usages:
            if i.name and i.name.value:
                if 'cores' == i.name.value:
                    cores = i.limit if i.limit else 0
                    cores_used = i.current_value if i.current_value else 0
                    break
                if usage_family == i.name.value:
                    cores_by_family = i.limit
                    cores_used_by_family = i.current_value \
                        if i.current_value else 0
        cores = min(cores, cores_by_family)
        cores_used = min(cores_used, cores_by_family)
        return {'vcpus': cores,
                'memory_mb': 100000000,
                'local_gb': 100000000,
                'vcpus_used': cores_used,
                'memory_mb_used': 0,
                'local_gb_used': 0,
                'hypervisor_type': hv_type.HYPERV,
                'hypervisor_version': 0300,
                'hypervisor_hostname': nodename,
                'cpu_info': '{"model": ["Intel(R) Xeon(R) CPU E5-2670 0 @ '
                            '2.60GHz"], "topology": {"cores": 16, "threads": '
                            '32}}',
                'supported_instances': [(arch.I686, hv_type.HYPERV,
                                         vm_mode.HVM),
                    (arch.X86_64, hv_type.HYPERV, vm_mode.HVM)],
                'numa_topology': None
                }

    def _prepare_network_profile(self, instance_uuid):
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
        network_profile = {
                'network_interfaces': [{
                    'id': nic.id,
                }]
            }
        return network_profile

    def _get_image_from_mapping(self, image_meta):
        image_name = image_meta.name
        image_ref = constant.IMAGE_MAPPING.get(image_name, None)
        if not image_ref:
            raise exception.ImageAzureMappingNotFound(image_name=image_name)
        LOG.debug("Get image mapping:{}".format(image_ref))
        return image_ref

    def _get_size_from_flavor(self, flavor):
        flavor_name = flavor.get('name')
        vm_size = constant.FLAVOR_MAPPING.get(flavor_name, None)
        if not vm_size:
            raise exception.FlavorAzureMappingNotFound(flavor_name=flavor_name)
        LOG.debug("Get size mapping:{}".format(vm_size))
        return vm_size

    def _prepare_os_profile(self, instance, storage_profile, admin_password):
        image_offer = storage_profile['image_reference']['offer']
        os_profile = dict(computer_name=instance.hostname,
                          admin_username=USER_NAME)
        if image_offer in LINUX_OFFER:
            instance.os_type = 'linux'
            if CONF.libvirt.inject_key and instance.get('key_data'):
                key_data = str(instance.key_data)
                os_profile['linuxConfiguration'] = {
                    'ssh': {
                        'publicKeys': {
                            'path': '/home/' + USER_NAME +
                                    '/.ssh/authorized_keys',
                            'keyData': key_data
                        }
                    }

                }
            else:
                os_profile['admin_password'] = admin_password
        elif image_offer in WINDOWS_OFFER:
            instance.os_type = 'windows'
            os_profile['admin_password'] = admin_password
        return os_profile


    def _create_vm_parameters(self, instance, storage_profile, vm_size,
                              network_profile, os_profile):
        """Create the VM parameters structure.
        """
        vm_parameters = {
            'location': CONF.azure.location,
            'os_profile': os_profile,
            'hardware_profile': {
                'vm_size': vm_size
            },
            'storage_profile': storage_profile,
            'network_profile': network_profile,
        }
        LOG.debug("Create vm parameters:{}".format(vm_parameters))
        return vm_parameters

    def _prepare_storage_profile(self, image_meta, instance):
        if 'location' in image_meta and 'type' in image_meta.location:
            if image_meta.location['type'] == AZURE:
                disk_name = instance.uuid + VHD_EXT
                uri = image_meta.location['url']

                # copy image diskt to new disk for instance.
                self.blob.copy_blob(VHDS_CONTAINER, disk_name, uri)

                def _wait_for_copy():
                    """Called at an copy until finish."""
                    copy = self.blob.get_blob_properties(
                        VHDS_CONTAINER, disk_name)
                    state = copy.properties.copy.status
                    if state == 'success':
                        LOG.info(_LI("Copied image disk to new blob:{} in"
                                     " Azure.".format(disk_name)))
                        raise loopingcall.LoopingCallDone()
                    else:
                        LOG.debug(
                            'copy os disk: {} in Azure Progress '
                            '{}'.format(disk_name,
                                        copy.properties.copy.progress))

                timer = loopingcall.FixedIntervalLoopingCall(_wait_for_copy)
                timer.start(interval=0.5).wait()

                disk_uri = self.blob.make_blob_url(VHDS_CONTAINER, disk_name)
                storage_profile = {
                    'os_disk': {
                        'name': instance.uuid,
                        'caching': 'None',
                        'create_option': 'attach',
                        'vhd': {'uri': disk_uri}
                    }
                }
            else:
                raise Exception('Unknown type of location of image!')
        else:
            image_reference = self._get_image_from_mapping(image_meta) or None
            uri = self.blob.make_blob_url(
                VHDS_CONTAINER, instance.uuid+VHD_EXT)
            storage_profile = {
                'image_reference': image_reference,
                'os_disk': {
                    'name': instance.uuid,
                    'caching': 'None',
                    'create_option': 'fromImage',
                    'vhd': {'uri': uri}
                }
            }

        return storage_profile

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None):
        instance_uuid = instance.uuid
        storage_profile = self._prepare_storage_profile(image_meta, instance)
        vm_size = self._get_size_from_flavor(instance.get_flavor()) or None
        network_profile = self._prepare_network_profile(instance_uuid)
        os_profile = self._prepare_os_profile(
            instance, storage_profile, admin_password)
        vm_parameters = self._create_vm_parameters(
            instance, storage_profile, vm_size, network_profile, os_profile)

        async_vm_action = self.compute.virtual_machines.create_or_update(
            CONF.azure.resource_group, instance_uuid, vm_parameters)
        LOG.debug("Calling Create Instance in Azure ...", instance=instance)
        async_vm_action.wait()
        LOG.debug("Create Instance in Azure Finish.", instance=instance)
        # TODO DELETE NIC if create vm failed.

    def _cleanup_instance(self, instance):
        # 1 clean vhd
        os_container_name = 'vhds'
        os_blob_name = instance.uuid + '.vhd'
        self.blob.delete_blob(os_container_name, os_blob_name)
        LOG.debug("Delete instance's Volume", instance=instance)
        async_vm_action = self.network.network_interfaces.delete(
            CONF.azure.resource_group, instance.uuid
        )
        async_vm_action.wait()
        LOG.debug("Delete instance's Interface", instance=instance)
        return True

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        LOG.debug("Calling Delete Instance in Azure ...", instance=instance)
        async_vm_action = self.compute.virtual_machines.delete(
            CONF.azure.resource_group, instance.uuid)
        async_vm_action.wait()
        LOG.debug("Delete Instance in Azure Finish.", instance=instance)
        self._cleanup_instance(context, instance, network_info, block_device_info,
                     destroy_disks, migrate_data)
        LOG.info("Delete and Clean Up Instance in Azure Finish.",
                 instance=instance)

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        async_vm_action = self.compute.virtual_machines.restart(
            CONF.azure.resource_group, instance.uuid)
        async_vm_action.wait()
        LOG.debug("Restart Instance in Azure Finish.", instance=instance)

    def power_off(self, instance, timeout=0, retry_interval=0):
        async_vm_action = self.compute.virtual_machines.power_off(
            CONF.azure.resource_group, instance.uuid)
        async_vm_action.wait()
        LOG.debug("Power off Instance in Azure Finish.", instance=instance)

    def power_on(self, context, instance, network_info,
                 block_device_info=None):
        async_vm_action = self.compute.virtual_machines.start(
            CONF.azure.resource_group, instance.uuid)
        async_vm_action.wait()
        LOG.debug("Power On Instance in Azure Finish.", instance=instance)

    def rebuild(self, context, instance, image_meta, injected_files,
                admin_password, bdms, detach_block_devices,
                attach_block_devices, network_info=None,
                recreate=False, block_device_info=None,
                preserve_ephemeral=False):
        async_vm_action = self.compute.virtual_machines.redeploy(
            CONF.azure.resource_group, instance.uuid)
        LOG.debug("Calling Rebuild Instance in Azure ...", instance=instance)
        async_vm_action.wait()
        LOG.debug("Rebuild Instance in Azure Finish.", instance=instance)
        instance.task_state = task_states.REBUILD_SPAWNING
        instance.save()

    def finish_migration(self, context, migration, instance, disk_info,
                         network_info, image_meta, resize_instance,
                         block_device_info=None, power_on=True):
        # nothing need to do.
        pass

    def _get_new_size(self, instance, flavor):
        sizes = self.compute.virtual_machines.list_available_sizes(
            CONF.azure.resource_group, instance.uuid)
        vm_size = self._get_size_from_flavor(flavor) or None
        for i in sizes:
            if vm_size == i.name:
                LOG.debug('Resize Instance, get new size', instance=instance)
                return i.name
        LOG.debug('Resize Instance, size invalid in Azure', instance=instance)
        raise exception.FlavorInvalid(
            flavor_name=instance.get_flavor(),
            instance_uuid = instance.uuid)

    def migrate_disk_and_power_off(self, context, instance, dest,
                                   flavor, network_info,
                                   block_device_info=None,
                                   timeout=0, retry_interval=0):
        size_obj = self._get_new_size(instance, flavor)
        vm = self.compute.virtual_machines.get(
            CONF.azure.resource_group, instance.uuid)
        vm.hardware_profile.vm_size = size_obj
        async_vm_action = self.compute.virtual_machines.create_or_update(
            CONF.azure.resource_group, instance.uuid, vm)
        LOG.debug("Calling Resize Instance in Azure ...", instance=instance)
        async_vm_action.wait()
        LOG.debug("Resize Instance in Azure finish", instance=instance)
        return True

    def get_volume_connector(self, instance):
        # nothing need to do with volume
        props = {}
        props['platform'] = 'azure'
        props['os_type'] = 'azure'
        props['ip'] = CONF.my_ip
        props['host'] = CONF.host
        return props

    def confirm_migration(self, migration, instance, network_info):
        # nothing need to do with volume
        pass

    def set_admin_password(self, instance, new_pass):
        # extension = self.compute.virtual_machine_extensions.get(
        #     CONF.azure.resource_group, instance.uuid, 'enablevmaccess')

        if not self._check_password(new_pass):
            LOG.exception(_LE('set_admin_password failed: password does not'
                              ' meet reqirements.'),
                          instance=instance)
            raise Exception
        vm = self.compute.virtual_machines.get(
            CONF.azure.resource_group, instance.uuid)
        vm.os_profile.admin_password = new_pass
        LOG.debug(vm, instance=instance)
        async_vm_action = self.compute.virtual_machines.create_or_update(
            CONF.azure.resource_group, instance.uuid, vm)
        LOG.debug("Calling Reset Password of Instance in Azure ...",
                  instance=instance)
        async_vm_action.wait()
        LOG.debug("Reset Password of Instance in Azure finish",
                  instance=instance)

    def _check_password(self, password):
        """Check password according to azure's specification.

        :param password: password to set for a instance.
        :return: True or False, True for passed, False for failed.
        """
        rule = re.compile("(?=^.{8,72}$)((?=.*\d)(?=.*[A-Z])(?=.*[a-z])|"
                          "(?=.*\d)(?=.*[^A-Za-z0-9])(?=.*[a-z])|(?=.*[^A"
                          "-Za-z0-9])(?=.*[A-Z])(?=.*[a-z])|(?=.*\d)(?=.*"
                          "[A-Z])(?=.*[^A-Za-z0-9]))^.*")
        if not rule.match(password):
            return False

        disallow = ["abc@123", "P@$$w0rd", "P@ssw0rd", "P@ssword123",
                    "Pa$$word", "pass@word1", "Password!", "Password1",
                    "Password22", "iloveyou!"]
        return not password in disallow

    def attach_volume(self, context, connection_info, instance, mountpoint,
                      disk_bus=None, device_type=None, encryption=None):
        data = connection_info['data']
        vm = self.compute.virtual_machines.get(
            CONF.azure.resource_group, instance.uuid)
        data_disks = vm.storage_profile.data_disks
        luns = [i.lun for i in data_disks]
        new_lun = 0
        for i in range(100):
            if i not in luns:
                new_lun = i
                break
        data_disk = dict(lun=new_lun,
                         name=data['vhd_name'],
                         vhd=dict(uri=data['vhd_uri']),
                         create_option='attach',
                         disk_size_gb = data['vhd_size_gb'])
        data_disks.append(data_disk)
        async_vm_action = self.compute.virtual_machines.create_or_update(
            CONF.azure.resource_group, instance.uuid, vm)
        LOG.debug("Calling Attach Volume to  Instance in Azure ...",
                  instance=instance)
        async_vm_action.wait()
        LOG.debug("Attach Volume to Instance in Azure finish",
                  instance=instance)

    def detach_volume(self, connection_info, instance, mountpoint,
                      encryption=None):
        vhd_name = connection_info['data']['vhd_name']
        vm = self.compute.virtual_machines.get(
            CONF.azure.resource_group, instance.uuid)
        data_disks = vm.storage_profile.data_disks
        not_found = True
        for i in range(len(data_disks)):
            if vhd_name == data_disks[i].name:
                del data_disks[i]
                not_found = False
                break
        if not_found:
            LOG.warn('Volume: %s was not attached to Instance!' % vhd_name,
                     instance=instance)
            return
        async_vm_action = self.compute.virtual_machines.create_or_update(
            CONF.azure.resource_group, instance.uuid, vm)
        LOG.debug("Calling Detach Volume to  Instance in Azure ...",
                  instance=instance)
        async_vm_action.wait()
        LOG.debug("Detach Volume to Instance in Azure finish",
                  instance=instance)

    def snapshot(self, context, instance, image_id, update_task_state):
        snapshot = self._image_api.get(context, image_id)
        snapshot_name = 'snapshot-' + snapshot.id + VHD_EXT
        snapshot_url = self.blob.make_blob_url(VOLUME_CONTAINER, snapshot_name)
        vm_osdisk_url = self.blob.make_blob_url(VHDS_CONTAINER,
                                                instance.uuid+VHD_EXT)
        metadata = {'is_public': False,
                    'status': 'active',
                    'name': snapshot_name,
                    'location': {'url': snapshot_url,
                                 'type': AZURE},
                    'properties': {
                                   'kernel_id': instance.kernel_id,
                                   'image_location': 'snapshot',
                                   'image_state': 'available',
                                   'owner_id': instance.project_id,
                                   'ramdisk_id': instance.ramdisk_id,
                                   }
                    }
        self._image_api.update(context, image_id, metadata,
                               purge_props=False)
        LOG.debug("Update image for snapshot image.", instance=instance)

        self.blob.copy_blob(VOLUME_CONTAINER, snapshot_name, vm_osdisk_url)
        LOG.debug("Calling copy os disk in Azure...", insget_available_nodestance=instance)

        def _wait_for_copy():
            """Called at an copy until finish."""
            copy = self.blob.get_blob_properties(VOLUME_CONTAINER,
                                                 snapshot_name)
            state = copy.properties.copy.status

            if state == 'success':
                LOG.info(_LI("Copied osdisk to new blob:{} for instance:{} in"
                             " Azure.".format(snapshot_name, instance.uuid)))
                raise loopingcall.LoopingCallDone()
            else:
                LOG.debug(
                    'copy os disk: {} in Azure Progress '
                    '{}'.format(snapshot_name, copy.properties.copy.progress))

        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_copy)
        timer.start(interval=0.5).wait()

        LOG.debug('Created Image from Instance: {} in Azure'
                  '.'.format(instance.uuid))

    def resume_state_on_host_boot(self, context, instance, network_info,
                                  block_device_info=None):
        pass

    def delete_instance_files(self, instance):
        return self._cleanup_instance(instance)
