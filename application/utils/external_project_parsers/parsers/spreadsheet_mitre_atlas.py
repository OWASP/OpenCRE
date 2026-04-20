"""MITRE ATLAS mitigations from the master mapping spreadsheet / AI exchange CSV."""

from typing import Dict, List, Tuple

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers.master_spreadsheet_parser import (
    supported_resource_mapping,
)
from application.utils.external_project_parsers.parsers.spreadsheet_standard_family import (
    SpreadsheetStandardFamilyParser,
)

FAMILY_NAME = "MITRE ATLAS"


def parse_rows(
    rows_with_cre: List[Tuple[Dict[str, str], defs.CRE]],
) -> List[defs.Standard]:
    struct = supported_resource_mapping["Standards"][FAMILY_NAME]
    return SpreadsheetStandardFamilyParser(
        family_name=FAMILY_NAME, struct=struct
    ).parse_rows(rows_with_cre)
