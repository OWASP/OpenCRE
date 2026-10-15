"""Multi-lane embedding similarity for chat routing (no brand classifiers).

Lanes (``embeddings.source_channel``):
  - ``cre_graph`` — CRE nodes
  - ``corpus`` — standards / tools / document chunks
  - ``owasp_agent_meta`` — community metadata + optional evidence notes

Decide: clarify if all weak; single lane if one dominates; both if agent+CRE/corpus
are close.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from application.database.pgvector_utils import to_pgvector_literal

CHANNEL_CRE = "cre_graph"
CHANNEL_CORPUS = "corpus"
CHANNEL_AGENT = "owasp_agent_meta"
ALL_CHANNELS = (CHANNEL_CRE, CHANNEL_CORPUS, CHANNEL_AGENT)

EmbedFn = Callable[[str], Sequence[float]]


def sim_router_enabled() -> bool:
    raw = (os.environ.get("OWASP_AGENT_SIM_ROUTER") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def agent_top_k() -> int:
    return _int_env("OWASP_AGENT_TOP_K", 8)


@dataclass
class LaneHit:
    channel: str
    score: float
    embedding_id: Optional[str] = None
    content: str = ""
    url: str = ""
    doc_type: str = ""


@dataclass
class LaneDecision:
    """Routing outcome for chat."""

    action: str  # clarify | cre | agent | both
    scores: Dict[str, float]
    hits: Dict[str, Optional[LaneHit]]
    reason: str = ""
    # Ranked agent-lane candidates for LLM / margin pick (may be empty).
    agent_candidates: List[LaneHit] = field(default_factory=list)


def _top_hits_pg(
    connection: Any, *, channel: str, query_vec: Sequence[float], limit: int = 1
) -> List[LaneHit]:
    from sqlalchemy import text as sql_text

    q = to_pgvector_literal(list(query_vec))
    rows = connection.execute(
        sql_text(
            """
            SELECT id, doc_type, embeddings_content, embeddings_url,
                   1 - (embedding_vec <=> CAST(:q AS vector)) AS score
            FROM embeddings
            WHERE source_channel = :channel
              AND embedding_vec IS NOT NULL
            ORDER BY embedding_vec <=> CAST(:q AS vector)
            LIMIT :limit
            """
        ),
        {"q": q, "channel": channel, "limit": int(limit)},
    ).fetchall()
    out: List[LaneHit] = []
    for row in rows or []:
        out.append(
            LaneHit(
                channel=channel,
                score=float(row.score or 0.0),
                embedding_id=str(row.id) if row.id is not None else None,
                content=str(row.embeddings_content or ""),
                url=str(row.embeddings_url or ""),
                doc_type=str(row.doc_type or ""),
            )
        )
    return out


def _top_hit_pg(
    connection: Any, *, channel: str, query_vec: Sequence[float]
) -> Optional[LaneHit]:
    hits = _top_hits_pg(connection, channel=channel, query_vec=query_vec, limit=1)
    return hits[0] if hits else None


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    import math

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _top_hits_memory(
    rows: List[Dict[str, Any]],
    *,
    channel: str,
    query_vec: Sequence[float],
    limit: int = 1,
) -> List[LaneHit]:
    scored: List[LaneHit] = []
    for row in rows:
        if str(row.get("source_channel") or "") != channel:
            continue
        vec = row.get("embedding_vec") or []
        if isinstance(vec, str):
            from application.database.pgvector_utils import parse_stored_embedding_vec

            vec = parse_stored_embedding_vec(vec)
        score = _cosine(query_vec, vec)
        scored.append(
            LaneHit(
                channel=channel,
                score=score,
                embedding_id=str(row.get("id") or "") or None,
                content=str(row.get("embeddings_content") or ""),
                url=str(row.get("embeddings_url") or ""),
                doc_type=str(row.get("doc_type") or ""),
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[: max(1, int(limit))]


def _top_hit_memory(
    rows: List[Dict[str, Any]], *, channel: str, query_vec: Sequence[float]
) -> Optional[LaneHit]:
    hits = _top_hits_memory(rows, channel=channel, query_vec=query_vec, limit=1)
    return hits[0] if hits else None


def score_lanes(
    *,
    query_vec: Sequence[float],
    connection: Any = None,
    memory_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Optional[LaneHit]]:
    """Return best hit per channel."""
    out: Dict[str, Optional[LaneHit]] = {}
    if memory_rows is not None:
        for ch in ALL_CHANNELS:
            out[ch] = _top_hit_memory(memory_rows, channel=ch, query_vec=query_vec)
        return out
    if connection is None:
        return {ch: None for ch in ALL_CHANNELS}
    for ch in ALL_CHANNELS:
        try:
            out[ch] = _top_hit_pg(connection, channel=ch, query_vec=query_vec)
        except Exception:
            out[ch] = None
    return out


def score_agent_candidates(
    *,
    query_vec: Sequence[float],
    connection: Any = None,
    memory_rows: Optional[List[Dict[str, Any]]] = None,
    limit: Optional[int] = None,
) -> List[LaneHit]:
    """Ranked top-k hits from the agent meta lane."""
    k = limit if limit is not None else agent_top_k()
    if memory_rows is not None:
        return _top_hits_memory(
            memory_rows, channel=CHANNEL_AGENT, query_vec=query_vec, limit=k
        )
    if connection is None:
        return []
    try:
        return _top_hits_pg(
            connection, channel=CHANNEL_AGENT, query_vec=query_vec, limit=k
        )
    except Exception:
        return []


def decide_lanes(
    hits: Dict[str, Optional[LaneHit]],
    *,
    agent_candidates: Optional[List[LaneHit]] = None,
) -> LaneDecision:
    """Apply thresholds to lane hits."""
    t_high = _float_env("OWASP_AGENT_SIM_HIGH", 0.78)
    t_mid = _float_env("OWASP_AGENT_SIM_MID", 0.65)
    t_low = _float_env("OWASP_AGENT_SIM_LOW", 0.55)
    margin = _float_env("OWASP_AGENT_SIM_MARGIN", 0.05)
    cands = list(agent_candidates or [])

    scores: Dict[str, float] = {}
    for ch in ALL_CHANNELS:
        hit = hits.get(ch)
        scores[ch] = hit.score if hit is not None else 0.0
    s_cre = max(scores[CHANNEL_CRE], scores[CHANNEL_CORPUS])
    s_agent = scores[CHANNEL_AGENT]
    best = max(scores.values()) if scores else 0.0

    if best < t_low:
        return LaneDecision(
            action="clarify",
            scores=scores,
            hits=hits,
            reason=f"all_below_low:{best:.3f}",
            agent_candidates=cands,
        )

    # Strong agent, CRE/corpus not close → agent
    if s_agent >= t_high and s_agent >= s_cre + margin:
        return LaneDecision(
            action="agent",
            scores=scores,
            hits=hits,
            reason="agent_dominates",
            agent_candidates=cands,
        )
    # Strong CRE/corpus, agent weak → CRE RAG
    if s_cre >= t_high and s_cre >= s_agent + margin:
        return LaneDecision(
            action="cre",
            scores=scores,
            hits=hits,
            reason="cre_dominates",
            agent_candidates=cands,
        )
    # Both mid+ and close → both
    if (
        s_agent >= t_mid
        and s_cre >= t_mid
        and abs(s_agent - s_cre) <= max(margin, 0.08)
    ):
        return LaneDecision(
            action="both",
            scores=scores,
            hits=hits,
            reason="agent_and_cre_close",
            agent_candidates=cands,
        )
    if s_agent >= s_cre and s_agent >= t_mid:
        return LaneDecision(
            action="agent",
            scores=scores,
            hits=hits,
            reason="agent_best_mid",
            agent_candidates=cands,
        )
    if s_cre >= t_mid:
        return LaneDecision(
            action="cre",
            scores=scores,
            hits=hits,
            reason="cre_best_mid",
            agent_candidates=cands,
        )
    return LaneDecision(
        action="clarify",
        scores=scores,
        hits=hits,
        reason=f"ambiguous_mid:{best:.3f}",
        agent_candidates=cands,
    )


def route_prompt(
    prompt: str,
    *,
    embed_fn: EmbedFn,
    connection: Any = None,
    memory_rows: Optional[List[Dict[str, Any]]] = None,
    top_k: Optional[int] = None,
) -> LaneDecision:
    vec = list(embed_fn(prompt))
    hits = score_lanes(query_vec=vec, connection=connection, memory_rows=memory_rows)
    cands = score_agent_candidates(
        query_vec=vec,
        connection=connection,
        memory_rows=memory_rows,
        limit=top_k,
    )
    return decide_lanes(hits, agent_candidates=cands)


def is_evidence_hit(hit: Optional[LaneHit]) -> bool:
    if not hit:
        return False
    return (hit.url or "").startswith("owasp-agent://evidence/")


def is_meta_hit(hit: Optional[LaneHit]) -> bool:
    if not hit:
        return False
    return (hit.url or "").startswith("owasp-agent://meta/")
