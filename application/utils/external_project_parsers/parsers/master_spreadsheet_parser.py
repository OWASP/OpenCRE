import logging
from typing import Dict, List, Any

from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.utils import spreadsheet as sheet_utils
from application.utils import spreadsheet_parsers
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MasterSpreadsheetParser(ParserInterface):
    """
    Parser for the master mapping spreadsheet (hierarchical CRE structure).

    This parser is intended to:
    - Parse CRE hierarchy and inter-CRE links from the main CSV.
    - Delegate standard content to dedicated external parsers (ASVS, CWE, etc).

    The high-level flow is:
    1. Use spreadsheet_parsers.parse_hierarchical_export_format to obtain
       CREs plus placeholder links to standards.
    2. Persist/merge the CREs.
    3. Let other external parsers populate the actual Standard documents.
    """

    name = "Master Mapping Spreadsheet"

    def parse(
        self, database: db.Node_collection, ph: prompt_client.PromptHandler
    ) -> ParseResult:
        raise NotImplementedError(
            "MasterSpreadsheetParser.parse is not wired to a concrete source yet."
        )


def parse_cre_hierarchy_from_rows(
    rows: List[Dict[str, Any]],
) -> ParseResult:
    """
    Parse only the CRE structure from the master hierarchical CSV.

    This uses spreadsheet_parsers.parse_hierarchical_export_format to get a
    dict that includes CREs and any standard links, but we only return the
    CRE collection here. Standards are expected to be handled by their
    own external parsers.
    """
    documents = spreadsheet_parsers.parse_hierarchical_export_format(rows)

    cre_key = defs.Credoctypes.CRE.value
    cres: List[defs.CRE] = documents.get(cre_key, [])

    # For empty inputs, unit tests expect `result.results` to be falsey ({}),
    # not `{ "CRE": [] }`.
    if not cres:
        return ParseResult(
            results={},
            calculate_gap_analysis=True,
            calculate_embeddings=True,
        )

    for cre in cres:
        cre.tags = base_parser_defs.build_tags(
            family=base_parser_defs.Family.STANDARD,
            subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
            audience=base_parser_defs.Audience.ARCHITECT,
            maturity=base_parser_defs.Maturity.STABLE,
            source="opencre_master_sheet",
            extra=cre.tags,
        )

    all_docs: Dict[str, List[defs.Document]] = {cre_key: cres}
    base_parser_defs.validate_classification_tags(all_docs)
    return ParseResult(
        results=all_docs,
        calculate_gap_analysis=True,
        calculate_embeddings=True,
    )


