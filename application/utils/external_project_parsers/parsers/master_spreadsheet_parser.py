import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from application.utils.external_project_parsers.parsers.spreadsheet_standard_family import (
    is_empty,
    parse_standards_for_family,
)


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_CRE_ID_TOKEN = re.compile(r"^\d{3}-\d{3}$")
# Legacy DB exports sometimes stored display names with a redundant " (123-456)" suffix.
_CRE_NAME_LEGACY_ID_SUFFIX = re.compile(r"^(.+) \((\d{3}-\d{3})\)$")


def _cre_display_names_equivalent(
    sheet_name: str, db_name: str, *, expected_cre_id: str
) -> bool:
    """
    True if the sheet title and the DB title refer to the same CRE.

    The database may still carry a legacy suffix like "Foo (220-442)" while the
    sheet uses the clean title "Foo" (preferred for display). If the DB name has
    a parenthetical ID, it must match ``expected_cre_id``.
    """
    s = sheet_name.strip()
    d = db_name.strip()
    if s == d:
        return True
    m = _CRE_NAME_LEGACY_ID_SUFFIX.match(d)
    if not m:
        return False
    base, suffix_id = m.group(1).strip(), m.group(2)
    if base != s:
        return False
    return suffix_id == expected_cre_id


supported_resource_mapping = {
    "CRE": {
        "id": "CRE ID",
        "name": "CRE hierarchy",
        "tags": "CRE Tags",
        "links": "Link to other CRE",
        "description": "",
    },
    "Standards": {
        "ASVS": {
            "section": "Standard ASVS 4.0.3 description",
            "sectionID": "Standard ASVS 4.0.3 Item",
            "subsection": "",
            "hyperlink": "Standard ASVS 4.0.3 Hyperlink",
        },
        "OWASP Proactive Controls": {
            "section": "Standard OPC (ASVS source)",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard OPC (ASVS source)-hyperlink",
            "separator": ";",
        },
        "CWE": {
            "section": "",
            "sectionID": "Standard CWE (from ASVS)",
            "subsection": "",
            "hyperlink": "Standard CWE (from ASVS)-hyperlink",
        },
        "NIST 800-53 v5": {
            "section": "Standard NIST 800-53 v5",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard NIST 800-53 v5-hyperlink",
            "separator": "\n",
        },
        "OWASP Web Security Testing Guide (WSTG)": {
            "section": "Standard WSTG-item",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard WSTG-Hyperlink",
            "separator": ";",
        },
        "OWASP Cheat Sheets": {
            "section": "Standard Cheat_sheets",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard Cheat_sheets-Hyperlink",
            "separator": ";",
        },
        "NIST 800-63": {
            "section": "Standard NIST-800-63 (from ASVS)",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "",
            "separator": "/",
        },
        "OWASP Top 10 2021": {
            "section": "OWASP Top 10 2021 item",
            "sectionID": "OWASP Top 10 2021 item ID",
            "subsection": "",
            "hyperlink": "OWASP Top 10 2021 hyperlink",
        },
        "OWASP Top 10 2017": {
            "section": "Standard Top 10 2017 item",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard Top 10 2017 Hyperlink",
        },
        "Cloud Controls Matrix": {
            "section": "Source-CCM-Control Title",
            "sectionID": "Source-CCM ID",
            "subsection": "",
            "hyperlink": "",
            "separator": "\n",
        },
        "ISO 27001": {
            "section": "Standard 27001/2:2022",
            "sectionID": "Standard 27001/2:2022 Section ID",
            "subsection": "",
            "hyperlink": "",
            "separator": "\n",
        },
        "SAMM": {
            "section": "Standard SAMM v2",
            "sectionID": "Standard SAMM v2 ID",
            "subsection": "",
            "hyperlink": "Standard SAMM v2 hyperlink",
            "separator": "\n",
        },
        "NIST SSDF": {
            "section": "Standard NIST SSDF",
            "sectionID": "Standard NIST SSDF ID",
            "subsection": "",
            "hyperlink": "",
            "separator": "\n",
        },
        "MITRE ATLAS": {
            "section": "Standard MITRE ATLAS",
            "sectionID": "Standard MITRE ATLAS ID",
            "subsection": "",
            "hyperlink": "Standard MITRE ATLAS hyperlink",
            "separator": ";",
        },
        "OWASP AI Exchange": {
            "section": "Standard OWASP AI Exchange",
            "sectionID": "Standard OWASP AI Exchange ID",
            "subsection": "",
            "hyperlink": "Standard OWASP AI Exchange hyperlink",
            "separator": ";",
        },
        "OWASP Top10 for LLM": {
            "section": "Standard OWASP Top10 for LLM",
            "sectionID": "Standard OWASP Top10 for LLM ID",
            "subsection": "Standard OWASP Top10 for LLM notes",
            "hyperlink": "Standard OWASP Top10 for LLM hyperlink",
            "separator": ";",
        },
        "OWASP Top10 for ML": {
            "section": "Standard OWASP Top10 for ML",
            "sectionID": "Standard OWASP Top10 for ML ID",
            "subsection": "",
            "hyperlink": "Standard OWASP Top10 for ML hyperlink",
            "separator": ";",
        },
        "BIML": {
            "section": "Standard BIML",
            "sectionID": "Standard BIML ID",
            "subsection": "",
            "hyperlink": "Standard BIML hyperlink",
            "separator": ";",
        },
        "ETSI": {
            "section": "Standard ETSI",
            "sectionID": "Standard ETSI ID",
            "subsection": "",
            "hyperlink": "Standard ETSI hyperlink",
            "separator": ";",
        },
        "ENISA": {
            "section": "Standard ENISA",
            "sectionID": "Standard ENISA ID",
            "subsection": "",
            "hyperlink": "Standard ENISA hyperlink",
            "separator": ";",
        },
        "NIST AI 100-2": {
            "section": "Standard NIST AI 100-2",
            "sectionID": "Standard NIST AI 100-2 ID",
            "subsection": "",
            "hyperlink": "Standard NIST AI 100-2 hyperlink",
            "separator": ";",
        },
    },
}


