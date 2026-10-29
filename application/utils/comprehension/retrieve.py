"""Dedicated nearest-neighbour search over comprehension documents.

The shared agent lane returns only a few hits across every document kind, so
comprehension docs get crowded out; this searches them directly.
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar
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


_EXT_ALIAS_CACHE: dict = {"at": 0.0, "map": {}}


def alias_phrase(slug: str) -> str:
    """Words a person would use for a repo slug: owasp-www-project-top-ten -> 'top ten'."""
    if slug.startswith("ext-"):  # external source: ext-owasp-benelux -> 'benelux'
        slug = slug[len("ext-") :]
    return _STRIP.sub("", slug).replace("-", " ").strip()


def _external_aliases() -> dict:
    """{ext slug: [lower-case phrases]} from the approved external sources (10 min cache)."""
    if time.time() - _EXT_ALIAS_CACHE["at"] < 600:
        return _EXT_ALIAS_CACHE["map"]
    out: dict = {}
    try:
        from application import sqla
        from application.utils.comprehension import external

        for spec in external.load_specs(sqla.session):
            phrases = [spec.name, *spec.aliases]
            out[external.slug_for(spec)] = [
                " ".join(re.sub(r"[^a-z0-9]+", " ", p.lower()).split())
                for p in phrases
                if p
            ]
    except Exception:  # noqa: BLE001 - registry trouble must not break retrieval
        out = {}
    _EXT_ALIAS_CACHE.update(at=time.time(), map=out)
    return out


def matched_slugs(question: str, slugs: List[str], limit: int = 3) -> List[str]:
    """Repo slugs whose alias phrase appears as whole words in the question (longest first)."""
    q = " " + re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip() + " "
    found = []
    ext = _external_aliases()
    for slug in slugs:
        for phrase in [alias_phrase(slug), *ext.get(slug, [])]:
            if len(phrase) >= 4 and f" {phrase} " in q:
                found.append((len(phrase), slug))
                break
    found.sort(reverse=True)
    return [s for _, s in found[:limit]]


def _known_slugs(conn) -> List[str]:
    from sqlalchemy import text as sql_text

    from application.utils.comprehension import flags

    wide = flags.on("WIDEMATCH")
    cache_key = "wide" if wide else "digested"
    if (
        _REPO_CACHE.get("key") == cache_key
        and time.time() - _REPO_CACHE["at"] < 600
        and _REPO_CACHE["slugs"]
    ):
        return _REPO_CACHE["slugs"]
    if wide:
        rows = conn.execute(
            sql_text(
                "SELECT DISTINCT substring(embeddings_url from 'comprehension-(.+?)-raw-') "
                "FROM embeddings WHERE embeddings_url LIKE 'owasp-agent://evidence/comprehension-%-raw-%'"
            )
        ).fetchall()
        slugs = sorted({r[0] for r in rows if r[0]})
    else:
        rows = conn.execute(
            sql_text(
                "SELECT DISTINCT embeddings_url FROM embeddings "
                "WHERE embeddings_url LIKE 'owasp-agent://evidence/comprehension-%-overview'"
            )
        ).fetchall()
        slugs = sorted({m.group(1) for (u,) in rows if (m := _SLUG_RE.match(u))})
    ext_rows = conn.execute(
        sql_text(
            "SELECT DISTINCT substring(embeddings_url from 'comprehension-(ext-.+?)-raw-') "
            "FROM embeddings WHERE embeddings_url LIKE 'owasp-agent://evidence/comprehension-ext-%-raw-%'"
        )
    ).fetchall()
    slugs = sorted(set(slugs) | {r[0] for r in ext_rows if r[0]})
    _REPO_CACHE.update(at=time.time(), slugs=slugs, key=cache_key)
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
    SELECT c.id, c.doc_type, c.embeddings_content, c.embeddings_url,
           ts_rank_cd(to_tsvector('english', c.embeddings_content), q.query) AS score
    FROM (
        SELECT id, doc_type, embeddings_content, embeddings_url
        FROM embeddings, websearch_to_tsquery('english', :kw) AS query
        WHERE source_channel = :channel
          AND embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'
          AND to_tsvector('english', embeddings_content) @@ query
        LIMIT 300
    ) c, websearch_to_tsquery('english', :kw) AS q(query)
    ORDER BY score DESC
    LIMIT :limit
"""

_ALL = "embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'"


