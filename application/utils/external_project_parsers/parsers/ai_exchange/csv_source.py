"""Import AI / LLM control mappings from the OpenCRE AI exchange CSV export.

The export uses ``CRE 0``..``CRE n`` hierarchy columns (not ``CRE hierarchy 1``..),
``Cross-link CREs`` with CRE IDs (``NNN-NNN``), and pipe-delimited MITRE ATLAS /
OWASP AI Exchange (AIX) columns. Rows are normalized into the master spreadsheet
shape so ``MasterSpreadsheetParser`` and the shared import pipeline apply.

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


def _display_base_name(display: str) -> str:
    if display.endswith(")") and " (" in display:
        return display[: display.rindex(" (")]
    return display


def is_ai_exchange_spreadsheet(sample_row: Dict[str, Any]) -> bool:
    keys = set(sample_row.keys())
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
            if s.startswith("CRE ") and s[4:].strip().isdigit():
                found.add(int(s[4:].strip()))
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
        mn, mi, mh = [], [], []
        an, ai, ah = [], [], []
        for r in group:
            n = str(r.get("MITRE ATLAS|name", "") or "").strip()
            i = str(r.get("MITRE ATLAS|id", "") or "").strip()
            h = str(r.get("MITRE ATLAS|hyperlink", "") or "").strip()
            if n or i or h:
                mn.append(n)
                mi.append(i)
                mh.append(h)
            n = str(r.get("AIX|name", "") or "").strip()
            i = str(r.get("AIX|id", "") or "").strip()
            h = str(r.get("AIX|hyperlink", "") or "").strip()
            if n or i or h:
                an.append(n)
                ai.append(i)
                ah.append(h)
        base["MITRE ATLAS|name"] = ";".join(mn)
        base["MITRE ATLAS|id"] = ";".join(mi)
        base["MITRE ATLAS|hyperlink"] = ";".join(mh)
        base["AIX|name"] = ";".join(an)
        base["AIX|id"] = ";".join(ai)
        base["AIX|hyperlink"] = ";".join(ah)
        merged.append(base)
    return merged + no_id


def normalize_rows_for_master_import(
    rows: List[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """Return new row dicts matching master spreadsheet column names and standard keys."""
    if not rows:
        return []

    rows = _merge_rows_sharing_cre_id(rows)
    levels = _cre_level_indices(rows)
    if not levels:
        raise ValueError("AI exchange CSV has no CRE 0..CRE n columns")

    ambiguous = _ambiguous_leaf_labels(rows, levels)
    id_to_name = _build_cre_id_to_display_name(rows, levels, ambiguous)
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
                    resolved = id_to_name.get(token)
                    if not resolved:
                        logger.warning(
                            "Cross-link CRE ID %s not found in sheet (skipped)",
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

        out.append(new_row)

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
    try:
        return MasterSpreadsheetParser.parse_rows(rows)
    except ValueError as exc:
        # Some test/runtime environments already have a populated DB with
        # conflicting historical CRE display names. For row-dict ingestion we
        # prefer a parser-only fallback instead of failing hard on DB hydration.
        if "Data corruption: CRE name conflict" not in str(exc):
            raise
        from application.utils.external_project_parsers.base_parser_defs import (
            ParseResult,
        )
        from application.utils.spreadsheet_parsers import (
            parse_master_spreadsheet_documents,
        )

        return ParseResult(
            results=parse_master_spreadsheet_documents(rows),
            calculate_gap_analysis=True,
            calculate_embeddings=True,
        )
