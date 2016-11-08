### Jacket Nova API

|Category|API|Azure
|:--|:--|:--
|API versions|List API versions|compute driver管理不了,发行软件时指定
|Limits|List limits|compute driver管理不了,查询DB
|Extensions|List extensions|compute driver管理不了,查询DB."Extensions are a deprecated concept in Nova."
||Get extension|compute driver管理不了,查询DB
|Servers|List servers|compute driver管理不了,查询DB
||Create server|Azure api: Create or update a VM  实现细节: 创建VM过程如下:  1 flavor: 在openstack外创建azure有而原来openstack没有的flavor, 然后在配置文件里写入openstack flavor与azure的映射关系.azure的hardware profile的vm_size,比如"Standard_DS1".  2 image: 镜像两边分别有各自的,然后在配置文件里配置对应关系,创建时用户选用openstack这边的image id,实际创建时通过映射关系找到azure上对应的ID.   3 boot from volume: 只能使用azure上有的volume,然后创建VM时直接指定这个VHD作为系统盘.  4 keypair: 把相应的keypair的公钥传入到新创建VM.  5 password: 支持创建时指定管理员密码, azure对应位置:os_profile'里面的'admin_password'.  6 network: 在配置文件里配置好有几个网络,几个子网,创建VM时指定, azure对应位置'network_profile':'network_interfaces':'id'.  7 security group: 创建VM的网卡时,指定哪个网络安全组(Network Security Group (NSG))作用在VM的网卡上,需要提前在azure上创建与openstack安全组对应的NSG.  8 映射ID:azure支持tags,可以在调用azure接口创建VM时把openstack这边的VM ID写入到azure那边的tags里面.
||List details for servers|compute driver管理不了,查询DB
||Get server details|compute driver管理不了,查询DB
||Update server|compute driver管理不了,更新DB记录
||Delete server|Azure api: Delete a VM  实现细节: azure接口文档没说明删除VM后,跟VM相关的资源是否删除,如果没删除,那按照openstack的做法,对网络接口,系统磁盘进行删除操作.
|Server metadata|Show server metadata|compute driver管理不了,查询DB
||Create or replace server metadata items|compute driver管理不了,查询DB
||Update server metadata items|azure更新VM只有Create or update a VM这个接口,没看到可以更新metadata
||Show server metadata item details|compute driver管理不了,查询DB
||Create or update server metadata item|azure更新VM只有Create or update a VM这个接口,没看到可以更新metadata
||Delete server metadata item|azure更新VM只有Create or update a VM这个接口,没看到可以更新metadata
|Server addresses|List addresses|compute driver管理不了,查询DB
||List addresses by network|compute driver管理不了,查询DB
|Server actions|Change password|Azure api: Create or update a VM  实现细节: 有密码复杂度要求,实现时查看azure文档做检查,复杂度不通过返回错误提示.
||Reboot server|Azure api: Restart a VM  实现细节: 无
||Rebuild server|不支持
||Resize server|Azure api: Create or update a VM  实现细节: 选择新的flaovor后,通过这个接口对VM配置进行更新,azure的更新VM接口会要求重启VM.
||Confirm resized server|不支持
||Revert resized server|不支持
||Create image|Azure api: Copy Blob  实现细节: 本身azure里面的blog 就跟image存储性质一样,是page blob,所以无须作另外工作,参考clone volume.
|Flavors|List flavors|compute driver管理不了,查询DB
||List details for flavors|compute driver管理不了,查询DB
||Get flavor details|compute driver管理不了,查询DB
|Images|List images|compute driver管理不了,调用glance接口
||List images details|compute driver管理不了,调用glance接口
||Get image details|compute driver管理不了,调用glance接口
||Delete image|compute driver管理不了,调用glance接口
|Image metadata|Show image metadata|compute driver管理不了,调用glance接口
||Create or replace image metadata|compute driver管理不了,调用glance接口
||Update image metadata items|compute driver管理不了,调用glance接口
||Show image metadata item details|compute driver管理不了,调用glance接口
||Create or update image metadata item|compute driver管理不了,调用glance接口
||Delete image metadata item|compute driver管理不了,调用glance接口
|Servers with block device mapping format (servers)|List servers|不明白对应哪个NOVA API接口
||Create server|不明白对应哪个NOVA API接口
|Servers with configuration drive (servers)|Create server with configuration drive|不明白对应哪个NOVA API接口
||Get server information with configuration drive|不明白对应哪个NOVA API接口
||Get server details with configuration drive|不明白对应哪个NOVA API接口
|Servers console (servers)|Get console|azure API不支持
|Servers console output (servers)|Get console output for an instance|azure支持创建VM时,指定storage account的uri,会把启动时的console输出/屏幕截图存储.
|Servers extended attributes (servers)|List servers with extended server attributes|compute driver管理不了,查询DB
||Show extended server attributes|compute driver管理不了,查询DB
|Servers with extended availability zones (servers)|Show server|compute driver管理不了,查询DB
||List details for servers|compute driver管理不了,查询DB
|Servers extended status (servers)|Show server extended status|compute driver管理不了,查询DB
||List extended status for servers|compute driver管理不了,查询DB
|Servers with IP type (servers)|Show IP type|不明白对应哪个NOVA API接口
||List servers with IP type|不明白对应哪个NOVA API接口
|Servers multiple create (servers)|Create multiple servers|Azure api: Create or update a VM  实现细节: 多次创建VM,检查要创建VM的指定资源是否是唯一的,比如指定某个IP,某个磁盘等,是不允许的.
|Servers deferred delete (servers, action)|Force delete server|Azure api: Delete a VM  实现细节: azure的删除本身就是强制的.
||Restore server|Azure api: DStop and deallocate a virtual machine和Start a VM  实现细节: azure支持不占用计算资源的关机,不收费,需要时可以恢复使用.但这些资源要有机制进行定期回收,不然会变成垃圾资源.
|Servers rescue and unrescue (servers, action)|Rescue server|不支持
||Unrescue server|不支持
|Servers shelve (servers, action)|Shelve server|不支持
||Remove a shelved instance|不支持
||Restore shelved server|不支持
|Servers start and stop (servers, action)|Start server|Azure api: Start a VM  实现细节: 通过映射关系,找到azure上的VM,执行开机操作.
||Stop server|Azure api: Stop a VM  实现细节: 通过映射关系,找到azure上的VM,执行关闭操作.
|Servers diagnostics (servers, diagnostics)|Get server diagnostics|azure支持创建VM时,指定storage account的uri,会把启动时的console输出/屏幕截图存储,把这个uri存储在VM属性里面.
|Servers and images with disk config (servers, images)|Create server|不明白对应哪个NOVA API接口
||Show server information|不明白对应哪个NOVA API接口
||Update server|不明白对应哪个NOVA API接口
||Resize server|不明白对应哪个NOVA API接口
||Rebuild server|不明白对应哪个NOVA API接口
||List servers|不明白对应哪个NOVA API接口
||Get image information|不明白对应哪个NOVA API接口
||List images|不明白对应哪个NOVA API接口
|Servers availability zones (servers, os-availability-zone)|Create server with availability zone|不支持
||List availability zones|不支持
||List availability zones with details|不支持
||Show availability zone information|不支持
|Servers password (servers, os-server-password)|Get server password|compute driver管理不了,查询DB
||Clear server password|Azure api: Create or update a VM  实现细节: 更新VM信息时,"osProfile"里有"adminPassword"留空.
|Servers virtual interfaces (servers, os-virtual-interfaces)|List virtual interfaces|compute driver管理不了,查询DB
||Show virtual interface and attached network|不明白对应哪个NOVA API接口
|Servers with volume attachments (servers, os-volume_attachments)|Attach volume|Azure api: Create or update a VM  实现细节: 更新VM信息时带上要挂载的volume的blob uri.'data_disk'.需要提前创建好.
||List volume attachments|compute driver管理不了,查询DB
||Show volume attachment details|compute driver管理不了,查询DB
||Detach volume|Azure api:  Create or update a VM  实现细节: 更新VM信息时减少要卸载的volume的blob uri.'data_disk'.
|Server boot from volume (os-volumes_boot)|Create server|Azure api: Create or update a VM  实现细节: 与普通创建VM基本相同,除了下面这点  - boot from volume: 只能使用azure上有的volume,然后创建VM时直接指定这个VHD作为系统盘.  |Flavors create and delete (flavors)|Create flavor|compute driver管理不了
||Delete flavor|compute driver管理不了
|Flavors with disabled attribute (flavors)|Get flavor disabled status details|compute driver管理不了
||List flavors with flavor disabled status|compute driver管理不了
|Flavors with extended attributes (flavors)|Create flavor with extra data|compute driver管理不了
||Get flavor extra data details|compute driver管理不了
||List flavors with extra data|compute driver管理不了
|Flavors with rxtx_factor extended attribute (flavors)|Create flavor with rxtx_factor|compute driver管理不了
||Get flavor with rxtx_factor|compute driver管理不了
||Get flavor Details with rxtx_factor|compute driver管理不了
|Flavors with extra-specs (flavors, os-extra-specs)|List flavor extra specs|compute driver管理不了
||Create flavor extra specs|compute driver管理不了
||Get flavor extra spec details|compute driver管理不了
||Update flavor extra specs|compute driver管理不了
||Delete flavor extra specs|compute driver管理不了
|Flavors access (flavors, os-flavor-access)|List flavors with access type|compute driver管理不了
||Create private flavor|compute driver管理不了
||Show flavor access type|compute driver管理不了
||List tenants with access to private flavor|compute driver管理不了
||Add access to private flavor|compute driver管理不了
||Delete access from private flavor|compute driver管理不了
|Flavors swap (flavors, os-flavor-swap)|List flavor extra specs|compute driver管理不了
||Create flavor extra specs|compute driver管理不了
|Limits with project usage (limits)|Get limits|compute driver管理不了,但可以查看azure里面的limit,进行配置.
|Limits with project usage for administrators (limits)|Get customer limits|compute driver管理不了,但可以查看azure里面的limit,进行配置.
|Attach interfaces (os-interface)|Create interface|实现不了,因为这个过程会调用网络APIself.network_api.deallocate_port_for_instance,如果网络没对接azure,实现不了.  Azure api: Create or update a VM  实现细节: 更新VM信息时增加某个网络接口的信息.'network_profile':'network_interfaces':'id',需要提前创建好.
||List interfaces|实现不了,因为这个过程会调用网络API,如果网络没对接azure,实现不了.
||Show attached interface information|实现不了,因为这个过程会调用网络APIself.network_api.deallocate_port_for_instance,如果网络没对接azure,实现不了.
||Detach interface|实现不了,因为这个过程会调用网络APIself.network_api.deallocate_port_for_instance,如果网络没对接azure,实现不了.
|Keypairs (os-keypairs)|List keypairs|compute driver管理不了,查询DB
||Create or import keypair|compute driver管理不了,更新DB操作
||Delete keypair||compute driver管理不了,更新DB操作
||Show keypair information|compute driver管理不了,查询DB
|Quota class (os-quota-class-sets)|Show quota|compute driver管理不了,查询DB,但可以查看azure里面的limit,进行配置,以下几条相同.
||Update quota|compute driver管理不了,更新DB操作
|Quota sets (os-quota-sets)|Show quotas|compute driver管理不了,查询DB
||Update quotas|compute driver管理不了,更新DB操作
||Delete quotas|compute driver管理不了,更新DB操作
||Get default quotas|compute driver管理不了,查询DB
||Show quotas for user|compute driver管理不了,查询DB
||Update quotas for user|compute driver管理不了,更新DB操作
||Delete quotas for user|compute driver管理不了,更新DB操作
||Show quota details for user|compute driver管理不了,更新DB操作
|Usage reports (os-simple-tenant-usage)|List usage information for all tenants|compute driver管理不了,查询DB
||Get tenant usage information|同上
|Servers administrative actions (servers, action)|Pause server|azure不支持
||Unpause server|azure不支持
||Suspend server|azure不支持
||Resume server|azure不支持
||Inject network information|实现不了,因为这个过程会调用网络API:self.network_api.get_instance_nw_info ,如果网络没对接azure,实现不了.
||Lock server|azure不支持
||Unlock server|azure不支持
||Create server backup|Azure api: Snapshot Blob  实现细节: 要把azure blob信息添加到volume,放到provider_id.
||Reset server state|compute driver管理不了更新DB操作
||Add floating IP address|实现不了,因为这个过程会调用网络API:self.network_api.allocate_floating_ip和self.network_api.get_floating_ip_by_address,如果网络没对接azure,实现不了.


