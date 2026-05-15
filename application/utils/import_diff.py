"""
Module C – baseline diff scaffolding for standards (Step 6) and
structured change-set model (Step 7).

Provides helpers to compare two standard snapshots and produce a structured diff,
plus a change-set vocabulary for add/remove/modify operations.
"""

import json
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Set, Tuple

from application.defs import cre_defs as defs


def stable_json(value: Any) -> str:
    """Canonical JSON representation for stable hashing/diffing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_loads(value: str) -> Any:
    return json.loads(value)


@dataclass
class StandardDiff:
    """Result of diffing two standard snapshots."""

    added: List[defs.Standard] = field(default_factory=list)
    removed: List[defs.Standard] = field(default_factory=list)
    modified: List[Tuple[defs.Standard, defs.Standard]] = field(default_factory=list)


def _standard_key(std: defs.Standard) -> Tuple[str, str, str]:
    """Identity key for a standard entry: (name, section, sectionID)."""
    return (
        std.name or "",
        getattr(std, "section", "") or "",
        getattr(std, "sectionID", "") or "",
    )


def _standard_content_hash(std: defs.Standard) -> str:
    """Serializable content for equality check."""
    return str(
        {
            "name": std.name,
            "section": getattr(std, "section", ""),
            "subsection": getattr(std, "subsection", ""),
            "sectionID": getattr(std, "sectionID", ""),
            "description": getattr(std, "description", ""),
        }
    )


def standard_snapshot_map(
    standards: List[defs.Standard],
) -> Dict[Tuple[str, str, str], str]:
    """Stable snapshot map of standard identity -> content hash."""
    return {_standard_key(s): _standard_content_hash(s) for s in standards}


def diff_standards(
    previous: List[defs.Standard],
    new: List[defs.Standard],
) -> StandardDiff:
    """
    Compare two standard snapshots. Returns added, removed, and modified entries.

    Identity is (name, section, sectionID). Modified = same key, different content.
    """
    prev_map: Dict[Tuple[str, str, str], defs.Standard] = {
        _standard_key(s): s for s in previous
    }
    new_map: Dict[Tuple[str, str, str], defs.Standard] = {
        _standard_key(s): s for s in new
    }

    prev_keys: Set[Tuple[str, str, str]] = set(prev_map.keys())
    new_keys: Set[Tuple[str, str, str]] = set(new_map.keys())

    added = [new_map[k] for k in (new_keys - prev_keys)]
    removed = [prev_map[k] for k in (prev_keys - new_keys)]
    modified = [
        (prev_map[k], new_map[k])
        for k in (prev_keys & new_keys)
        if _standard_content_hash(prev_map[k]) != _standard_content_hash(new_map[k])
    ]

    return StandardDiff(added=added, removed=removed, modified=modified)


# Step 7: Structured change-set vocabulary


@dataclass
class AddControl:
    """A control/standard entry was added."""

    op: str = "add_control"
    key: Tuple[str, str, str] = ("", "", "")
    document: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemoveControl:
    """A control/standard entry was removed."""

    op: str = "remove_control"
    key: Tuple[str, str, str] = ("", "", "")
    document: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModifyControl:
    """A control/standard entry was modified."""

    op: str = "modify_control"
    key: Tuple[str, str, str] = ("", "", "")
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)


ChangeSetOp = AddControl | RemoveControl | ModifyControl


def diff_to_change_set(diff: StandardDiff) -> List[ChangeSetOp]:
    """Convert StandardDiff to structured change-set operations."""
    ops: List[ChangeSetOp] = []
    for std in diff.added:
        ops.append(
            AddControl(
                key=_standard_key(std),
                document=_standard_to_dict(std),
            )
        )
    for std in diff.removed:
        ops.append(
            RemoveControl(
                key=_standard_key(std),
                document=_standard_to_dict(std),
            )
        )
    for prev, new in diff.modified:
        ops.append(
            ModifyControl(
                key=_standard_key(prev),
                before=_standard_to_dict(prev),
                after=_standard_to_dict(new),
            )
        )
    return ops


def _standard_to_dict(std: defs.Standard) -> Dict[str, Any]:
    """Serialize Standard to JSON-suitable dict."""
    d = {
        "name": std.name,
        "section": getattr(std, "section", ""),
        "subsection": getattr(std, "subsection", ""),
        "sectionID": getattr(std, "sectionID", ""),
        "description": getattr(std, "description", ""),
    }
    linked_cres = []
    for link in getattr(std, "links", []):
        doc = getattr(link, "document", None)
        if doc and getattr(doc, "doctype", None) == defs.Credoctypes.CRE:
            linked_cres.append(
                {
                    "id": getattr(doc, "id", ""),
                    "name": getattr(doc, "name", ""),
                }
            )
    if linked_cres:
        d["linked_cres"] = linked_cres
    return d


def change_set_to_json(ops: List[ChangeSetOp]) -> str:
    """Serialize change-set to JSON. Keys as tuples become lists."""

    def _serialize(op: ChangeSetOp) -> Dict[str, Any]:
        d = asdict(op)
        if "key" in d and isinstance(d["key"], tuple):
            d["key"] = list(d["key"])
        return d

    return json.dumps([_serialize(op) for op in ops], indent=2)


def change_set_from_json(data: str) -> List[ChangeSetOp]:
    """Deserialize change-set from JSON."""
    loaded = json.loads(data)
    result: List[ChangeSetOp] = []
    for item in loaded:
        op_type = item.get("op", "")
        key = tuple(item["key"]) if "key" in item else ("", "", "")
        if op_type == "add_control":
            result.append(AddControl(key=key, document=item.get("document", {})))
        elif op_type == "remove_control":
            result.append(RemoveControl(key=key, document=item.get("document", {})))
        elif op_type == "modify_control":
            result.append(
                ModifyControl(
                    key=key,
                    before=item.get("before", {}),
                    after=item.get("after", {}),
                )
            )
        else:
            # Ignore unknown ops for forward-compatibility.
            continue
    return result


# Step 8: Conflict detection


def detect_manual_edit_keys(
    baseline: List[defs.Standard],
    current_main_graph: List[defs.Standard],
) -> Set[Tuple[str, str, str]]:
    """
    Detect standards that were edited manually in the main graph.

    We mark a key as manually edited when:
    - it exists in both baseline and current snapshots, and
    - content hash differs.
    """
    baseline_map = standard_snapshot_map(baseline)
    current_map = standard_snapshot_map(current_main_graph)
    shared_keys = set(baseline_map.keys()) & set(current_map.keys())
    return {k for k in shared_keys if baseline_map[k] != current_map[k]}


def detect_conflicts(
    ops: List[ChangeSetOp],
    manually_edited_keys: Set[Tuple[str, str, str]],
) -> List[ChangeSetOp]:
    """
    Mark operations that would overwrite manual edits as conflicts.
    Returns the ops that are conflicts (should not be applied automatically).
    """
    conflicts: List[ChangeSetOp] = []
    for op in ops:
        if isinstance(op, ModifyControl) and op.key in manually_edited_keys:
            conflicts.append(op)
        elif isinstance(op, RemoveControl) and op.key in manually_edited_keys:
            conflicts.append(op)
    return conflicts


def has_conflicts(
    ops: List[ChangeSetOp], manually_edited_keys: Set[Tuple[str, str, str]]
) -> bool:
    """True if any op would conflict with manual edits."""
    return len(detect_conflicts(ops, manually_edited_keys)) > 0


def live_standard_defs_for_resource(
    collection: Any, standard_name: str
) -> List[defs.Standard]:
    """Load current main-graph Standard defs for one resource name (for staging conflicts)."""
    rows = collection.get_nodes(name=standard_name) or []
    out: List[defs.Standard] = []
    for n in rows:
        if isinstance(n, defs.Standard):
            out.append(n)
    return out


def impacted_standard_names_from_ops(ops: List[ChangeSetOp]) -> Set[str]:
    return {str(op.key[0]) for op in ops if op.key and len(op.key) > 0}


def impacted_cre_external_ids_for_standards(
    collection: Any, standard_names: Set[str]
) -> Set[str]:
    """CRE external ids linked to any node under the given standard names."""
    ids: Set[str] = set()
    for name in standard_names:
        for node in collection.get_nodes(name=name) or []:
            for link in getattr(node, "links", None) or []:
                doc = getattr(link, "document", None)
                if doc is None:
                    continue
                dt = getattr(doc, "doctype", None)
                val = dt.value if hasattr(dt, "value") else str(dt)
                if val != defs.Credoctypes.CRE.value:
                    continue
                eid = getattr(doc, "id", None) or ""
                if eid:
                    ids.add(eid)
    return ids
