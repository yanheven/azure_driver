import mock
import unittest

from nova.virt.azureapi import adapter

USERNAME = 'AZUREUSER'
PASSWORD = 'PASSWORD'
SUBSCRIBE_ID = 'ID'
RG = 'RG'
SAC = 'SC'
KEY = 'KEY'


class FakeKey(object):
    class Value(object):
        value = KEY
    keys = [Value()]

class AzureTestCase(unittest.TestCase):

    @mock.patch('nova.virt.azureapi.adapter.UserPassCredentials')
    @mock.patch('nova.virt.azureapi.adapter.ResourceManagementClient')
    @mock.patch('nova.virt.azureapi.adapter.ComputeManagementClient')
    @mock.patch('nova.virt.azureapi.adapter.NetworkManagementClient')
    @mock.patch('nova.virt.azureapi.adapter.StorageManagementClient')
    @mock.patch('nova.virt.azureapi.adapter.CloudStorageAccount')
    # @mock.patch.object(adapter.StorageManagementClient,
    #                    'storage_accounts',
    #                    return_value=mock.MagicMock)
    # @mock.patch.object(adapter.CloudStorageAccount,
    #                    'create_page_blob_service')
    def test_init(self, cloudstorage, storage, netowrk, compute, resource,
                  credential):
        storage().storage_accounts.list_keys = mock.Mock(return_value=FakeKey)
        print storage.storage_accounts.list_keys()
        cloudstorage.create_page_blob_service = mock.Mock()

        azure = adapter.Azure(USERNAME, PASSWORD, SUBSCRIBE_ID, RG, SAC)

        credential.assert_called_once_with(USERNAME, PASSWORD)
        resource.assert_called_once_with(credential(), SUBSCRIBE_ID)
        compute.assert_called_once_with(credential(), SUBSCRIBE_ID)
        netowrk.assert_called_once_with(credential(), SUBSCRIBE_ID)
        storage.assert_called_with(credential(), SUBSCRIBE_ID)
        cloudstorage.assert_called_once_with(account_name=SAC, account_key=KEY)
        self.assertTrue(hasattr(azure, 'blob'))
        self.assertTrue(hasattr(azure, 'resource'))
        self.assertTrue(hasattr(azure, 'compute'))
        self.assertTrue(hasattr(azure, 'network'))
        self.assertTrue(hasattr(azure, 'storage'))


if __name__ == '__main__':
    unittest.main()