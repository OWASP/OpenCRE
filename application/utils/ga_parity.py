"""
Helpers to compare Postgres gap_analysis cache rows with Neo4j-computed GA.

Used by ``scripts/verify_ga_postgres_neo_parity.py`` and unit tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Sequence, Tuple

if TYPE_CHECKING:
    from application.database import db as db_mod


def directed_eligible_pairs(standard_names: Sequence[str]) -> List[Tuple[str, str]]:
    """All ordered pairs (A, B) with A != B from a sorted unique list."""
    stds = sorted({str(s).strip() for s in standard_names if str(s).strip()})
    out: List[Tuple[str, str]] = []
    for a in stds:
        for b in stds:
            if a != b:
                out.append((a, b))
    return out


def pg_neo_material_agree(pg_material: bool, neo_formatted_path_count: int) -> bool:
    """
    True when SQL materiality matches Neo formatted-path count.

    We treat a primary GA row as "material" iff ``result`` is a non-empty dict/list.
    Neo side uses the same formatter as ``NEO_DB.gap_analysis`` (length of parsed_paths).
    """
    neo_material = neo_formatted_path_count > 0
    return pg_material == neo_material


def count_empty_primary_gap_rows(session: Any, gap_model: Any) -> int:
    """Primary rows (no subresource ``->``) whose ``ga_object`` is not material."""
    from sqlalchemy import not_

    from application.utils.gap_analysis import primary_gap_analysis_payload_is_material

    rows = (
        session.query(gap_model.ga_object)
        .filter(not_(gap_model.cache_key.like("% >> %->%")))
        .all()
    )
    n = 0
    for (payload,) in rows:
        if not primary_gap_analysis_payload_is_material(str(payload or "")):
            n += 1
    return n


def ga_matrix_standard_names(collection: "db_mod.Node_collection") -> List[str]:
    """
    Standard names included in the GA matrix (same rule as ``/rest/v1/ga_standards``).
    """
    from application.cmd import cre_main

    standards = sorted(set(collection.standards()))
    return sorted(
        s for s in standards if cre_main.resource_name_ga_eligible_in_db(collection, s)
    )
