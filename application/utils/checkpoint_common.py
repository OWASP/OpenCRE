"""
Shared helpers for checkpoint scripts (spreadsheet import, upstream sync, diffs).

Used by scripts/checkpoint_step2b_verify.py and scripts/checkpoint_step3_grand_verify.py.
"""

from __future__ import annotations

import ast
import difflib
import importlib
import json
import os
import pkgutil
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Type

try:
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:

    def load_dotenv(*args: Any, **kwargs: Any) -> None:
        pass


def repo_root() -> str:
    """OpenCRE repository root (parent of ``application/``)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _fetch_all(
    conn: sqlite3.Connection, sql: str, params: tuple = ()
) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _connect_sqlite(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path)


def _json_canonical(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        if not v:
            return ""
        try:
            parsed = json.loads(v)
        except Exception:
            return v
        return json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if isinstance(v, (bytes, bytearray)):
        try:
            return _json_canonical(v.decode("utf-8"))
        except Exception:
            return str(v)
    return v


def _normalize_tags(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return sorted(parts)
    if isinstance(v, (bytes, bytearray)):
        v = v.decode("utf-8") if v else ""
    if not isinstance(v, str):
        return [str(v)]
    parts = [p.strip() for p in v.split(",") if p.strip()]
    return sorted(parts)


def _extract_pair_from_ga_key(cache_key: str) -> Optional[Tuple[str, str]]:
    if " >> " not in cache_key:
        return None
    left, right = cache_key.split(" >> ", 1)
    if "->" in right:
        right = right.split("->", 1)[0]
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return (left, right)


def load_gap_analysis(db_path: str) -> Dict[str, Any]:
    """Load gap_analysis_results as canonicalized JSON by cache_key."""
    with _connect_sqlite(db_path) as conn:
        rows = _fetch_all(
            conn,
            """
            SELECT cache_key, ga_object
            FROM gap_analysis_results
            """,
        )
    out: Dict[str, Any] = {}
    for r in rows:
        key = str(r.get("cache_key") or "")
        if not key:
            continue
        out[key] = _json_canonical(r.get("ga_object"))
    return out


def scoped_ga_diff(
    import_ga: Dict[str, Any],
    golden_ga: Dict[str, Any],
    import_resource_names: Set[str],
) -> Tuple[List[str], List[str]]:
    """
    Compare GA cache only for scope where both pair resources are present in import DB.
    Returns (missing_keys, mismatched_keys).
    """
    scope_keys: Set[str] = set()
    for key in set(import_ga.keys()) | set(golden_ga.keys()):
        pair = _extract_pair_from_ga_key(key)
        if not pair:
            continue
        if pair[0] in import_resource_names and pair[1] in import_resource_names:
            scope_keys.add(key)

    missing: List[str] = []
    mismatched: List[str] = []
    for key in sorted(scope_keys):
        in_import = key in import_ga
        in_golden = key in golden_ga
        if not in_import or not in_golden:
            missing.append(key)
            continue
        if import_ga[key] != golden_ga[key]:
            mismatched.append(key)
    return missing, mismatched


def load_standards(db_path: str) -> Dict[str, Dict[str, Any]]:
    """Load all nodes (standards) from DB keyed by (name, section, section_id)."""
    with _connect_sqlite(db_path) as conn:
        rows = _fetch_all(
            conn,
            """
            SELECT id, name, section, subsection, version, section_id,
                   description, tags, ntype, link, document_metadata
            FROM node
            """,
        )
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = (r["name"] or "", r["section"] or "", r["section_id"] or "")
        out[str(key)] = {
            "id": r["id"],
            "name": r["name"],
            "section": r["section"],
            "subsection": r["subsection"],
            "version": r["version"],
            "section_id": r["section_id"],
            "description": r["description"],
            "tags": _normalize_tags(r["tags"]),
            "ntype": r["ntype"],
            "link": r["link"],
            "document_metadata": _json_canonical(r["document_metadata"]),
        }
    return out


def diff_standards(
    golden: Dict[str, Dict[str, Any]],
    import_db: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], List[str], List[Tuple[str, Dict[str, Any]]]]:
    """
    Compare standards: golden (reference) vs import_db (our import).
    Returns (only_in_golden, only_in_import, changed).
    """
    golden_keys = set(golden.keys())
    import_keys = set(import_db.keys())

    only_in_golden = sorted(golden_keys - import_keys)
    only_in_import = sorted(import_keys - golden_keys)

    changed: List[Tuple[str, Dict[str, Any]]] = []
    for key in sorted(golden_keys & import_keys):
        g = golden[key]
        i = import_db[key]
        diffs: Dict[str, Any] = {}
        for field in [
            "name",
            "section",
            "subsection",
            "version",
            "section_id",
            "description",
            "tags",
            "ntype",
            "link",
            "document_metadata",
        ]:
            if _json_canonical(g.get(field)) != _json_canonical(i.get(field)):
                diffs[field] = {"golden": g.get(field), "import": i.get(field)}
        if diffs:
            changed.append((str(key), diffs))

    return (only_in_golden, only_in_import, changed)


def _parse_standard_key(key: str) -> Optional[Tuple[str, str, str]]:
    try:
        parsed = ast.literal_eval(key)
    except Exception:
        return None
    if (
        isinstance(parsed, tuple)
        and len(parsed) == 3
        and all(isinstance(x, str) for x in parsed)
    ):
        return (parsed[0], parsed[1], parsed[2])
    return None


def suggest_upstream_candidates(
    missing_in_upstream: List[str],
    golden_standards: Dict[str, Dict[str, Any]],
) -> List[str]:
    """
    For each import-only standard key, suggest likely upstream candidates:
    - same family + exact section_id (if available)
    - otherwise top fuzzy section matches within same family
    """
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for g in golden_standards.values():
        fam = str(g.get("name") or "")
        by_family.setdefault(fam, []).append(g)

    out: List[str] = []
    for raw_key in missing_in_upstream:
        parsed = _parse_standard_key(raw_key)
        if not parsed:
            out.append(f"{raw_key} -> could not parse key")
            continue
        fam, section, section_id = parsed
        family_rows = by_family.get(fam, [])
        if not family_rows:
            out.append(f"{raw_key} -> no upstream entries for family '{fam}'")
            continue

        # Strong signal: exact section_id within same family.
        sid_matches = [
            r
            for r in family_rows
            if str(r.get("section_id") or "") == section_id and section_id
        ]
        if sid_matches:
            row = sid_matches[0]
            out.append(
                f"{raw_key} -> same section_id in upstream: "
                f"({fam!r}, {str(row.get('section') or '')!r}, {section_id!r})"
            )
            continue

        # Fallback: fuzzy section text matches within same family.
        upstream_sections = [
            str(r.get("section") or "")
            for r in family_rows
            if str(r.get("section") or "")
        ]
        if not upstream_sections:
            out.append(
                f"{raw_key} -> family exists upstream but no section text candidates"
            )
            continue
        close = difflib.get_close_matches(section, upstream_sections, n=3, cutoff=0.4)
        if close:
            out.append(f"{raw_key} -> closest upstream sections: {close}")
        else:
            out.append(f"{raw_key} -> no close upstream section text match")
    return out


def run_import_with_ga(db_path: str, core_spreadsheet_url: str) -> None:
    """Import main spreadsheet into db_path with GA, no embeddings."""
    os.environ["CRE_NO_GEN_EMBEDDINGS"] = "1"
    os.environ.pop("CRE_NO_CALCULATE_GAP_ANALYSIS", None)

    sys.path.insert(0, repo_root())
    from application import sqla
    from application.cmd import cre_main
    from application.prompt_client import prompt_client
    from application.utils import spreadsheet as sheet_utils

    print(f"Importing main spreadsheet: {core_spreadsheet_url}")
    os.environ.setdefault("OpenCRE_gspread_Auth", "service_account")

    spreadsheet = sheet_utils.read_spreadsheet(
        url=core_spreadsheet_url,
        alias="core spreadsheet",
        validate=False,
    )

    core_rows: Optional[List[Dict[str, Any]]] = None
    for _, contents in spreadsheet.items():
        if contents and isinstance(contents, list) and contents[0]:
            if any(str(k).startswith("CRE hierarchy") for k in contents[0].keys()):
                core_rows = contents
                break

    if not core_rows:
        raise RuntimeError("Could not find a worksheet with 'CRE hierarchy' columns.")

    collection = cre_main.db_connect(path=db_path)
    sqla.create_all()

    # Do not call parse_hierarchical_export_format() on core_rows before this:
    # _parse_cre_graph_and_rows mutates each row dict in place (pops CRE ID, tags,
    # hierarchy columns, etc.). A second parse on the same list would skip rows and
    # drop spreadsheet-backed standards (ASVS, CWE, …). Full CRE + standards import
    # happens inside parse_standards_from_spreadsheeet → MasterSpreadsheetParser.parse_rows.
    prompt_handler = prompt_client.PromptHandler(database=collection)
    cre_main.parse_standards_from_spreadsheeet(
        core_rows,
        cache_location=db_path,
        prompt_handler=prompt_handler,
    )
    print("Import complete (with GA).")


def run_upstream_download(db_path: str) -> None:
    """
    Populate golden DB using the supported CLI entrypoint (same as ``python cre.py --upstream_sync``).
    Checkpoint-only: create schema on the empty file, then shell out to cre.py.
    """
    root = repo_root()
    print("Downloading upstream golden dataset (cre.py --upstream_sync)...")

    sys.path.insert(0, root)
    from application import sqla
    from application.cmd import cre_main

    cre_main.db_connect(path=db_path)
    sqla.create_all()

    env = os.environ.copy()
    env.setdefault("NO_LOAD_GRAPH_DB", "1")
    env.setdefault("CRE_NO_NEO4J", "1")

    cre_py = os.path.join(root, "cre.py")
    subprocess.run(
        [
            sys.executable,
            cre_py,
            "--upstream_sync",
            "--cache_file",
            os.path.abspath(db_path),
        ],
        cwd=root,
        env=env,
        check=True,
    )
    print("Upstream download complete.")


def load_all_parser_modules() -> None:
    """Import every module under ``external_project_parsers.parsers`` so ParserInterface subclasses exist."""
    import application.utils.external_project_parsers.parsers as parsers_pkg

    for info in pkgutil.iter_modules(parsers_pkg.__path__):
        importlib.import_module(f"{parsers_pkg.__name__}.{info.name}")


MASTER_PARSER_NAME = "Master Mapping Spreadsheet"


def external_parser_classes() -> List[Type[Any]]:
    """
    Return ParserInterface subclasses except the master spreadsheet parser, sorted by ``name``.
    """
    load_all_parser_modules()
    from application.utils.external_project_parsers import base_parser_defs

    out: List[Type[Any]] = []
    for cls in base_parser_defs.ParserInterface.__subclasses__():
        if getattr(cls, "name", None) == MASTER_PARSER_NAME:
            continue
        out.append(cls)
    return sorted(out, key=lambda c: str(getattr(c, "name", c.__name__)))


def sqlite_metrics(db_path: str) -> Dict[str, int]:
    """Lightweight counts for checkpoint assertions."""
    with _connect_sqlite(db_path) as conn:
        node_n = conn.execute("SELECT COUNT(*) FROM node").fetchone()[0]
        try:
            cre_n = conn.execute("SELECT COUNT(*) FROM cre").fetchone()[0]
        except sqlite3.OperationalError:
            cre_n = -1
        ga_n = conn.execute("SELECT COUNT(*) FROM gap_analysis_results").fetchone()[0]
    standards = load_standards(db_path)
    return {
        "node_count": int(node_n),
        "cre_count": int(cre_n),
        "gap_analysis_rows": int(ga_n),
        "standards_keys": len(standards),
    }


def metric_bounds_errors(
    metrics: Dict[str, int],
    bounds: Optional[Dict[str, Any]],
    label: str,
) -> List[str]:
    """Return human-readable errors when ``metrics`` violate ``*_min`` / ``*_max`` in ``bounds``."""
    if not bounds:
        return []
    errs: List[str] = []
    for key, val in metrics.items():
        lo = bounds.get(f"{key}_min")
        hi = bounds.get(f"{key}_max")
        if lo is not None and val < int(lo):
            errs.append(f"{label}: {key}={val} < min {lo}")
        if hi is not None and val > int(hi):
            errs.append(f"{label}: {key}={val} > max {hi}")
    return errs


def final_diff_bounds_errors(
    *,
    only_golden: int,
    only_import: int,
    changed: int,
    scoped_ga_missing: int,
    scoped_ga_mismatch: int,
    bounds: Optional[Dict[str, Any]],
    label: str,
) -> List[str]:
    """Validate summary diff counts against optional ``*_min`` / ``*_max`` in ``bounds``."""
    if not bounds:
        return []
    mapping = {
        "only_golden": only_golden,
        "only_import": only_import,
        "changed": changed,
        "scoped_ga_missing": scoped_ga_missing,
        "scoped_ga_mismatch": scoped_ga_mismatch,
    }
    errs: List[str] = []
    for key, val in mapping.items():
        lo = bounds.get(f"{key}_min")
        hi = bounds.get(f"{key}_max")
        if lo is not None and val < int(lo):
            errs.append(f"{label}: {key}={val} < min {lo}")
        if hi is not None and val > int(hi):
            errs.append(f"{label}: {key}={val} > max {hi}")
    return errs
