"""Dedicated nearest-neighbour search over comprehension documents.

The shared agent lane returns only a few hits across every document kind, so
comprehension docs get crowded out; this searches them directly.
"""

from __future__ import annotations

import os
import re
import time
from typing import List

from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT, LaneHit


def retrieval_k() -> int:
    try:
        return max(1, int(os.environ.get("OWASP_COMPREHENSION_TOP_K", "24")))
    except ValueError:
        return 24


_SLUG_RE = re.compile(
    r"^owasp-agent://evidence/comprehension-(.+?)-(?:overview|claim|dclaim|doc|raw)(?:-.*)?$"
)
_REPO_CACHE: dict = {"at": 0.0, "slugs": []}
_STRIP = re.compile(r"^(?:owasp-)?(?:www-project-|www-)?")


def alias_phrase(slug: str) -> str:
    """Words a person would use for a repo slug: owasp-www-project-top-ten -> 'top ten'."""
    return _STRIP.sub("", slug).replace("-", " ").strip()


def matched_slugs(question: str, slugs: List[str], limit: int = 3) -> List[str]:
    """Repo slugs whose alias phrase appears as whole words in the question (longest first)."""
    q = " " + re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip() + " "
    found = []
    for slug in slugs:
        phrase = alias_phrase(slug)
        if len(phrase) >= 4 and f" {phrase} " in q:
            found.append((len(phrase), slug))
    found.sort(reverse=True)
    return [s for _, s in found[:limit]]


def _known_slugs(conn) -> List[str]:
    from sqlalchemy import text as sql_text

    if time.time() - _REPO_CACHE["at"] < 600 and _REPO_CACHE["slugs"]:
        return _REPO_CACHE["slugs"]
    rows = conn.execute(
        sql_text(
            "SELECT DISTINCT embeddings_url FROM embeddings "
            "WHERE embeddings_url LIKE 'owasp-agent://evidence/comprehension-%-overview'"
        )
    ).fetchall()
    slugs = sorted({m.group(1) for (u,) in rows if (m := _SLUG_RE.match(u))})
    _REPO_CACHE.update(at=time.time(), slugs=slugs)
    return slugs


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
        sql = """
            SELECT id, doc_type, embeddings_content, embeddings_url,
                   1 - (embedding_vec <=> CAST(:q AS vector)) AS score
            FROM embeddings
            WHERE source_channel = :channel
              AND embedding_vec IS NOT NULL
              AND {where}
            ORDER BY embedding_vec <=> CAST(:q AS vector)
            LIMIT :limit
        """
        with sqla.session.get_bind().connect() as conn:
            rows = list(
                conn.execute(
                    sql_text(
                        sql.format(
                            where="embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'"
                        )
                    ),
                    {"q": q, "channel": CHANNEL_AGENT, "limit": retrieval_k()},
                ).fetchall()
            )
            scoped = (
                matched_slugs(question, _known_slugs(conn))
                if os.environ.get("OWASP_COMPREHENSION_SCOPE", "0") == "1"
                else []
            )
            boosted = set()
            for slug in scoped:
                part = conn.execute(
                    sql_text(sql.format(where="embeddings_url LIKE :pat")),
                    {
                        "q": q,
                        "channel": CHANNEL_AGENT,
                        "limit": retrieval_k(),
                        "pat": f"owasp-agent://evidence/comprehension-{slug}-%",
                    },
                ).fetchall()
                rows += part
                boosted |= {str(r.id) for r in part}
        best = {}
        for r in rows or []:
            sc = float(r.score or 0.0) + (0.2 if str(r.id) in boosted else 0.0)
            if r.embeddings_url not in best or sc > best[r.embeddings_url][0]:
                best[r.embeddings_url] = (sc, r)
        return [
            LaneHit(
                channel=CHANNEL_AGENT,
                score=sc,
                embedding_id=str(r.id),
                content=str(r.embeddings_content or ""),
                url=str(r.embeddings_url or ""),
                doc_type=str(r.doc_type or ""),
            )
            for sc, r in sorted(best.values(), key=lambda t: -t[0])
        ]
    except Exception:
        return []