class MasterSpreadsheetParser(ParserInterface):
    """
    Parser for the master mapping spreadsheet (hierarchical CRE structure).

    CRE rows and inter-CRE links are parsed here; each spreadsheet-backed
    standard family has its own module under ``spreadsheet_*.py``, dispatched
    via ``spreadsheet_standards_dispatch``.
    """

    name = "Master Mapping Spreadsheet"

    def parse(
        self, database: db.Node_collection, ph: prompt_client.PromptHandler
    ) -> ParseResult:
        raise NotImplementedError(
            "MasterSpreadsheetParser.parse is not wired to a concrete source yet."
        )

    @staticmethod
    def parse_rows(rows: List[Dict[str, Any]]) -> ParseResult:
        """
        Parse master spreadsheet rows into CRE + per-family standard documents.

        This is the entrypoint used by `cre_main` for spreadsheet imports.
        """
        documents = parse_master_spreadsheet_documents(rows)
        return ParseResult(
            results=documents,
            calculate_gap_analysis=True,
            calculate_embeddings=True,
        )


def parse_cre_hierarchy_from_rows(
    rows: List[Dict[str, Any]],
) -> ParseResult:
    """
    Parse only the CRE structure from the master hierarchical CSV.

    Uses CRE-only ``parse_hierarchical_export_format`` (no spreadsheet columns
    for ASVS, CWE, etc.). Full import merges those via
    ``parse_master_spreadsheet_documents``.
    """
    documents = parse_hierarchical_export_format(rows)

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


@dataclass
class UninitializedMapping:
    complete_cre: defs.CRE
    other_cre_name: str
    relationship: defs.LinkTypes


def get_supported_resources_from_main_csv() -> List[str]:
    return supported_resource_mapping["Standards"].keys()


