"""Aggregate spreadsheet-derived standards: one module per family, same master sheet."""

from typing import Dict, List, Tuple

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers.master_spreadsheet_parser import (
    add_standard_to_documents_array,
    supported_resource_mapping,
)
from application.utils.external_project_parsers.parsers import (
    spreadsheet_asvs,
    spreadsheet_cloud_controls_matrix,
    spreadsheet_cwe,
    spreadsheet_iso27001,
    spreadsheet_mitre_atlas,
    spreadsheet_nist_800_53_v5,
    spreadsheet_nist_800_63,
    spreadsheet_nist_ai_100_2,
    spreadsheet_nist_ssdf,
    spreadsheet_biml,
    spreadsheet_enisa,
    spreadsheet_etsi,
    spreadsheet_owasp_ai_exchange,
    spreadsheet_owasp_cheat_sheets,
    spreadsheet_owasp_proactive_controls,
    spreadsheet_owasp_top10_llm,
    spreadsheet_owasp_top10_ml,
    spreadsheet_owasp_top10_2017,
    spreadsheet_owasp_top10_2021,
    spreadsheet_owasp_wstg,
    spreadsheet_samm,
)

# Order matches ``supported_resource_mapping["Standards"]`` for stable, predictable merges.
_SPREADSHEET_STANDARD_PARSERS = (
    spreadsheet_asvs,
    spreadsheet_owasp_proactive_controls,
    spreadsheet_cwe,
    spreadsheet_nist_800_53_v5,
    spreadsheet_owasp_wstg,
    spreadsheet_owasp_cheat_sheets,
    spreadsheet_nist_800_63,
    spreadsheet_owasp_top10_2021,
    spreadsheet_owasp_top10_2017,
    spreadsheet_cloud_controls_matrix,
    spreadsheet_iso27001,
    spreadsheet_samm,
    spreadsheet_nist_ssdf,
    spreadsheet_mitre_atlas,
    spreadsheet_owasp_ai_exchange,
    spreadsheet_owasp_top10_llm,
    spreadsheet_owasp_top10_ml,
    spreadsheet_biml,
    spreadsheet_etsi,
    spreadsheet_enisa,
    spreadsheet_nist_ai_100_2,
)

_expected = tuple(supported_resource_mapping["Standards"].keys())
_actual = tuple(m.FAMILY_NAME for m in _SPREADSHEET_STANDARD_PARSERS)
if _expected != _actual:
    raise RuntimeError(
        "spreadsheet_standards_dispatch out of sync with supported_resource_mapping "
        f"Standards keys: expected {_expected}, got {_actual}"
    )


def all_standards_from_rows(
    rows_with_cre: List[Tuple[Dict[str, str], defs.CRE]],
) -> Dict[str, List[defs.Document]]:
    out: Dict[str, List[defs.Document]] = {}
    for mod in _SPREADSHEET_STANDARD_PARSERS:
        for std in mod.parse_rows(rows_with_cre):
            out = add_standard_to_documents_array(std, out)
    return out
