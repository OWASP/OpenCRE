"""Dedicated nearest-neighbour search over comprehension documents.

The shared agent lane returns only a few hits across every document kind, so
comprehension docs get crowded out; this searches them directly.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, List

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


_DENSE_SQL = """
    SELECT id, doc_type, embeddings_content, embeddings_url,
           {score} AS score
    FROM embeddings
    WHERE source_channel = :channel
      AND embedding_vec IS NOT NULL
      AND {where}
    ORDER BY {dist}
    LIMIT :limit
"""

_KW_SQL = """
    SELECT id, doc_type, embeddings_content, embeddings_url,
           ts_rank_cd(to_tsvector('english', embeddings_content), query) AS score
    FROM embeddings, websearch_to_tsquery('english', :kw) AS query
    WHERE source_channel = :channel
      AND embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'
      AND to_tsvector('english', embeddings_content) @@ query
    ORDER BY score DESC
    LIMIT :limit
"""

_ALL = "embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'"


def _hit(r: Any, score: float) -> LaneHit:
    return LaneHit(
        channel=CHANNEL_AGENT,
        score=score,
        embedding_id=str(r.id),
        content=str(r.embeddings_content or ""),
        url=str(r.embeddings_url or ""),
        doc_type=str(r.doc_type or ""),
    )


def _dense(
    conn: Any, q: str, where: str, limit: int, params: dict | None = None
) -> List[LaneHit]:
    from sqlalchemy import text as sql_text

    from application.utils.owasp_agent.lane_similarity import cosine_exprs

    dist, score = cosine_exprs()
    rows = conn.execute(
        sql_text(_DENSE_SQL.format(where=where, dist=dist, score=score)),
        {"q": q, "channel": CHANNEL_AGENT, "limit": limit, **(params or {})},
    ).fetchall()
    return [_hit(r, float(r.score or 0.0)) for r in rows or []]


def _keyword(conn: Any, question: str, limit: int) -> List[LaneHit]:
    from sqlalchemy import text as sql_text

    from application.utils.comprehension.extras import keywords

    kws = keywords(question)
    if not kws:
        return []
    rows = conn.execute(
        sql_text(_KW_SQL),
        {"kw": " or ".join(kws), "channel": CHANNEL_AGENT, "limit": limit},
    ).fetchall()
    return [_hit(r, float(r.score or 0.0)) for r in rows or []]


def _expand(conn: Any, hits: List[LaneHit]) -> None:
    """Attach neighbouring raw chunks (previous/next) to each raw hit, in place."""
    from sqlalchemy import text as sql_text

    from application.utils.comprehension.extras import merge_neighbours, neighbour_urls

    want = {u for h in hits for u in neighbour_urls(h.url)}
    if not want:
        return
    rows = conn.execute(
        sql_text(
            "SELECT embeddings_url, embeddings_content FROM embeddings "
            "WHERE source_channel = :channel AND embeddings_url = ANY(:urls)"
        ),
        {"channel": CHANNEL_AGENT, "urls": list(want)},
    ).fetchall()
    text = {r.embeddings_url: str(r.embeddings_content or "") for r in rows}
    for h in hits:
        nb = neighbour_urls(h.url)
        if nb:
            prev = text.get(nb[0]) if len(nb) == 2 else None
            nxt = text.get(nb[-1])
            h.content = merge_neighbours(h.content, prev, nxt)


def fetch_comprehension_hits(
    question: str, queries: List[str] | None = None
) -> List[LaneHit]:
    """Best-effort: [] when pgvector or embeddings are unavailable.

    ``queries`` (query-understanding sub-questions) are searched in addition to
    the question itself and fused.
    """
    try:
        from application import sqla
        from application.database import db as db_mod
        from application.prompt_client import prompt_client
        from application.database.pgvector_utils import to_pgvector_literal
        from application.utils.comprehension import flags
        from application.utils.comprehension.extras import rrf

        database = db_mod.Node_collection()
        if not database.can_use_pgvector_similarity():
            return []
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)
        texts = [question] + [q for q in (queries or []) if q and q != question]
        k = retrieval_k()
        wide = k * 2 if flags.on("RERANK") else k
        with sqla.session.get_bind().connect() as conn:
            slugs = _known_slugs(conn)
            rankings: List[List[LaneHit]] = []
            from application.utils.comprehension.embedcache import embed_many

            vecs = embed_many(texts, handler.get_text_embeddings)
            for t, vec in zip(texts, vecs):
                q = to_pgvector_literal(list(vec))
                dense = _dense(conn, q, _ALL, wide)
                rankings.append(dense)
                if flags.on("HYBRID"):
                    rankings.append(_keyword(conn, t, wide))
                scoped = matched_slugs(t, slugs)
                if flags.on("PERPROJECT") and len(scoped) >= 2:
                    for slug in scoped:
                        rankings.append(
                            _dense(
                                conn,
                                q,
                                "embeddings_url LIKE :pat",
                                max(4, wide // len(scoped)),
                                {
                                    "pat": f"owasp-agent://evidence/comprehension-{slug}-%"
                                },
                            )
                        )
                if os.environ.get("OWASP_COMPREHENSION_SCOPE", "0") == "1":
                    for slug in scoped:
                        part = _dense(
                            conn,
                            q,
                            "embeddings_url LIKE :pat",
                            wide,
                            {"pat": f"owasp-agent://evidence/comprehension-{slug}-%"},
                        )
                        for h in part:
                            h.score += 0.2
                        rankings.append(part)
            if len(rankings) == 1:
                hits = rankings[0]
            else:
                hits = rrf(rankings, key=lambda h: h.url)
            if flags.on("EXPAND"):
                _expand(conn, hits[: max(k, 12)])
        return hits
    except Exception:
        return []


def prefetch_embedding(text: str) -> None:
    """Start embedding ``text`` in the background (best-effort)."""
    try:
        from application.database import db as db_mod
        from application.prompt_client import prompt_client
        from application.utils.comprehension.embedcache import prefetch

        handler = prompt_client.PromptHandler(
            db_mod.Node_collection(), load_all_embeddings=False
        )
        prefetch(text, handler.get_text_embeddings)
    except Exception:
        pass
