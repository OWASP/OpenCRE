#!/usr/bin/env python3
import os
import sys
import json
import argparse
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import create_engine, inspect, text


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
        if isinstance(parsed, list):
            # Recursively canonicalize and sort lists of dictionaries if possible
            can_list = [_json_canonical(item) for item in parsed]
            try:
                can_list.sort(key=lambda x: json.dumps(x, sort_keys=True))
            except Exception:
                pass
            return json.dumps(
                can_list, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
        return json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    if isinstance(v, list):
        can_list = [_json_canonical(item) for item in v]
        try:
            can_list.sort(key=lambda x: json.dumps(x, sort_keys=True))
        except Exception:
            pass
        return json.dumps(
            can_list, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if isinstance(v, (bytes, bytearray)):
        try:
            return _json_canonical(v.decode("utf-8"))
        except Exception:
            return str(v)
    return v


def _normalize_tags(v: Any) -> Any:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return sorted(parts)
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8")
        except Exception:
            return [str(v)]
    if not isinstance(v, str):
        return [str(v)]
    if not v:
        return []
    parts = [p.strip() for p in v.split(",")]
    return sorted([p for p in parts if p])


def _connect_db(path: str) -> Any:
    if "://" not in path:
        path = f"sqlite:///{os.path.abspath(path)}"
    else:
        # Heroku DATABASE_URL uses postgres://; SQLAlchemy expects postgresql://
        if path.startswith("postgres://"):
            path = "postgresql://" + path[len("postgres://") :]
    engine = create_engine(path)
    return engine


def _fetch_all(engine: Any, query: str, params={}) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]


def _table_column_names(engine: Any, table: str) -> Set[str]:
    """Actual DB column names (handles prod vs staging at different Alembic revisions)."""
    try:
        insp = inspect(engine)
        if table not in insp.get_table_names():
            return set()
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return set()


def _document_metadata_select(engine: Any, table: str) -> str:
    """
    ORM uses SQL column name ``document_metadata`` (see db.CRE / db.Node). Older DBs may
    omit it; some schemas use ``metadata_json`` instead.
    """
    cols = _table_column_names(engine, table)
    if "document_metadata" in cols:
        return "document_metadata"
    if "metadata_json" in cols:
        return "metadata_json AS document_metadata"
    return "NULL AS document_metadata"


def _build_id_maps(db: Any) -> Tuple[Dict[str, str], Dict[str, str]]:
    cres = _fetch_all(db, "SELECT id, external_id FROM cre")
    cre_map = {str(r["id"]): str(r["external_id"]) for r in cres if r["external_id"]}

    nodes = _fetch_all(db, "SELECT id, name, section, section_id FROM node")
    node_map = {}
    for r in nodes:
        key_parts = [
            str(r.get("name") or ""),
            str(r.get("section") or ""),
            str(r.get("section_id") or ""),
        ]
        logical_key = "::".join(key_parts)
        node_map[str(r["id"])] = logical_key

    return cre_map, node_map


def diff_databases(
    imported_db_path: str,
    upstream_db_path: str,
    log_file: str,
    summary_out: Optional[Dict[str, Any]] = None,
) -> bool:
    log_fp = open(log_file, "w")

    def log_msg(msg: str):
        print(msg)
        log_fp.write(msg + "\n")
        log_fp.flush()

    log_msg("=== Starting Parity Check ===")
    log_msg(f"Imported DB: {imported_db_path}")
    log_msg(f"Upstream DB: {upstream_db_path}")

    imported = _connect_db(imported_db_path)
    upstream = _connect_db(upstream_db_path)

    log_msg("Building Logical ID Maps...")
    i_cre_map, i_node_map = _build_id_maps(imported)
    u_cre_map, u_node_map = _build_id_maps(upstream)

    # ---- Load links (structural) using logical IDs ----
    # Fundamental CRE structure is adjacency, not edge direction or label.
    # For parity we compare undirected CRE<->CRE connectivity.
    def _normalize_cre_pair(a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    def load_internal_edges(
        db: Any, cre_map: Dict[str, str]
    ) -> Set[Tuple[str, str, str]]:
        rows = _fetch_all(
            db, 'SELECT type, "group" as group_id, cre as cre_id FROM cre_links'
        )
        edges = set()
        for r in rows:
            g_logical = cre_map.get(str(r["group_id"]))
            c_logical = cre_map.get(str(r["cre_id"]))
            if g_logical and c_logical:
                edges.add((str(r["type"]), g_logical, c_logical))
        return edges

    def to_fundamental_internal_edges(
        edges: Set[Tuple[str, str, str]]
    ) -> Set[Tuple[str, str]]:
        pairs: Set[Tuple[str, str]] = set()
        for _, src, dst in edges:
            pairs.add(_normalize_cre_pair(src, dst))
        return pairs

    def load_external_edges(
        db: Any, cre_map: Dict[str, str], node_map: Dict[str, str]
    ) -> Set[Tuple[str, str, str]]:
        rows = _fetch_all(
            db, "SELECT type, cre as cre_id, node as node_id FROM cre_node_links"
        )
        edges = set()
        for r in rows:
            c_logical = cre_map.get(str(r["cre_id"]))
            n_logical = node_map.get(str(r["node_id"]))
            if c_logical and n_logical:
                edges.add((str(r["type"]), c_logical, n_logical))
        return edges

    log_msg("Loading Internal Edges...")
    i_internal = load_internal_edges(imported, i_cre_map)
    u_internal = load_internal_edges(upstream, u_cre_map)

    log_msg("Loading External Edges...")
    i_external = load_external_edges(imported, i_cre_map, i_node_map)
    u_external = load_external_edges(upstream, u_cre_map, u_node_map)

    def _edge_to_obj(edge: Tuple[str, str, str]) -> Dict[str, str]:
        etype, src, dst = edge
        return {"type": etype, "source_cre": src, "target_cre": dst}

    def _internal_diff_breakdown(
        imported_edges: Set[Tuple[str, str, str]],
        upstream_edges: Set[Tuple[str, str, str]],
    ) -> Dict[str, Any]:
        added_raw = set(imported_edges - upstream_edges)
        removed_raw = set(upstream_edges - imported_edges)

        # 1) reversed-only: same type, same endpoints, opposite direction.
        reversed_added: Set[Tuple[str, str, str]] = set()
        reversed_removed: Set[Tuple[str, str, str]] = set()
        for etype, src, dst in sorted(added_raw):
            rev = (etype, dst, src)
            if rev in removed_raw:
                reversed_added.add((etype, src, dst))
                reversed_removed.add(rev)

        # 2) type-changed: same direction exists in both DBs, but type set changed.
        i_by_dir: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        u_by_dir: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        for etype, src, dst in imported_edges:
            i_by_dir[(src, dst)].add(etype)
        for etype, src, dst in upstream_edges:
            u_by_dir[(src, dst)].add(etype)

        type_changed = []
        type_changed_added_edges: Set[Tuple[str, str, str]] = set()
        type_changed_removed_edges: Set[Tuple[str, str, str]] = set()
        for src_dst in sorted(set(i_by_dir.keys()) & set(u_by_dir.keys())):
            i_types = i_by_dir[src_dst]
            u_types = u_by_dir[src_dst]
            if i_types != u_types:
                src, dst = src_dst
                added_types = sorted(i_types - u_types)
                removed_types = sorted(u_types - i_types)
                type_changed.append(
                    {
                        "source_cre": src,
                        "target_cre": dst,
                        "upstream_types": sorted(u_types),
                        "imported_types": sorted(i_types),
                        "added_types": added_types,
                        "removed_types": removed_types,
                    }
                )
                for t in added_types:
                    type_changed_added_edges.add((t, src, dst))
                for t in removed_types:
                    type_changed_removed_edges.add((t, src, dst))

        # 3) true add/remove: anything left after excluding reversed-only and type-changed.
        true_added = added_raw - reversed_added - type_changed_added_edges
        true_removed = removed_raw - reversed_removed - type_changed_removed_edges

        # Remodeling spotlight: imported Contains where upstream has Related (either direction) or nothing.
        contains_remodeled = []
        contains_in_imported = {(s, d) for t, s, d in imported_edges if t == "Contains"}
        upstream_by_undir: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        for t, s, d in upstream_edges:
            upstream_by_undir[_normalize_cre_pair(s, d)].add(t)
        for src, dst in sorted(contains_in_imported):
            undir = _normalize_cre_pair(src, dst)
            u_types = upstream_by_undir.get(undir, set())
            if "Contains" in u_types:
                continue
            classification = (
                "related_in_upstream" if "Related" in u_types else "absent_in_upstream"
            )
            contains_remodeled.append(
                {
                    "source_cre": src,
                    "target_cre": dst,
                    "imported_type": "Contains",
                    "upstream_types_undirected": sorted(u_types),
                    "classification": classification,
                }
            )

        return {
            "reversed_only": {
                "count": len(reversed_added),
                "added_edges": [_edge_to_obj(e) for e in sorted(reversed_added)],
                "removed_edges": [_edge_to_obj(e) for e in sorted(reversed_removed)],
            },
            "type_changed": {
                "count": len(type_changed),
                "relationships": type_changed,
            },
            "true_add_remove": {
                "added_count": len(true_added),
                "removed_count": len(true_removed),
                "added_edges": [_edge_to_obj(e) for e in sorted(true_added)],
                "removed_edges": [_edge_to_obj(e) for e in sorted(true_removed)],
            },
            "contains_remodeled": {
                "count": len(contains_remodeled),
                "relationships": contains_remodeled,
            },
        }

    internal_breakdown = _internal_diff_breakdown(i_internal, u_internal)

    i_internal_fundamental = to_fundamental_internal_edges(i_internal)
    u_internal_fundamental = to_fundamental_internal_edges(u_internal)
    added_internal_edges = sorted(i_internal_fundamental - u_internal_fundamental)
    removed_internal_edges = sorted(u_internal_fundamental - i_internal_fundamental)

    if not added_internal_edges and not removed_internal_edges:
        log_msg("Checked Internal Edges (fundamental connectivity): OK")
    else:
        log_msg(
            "Checked Internal Edges (fundamental connectivity): "
            f"NOT OK ({len(added_internal_edges)} added, {len(removed_internal_edges)} removed)"
        )
    log_msg(
        "Internal Edge Remodeling Breakdown: "
        f"reversed-only={internal_breakdown['reversed_only']['count']}, "
        f"type-changed={internal_breakdown['type_changed']['count']}, "
        f"true-added={internal_breakdown['true_add_remove']['added_count']}, "
        f"true-removed={internal_breakdown['true_add_remove']['removed_count']}, "
        f"contains-remodeled={internal_breakdown['contains_remodeled']['count']}"
    )

    added_external_edges = sorted(i_external - u_external)
    removed_external_edges = sorted(u_external - i_external)

    if not added_external_edges and not removed_external_edges:
        log_msg("Checked External Edges: OK")
    else:
        log_msg(
            f"Checked External Edges: NOT OK ({len(added_external_edges)} added, {len(removed_external_edges)} removed)"
        )

    structural_diffs = bool(
        added_internal_edges
        or removed_internal_edges
        or added_external_edges
        or removed_external_edges
    )

    # ---- Content diffs using logical IDs ----
    def load_cres(db: Any) -> Dict[str, Dict[str, Any]]:
        cre_meta = _document_metadata_select(db, "cre")
        rows = _fetch_all(
            db,
            f"SELECT name, external_id, description, tags, {cre_meta} FROM cre",
        )
        cres = {}
        for r in rows:
            if not r["external_id"]:
                continue
            cres[str(r["external_id"])] = {
                "name": r["name"],
                "external_id": r["external_id"],
                "description": r["description"],
                "tags": _normalize_tags(r["tags"]),
                "document_metadata": _json_canonical(r["document_metadata"]),
            }
        return cres

    def load_nodes(db: Any) -> Dict[str, Dict[str, Any]]:
        node_meta = _document_metadata_select(db, "node")
        rows = _fetch_all(
            db,
            f"SELECT name, section, subsection, version, section_id, description, tags, ntype, link, {node_meta} FROM node",
        )
        nodes = {}
        for r in rows:
            key_parts = [
                str(r.get("name") or ""),
                str(r.get("section") or ""),
                str(r.get("section_id") or ""),
            ]
            logical_key = "::".join(key_parts)
            nodes[logical_key] = {
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
        return nodes

    log_msg("Loading CREs...")
    i_cre = load_cres(imported)
    u_cre = load_cres(upstream)

    added_cres = sorted(set(i_cre.keys()) - set(u_cre.keys()))
    removed_cres = sorted(set(u_cre.keys()) - set(i_cre.keys()))
    if not added_cres and not removed_cres:
        log_msg("Checked CRE Existence: OK")
    else:
        log_msg(
            f"Checked CRE Existence: NOT OK ({len(added_cres)} added, {len(removed_cres)} removed)"
        )

    log_msg("Loading Nodes...")
    i_node = load_nodes(imported)
    u_node = load_nodes(upstream)

    added_nodes = sorted(set(i_node.keys()) - set(u_node.keys()))
    removed_nodes = sorted(set(u_node.keys()) - set(i_node.keys()))
    if not added_nodes and not removed_nodes:
        log_msg("Checked Node Existence: OK")
    else:
        log_msg(
            f"Checked Node Existence: NOT OK ({len(added_nodes)} added, {len(removed_nodes)} removed)"
        )

    # ---- Gap Analysis Comparison ----
    def load_gap_analysis(db: Any) -> Dict[str, str]:
        rows = _fetch_all(db, "SELECT cache_key, ga_object FROM gap_analysis_results")
        # Normalize cache keys: "DSOMM >> CWE" might be "DevSecOps Maturity Model (DSOMM) >> CWE" upstream
        # The true standard name is the first part before >> and the second part after >>.
        # However, mapping arbitrary names back and forth is hard. We will compare what matches.
        return {str(r["cache_key"]).strip(): r["ga_object"] for r in rows}

    log_msg("Loading Gap Analysis Results...")
    i_ga = load_gap_analysis(imported)
    u_ga = load_gap_analysis(upstream)

    # Since imported standard names might differ from upstream (e.g. 'DSOMM' vs 'DevSecOps Maturity Model (DSOMM)'),
    # we'll do our best to map them if possible, otherwise we just compare intersection
    # To keep it simple and robust, we only warn on the exact string intersection

    intersect_ga = set(i_ga.keys()) & set(u_ga.keys())
    added_ga = sorted(set(i_ga.keys()) - set(u_ga.keys()))
    removed_ga = sorted(set(u_ga.keys()) - set(i_ga.keys()))

    from application.utils.gap_analysis import primary_gap_analysis_payload_is_material

    def _material_primary_keys(ga_map: Dict[str, str]) -> set[str]:
        return {
            k
            for k, v in ga_map.items()
            if "->" not in k and primary_gap_analysis_payload_is_material(str(v or ""))
        }

    i_ga_mat = _material_primary_keys(i_ga)
    u_ga_mat = _material_primary_keys(u_ga)
    added_ga_mat = sorted(i_ga_mat - u_ga_mat)
    removed_ga_mat = sorted(u_ga_mat - i_ga_mat)

    if not added_ga and not removed_ga:
        log_msg("Checked Gap Analysis cache keys (any row): OK")
    else:
        log_msg(
            f"Checked Gap Analysis cache keys (any row): NOT OK ({len(added_ga)} added, {len(removed_ga)} removed)"
        )
    log_msg(
        f"Material primary GA caches: imported={len(i_ga_mat)}, upstream={len(u_ga_mat)} "
        f"(symmetric diff {len(added_ga_mat) + len(removed_ga_mat)} keys)"
    )
    if added_ga_mat or removed_ga_mat:
        log_msg(
            f"Material primary GA key diff detail: only_in_imported={len(added_ga_mat)}, "
            f"only_in_upstream={len(removed_ga_mat)}"
        )

    content_diffs = []

    # Gap analysis diffs
    log_msg("Comparing Gap Analysis Content (informational only)...")
    ga_diff_count = 0
    for cache_key in sorted(intersect_ga):
        i_obj = _json_canonical(i_ga[cache_key])
        u_obj = _json_canonical(u_ga[cache_key])
        if i_obj != u_obj:
            ga_diff_count += 1
            content_diffs.append(
                {
                    "type": "GapAnalysis",
                    "cache_key": cache_key,
                    "diffs": {"upstream": u_obj, "imported": i_obj},
                }
            )

    if ga_diff_count == 0:
        log_msg("Checked Gap Analysis Content: OK")
    else:
        log_msg(
            f"Checked Gap Analysis Content: INFO ({ga_diff_count} diffs found; ignored)"
        )

    log_msg("Comparing CRE Properties (informational only)...")
    cre_diff_count = 0
    for cre_id in sorted(set(i_cre.keys()) & set(u_cre.keys())):
        i_c = i_cre[cre_id]
        u_c = u_cre[cre_id]
        diffs = {
            f: {"upstream": u_c.get(f), "imported": i_c.get(f)}
            for f in i_c.keys()
            if _json_canonical(i_c.get(f)) != _json_canonical(u_c.get(f))
        }
        if diffs:
            cre_diff_count += 1
            content_diffs.append({"type": "CRE", "id": cre_id, "diffs": diffs})

    if cre_diff_count == 0:
        log_msg("Checked CRE Properties: OK")
    else:
        log_msg(f"Checked CRE Properties: INFO ({cre_diff_count} diffs found; ignored)")

    log_msg("Comparing Node Properties (informational only)...")
    node_diff_count = 0
    for node_id in sorted(set(i_node.keys()) & set(u_node.keys())):
        i_n = i_node[node_id]
        u_n = u_node[node_id]
        diffs = {
            f: {"upstream": u_n.get(f), "imported": i_n.get(f)}
            for f in i_n.keys()
            if _json_canonical(i_n.get(f)) != _json_canonical(u_n.get(f))
        }
        if diffs:
            node_diff_count += 1
            content_diffs.append({"type": "Node", "id": node_id, "diffs": diffs})

    if node_diff_count == 0:
        log_msg("Checked Node Properties: OK")
    else:
        log_msg(
            f"Checked Node Properties: INFO ({node_diff_count} diffs found; ignored)"
        )

    if added_cres or removed_cres or added_nodes or removed_nodes:
        structural_diffs = True

    log_msg("Writing detailed JSON output to log file...")
    log_fp.write("\n=== Content Diffs JSON ===\n")
    log_fp.write(json.dumps(content_diffs, indent=2))
    log_fp.write("\n=== Added/Removed Nodes/CREs JSON ===\n")
    log_fp.write(
        json.dumps(
            {
                "added_cres": added_cres,
                "removed_cres": removed_cres,
                "added_nodes": added_nodes,
                "removed_nodes": removed_nodes,
                "added_ga": added_ga,
                "removed_ga": removed_ga,
            },
            indent=2,
        )
    )
    log_fp.write("\n=== Internal Edge Remodeling Breakdown JSON ===\n")
    log_fp.write(json.dumps(internal_breakdown, indent=2))
    log_fp.write("\n")

    if summary_out is not None:
        summary_out.clear()
        summary_out.update(
            {
                "imported_db": imported_db_path,
                "upstream_db": upstream_db_path,
                "structural_diffs": structural_diffs,
                "internal_edge_remodeling": internal_breakdown,
                "fundamental_cre_connectivity": {
                    "pairs_only_in_imported": added_internal_edges[:500],
                    "pairs_only_in_upstream": removed_internal_edges[:500],
                    "added_count": len(added_internal_edges),
                    "removed_count": len(removed_internal_edges),
                },
                "cre_node_edges": {
                    "added_external": added_external_edges[:500],
                    "removed_external": removed_external_edges[:500],
                    "added_count": len(added_external_edges),
                    "removed_count": len(removed_external_edges),
                },
                "cre_external_ids": {
                    "only_in_imported": added_cres[:500],
                    "only_in_upstream": removed_cres[:500],
                },
                "node_logical_keys": {
                    "only_in_imported": added_nodes[:500],
                    "only_in_upstream": removed_nodes[:500],
                },
                "gap_analysis_keys": {
                    "only_in_imported": added_ga[:200],
                    "only_in_upstream": removed_ga[:200],
                    "material_only_in_imported": added_ga_mat[:200],
                    "material_only_in_upstream": removed_ga_mat[:200],
                },
                "property_and_payload_diff_counts": {
                    "cre_rows_with_field_diffs": cre_diff_count,
                    "node_rows_with_field_diffs": node_diff_count,
                    "gap_analysis_payload_mismatches": ga_diff_count,
                },
                "content_diffs_sample": content_diffs[:40],
            }
        )

    # Content/tag/property deltas are informational for this benchmark.
    # Fail only on fundamental structure differences.
    if structural_diffs:
        log_msg("CRITICAL: Fundamental structural diffs found!")
        if structural_diffs:
            log_msg(f"Internal Edges Added: {len(added_internal_edges)}")
            log_msg(f"Internal Edges Removed: {len(removed_internal_edges)}")
            log_msg(f"External Edges Added: {len(added_external_edges)}")
            log_msg(f"External Edges Removed: {len(removed_external_edges)}")
            log_msg(f"Missing CREs: {len(removed_cres)}")
            log_msg(f"Missing Nodes: {len(removed_nodes)}")
            log_msg(f"Extra CREs: {len(added_cres)}")
            log_msg(f"Extra Nodes: {len(added_nodes)}")
        log_fp.close()
        return False

    if ga_diff_count > 0:
        log_msg(f"Info: Gap Analysis Payload Content Mismatches: {ga_diff_count}")
    if cre_diff_count > 0:
        log_msg(f"Info: CRE Property Mismatches: {cre_diff_count}")
    if node_diff_count > 0:
        log_msg(f"Info: Node Property Mismatches: {node_diff_count}")
    if added_ga:
        log_msg(f"Info: Extra Gap Analysis cache keys locally: {len(added_ga)}")
    if removed_ga:
        log_msg(f"Info: Missing Gap Analysis cache keys locally: {len(removed_ga)}")

    log_msg(
        f"Success! No fundamental structural diffs found. Detailed output is in {log_file}"
    )
    log_fp.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="Benchmark import parity.")
    parser.add_argument(
        "--upstream-db", required=True, help="Path to upstream synced DB"
    )
    parser.add_argument("--imported-db", required=True, help="Path to imported DB")
    parser.add_argument(
        "--log-file", default="content-diffs.log", help="Log file for content diffs"
    )
    args = parser.parse_args()

    if not diff_databases(args.imported_db, args.upstream_db, args.log_file):
        sys.exit(1)


if __name__ == "__main__":
    main()
