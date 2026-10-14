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
from dataclasses import dataclass
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


def _top_hit_pg(
    connection: Any, *, channel: str, query_vec: Sequence[float]
) -> Optional[LaneHit]:
    from sqlalchemy import text as sql_text

    q = to_pgvector_literal(list(query_vec))
    row = connection.execute(
        sql_text(
            """
            SELECT id, doc_type, embeddings_content, embeddings_url,
                   1 - (embedding_vec <=> CAST(:q AS vector)) AS score
            FROM embeddings
            WHERE source_channel = :channel
              AND embedding_vec IS NOT NULL
            ORDER BY embedding_vec <=> CAST(:q AS vector)
            LIMIT 1
            """
        ),
        {"q": q, "channel": channel},
    ).fetchone()
    if not row:
        return None
    return LaneHit(
        channel=channel,
        score=float(row.score or 0.0),
        embedding_id=str(row.id) if row.id else None,
        content=str(row.embeddings_content or ""),
        url=str(row.embeddings_url or ""),
        doc_type=str(row.doc_type or ""),
    )


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


def _top_hit_memory(
    rows: List[Dict[str, Any]], *, channel: str, query_vec: Sequence[float]
) -> Optional[LaneHit]:
    best: Optional[LaneHit] = None
    for row in rows:
        if str(row.get("source_channel") or "") != channel:
            continue
        vec = row.get("embedding_vec") or []
        if isinstance(vec, str):
            from application.database.pgvector_utils import parse_stored_embedding_vec

            vec = parse_stored_embedding_vec(vec)
        score = _cosine(query_vec, vec)
        hit = LaneHit(
            channel=channel,
            score=score,
            embedding_id=str(row.get("id") or "") or None,
            content=str(row.get("embeddings_content") or ""),
            url=str(row.get("embeddings_url") or ""),
            doc_type=str(row.get("doc_type") or ""),
        )
        if best is None or hit.score > best.score:
            best = hit
    return best


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


def decide_lanes(hits: Dict[str, Optional[LaneHit]]) -> LaneDecision:
    """Apply thresholds to lane hits."""
    t_high = _float_env("OWASP_AGENT_SIM_HIGH", 0.78)
    t_mid = _float_env("OWASP_AGENT_SIM_MID", 0.65)
    t_low = _float_env("OWASP_AGENT_SIM_LOW", 0.55)
    margin = _float_env("OWASP_AGENT_SIM_MARGIN", 0.05)

    scores = {ch: (hits[ch].score if hits.get(ch) else 0.0) for ch in ALL_CHANNELS}
    s_cre = max(scores[CHANNEL_CRE], scores[CHANNEL_CORPUS])
    s_agent = scores[CHANNEL_AGENT]
    best = max(scores.values()) if scores else 0.0

    if best < t_low:
        return LaneDecision(
            action="clarify",
            scores=scores,
            hits=hits,
            reason=f"all_below_low:{best:.3f}",
        )

    # Strong agent, CRE/corpus not close → agent
    if s_agent >= t_high and s_agent >= s_cre + margin:
        return LaneDecision(
            action="agent", scores=scores, hits=hits, reason="agent_dominates"
        )
    # Strong CRE/corpus, agent weak → CRE RAG
    if s_cre >= t_high and s_cre >= s_agent + margin:
        return LaneDecision(
            action="cre", scores=scores, hits=hits, reason="cre_dominates"
        )
    # Both mid+ and close → both
    if (
        s_agent >= t_mid
        and s_cre >= t_mid
        and abs(s_agent - s_cre) <= max(margin, 0.08)
    ):
        return LaneDecision(
            action="both", scores=scores, hits=hits, reason="agent_and_cre_close"
        )
    if s_agent >= s_cre and s_agent >= t_mid:
        return LaneDecision(
            action="agent", scores=scores, hits=hits, reason="agent_best_mid"
        )
    if s_cre >= t_mid:
        return LaneDecision(
            action="cre", scores=scores, hits=hits, reason="cre_best_mid"
        )
    return LaneDecision(
        action="clarify",
        scores=scores,
        hits=hits,
        reason=f"ambiguous_mid:{best:.3f}",
    )


def route_prompt(
    prompt: str,
    *,
    embed_fn: EmbedFn,
    connection: Any = None,
    memory_rows: Optional[List[Dict[str, Any]]] = None,
) -> LaneDecision:
    vec = list(embed_fn(prompt))
    hits = score_lanes(query_vec=vec, connection=connection, memory_rows=memory_rows)
    return decide_lanes(hits)


def is_evidence_hit(hit: Optional[LaneHit]) -> bool:
    if not hit:
        return False
    return (hit.url or "").startswith("owasp-agent://evidence/")