### Jacket Cinder API
####说明
OpenStack里面的volume对应azure里面是Storage里面的Page Blog,包括创建VM时指定的操作系统盘,额外挂载的数据盘,存储镜像,从VM导出的镜像,快照都是它.

- 容量是512B倍数.但由于VM最小接受磁盘容量是1GB,所以这里也建议最小可创建容量为1GB.
- VM挂载磁盘必须是以vhd结尾的page blob.
- create vhd footer with size and upload to azure.

|Category|API|Azure
|:--|:--|:--
|API versions|List API versions|volume driver管理不了,发行软件时指定
||Show API version details|volume driver管理不了,发行软件时指定
|API extensions (extensions)|List API extensions|volume driver管理不了,查询DB
|Limits (limits)|Show absolute limits|volume driver管理不了,查询DB,但可以查看azure里面的limit,进行配置.
|Volumes (volumes)|Create volume|Azure api: Copy Blob & Put Page  实现细节: copy new .vhd page blob from base .vhd, then resize it,只能通过container_name和blob_name来对卷进行定位.
||List volumes||volume driver管理不了,查询DB
||List volumes (detailed)|volume driver管理不了,查询DB
||Show volume information|volume driver管理不了,查询DB
||Update volume|volume driver管理不了,更新DB操作
||Delete volume|Azure api: Put Page  实现细节: 通过映射关系,找到azure上某个快照的blob,执行删除操作.
|Volume actions (volumes, action)|Reset volume statuses|volume driver管理不了,更新DB操作
||Set image metadata for volume|volume driver管理不了,更新DB操作:self.db.volume_metadata_update
||Remove image metadata from volume|volume driver管理不了,更新DB操作:self.db.volume_metadata_delete
||Attach volume|Azure api: Create or update a VM  实现细节: 更新VM信息时带上要挂载的volume的blob uri.'data_disk'.需要提前创建好.
|Backups (backups)|Create backup|Azure api: Copy Blob  实现细节: 要把azure blob信息添加到volume,放到provider_id.
||List backups|volume driver管理不了,查询DB
||List backups (detailed)|volume driver管理不了,查询DB
||Show backup details|volume driver管理不了,查询DB
||Delete backup|Azure api: Put Page  实现细节: 通过映射关系,找到azure上的blob,执行删除操作.
||Restore backup|azure原生不支持,但可以通过更新在openstack处的要恢复的卷所映射的azure的uri为备份的uri,达到恢复备份的目的.
|Backup actions (backups, action)|Force-delete backup|跟删除volume一样处理.
|Quota sets extension (os-quota-sets)|Show quotas|volume driver管理不了,查询DB
||Update quotas|volume driver管理不了,更新DB
||Delete quotas|volume driver管理不了,更新DB
||Get default quotas|volume driver管理不了,查询DB
||Show quotas for user|volume driver管理不了,查询DB
||Update quotas for user|volume driver管理不了,更新DB
||Delete quotas for user|volume driver管理不了,更新DB
||Show quota details for user|volume driver管理不了,查询DB
|Volume types (types)|List volume types|volume driver管理不了,查询DB
||Create volume type|volume driver管理不了,更新DB
||Update volume type|volume driver管理不了,更新DB
||Update extra specs for a volume type|volume driver管理不了,更新DB
||Show volume type information|volume driver管理不了,查询DB
||Delete volume type|volume driver管理不了,更新DB
|Volume snapshots (snapshots)|Create snapshot|Azure api: Snapshot Blob  实现细节: 在azure上创建快照.要把azure blob信息添加到volume,放到provider_id.
||List snapshots|volume driver管理不了,查询DB
||List snapshots (detailed)|volume driver管理不了,查询DB
||Show snapshot information|volume driver管理不了,查询DB
||Update snapshot|volume driver管理不了,更新DB
||Delete snapshot|Azure api: Put Page  实现细节: 跟删除卷一样处理.通过映射关系,找到azure上某个快照的blob,执行删除操作.
||Show snapshot metadata|volume driver管理不了,查询DB
||Update snapshot metadata|volume driver管理不了,更新DB
|Volume image metadata extension (os-vol-image-meta)|Show image metadata for volume|volume driver管理不了,查询DB