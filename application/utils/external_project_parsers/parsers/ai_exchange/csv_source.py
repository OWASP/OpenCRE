"""Import AI / LLM control mappings from the OpenCRE AI exchange CSV export.

The export uses ``CRE 0``..``CRE n`` hierarchy columns (not ``CRE hierarchy 1``..),
``Cross-link CREs`` with CRE IDs (``NNN-NNN``), plus pipe-delimited resource
columns (MITRE ATLAS, AIX, OWASP Top 10 LLM/ML, BIML, ETSI, ENISA, NIST AI
100-2). Rows are normalized into the master spreadsheet shape so
``MasterSpreadsheetParser`` and the shared import pipeline apply.

A future live AI Exchange parser should produce the same row shape (or call
``normalize_rows_for_master_import``) so imports stay unified.
"""
from __future__ import annotations

import copy
import csv
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

IMPORT_SOURCE_CSV = "ai_exchange_csv"

_CRE_ID_TOKEN = re.compile(r"^\d{3}-\d{3}$")
_CRE_COL_PATTERN = re.compile(r"^CRE\s*(\d+)$", re.IGNORECASE)

_HEADER_ALIASES = {
    "AIX|name": ["AIX|name", "AI Exchange|name"],
    "AIX|id": ["AIX|id", "AI Exchange|id"],
    "AIX|hyperlink": ["AIX|hyperlink", "AI Exchange|hyperlink"],
    "OWASPTop10LLM|name": ["OWASPTop10LLM|name", "OWASP Top10 LLM|name"],
    "OWASPTop10LLM|id": ["OWASPTop10LLM|id", "OWASP Top10 LLM|id"],
    "OWASPTop10LLM|hyperlink": [
        "OWASPTop10LLM|hyperlink",
        "OWASP Top10 LLM|hyperlink",
    ],
    "OWASPTop10LLM|notes": ["OWASPTop10LLM|notes", "OWASP Top10 LLM|notes"],
    "OWASPTop10ML|name": ["OWASPTop10ML|name", "OWASP Top10 ML|name"],
    "OWASPTop10ML|id": ["OWASPTop10ML|id", "OWASP Top10 ML|id"],
    "OWASPTop10ML|hyperlink": ["OWASPTop10ML|hyperlink", "OWASP Top10 ML|hyperlink"],
    "ETSI|name": ["ETSI|name", "ETSI SAI 005 MSR|name"],
    "ETSI|id": ["ETSI|id", "ETSI SAI 005 MSR|id"],
    "ETSI|hyperlink": ["ETSI|hyperlink", "ETSI SAI 005 MSR|hyperlink"],
    "ENISA|name": ["ENISA|name", "ENISA SMLA|name"],
    "ENISA|id": ["ENISA|id", "ENISA SMLA|id"],
    "ENISA|hyperlink": ["ENISA|hyperlink", "ENISA SMLA|hyperlink"],
}

_RESOURCE_COLUMN_SETS = [
    ("MITRE ATLAS|name", "MITRE ATLAS|id", "MITRE ATLAS|hyperlink"),
    ("AIX|name", "AIX|id", "AIX|hyperlink"),
    ("OWASPTop10LLM|name", "OWASPTop10LLM|id", "OWASPTop10LLM|hyperlink"),
    ("OWASPTop10ML|name", "OWASPTop10ML|id", "OWASPTop10ML|hyperlink"),
    ("BIML|name", "BIML|id", "BIML|hyperlink"),
    ("ETSI|name", "ETSI|id", "ETSI|hyperlink"),
    ("ENISA|name", "ENISA|id", "ENISA|hyperlink"),
    ("NIST AI 100-2|name", "NIST AI 100-2|id", "NIST AI 100-2|hyperlink"),
]


def _display_base_name(display: str) -> str:
    if display.endswith(")") and " (" in display:
        return display[: display.rindex(" (")]
    return display


def _canonicalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for raw_key, value in row.items():
        key = str(raw_key).strip()
        canonical_key = key
        cre_match = _CRE_COL_PATTERN.match(key)
        if cre_match:
            canonical_key = f"CRE {int(cre_match.group(1))}"
        else:
            for canonical, aliases in _HEADER_ALIASES.items():
                if key in aliases:
                    canonical_key = canonical
                    break

        if canonical_key in out:
            existing = out[canonical_key]
            if (existing is None or str(existing).strip() == "") and (
                value is not None and str(value).strip() != ""
            ):
                out[canonical_key] = value
        else:
            out[canonical_key] = value
    return out