def add_standard_to_documents_array(
    standard: defs.Standard, documents: Dict[str, List[defs.Document]]
) -> Dict[defs.Credoctypes, Dict[str, List[defs.Document]]]:
    if standard.name not in documents.keys():
        documents[standard.name] = []
    found = False
    index = 0
    docs = documents[standard.name]
    for doc in documents[standard.name]:
        if (
            doc.name == standard.name
            and doc.section == standard.section
            and doc.subsection == standard.subsection
            and doc.sectionID == standard.sectionID
            and doc.version == standard.version
        ):
            for lnk in standard.links:
                if lnk.document.id not in list([l.document.id for l in doc.links]):
                    doc = doc.add_link(lnk)
            docs[index] = doc

            found = True
        index += 1
    documents[standard.name] = docs
    if not found:
        documents[standard.name].append(standard)
    return documents


def reconcile_uninitializedMappings(
    cres: Dict[str, defs.CRE], u_mappings: List[UninitializedMapping]
) -> Dict[str, defs.CRE]:
    for mapping in u_mappings:
        other_cre = cres.get(mapping.other_cre_name)
        if not other_cre:
            logger.warning(
                "Skipping link: CRE '%s' is not registered (no resolved ID in sheet); "
                "cannot link from '%s'",
                mapping.other_cre_name,
                mapping.complete_cre.name,
            )
            continue
        cre = cres[mapping.complete_cre.name]
        cres[cre.name] = cre.add_link(
            defs.Link(ltype=mapping.relationship, document=other_cre.shallow_copy())
        )
    return cres


def get_highest_cre_name(
    mapping: Dict[str, str], highest_hierarchy: int = 5
) -> tuple[int, str]:
    for i in range(highest_hierarchy, 0, -1):
        if not is_empty(mapping.get(f"CRE hierarchy {i}")):
            return i, mapping.get(f"CRE hierarchy {i}").strip()
    return -1, None


def _build_cre_name_to_id_map(
    cre_file: List[Dict[str, str]],
    max_hierarchy: int,
) -> Dict[str, str]:
    name_to_id: Dict[str, str] = {}
    for mapping in cre_file:
        ch, name = get_highest_cre_name(
            mapping=mapping, highest_hierarchy=max_hierarchy
        )
        if name is None or is_empty(name):
            continue
        row_id = str(mapping.get("CRE ID", "")).strip()
        if is_empty(row_id):
            continue
        if name in name_to_id and name_to_id[name] != row_id:
            raise ValueError(
                f"duplicate CRE name '{name}' with conflicting IDs: "
                f"{name_to_id[name]} vs {row_id}"
            )
        if name not in name_to_id:
            name_to_id[name] = row_id
    return name_to_id


