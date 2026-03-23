import logging
from typing import Dict, List, Any

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers import export_format_parser
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import ParseResult


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse_rows_to_documents(rows: List[Dict[str, Any]]) -> ParseResult:
    """
    Parser for the MyOpenCRE CSV import format.

    This mirrors the legacy logic from web_main.import_from_cre_csv, but
    additionally applies classification tags using the shared tagging
    conventions. It reuses export_format_parser.parse_export_format to
    understand the CSV structure.
    """
    documents = export_format_parser.parse_export_format(rows)

    # CREs are under the Credoctypes.CRE value key
    cre_key = defs.Credoctypes.CRE.value
    cres: List[defs.CRE] = documents.pop(cre_key, [])

    for cre in cres:
        cre.tags = base_parser_defs.build_tags(
            family=base_parser_defs.Family.STANDARD,
            subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
            audience=base_parser_defs.Audience.ARCHITECT,
            maturity=base_parser_defs.Maturity.STABLE,
            source="myopencre_csv",
            extra=cre.tags,
        )

    for standard_name, entries in documents.items():
        tagged_entries: List[defs.Standard] = []
        for doc in entries:
            if not isinstance(doc, defs.Standard):
                tagged_entries.append(doc)
                continue
            # Use a generic standard classification for MyOpenCRE imports
            family = base_parser_defs.Family.STANDARD
            subtype = base_parser_defs.Subtype.REQUIREMENTS_STANDARD
            audience = base_parser_defs.Audience.DEVELOPER
            maturity = base_parser_defs.Maturity.STABLE
            source = standard_name.replace(" ", "_").lower()
            doc.tags = base_parser_defs.build_tags(
                family=family,
                subtype=subtype,
                audience=audience,
                maturity=maturity,
                source=source,
                extra=doc.tags,
            )
            tagged_entries.append(doc)
        documents[standard_name] = tagged_entries

    all_docs: Dict[str, List[defs.Document]] = {cre_key: cres}
    all_docs.update(documents)
    base_parser_defs.validate_classification_tags(all_docs)
    return ParseResult(results=all_docs, calculate_gap_analysis=True, calculate_embeddings=True)

