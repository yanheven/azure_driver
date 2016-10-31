Date:2016-10-31

####6 spawn
Azure api: Create or update a VM
TODO: 创建VM过程如下:
- flavor: 在openstack外创建azure有而原来openstack没有的flavor, 然后在配置文件里写入openstack flavor与azure的映射关系.azure的hardware profile的vm_size,比如"Standard_DS1".
- image: openstack原来的镜像,通过glance下载,转换格式到VHD,然后上传到azure blob存储里,把对应映射ID关系分别写到两边某个META或者备注处,方便反射查找.  
- boot from volume: 把相应的卷下载,上传到azure blob存储里,然后创建VM时直接指定这个VHD作为系统盘.
- key-name: 把相应的keypair的公钥传入到新创建VM.
- password: 支持创建时指定管理员密码, azure对应位置:os_profile'里面的'admin_password'.
- network: 在配置文件里配置好有几个网络,几个子网,创建VM时指定.这些信息只在azure处有,openstack处没有对应的,有个潜在的问题是GUI处显示VM信息时关于网络的超链接就有问题, azure对应位置'network_profile':'network_interfaces':'id'.


####7 list_instances
Azure api: List VMs in a resource group 和 List VMs in a subscription
TODO: 键值转换.

####8 get_info
Azure api: Get VM information
TODO: 键值转换.

####9 list_instance_uuids
Azure api: List VMs in a resource group 和 List VMs in a subscription
TODO: 对得到的VM 里面的ID进行映射.

####10 rebuild
Azure api: 不用实现,按接口未实现处理
TODO: 接口未实现,接口会自动销毁VM,然后以之前的配置新那一个VM.