def docs_where() -> str:
    """Which comprehension documents to search: all (default), raw chunks only, or digests only."""
    mode = (os.environ.get("OWASP_COMPREHENSION_DOCS") or "all").strip().lower()
    if mode == "raw":
        return _ALL + " AND embeddings_url LIKE '%-raw-%'"
    if mode == "digest":
        return _ALL + " AND embeddings_url NOT LIKE '%-raw-%'"
    return _ALL


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
    if limit > 40:  # the HNSW index returns at most ef_search (default 40) rows
        try:
            conn.execute(
                sql_text(f"SET LOCAL hnsw.ef_search = {min(1000, int(limit))}")
            )
        except (
            Exception
        ):  # noqa: BLE001 - non-pgvector / older pgvector: keep the default
            pass
    rows = conn.execute(
        sql_text(_DENSE_SQL.format(where=where, dist=dist, score=score)),
        {"q": q, "channel": CHANNEL_AGENT, "limit": limit, **(params or {})},
    ).fetchall()
    return [_hit(r, float(r.score or 0.0)) for r in rows or []]


def _keyword(conn: Any, question: str, limit: int) -> List[LaneHit]:
    """Full-text hits: AND the most distinctive words, relaxing until a few rows match.

    An OR over common words matches thousands of rows and ranking them is slow, so
    the candidate set is capped and the query is kept selective.
    """
    from sqlalchemy import text as sql_text

    from application.utils.comprehension.extras import (
        keywords,
        phrase_queries,
        relaxed_and_queries,
    )

    kws = keywords(question)
    for kw in phrase_queries(question, kws) + relaxed_and_queries(kws):
        rows = conn.execute(
            sql_text(_KW_SQL),
            {"kw": kw, "channel": CHANNEL_AGENT, "limit": limit},
        ).fetchall()
        if len(rows) >= 3:
            return [_hit(r, float(r.score or 0.0)) for r in rows]
    return []


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


def _feature_projects(conn: Any, q: str, dense: List[LaneHit]) -> None:
    """Remember each featured project's best chunk when it is close enough to the best match."""
    from application.utils.comprehension import authority

    try:
        featured = {s: w for s, w in authority.weights().items() if w > 1.0}
    except Exception:  # noqa: BLE001
        return
    if not featured or not dense:
        return
    best = max(float(h.score) for h in dense)
    urls = authority.featured_urls()
    for slug, w in featured.items():
        top = _dense(
            conn,
            q,
            "embeddings_url LIKE :pat",
            1,
            {"pat": f"owasp-agent://evidence/comprehension-{slug}-%"},
        )
        if top and float(top[0].score) >= best - authority.tolerance(w):
            _, _, tail = top[0].content.partition("\n\nCitations:")
            cite = next(
                (c.strip() for c in tail.split(",") if c.strip().startswith("http")), ""
            )
            if cite and cite not in urls:
                urls.append(cite)
    authority.set_featured(urls)


def _slug_of(hit: LaneHit) -> str:
    m = _SLUG_RE.match(hit.url or "")
    return m.group(1) if m else ""


def _apply_authority(hits: List[LaneHit]) -> List[LaneHit]:
    """Admin authority weights, then (TOPPROJECTS) the best 3 projects each get a share."""
    from application.utils.comprehension import authority, flags, paths

    for (
        h
    ) in hits:  # file path as a signal: archives, tests, changelogs rank a little lower
        _, _, tail = (h.content or "").partition("\n\nCitations:")
        cite = next(
            (c.strip() for c in tail.split(",") if c.strip().startswith("http")), ""
        )
        if cite:
            h.score = float(h.score) * paths.priority(cite)
    hits.sort(key=lambda h: -float(h.score))
    hits = authority.bias(hits, _slug_of)
    if flags.on("TOPPROJECTS"):
        hits = authority.diversify(hits, _slug_of, projects=3, per=5)
    return hits


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
        from application.utils.comprehension.shared import shared_handler

        handler = shared_handler(database)
        from application.utils.comprehension import authority as _authority

        _authority.reset_featured()
        texts = [question] + [q for q in (queries or []) if q and q != question]
        k = retrieval_k()
        wide = k * 2 if flags.on("RERANK") else k
        with sqla.session.get_bind().connect() as conn:
            slugs = _known_slugs(conn)
            rankings: List[List[LaneHit]] = []
            keyword_hits: List[LaneHit] = []
            from application.utils.comprehension.embedcache import embed_many

            vecs = embed_many(texts, handler.get_text_embeddings)
            for t, vec in zip(texts, vecs):
                q = to_pgvector_literal(list(vec))
                dense = _dense(
                    conn,
                    q,
                    docs_where(),
                    max(wide, 300) if flags.on("TOPPROJECTS") else wide,
                )
                rankings.append(dense)
                if t == question:
                    _feature_projects(conn, q, dense)
                if flags.on("HYBRID"):
                    keyword_hits += _keyword(conn, t, wide)
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
            if keyword_hits:
                hits = supplement_with_keyword(hits, keyword_hits)
            hits = _apply_authority(hits)
            if flags.on("EXPAND"):
                _expand(conn, hits[: max(k, 12)])
        return hits
    except Exception:
        return []


