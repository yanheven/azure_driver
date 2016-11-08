from nova.i18n import _
from nova import exception


class ImageAzureMappingNotFound(exception.NotFound):
    msg_fmt = _("Image %(image_name)s could not be found in Azure Mapping.")


class FlavorAzureMappingNotFound(exception.NotFound):
    msg_fmt = _("Flavor %(flavor_name)s could not be found in Azure Mapping.")


class FlavorInvalid(exception.Invalid):
    msg_fmt = _("Flavor %(flavor_name)s are Invalid for Instance "
                "%(instance_uuid)s in Azure.")
