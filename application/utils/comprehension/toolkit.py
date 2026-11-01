"""Read-only research tools for calling agents (MCP): search, list, read, overview.

They read the comprehension documents (raw source chunks and digests) so an
agent that loops and verifies on its own can see the evidence behind ``ask``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from application.utils.comprehension.retrieve import (
    _SLUG_RE,
    _dense,
    _known_slugs,
    alias_phrase,
    docs_where,
    matched_slugs,
)

_PATH_RE = re.compile(r"^[^/\n]+ / (.+?): ")
_CITE = "\n\nCitations:"
_RELATED = "\n\nRelated questions:"


def path_of(content: str) -> str:
    """Source file path from a raw document body ("family / path: text")."""
    m = _PATH_RE.match(content or "")
    return m.group(1) if m else ""


def body_of(content: str) -> str:
    """Document text without the citation tail."""
    return (content or "").split(_CITE)[0]


def resolve_slug(conn: Any, project: str) -> Optional[str]:
    """A repo slug from a name like "ASVS", "owasp-asvs" or "Web Security Testing Guide"."""
    slugs = _known_slugs(conn)
    key = re.sub(r"[^a-z0-9]+", "-", (project or "").lower()).strip("-")
    for s in slugs:
        if key in (s, s.replace("owasp-", "", 1), s.replace("owasp-www-project-", "")):
            return s
    found = matched_slugs(project or "", slugs, limit=1)
    return found[0] if found else None


def _rows(conn: Any, sql: str, **params: Any) -> List[Any]:
    from sqlalchemy import text as sql_text

    return conn.execute(sql_text(sql), params).fetchall()


def project_overview(conn: Any, project: str) -> Dict[str, Any]:
    slug = resolve_slug(conn, project)
    if not slug:
        return {"ok": False, "message": f"No indexed project matches {project!r}"}
    rows = _rows(
        conn,
        "SELECT embeddings_content FROM embeddings WHERE embeddings_url = :u LIMIT 1",
        u=f"owasp-agent://evidence/comprehension-{slug}-overview",
    )
    text = body_of(rows[0][0]) if rows else ""
    return {"ok": bool(text), "project": slug, "overview": text}


def list_project_docs(conn: Any, project: str) -> Dict[str, Any]:
    slug = resolve_slug(conn, project)
    if not slug:
        return {"ok": False, "message": f"No indexed project matches {project!r}"}
    rows = _rows(
        conn,
        "SELECT embeddings_content FROM embeddings WHERE embeddings_url LIKE :p",
        p=f"owasp-agent://evidence/comprehension-{slug}-raw-%",
    )
    counts: Dict[str, int] = {}
    for (content,) in rows:
        p = path_of(content)
        if p:
            counts[p] = counts.get(p, 0) + 1
    docs = [{"path": p, "chunks": n} for p, n in sorted(counts.items())]
    return {"ok": True, "project": slug, "documents": docs}


def get_source(
    conn: Any, project: str, path: str, max_chars: int = 20000
) -> Dict[str, Any]:
    slug = resolve_slug(conn, project)
    if not slug:
        return {"ok": False, "message": f"No indexed project matches {project!r}"}
    rows = _rows(
        conn,
        "SELECT embeddings_url, embeddings_content FROM embeddings "
        "WHERE embeddings_url LIKE :p ORDER BY embeddings_url",
        p=f"owasp-agent://evidence/comprehension-{slug}-raw-%",
    )
    parts = [body_of(c) for _, c in rows if path_of(c) == path]
    if not parts:
        return {"ok": False, "message": f"No document {path!r} in {slug}"}
    text = "\n\n".join(p.split(": ", 1)[-1] for p in parts)
    return {
        "ok": True,
        "project": slug,
        "path": path,
        "text": text[: int(max_chars)],
        "truncated": len(text) > int(max_chars),
        "url": f"https://github.com/{_repo_of(slug)}/blob/HEAD/{path}",
    }


def _repo_of(slug: str) -> str:
    return "OWASP/" + slug.replace("owasp-www-project-", "www-project-").replace(
        "owasp-", "", 1
    )


def search_sources(
    conn: Any, query: str, project: Optional[str] = None, k: int = 8
) -> Dict[str, Any]:
    from application.database import db as db_mod
    from application.database.pgvector_utils import to_pgvector_literal
    from application.utils.comprehension.embedcache import embed_many
    from application.utils.comprehension.shared import shared_handler

    where = docs_where()
    params: Dict[str, Any] = {}
    if project:
        slug = resolve_slug(conn, project)
        if not slug:
            return {"ok": False, "message": f"No indexed project matches {project!r}"}
        where += " AND embeddings_url LIKE :proj"
        params["proj"] = f"owasp-agent://evidence/comprehension-{slug}-%"
    handler = shared_handler(db_mod.Node_collection())
    vec = embed_many([query], handler.get_text_embeddings)[0]
    hits = _dense(
        conn, to_pgvector_literal(list(vec)), where, max(1, min(int(k), 25)), params
    )
    results = []
    for h in hits:
        m = _SLUG_RE.match(h.url)
        content = h.content or ""
        cites = content.split(_CITE)[1].strip() if _CITE in content else ""
        results.append(
            {
                "project": alias_phrase(m.group(1)) if m else "",
                "score": round(h.score, 3),
                "path": path_of(content),
                "snippet": body_of(content).split(_RELATED)[0][:700],
                "citations": [c.strip() for c in cites.split(",") if c.strip()],
            }
        )
    return {"ok": True, "query": query, "results": results}