def supplement_with_keyword(
    dense: List[LaneHit], keyword: List[LaneHit], head: int = 0, take: int = 0
) -> List[LaneHit]:
    """Keep the strongest dense hits, slot a few keyword hits right behind them.

    Interleaving by rank let name-only keyword matches push real semantic answers
    out of the top spots, so keyword hits only supplement the dense head.
    """
    head = head or int(os.environ.get("OWASP_CX_HYBRID_HEAD", "6"))
    take = take or int(os.environ.get("OWASP_CX_HYBRID_TAKE", "4"))
    first = dense[:head]
    seen = {h.url for h in first}
    extra = [h for h in keyword if h.url not in seen][:take]
    seen |= {h.url for h in extra}
    out = first + extra + [h for h in dense[head:] if h.url not in seen]
    top = float(out[0].score) if out else 0.0
    for i, h in enumerate(out):  # keep the order stable under later score sorts
        h.score = top - i * 1e-4
    return out


def prefetch_embedding(text: str) -> None:
    """Start embedding ``text`` in the background (best-effort)."""
    try:
        from application.database import db as db_mod
        from application.prompt_client import prompt_client
        from application.utils.comprehension.embedcache import prefetch

        from application.utils.comprehension.shared import shared_handler

        handler = shared_handler(db_mod.Node_collection())
        prefetch(text, handler.get_text_embeddings)
    except Exception:
        pass


_CITE_TAIL = "\n\nCitations:"
_RELATED_TAIL = "\n\nRelated questions:"


def longctx_max_chars() -> int:
    try:
        return max(10_000, int(os.environ.get("OWASP_CX_LONGCTX_CHARS", "700000")))
    except ValueError:
        return 700_000


def assemble_project_sources(
    rows: List[tuple], max_chars: int = 700_000, min_chars: int = 500
) -> List[tuple]:
    """Group a project's raw chunks (url, content) into one source per file, in order.

    Returns [(text, [file_url])]; [] when the project is too small to matter or too big
    to read whole. Index-only text (generated questions) is dropped.
    """
    by_file: dict = {}
    order: List[str] = []
    total = 0
    for _url, content in rows:
        body, _, tail = (content or "").partition(_CITE_TAIL)
        body = body.partition(_RELATED_TAIL)[0].strip()
        cite = next(
            (c.strip() for c in tail.split(",") if c.strip().startswith("http")), ""
        )
        if not body or not cite:
            continue
        total += len(body)
        if total > max_chars:
            return []
        if cite not in by_file:
            by_file[cite] = []
            order.append(cite)
        by_file[cite].append(body)
    if total < min_chars:
        return []
    return [("\n".join(by_file[c]), [c]) for c in order]


def longctx_max_projects() -> int:
    try:
        return max(1, int(os.environ.get("OWASP_CX_LONGCTX_PROJECTS", "1")))
    except ValueError:
        return 1


def route_project(conn: Any, question: str) -> List[str]:
    """Slug of the one project whose overview best matches the question ([] if unsure)."""
    from application.database import db as db_mod
    from application.database.pgvector_utils import to_pgvector_literal
    from application.utils.comprehension.embedcache import embed_many
    from application.utils.comprehension.shared import shared_handler

    handler = shared_handler(db_mod.Node_collection())
    vec = embed_many([question], handler.get_text_embeddings)[0]
    hits = _dense(
        conn,
        to_pgvector_literal(list(vec)),
        "embeddings_url LIKE 'owasp-agent://evidence/comprehension-%-overview'",
        2,
    )
    if not hits:
        return []
    min_score = float(os.environ.get("OWASP_CX_PROJROUTE_MIN", "0.62"))
    margin = float(os.environ.get("OWASP_CX_PROJROUTE_MARGIN", "0.03"))
    second = hits[1].score if len(hits) > 1 else 0.0
    if hits[0].score < min_score or hits[0].score - second < margin:
        return []
    m = _SLUG_RE.match(hits[0].url)
    return [m.group(1)] if m else []


