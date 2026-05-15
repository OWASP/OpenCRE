import logging
import re
from typing import Dict, List, Any, Tuple

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers import export_format_parser
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import ParseResult


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_CRE_ID_TOKEN = re.compile(r"^\d{3}-\d{3}$")


def _load_existing_cre_identity_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    try:
        from application.database import db

        rows = db.CRE.query.with_entities(db.CRE.external_id, db.CRE.name).all()
    except Exception:
        return {}, {}

    id_to_name: Dict[str, str] = {}
    name_to_id: Dict[str, str] = {}
    for external_id, name in rows:
        cre_id = str(external_id or "").strip()
        cre_name = str(name or "").strip()
        if not cre_id or not cre_name or not _CRE_ID_TOKEN.match(cre_id):
            continue
        id_to_name[cre_id] = cre_name
        name_to_id[cre_name.lower()] = cre_id
    return id_to_name, name_to_id


def _reconcile_cre_identities(cres: List[defs.CRE]) -> List[defs.CRE]:
    """
    Hydrate incomplete CRE identities from DB and fail fast on identity conflicts:
    - same ID with different name
    - same name with different ID
    """
    db_id_to_name, db_name_to_id = _load_existing_cre_identity_maps()
    for cre in cres:
        name = str(cre.name or "").strip()
        resolved_id = str(cre.id or "").strip()
        if not name:
            raise ValueError("Missing CRE name")

        if not resolved_id:
            resolved_id = db_name_to_id.get(name.lower(), "")
        if not resolved_id and _CRE_ID_TOKEN.match(name):
            resolved_id = name
        if not resolved_id:
            raise ValueError(
                f"Missing CRE ID for '{name}' and could not hydrate from DB context"
            )
        if not _CRE_ID_TOKEN.match(resolved_id):
            raise ValueError(f"Invalid CRE ID format '{resolved_id}' for '{name}'")

        db_name_for_id = db_id_to_name.get(resolved_id)
        if db_name_for_id:
            if _CRE_ID_TOKEN.match(name):
                name = db_name_for_id
            elif name != db_name_for_id:
                raise ValueError(
                    "Data corruption: CRE ID conflict for "
                    f"{resolved_id}: csv name '{name}' != db name '{db_name_for_id}'"
                )

        db_id_for_name = db_name_to_id.get(name.lower())
        if db_id_for_name and db_id_for_name != resolved_id:
            raise ValueError(
                "Data corruption: CRE name conflict for "
                f"{name}: csv ID '{resolved_id}' != db id '{db_id_for_name}'"
            )

        cre.name = name
        cre.id = resolved_id
    return cres


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
    cres = _reconcile_cre_identities(cres)

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
    return ParseResult(
        results=all_docs, calculate_gap_analysis=True, calculate_embeddings=True
    )