def _load_existing_cre_identity_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Best-effort CRE identity map from DB:
    - id_to_name: external_id -> name
    - name_to_id: lower(name) -> external_id
    """
    try:
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


def _hydrate_and_validate_cre_identity(
    *,
    name: str,
    resolved_id: str,
    db_id_to_name: Dict[str, str],
    db_name_to_id: Dict[str, str],
) -> Tuple[str, str]:
    """
    Hydrate incomplete identities from DB and fail fast on corruption:
    - same ID with different name
    - same name with different ID
    """
    hydrated_name = name
    hydrated_id = resolved_id

    if not hydrated_id:
        known_id = db_name_to_id.get(hydrated_name.lower(), "")
        if known_id:
            hydrated_id = known_id

    if not hydrated_id and _CRE_ID_TOKEN.match(hydrated_name):
        hydrated_id = hydrated_name

    if hydrated_id and not _CRE_ID_TOKEN.match(hydrated_id):
        raise ValueError(f"Invalid CRE ID format '{hydrated_id}' for '{hydrated_name}'")

    db_name_for_id = db_id_to_name.get(hydrated_id) if hydrated_id else None
    if db_name_for_id:
        if _CRE_ID_TOKEN.match(hydrated_name):
            # ID-only row; hydrate the display name from DB.
            hydrated_name = db_name_for_id
        elif not _cre_display_names_equivalent(
            hydrated_name, db_name_for_id, expected_cre_id=hydrated_id
        ):
            raise ValueError(
                "Data corruption: CRE ID conflict for "
                f"{hydrated_id}: sheet name '{hydrated_name}' != db name '{db_name_for_id}'"
            )

    db_id_for_name = db_name_to_id.get(hydrated_name.lower())
    if db_id_for_name and hydrated_id and db_id_for_name != hydrated_id:
        raise ValueError(
            "Data corruption: CRE name conflict for "
            f"{hydrated_name}: sheet ID '{hydrated_id}' != db id '{db_id_for_name}'"
        )

    return hydrated_name, hydrated_id


def update_cre_in_links(
    documents: Dict[str, defs.CRE], cre: defs.CRE
) -> List[defs.CRE]:
    for c in documents.values():
        for link in c.links:
            if link.document.name == cre.name:
                link.document = cre.shallow_copy()
    return documents


def _parse_cre_graph_and_rows(
    cre_file: List[Dict[str, str]],
) -> Tuple[Dict[str, List[defs.Document]], List[Tuple[Dict[str, str], defs.CRE]]]:
    logger.info("Spreadsheet is hierarchical export format")
    documents: Dict[str, List[defs.Document]] = {defs.Credoctypes.CRE.value: []}
    rows_with_cre: List[Tuple[Dict[str, str], defs.CRE]] = []
    if not cre_file:
        return documents, rows_with_cre
    max_hierarchy = len([key for key in cre_file[0].keys() if "CRE hierarchy" in key])

    cre_name_to_id = _build_cre_name_to_id_map(cre_file, max_hierarchy)

    db_id_to_name, db_name_to_id = _load_existing_cre_identity_maps()
    cre_dict = {}
    uninitialized_cre_mappings: List[UninitializedMapping] = []
    for mapping in cre_file:
        cre: defs.CRE
        name: str = ""
        current_hierarchy: int = 0
        higher_cre: int = 0

        current_hierarchy, name = get_highest_cre_name(
            mapping=mapping, highest_hierarchy=max_hierarchy
        )
        if name is None:
            continue

        if current_hierarchy > 0:
            higher_cre = 0
            for i in range(current_hierarchy - 1, 0, -1):
                if not is_empty(mapping.get(f"CRE hierarchy {str(i)}")):
                    higher_cre = i
                    break

        if is_empty(name):
            raise ValueError(
                f'Found entry with ID \'{mapping.get("CRE ID")}\' hierarchy {current_hierarchy} without a cre name'
            )

        row_id = str(mapping.get("CRE ID", "")).strip()
        resolved_id = row_id if not is_empty(row_id) else cre_name_to_id.get(name, "")
        name, resolved_id = _hydrate_and_validate_cre_identity(
            name=name,
            resolved_id=resolved_id,
            db_id_to_name=db_id_to_name,
            db_name_to_id=db_name_to_id,
        )

        if name in cre_dict.keys():
            curr_id = resolved_id
            if (
                cre_dict[name].id != curr_id
                and cre_dict[name].id != ""
                and curr_id != ""
            ):
                err_msg = f"duplicate entry for cre named {name}, previous id:{cre_dict[name].id}, new id {curr_id}"
                raise ValueError(err_msg)
            cre = cre_dict[name]
        elif resolved_id:
            if not is_empty(row_id):
                mapping.pop("CRE ID")
            cre = defs.CRE(name=name, id=resolved_id)
        else:
            raise ValueError(
                f"Missing CRE ID for '{name}' and could not hydrate from DB or sheet context"
            )

        if not is_empty(str(mapping.get("CRE Tags")).strip()):
            ts = set()
            for x in str(mapping.pop("CRE Tags")).split(","):
                ts.add(x.strip())
            cre.tags = list(ts)
        if cre:
            cre_dict = update_cre_in_links(cre_dict, cre)

        link_key = "Link to other CRE"
        # CRE Tags double as Related-link references to topic CREs
        # (e.g. tag "Cryptography" means this CRE is Related to the Cryptography CRE).
        # Always append tags so rows with an empty "Link to other CRE" column still
        # get their tag-derived Related links registered.
        mapping[link_key] = f'{mapping.get(link_key, "")},{",".join(cre.tags)}'

        if not is_empty(str(mapping.get(link_key, "")).strip()):
            other_cres = list(
                set(
                    [
                        x.strip()
                        for x in str(mapping.pop(link_key, "")).split(",")
                        if not is_empty(x.strip())
                    ]
                )
            )
            for other_cre in other_cres:
                logger.info(f"{cre.id}: Found 'other cre' {other_cre}")
                if not cre_dict.get(other_cre):
                    logger.info(
                        f"{cre.id}: We don't know yet of 'other cre' {other_cre}, adding to uninitialized mappings"
                    )
                    uninitialized_cre_mappings.append(
                        UninitializedMapping(
                            complete_cre=cre,
                            other_cre_name=other_cre.strip(),
                            relationship=defs.LinkTypes.Related,
                        )
                    )
                else:
                    logger.info(
                        f"{cre.id}: We knew yet 'other cre' {other_cre}, adding regular link"
                    )
                    new_cre = cre_dict[other_cre.strip()]
                    lnk = defs.Link(
                        ltype=defs.LinkTypes.Related,
                        document=new_cre.shallow_copy(),
                    )
                    if cre.has_link(lnk):
                        indx = cre.links.index(lnk)
                        cre.links[indx].document = new_cre.shallow_copy()
                    else:
                        cre = cre.add_link(lnk)

        rows_with_cre.append((dict(mapping), cre))

        if higher_cre and not is_empty(
            str(mapping.get(f"CRE hierarchy {str(higher_cre)}")).strip()
        ):
            name_hi = str(mapping.pop(f"CRE hierarchy {str(higher_cre)}")).strip()
            cre_hi = cre_dict.get(name_hi)
            if not cre_hi:
                uninitialized_cre_mappings.append(
                    UninitializedMapping(
                        complete_cre=cre,
                        other_cre_name=name_hi,
                        relationship=defs.LinkTypes.PartOf,
                    )
                )
            else:
                existing_link = [
                    c
                    for c in cre_hi.links
                    if c.document.doctype == defs.Credoctypes.CRE
                    and c.document.name == cre.name
                ]
                if existing_link:
                    cre_hi.links[cre_hi.links.index(existing_link[0])].document = (
                        cre.shallow_copy()
                    )
                else:
                    cre_hi = cre_hi.add_link(
                        defs.Link(
                            ltype=defs.LinkTypes.Contains, document=cre.shallow_copy()
                        )
                    )
                cre_dict[cre_hi.name] = cre_hi
        if cre:
            cre_dict[cre.name] = cre

    cre_dict = reconcile_uninitializedMappings(cre_dict, uninitialized_cre_mappings)
    cres = list(cre_dict.values())
    # Ensure CREs coming from the master spreadsheet are classification-tagged.
    # (The central import pipeline validates tags for all documents.)
    for cre in cres:
        cre.tags = base_parser_defs.build_tags(
            family=base_parser_defs.Family.STANDARD,
            subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
            audience=base_parser_defs.Audience.ARCHITECT,
            maturity=base_parser_defs.Maturity.STABLE,
            source="opencre_master_sheet",
            extra=cre.tags,
        )

    documents[defs.Credoctypes.CRE.value] = cres
    return documents, rows_with_cre


def parse_hierarchical_export_format(
    cre_file: List[Dict[str, str]],
) -> Dict[str, List[defs.Document]]:
    """CRE hierarchy only (no spreadsheet standard columns)."""
    documents, _ = _parse_cre_graph_and_rows(cre_file)
    return documents


def parse_master_spreadsheet_documents(
    cre_file: List[Dict[str, str]],
) -> Dict[str, List[defs.Document]]:
    """Full master sheet: CREs plus all families handled in ``spreadsheet_*.py``."""
    from application.utils.external_project_parsers.parsers.spreadsheet_standards_dispatch import (
        all_standards_from_rows,
    )

    documents, rows_with_cre = _parse_cre_graph_and_rows(cre_file)
    merged: Dict[str, List[defs.Document]] = dict(documents)
    merged.update(all_standards_from_rows(rows_with_cre))
    return merged


def parse_standards(
    mapping: Dict[str, str], standards_mapping: Dict[str, Dict[str, Any]] = None
) -> List[defs.Link]:
    if not standards_mapping:
        standards_mapping = supported_resource_mapping

    links: List[defs.Link] = []
    for name, struct in standards_mapping.get("Standards", {}).items():
        links.extend(parse_standards_for_family(mapping, name, struct))
    return links