PICK_SYSTEM = (
    "You decide which single OWASP project a question is about. Candidates are numbered with a "
    'snippet of their text. Answer with JSON only: {"project": <candidate number or null>, '
    '"confidence": <0 to 1>}. Use null when the question could be about several candidates, '
    "about none of them, or does not make clear which project it means."
)
_PICK_STATE: "ContextVar[str]" = ContextVar("comprehension_pick", default="")


def last_pick() -> str:
    """Readable name of the project chosen by PICK for the current question ('' if none)."""
    return _PICK_STATE.get()


def pick_candidates(conn: Any, question: str, limit: int = 8) -> List[tuple]:
    """(slug, snippet) of the best-matching distinct projects, best first."""
    from application.database import db as db_mod
    from application.database.pgvector_utils import to_pgvector_literal
    from application.utils.comprehension.embedcache import embed_many
    from application.utils.comprehension.shared import shared_handler

    handler = shared_handler(db_mod.Node_collection())
    vec = embed_many([question], handler.get_text_embeddings)[0]
    hits = _dense(conn, to_pgvector_literal(list(vec)), docs_where(), 60)
    seen: dict = {}
    for h in hits:
        m = _SLUG_RE.match(h.url or "")
        if not m or m.group(1) in seen:
            continue
        body = (
            (h.content or "")
            .split("\n\nCitations:")[0]
            .split("\n\nRelated questions:")[0]
        )
        seen[m.group(1)] = " ".join(body.split())[:220]
        if len(seen) >= limit:
            break
    return list(seen.items())


def pick_project(conn: Any, question: str, llm: Any = None) -> str:
    """Slug of the project the question is about, chosen by a cheap model; '' when unsure."""
    from application.utils.comprehension import extras, flags

    llm = llm or flags.helper_llm()
    if llm is None:
        return ""
    cands = pick_candidates(conn, question)
    if len(cands) < 2:
        return ""
    menu = "\n".join(
        f"{i}. {alias_phrase(slug)}: {snippet}"
        for i, (slug, snippet) in enumerate(cands, 1)
    )
    try:
        data = extras.parse_json(
            llm(PICK_SYSTEM, f"Question: {question}\n\nCandidates:\n{menu}")
        )
        n = int(data.get("project"))
        conf = float(data.get("confidence") or 0)
    except Exception:  # noqa: BLE001 - null / malformed means "unsure"
        return ""
    if conf < float(os.environ.get("OWASP_CX_PICK_MIN", "0.7")) or not 1 <= n <= len(
        cands
    ):
        return ""
    return cands[n - 1][0]


def named_slugs(question: str, limit: int = 4) -> List[str]:
    """Repo slugs of the projects the question names (up to ``limit``); [] on any failure."""
    try:
        from application import sqla

        with sqla.session.get_bind().connect() as conn:
            return matched_slugs(question, _known_slugs(conn), limit=limit)
    except Exception:
        return []


def project_sources(question: str, max_projects: int | None = None) -> List[tuple]:
    """Whole text of the projects the question names (1..N); [] if none, too many or too big."""
    try:
        from sqlalchemy import text as sql_text

        from application import sqla

        limit = max_projects or longctx_max_projects()
        with sqla.session.get_bind().connect() as conn:
            slugs = matched_slugs(question, _known_slugs(conn), limit=limit + 1)
            _PICK_STATE.set("")
            if not slugs:
                from application.utils.comprehension import flags

                if flags.on("PROJROUTE"):
                    slugs = route_project(conn, question)
                elif flags.on("PICK"):
                    chosen = pick_project(conn, question)
                    if chosen:
                        slugs = [chosen]
                        _PICK_STATE.set(alias_phrase(chosen).title())
            if not slugs or len(slugs) > limit:
                return []
            rows: List[tuple] = []
            for slug in slugs:
                found = conn.execute(
                    sql_text(
                        "SELECT embeddings_url, embeddings_content FROM embeddings "
                        "WHERE source_channel = :channel AND embeddings_url LIKE :pat "
                        "ORDER BY embeddings_url"
                    ),
                    {
                        "channel": CHANNEL_AGENT,
                        "pat": f"owasp-agent://evidence/comprehension-{slug}-raw-%",
                    },
                ).fetchall()
                rows += [(r.embeddings_url, r.embeddings_content) for r in found]
        return assemble_project_sources(rows, max_chars=longctx_max_chars())
    except Exception:
        return []
