from application.utils.external_project_parsers.parsers.capec_parser import Capec
from application.utils.external_project_parsers.parsers.ccmv4 import CloudControlsMatrix
from application.utils.external_project_parsers.parsers.cheatsheets_parser import (
    Cheatsheets,
)
from application.utils.external_project_parsers.parsers.cloud_native_security_controls import (
    CloudNativeSecurityControls,
)
from application.utils.external_project_parsers.parsers.cwe import CWE
from application.utils.external_project_parsers.parsers.dsomm import DSOMM
from application.utils.external_project_parsers.parsers.iso27001 import ISO27001
from application.utils.external_project_parsers.parsers.juiceshop import JuiceShop
from application.utils.external_project_parsers.parsers.misc_tools_parser import (
    MiscTools,
)
from application.utils.external_project_parsers.parsers.pci_dss import PciDss
from application.utils.external_project_parsers.parsers.secure_headers import (
    SecureHeaders,
)
from application.utils.external_project_parsers.parsers.skf_parser import SKF
from application.utils.external_project_parsers.parsers.zap_alerts_parser import ZAP

__all__ = [
    "Capec",
    "CloudControlsMatrix",
    "Cheatsheets",
    "CloudNativeSecurityControls",
    "CWE",
    "DSOMM",
    "ISO27001",
    "JuiceShop",
    "MiscTools",
    "PciDss",
    "SecureHeaders",
    "SKF",
    "ZAP",
]
