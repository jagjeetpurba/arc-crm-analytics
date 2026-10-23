from .. import config
from .base import ERPClient


def get_erp() -> ERPClient:
    if config.ERP_MODE == "airgen":
        from .airgen import AirgenERP
        return AirgenERP()
    from .local import LocalERP
    return LocalERP(config.LOCAL_DB)
