"""CRE-graph hop distance for B2 predictions (gap-analysis style weights).

Classifies each scorable section into an exclusive bucket:
  exact | one_hop_related | one_hop_contains | multi_hop | hallucination | irrelevant

Hallucination = every predicted CRE id is unknown (invented).
Irrelevant = at least one predicted CRE exists in the graph but no path to gold.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

# Mirror application.utils.gap_analysis.PENALTIES for CRE↔CRE edges.
PENALTIES = {
    "RELATED": 2,
    "CONTAINS_UP": 2,
    "CONTAINS_DOWN": 1,
    "SAME": 0,
}

BUCKETS = (
    "exact",
    "one_hop_related",
    "one_hop_contains",
    "multi_hop",
    "hallucination",
    "irrelevant",
)


@dataclass(frozen=True)
class TypedEdge:
    src: str
    dst: str
    relationship: str  # RELATED | CONTAINS_UP | CONTAINS_DOWN

    @property
    def penalty(self) -> int:
        return int(PENALTIES[self.relationship])


@dataclass
class CreAdjacency:
    known_ids: frozenset
    # src -> list of TypedEdge
    _out: Dict[str, List[TypedEdge]]

    def __init__(
        self,
        known_ids: Iterable[str],
        edges: Sequence[TypedEdge],
    ) -> None:
        self.known_ids = frozenset(known_ids)
        out: Dict[str, List[TypedEdge]] = defaultdict(list)
        for e in edges:
            out[e.src].append(e)
        self._out = dict(out)

    def neighbors(self, node: str) -> List[TypedEdge]:
        return self._out.get(node) or []

    def to_serializable(self) -> Dict[str, Any]:
        return {
            "known_ids": sorted(self.known_ids),
            "edges": [
                {"src": e.src, "dst": e.dst, "relationship": e.relationship}
                for src_edges in self._out.values()
                for e in src_edges
            ],
        }

    @classmethod
    def from_serializable(cls, payload: Mapping[str, Any]) -> "CreAdjacency":
        edges = [
            TypedEdge(
                str(e["src"]),
                str(e["dst"]),
                str(e["relationship"]),
            )
            for e in (payload.get("edges") or [])
        ]
        return cls(known_ids=payload.get("known_ids") or [], edges=edges)


def save_adjacency(adj: CreAdjacency, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(adj.to_serializable(), separators=(",", ":")).encode("utf-8")
    if str(path).endswith(".gz"):
        path.write_bytes(gzip.compress(raw))
    else:
        path.write_bytes(raw)


def load_adjacency(path: Path) -> CreAdjacency:
    data = path.read_bytes()
    if str(path).endswith(".gz"):
        data = gzip.decompress(data)
    return CreAdjacency.from_serializable(json.loads(data.decode("utf-8")))


def build_adjacency_from_db(session: Any) -> CreAdjacency:
    """Load CRE external_ids + Related/Contains edges from SQLAlchemy session.

    InternalLinks convention (application.database.db.InternalLinks):
      group = higher / parent CRE uuid
      cre   = lower / child CRE uuid
      type  = Contains | Related
    """
    from application.database.db import CRE, InternalLinks

    id_to_ext: Dict[str, str] = {}
    for row in session.query(CRE.id, CRE.external_id).all():
        ext = (row.external_id or "").strip()
        if not ext:
            continue
        id_to_ext[str(row.id)] = ext

    edges: List[TypedEdge] = []
    seen: Set[Tuple[str, str, str]] = set()

    def add(src: str, dst: str, rel: str) -> None:
        key = (src, dst, rel)
        if key in seen:
            return
        seen.add(key)
        edges.append(TypedEdge(src, dst, rel))

    for link in session.query(InternalLinks).all():
        ltype = (link.type or "").strip()
        higher = id_to_ext.get(str(link.group))
        lower = id_to_ext.get(str(link.cre))
        if not higher or not lower or higher == lower:
            continue
        if ltype == "Related":
            add(higher, lower, "RELATED")
            add(lower, higher, "RELATED")
        elif ltype == "Contains":
            # group Contains cre → DOWN from parent, UP from child
            add(higher, lower, "CONTAINS_DOWN")
            add(lower, higher, "CONTAINS_UP")
        # PartOf forbidden by DB constraint; ignore other types

    return CreAdjacency(known_ids=id_to_ext.values(), edges=edges)


PathEdge = TypedEdge


def _best_path(
    start: str,
    goals: Set[str],
    adj: CreAdjacency,
) -> Optional[Tuple[int, int, List[TypedEdge]]]:
    """BFS shortest hop path; among equal hops prefer lower GA path_penalty.

    Returns (hop_count, path_penalty, edges) or None.
    """
    if start in goals:
        return (0, 0, [])
    if start not in adj.known_ids:
        return None

    # state: node -> (hop_count, path_penalty, edges)
    best: Dict[str, Tuple[int, int, List[TypedEdge]]] = {
        start: (0, 0, []),
    }
    q: deque[str] = deque([start])
    found: List[Tuple[int, int, List[TypedEdge]]] = []

    while q:
        node = q.popleft()
        hops, pen, path = best[node]
        if found and hops > found[0][0]:
            # BFS layer past shortest goal hop — stop
            continue
        for edge in adj.neighbors(node):
            nxt = edge.dst
            nh, np_ = hops + 1, pen + edge.penalty
            npath = path + [edge]
            prev = best.get(nxt)
            if prev is None or (nh, np_) < (prev[0], prev[1]):
                best[nxt] = (nh, np_, npath)
                q.append(nxt)
            if nxt in goals:
                cand = (nh, np_, npath)
                if not found or cand[:2] < found[0][:2]:
                    found = [cand]
                elif cand[:2] == found[0][:2]:
                    found.append(cand)

    if not found:
        return None
    found.sort(key=lambda t: (t[0], t[1]))
    return found[0]


def classify_section(
    *,
    gold: Sequence[str],
    predicted: Sequence[str],
    adj: CreAdjacency,
) -> Dict[str, Any]:
    g = {str(x).strip() for x in gold if str(x).strip()}
    p = [str(x).strip() for x in predicted if str(x).strip()]
    p_set = set(p)

    invented = sorted(x for x in p_set if x not in adj.known_ids)
    known_preds = sorted(x for x in p_set if x in adj.known_ids)

    base: Dict[str, Any] = {
        "gold": sorted(g),
        "predicted": sorted(p_set),
        "invented": invented,
        "known_predicted": known_preds,
        "hop_count": None,
        "path_penalty": None,
        "path_edges": [],
        "best_pred": None,
        "best_gold": None,
        "bucket": "irrelevant",
    }

    if not g:
        base["bucket"] = "irrelevant"
        return base

    if p_set & g:
        base["bucket"] = "exact"
        base["hop_count"] = 0
        base["path_penalty"] = 0
        hit = sorted(p_set & g)[0]
        base["best_pred"] = hit
        base["best_gold"] = hit
        return base

    if not known_preds:
        base["bucket"] = "hallucination" if p_set else "irrelevant"
        return base

    best: Optional[Tuple[int, int, List[TypedEdge], str, str]] = None
    for pred in known_preds:
        path = _best_path(pred, g, adj)
        if path is None:
            continue
        hops, pen, edges = path
        # destination is last edge dst or pred if empty
        dest = edges[-1].dst if edges else pred
        cand = (hops, pen, edges, pred, dest)
        if best is None or (hops, pen) < (best[0], best[1]):
            best = cand

    if best is None:
        base["bucket"] = "irrelevant"
        return base

    hops, pen, edges, pred, dest = best
    base["hop_count"] = hops
    base["path_penalty"] = pen
    base["best_pred"] = pred
    base["best_gold"] = dest
    base["path_edges"] = [
        {"src": e.src, "dst": e.dst, "relationship": e.relationship, "penalty": e.penalty}
        for e in edges
    ]

    if hops == 1:
        rel = edges[0].relationship
        if rel == "RELATED":
            base["bucket"] = "one_hop_related"
        else:
            base["bucket"] = "one_hop_contains"
    else:
        base["bucket"] = "multi_hop"
    return base


def score_details(
    details: Sequence[Mapping[str, Any]],
    adj: CreAdjacency,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    counts = {b: 0 for b in BUCKETS}
    scorable = 0
    pred_total = 0
    invented_total = 0

    for d in details:
        if d.get("aligned") is False:
            continue
        gold = d.get("gold") or []
        if not gold:
            continue
        predicted = d.get("predicted") or []
        scorable += 1
        row = classify_section(gold=gold, predicted=predicted, adj=adj)
        row["resource"] = d.get("resource")
        row["section_id"] = d.get("section_id")
        row["exact_hit"] = bool(d.get("hit"))
        rows.append(row)
        counts[row["bucket"]] += 1
        pred_total += len(row["predicted"])
        invented_total += len(row["invented"])

    rates = {
        b: round((counts[b] / scorable) if scorable else 0.0, 4) for b in BUCKETS
    }
    d1 = counts["exact"] + counts["one_hop_related"] + counts["one_hop_contains"]
    ga_useful = d1 + counts["multi_hop"]
    rates["distance1_hit"] = round((d1 / scorable) if scorable else 0.0, 4)
    rates["ga_path_hit"] = round((ga_useful / scorable) if scorable else 0.0, 4)
    # Hop-capped soft hits (CRE graph is often one component → unbounded path ≈ always true)
    within2 = sum(
        1
        for r in rows
        if r["bucket"] == "exact"
        or (
            r.get("hop_count") is not None
            and int(r["hop_count"]) <= 2
            and r["bucket"] != "hallucination"
            and r["bucket"] != "irrelevant"
        )
    )
    within3 = sum(
        1
        for r in rows
        if r["bucket"] == "exact"
        or (
            r.get("hop_count") is not None
            and int(r["hop_count"]) <= 3
            and r["bucket"] != "hallucination"
            and r["bucket"] != "irrelevant"
        )
    )
    rates["within_2_hops"] = round((within2 / scorable) if scorable else 0.0, 4)
    rates["within_3_hops"] = round((within3 / scorable) if scorable else 0.0, 4)
    rates["invented_pred"] = round(
        (invented_total / pred_total) if pred_total else 0.0, 4
    )

    return {
        "scorable": scorable,
        "counts": counts,
        "rates": rates,
        "pred_ids_total": pred_total,
        "invented_ids_total": invented_total,
        "rows": rows,
    }
