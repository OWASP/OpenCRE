"""Dedicated nearest-neighbour search over comprehension documents.

The shared agent lane returns only a few hits across every document kind, so
comprehension docs get crowded out; this searches them directly.
"""

from __future__ import annotations

import os
from typing import List

from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT, LaneHit


def retrieval_k() -> int:
    try:
        return max(1, int(os.environ.get("OWASP_COMPREHENSION_TOP_K", "24")))
    except ValueError:
        return 24


def fetch_comprehension_hits(question: str) -> List[LaneHit]:
    """Best-effort: [] when pgvector or embeddings are unavailable."""
    try:
        from sqlalchemy import text as sql_text

        from application import sqla
        from application.database import db as db_mod
        from application.prompt_client import prompt_client
        from application.database.pgvector_utils import to_pgvector_literal

        database = db_mod.Node_collection()
        if not database.can_use_pgvector_similarity():
            return []
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)
        q = to_pgvector_literal(list(handler.get_text_embeddings(question)))
        with sqla.session.get_bind().connect() as conn:
            rows = conn.execute(
                sql_text(
                    """
                    SELECT id, doc_type, embeddings_content, embeddings_url,
                           1 - (embedding_vec <=> CAST(:q AS vector)) AS score
                    FROM embeddings
                    WHERE source_channel = :channel
                      AND embedding_vec IS NOT NULL
                      AND embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'
                    ORDER BY embedding_vec <=> CAST(:q AS vector)
                    LIMIT :limit
                    """
                ),
                {"q": q, "channel": CHANNEL_AGENT, "limit": retrieval_k()},
            ).fetchall()
        return [
            LaneHit(
                channel=CHANNEL_AGENT,
                score=float(r.score or 0.0),
                embedding_id=str(r.id),
                content=str(r.embeddings_content or ""),
                url=str(r.embeddings_url or ""),
                doc_type=str(r.doc_type or ""),
            )
            for r in rows or []
        ]
    except Exception:
        return []