def is_ai_exchange_spreadsheet(sample_row: Dict[str, Any]) -> bool:
    normalized = _canonicalize_row_keys(sample_row)
    keys = set(normalized.keys())
    return (
        "CRE 0" in keys
        and "CRE ID" in keys
        and any(str(k).startswith("AIX|") for k in keys)
    )


def _cre_level_indices(rows: List[Dict[str, Any]]) -> List[int]:
    found: set[int] = set()
    for row in rows:
        for k in row.keys():
            s = str(k)
            m = _CRE_COL_PATTERN.match(s)
            if m:
                found.add(int(m.group(1)))
    return sorted(found)


def _leaf_cre_name(row: Dict[str, Any], levels: List[int]) -> Optional[str]:
    for idx in reversed(levels):
        key = f"CRE {idx}"
        raw = row.get(key, "")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _ambiguous_leaf_labels(rows: List[Dict[str, Any]], levels: List[int]) -> set[str]:
    """Leaf titles shared by more than one CRE ID (master sheet assumes unique names)."""
    leaf_to_ids: Dict[str, set[str]] = {}
    for row in rows:
        cid = str(row.get("CRE ID", "") or "").strip()
        if not cid:
            continue
        leaf = _leaf_cre_name(row, levels)
        if not leaf:
            continue
        leaf_to_ids.setdefault(leaf, set()).add(cid)
    return {leaf for leaf, ids in leaf_to_ids.items() if len(ids) > 1}


def _hierarchy_cells_normalized(
    row: Dict[str, Any], levels: List[int], ambiguous_leaves: set[str]
) -> Dict[int, str]:
    """CRE column values for one row; disambiguate duplicate leaf titles with ``(NNN-NNN)``."""
    cells: Dict[int, str] = {}
    for idx in levels:
        raw = row.get(f"CRE {idx}", "")
        cells[idx] = str(raw).strip() if raw is not None else ""
    leaf = _leaf_cre_name(row, levels)
    cid = str(row.get("CRE ID", "") or "").strip()
    if leaf and cid and leaf in ambiguous_leaves:
        deepest_idx = max((i for i in levels if cells[i]), default=-1)
        if deepest_idx >= 0:
            cells[deepest_idx] = f"{leaf} ({cid})"
    return cells


def _build_cre_id_to_display_name(
    rows: List[Dict[str, Any]], levels: List[int], ambiguous_leaves: set[str]
) -> Dict[str, str]:
    id_to_name: Dict[str, str] = {}
    for row in rows:
        cid = str(row.get("CRE ID", "") or "").strip()
        if not cid:
            continue
        cells = _hierarchy_cells_normalized(row, levels, ambiguous_leaves)
        deepest_idx = max((i for i in levels if cells[i]), default=-1)
        display = cells[deepest_idx] if deepest_idx >= 0 else ""
        if not display:
            continue
        if cid in id_to_name and id_to_name[cid] != display:
            raise ValueError(
                f"CRE ID {cid} maps to different display names: "
                f"{id_to_name[cid]!r} vs {display!r}"
            )
        id_to_name[cid] = display
    return id_to_name


