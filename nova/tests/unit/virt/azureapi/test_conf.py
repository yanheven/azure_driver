from nova import test
from nova.virt.azureapi.conf import azureapi
from oslo_config import cfg

CONF = cfg.CONF


class AzureConfTestCase(test.NoDBTestCase):

    def test_register_opts(self):
        azureapi.register_opts(CONF)

    def test_list_opts(self):
        azureapi.list_opts()
