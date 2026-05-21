import hashlib
import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple


Snapshot = Dict[str, List[Tuple[Any, ...]]]

REQUIRED_TABLES = ("cre", "node", "cre_links", "cre_node_links")


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _cre_key(row: Mapping[str, Any]) -> Tuple[str, ...]:
    return (
        _normalize(row.get("external_id")),
        _normalize(row.get("name")),
        _normalize(row.get("description")),
        _normalize(row.get("tags")),
    )


def _node_key(row: Mapping[str, Any]) -> Tuple[str, ...]:
    return (
        _normalize(row.get("name")),
        _normalize(row.get("section")),
        _normalize(row.get("subsection")),
        _normalize(row.get("section_id")),
        _normalize(row.get("version")),
        _normalize(row.get("description")),
        _normalize(row.get("tags")),
        _normalize(row.get("ntype")),
        _normalize(row.get("link")),
    )


def _validate_table_presence(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    missing = [table for table in REQUIRED_TABLES if table not in rows]
    if missing:
        raise ValueError(f"Missing required tables: {missing}")


def build_canonical_snapshot(
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Snapshot:
    _validate_table_presence(rows)

    cre_id_to_key: Dict[str, Tuple[str, ...]] = {}
    node_id_to_key: Dict[str, Tuple[str, ...]] = {}

    cre_rows: List[Tuple[str, ...]] = []
    node_rows: List[Tuple[str, ...]] = []
    cre_links_rows: List[Tuple[Any, ...]] = []
    cre_node_links_rows: List[Tuple[Any, ...]] = []

    for row in rows["cre"]:
        key = _cre_key(row)
        row_id = _normalize(row.get("id"))
        cre_id_to_key[row_id] = key
        cre_rows.append(key)

    for row in rows["node"]:
        key = _node_key(row)
        row_id = _normalize(row.get("id"))
        node_id_to_key[row_id] = key
        node_rows.append(key)

    for row in rows["cre_links"]:
        group_id = _normalize(row.get("group"))
        cre_id = _normalize(row.get("cre"))
        if group_id not in cre_id_to_key or cre_id not in cre_id_to_key:
            raise ValueError(
                f"cre_links contains unknown IDs: group={group_id}, cre={cre_id}"
            )
        cre_links_rows.append(
            (
                _normalize(row.get("type")),
                cre_id_to_key[group_id],
                cre_id_to_key[cre_id],
            )
        )

    for row in rows["cre_node_links"]:
        cre_id = _normalize(row.get("cre"))
        node_id = _normalize(row.get("node"))
        if cre_id not in cre_id_to_key or node_id not in node_id_to_key:
            raise ValueError(
                f"cre_node_links contains unknown IDs: cre={cre_id}, node={node_id}"
            )
        cre_node_links_rows.append(
            (
                _normalize(row.get("type")),
                cre_id_to_key[cre_id],
                node_id_to_key[node_id],
            )
        )

    snapshot: Snapshot = {
        "cre": sorted(cre_rows),
        "node": sorted(node_rows),
        "cre_links": sorted(cre_links_rows),
        "cre_node_links": sorted(cre_node_links_rows),
    }
    return snapshot


def snapshot_digest(snapshot: Snapshot) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_diff(expected: Snapshot, actual: Snapshot) -> Dict[str, Dict[str, Any]]:
    diff: Dict[str, Dict[str, Any]] = {}
    for table in REQUIRED_TABLES:
        missing = sorted(set(expected.get(table, [])) - set(actual.get(table, [])))
        extra = sorted(set(actual.get(table, [])) - set(expected.get(table, [])))
        if missing or extra:
            diff[table] = {
                "missing_count": len(missing),
                "extra_count": len(extra),
                "missing_sample": missing[:3],
                "extra_sample": extra[:3],
            }
    return diff