def _merge_rows_sharing_cre_id(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One combined row per CRE ID so duplicate sheet lines do not duplicate CRE links."""
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    id_order: List[str] = []
    no_id: List[Dict[str, Any]] = []
    for row in rows:
        cid = str(row.get("CRE ID", "") or "").strip()
        if not cid:
            no_id.append(row)
            continue
        if cid not in by_id:
            id_order.append(cid)
        by_id.setdefault(cid, []).append(row)

    merged: List[Dict[str, Any]] = []
    for cid in id_order:
        group = by_id[cid]
        if len(group) == 1:
            merged.append(group[0])
            continue
        base = copy.deepcopy(group[0])
        xtok: List[str] = []
        for r in group:
            raw = r.get("Cross-link CREs", "")
            if raw is not None and str(raw).strip():
                for part in re.split(r"[;,]", str(raw)):
                    t = part.strip()
                    if t:
                        xtok.append(t)
        base["Cross-link CREs"] = ";".join(dict.fromkeys(xtok))
        merged_resource_parts: Dict[str, List[str]] = {}
        for name_col, id_col, hyperlink_col in _RESOURCE_COLUMN_SETS:
            merged_resource_parts[name_col] = []
            merged_resource_parts[id_col] = []
            merged_resource_parts[hyperlink_col] = []
        merged_resource_parts["OWASPTop10LLM|notes"] = []
        for r in group:
            for name_col, id_col, hyperlink_col in _RESOURCE_COLUMN_SETS:
                n = str(r.get(name_col, "") or "").strip()
                i = str(r.get(id_col, "") or "").strip()
                h = str(r.get(hyperlink_col, "") or "").strip()
                if n or i or h:
                    merged_resource_parts[name_col].append(n)
                    merged_resource_parts[id_col].append(i)
                    merged_resource_parts[hyperlink_col].append(h)
            owasp_llm_note = str(r.get("OWASPTop10LLM|notes", "") or "").strip()
            if owasp_llm_note:
                merged_resource_parts["OWASPTop10LLM|notes"].append(owasp_llm_note)
        for col, parts in merged_resource_parts.items():
            base[col] = ";".join(parts)
        merged.append(base)
    return merged + no_id


def normalize_rows_for_master_import(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Return new row dicts matching master spreadsheet column names and standard keys."""
    if not rows:
        return []

    rows = [_canonicalize_row_keys(dict(r)) for r in rows]
    rows = _merge_rows_sharing_cre_id(rows)
    levels = _cre_level_indices(rows)
    if not levels:
        raise ValueError("AI exchange CSV has no CRE 0..CRE n columns")

    ambiguous = _ambiguous_leaf_labels(rows, levels)
    id_to_name = _build_cre_id_to_display_name(rows, levels, ambiguous)
    db_id_to_name = _load_existing_cre_names_by_id()
    out: List[Dict[str, str]] = []

    for row in rows:
        new_row: Dict[str, str] = {}
        cells = _hierarchy_cells_normalized(row, levels, ambiguous)
        for idx in levels:
            new_row[f"CRE hierarchy {idx + 1}"] = cells.get(idx, "")

        new_row["CRE ID"] = str(row.get("CRE ID", "") or "").strip()

        link_names: List[str] = []
        raw_x = row.get("Cross-link CREs", "")
        if raw_x is not None and str(raw_x).strip():
            for part in re.split(r"[;,]", str(raw_x)):
                token = part.strip()
                if not token:
                    continue
                resolved: Optional[str] = None
                if _CRE_ID_TOKEN.match(token):
                    resolved = id_to_name.get(token) or db_id_to_name.get(token)
                    if not resolved:
                        logger.warning(
                            "Cross-link CRE ID %s not found in sheet/DB (skipped)",
                            token,
                        )
                elif token in id_to_name.values():
                    resolved = token
                else:
                    for disp in id_to_name.values():
                        if disp == token or _display_base_name(disp) == token:
                            resolved = disp
                            break
                    if not resolved:
                        logger.warning(
                            "Cross-link value %r is neither a known CRE ID nor a "
                            "resolved leaf name (skipped)",
                            token,
                        )
                if resolved:
                    link_names.append(resolved)
        new_row["Link to other CRE"] = ",".join(dict.fromkeys(link_names))

        new_row["Standard MITRE ATLAS"] = str(
            row.get("MITRE ATLAS|name", "") or ""
        ).strip()
        new_row["Standard MITRE ATLAS ID"] = str(
            row.get("MITRE ATLAS|id", "") or ""
        ).strip()
        new_row["Standard MITRE ATLAS hyperlink"] = str(
            row.get("MITRE ATLAS|hyperlink", "") or ""
        ).strip()
        new_row["Standard OWASP AI Exchange"] = str(
            row.get("AIX|name", "") or ""
        ).strip()
        new_row["Standard OWASP AI Exchange ID"] = str(
            row.get("AIX|id", "") or ""
        ).strip()
        new_row["Standard OWASP AI Exchange hyperlink"] = str(
            row.get("AIX|hyperlink", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for LLM"] = str(
            row.get("OWASPTop10LLM|name", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for LLM ID"] = str(
            row.get("OWASPTop10LLM|id", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for LLM hyperlink"] = str(
            row.get("OWASPTop10LLM|hyperlink", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for LLM notes"] = str(
            row.get("OWASPTop10LLM|notes", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for ML"] = str(
            row.get("OWASPTop10ML|name", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for ML ID"] = str(
            row.get("OWASPTop10ML|id", "") or ""
        ).strip()
        new_row["Standard OWASP Top10 for ML hyperlink"] = str(
            row.get("OWASPTop10ML|hyperlink", "") or ""
        ).strip()
        new_row["Standard BIML"] = str(row.get("BIML|name", "") or "").strip()
        new_row["Standard BIML ID"] = str(row.get("BIML|id", "") or "").strip()
        new_row["Standard BIML hyperlink"] = str(
            row.get("BIML|hyperlink", "") or ""
        ).strip()
        new_row["Standard ETSI"] = str(row.get("ETSI|name", "") or "").strip()
        new_row["Standard ETSI ID"] = str(row.get("ETSI|id", "") or "").strip()
        new_row["Standard ETSI hyperlink"] = str(
            row.get("ETSI|hyperlink", "") or ""
        ).strip()
        new_row["Standard ENISA"] = str(row.get("ENISA|name", "") or "").strip()
        new_row["Standard ENISA ID"] = str(row.get("ENISA|id", "") or "").strip()
        new_row["Standard ENISA hyperlink"] = str(
            row.get("ENISA|hyperlink", "") or ""
        ).strip()
        new_row["Standard NIST AI 100-2"] = str(
            row.get("NIST AI 100-2|name", "") or ""
        ).strip()
        new_row["Standard NIST AI 100-2 ID"] = str(
            row.get("NIST AI 100-2|id", "") or ""
        ).strip()
        new_row["Standard NIST AI 100-2 hyperlink"] = str(
            row.get("NIST AI 100-2|hyperlink", "") or ""
        ).strip()

        out.append(new_row)

    return out


def _load_existing_cre_names_by_id() -> Dict[str, str]:
    """
    Best-effort lookup of known CRE IDs from the live DB so CSV cross-links can
    target existing CREs even when those IDs are not present in the same sheet.
    """
    try:
        from application.database import db
    except Exception:
        return {}

    try:
        rows = db.CRE.query.with_entities(db.CRE.external_id, db.CRE.name).all()
    except Exception:
        # Keep CSV normalization deterministic/offline-friendly when DB is not
        # configured (common in unit tests).
        return {}

    out: Dict[str, str] = {}
    for external_id, name in rows:
        cre_id = str(external_id or "").strip()
        cre_name = str(name or "").strip()
        if cre_id and cre_name and _CRE_ID_TOKEN.match(cre_id):
            out[cre_id] = cre_name
    return out


def load_csv_rows(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_csv_to_parse_result(path: str) -> Any:
    """Parse an on-disk AI exchange export CSV into a full ``ParseResult``."""
    from application.utils.external_project_parsers.parsers.master_spreadsheet_parser import (
        MasterSpreadsheetParser,
    )

    rows = load_csv_rows(path)
    if rows and is_ai_exchange_spreadsheet(rows[0]):
        rows_typed: List[Dict[str, Any]] = [dict(r) for r in rows]
        rows = normalize_rows_for_master_import(rows_typed)
    return MasterSpreadsheetParser.parse_rows(rows)


def parse_row_dicts_to_parse_result(
    rows: List[Dict[str, Any]],
) -> Any:
    """Parse already-loaded CSV rows (dicts from ``csv.DictReader``)."""
    from application.utils.external_project_parsers.parsers.master_spreadsheet_parser import (
        MasterSpreadsheetParser,
    )

    if not rows:
        return MasterSpreadsheetParser.parse_rows([])
    row0 = rows[0]
    if is_ai_exchange_spreadsheet(row0):
        rows = normalize_rows_for_master_import(copy.deepcopy(rows))
    return MasterSpreadsheetParser.parse_rows(rows)
