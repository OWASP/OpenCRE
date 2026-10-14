#!/usr/bin/env python3
"""Embed OWASP agent meta (+ evidence) into shared ``embeddings``.

Uses Gemini REST (urllib) by default to avoid litellm/Flask OOM on small dynos.
Falls back to litellm when ``OWASP_AGENT_EMBED_VIA=litellm``.

  PYTHONPATH=. python scripts/owasp_agent_embed_meta.py
  PYTHONPATH=. python scripts/owasp_agent_embed_meta.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Sequence

from sqlalchemy import create_engine, text


def _db_url() -> str:
    raw = (
        (os.environ.get("DATABASE_URL") or "").strip()
        or (os.environ.get("DEV_DATABASE_URL") or "").strip()
    )
    if not raw:
        raise SystemExit("DATABASE_URL / DEV_DATABASE_URL required")
    try:
        from application.utils.postgres_url import (
            is_postgres_url,
            sqlalchemy_postgres_url,
        )

        if is_postgres_url(raw):
            return sqlalchemy_postgres_url(raw)
    except Exception:
        if raw.startswith("postgres://"):
            return "postgresql+psycopg2://" + raw.split("://", 1)[1]
        if raw.startswith("postgresql://"):
            return "postgresql+psycopg2://" + raw.split("://", 1)[1]
    return raw


def _to_pgvector(vec: Sequence[float]) -> str:
    try:
        from application.database.pgvector_utils import to_pgvector_literal

        return to_pgvector_literal(list(vec))
    except Exception:
        return "[" + ",".join(str(float(x)) for x in vec) + "]"


def _embed_gemini_rest(text_in: str) -> List[float]:
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required for REST embed path")
    model = (os.environ.get("CRE_EMBED_MODEL") or "gemini-embedding-001").strip()
    if model.startswith("gemini/"):
        model = model.split("/", 1)[1]
    if not model.startswith("models/"):
        model = "models/" + model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/{model}"
        f":embedContent?key={api_key}"
    )
    body = json.dumps(
        {
            "model": model,
            "content": {"parts": [{"text": text_in[:8000]}]},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"gemini embed HTTP {e.code}: {detail}") from e
    return [float(x) for x in data["embedding"]["values"]]


def _embed_litellm(text_in: str) -> List[float]:
    from application.prompt_client import litellm_router

    model = (os.environ.get("CRE_EMBED_MODEL") or "").strip() or (
        "gemini/gemini-embedding-001"
    )
    resp = litellm_router.embedding(model=model, input=[text_in])
    vecs = litellm_router.extract_embeddings(resp)
    if not vecs or not vecs[0]:
        raise RuntimeError("empty embedding")
    return list(vecs[0])


def _embed_factory() -> Callable[[str], List[float]]:
    via = (os.environ.get("OWASP_AGENT_EMBED_VIA") or "rest").strip().lower()
    if via == "litellm":
        return _embed_litellm
    return _embed_gemini_rest


def _text_for_row(kind: str, key: str, name: str, payload: Dict[str, Any]) -> str:
    try:
        from application.utils.owasp_agent.meta_embeddings import text_for_meta_entity

        row = dict(payload)
        row.update(
            {"kind": kind, "key": key, "name": name or payload.get("name") or ""}
        )
        return text_for_meta_entity(row)
    except Exception:
        bits = [f"OWASP {kind}: {name}", f"key={key}"]
        for field in (
            "description",
            "level",
            "url",
            "group",
            "city",
            "country",
            "role",
            "year",
            "statement",
        ):
            if payload.get(field):
                bits.append(f"{field}: {payload[field]}")
        leaders = payload.get("leaders")
        if isinstance(leaders, list) and leaders:
            bits.append("leaders: " + ", ".join(str(x) for x in leaders if x))
        return "\n".join(bits)


def _upsert(
    conn,
    *,
    url: str,
    doc_type: str,
    content: str,
    vec: Sequence[float],
    model_id: str,
) -> None:
    literal = _to_pgvector(vec)
    dim = len(vec)
    existing = conn.execute(
        text(
            "SELECT id FROM embeddings "
            "WHERE embeddings_url = :url AND source_channel = 'owasp_agent_meta' "
            "LIMIT 1"
        ),
        {"url": url},
    ).fetchone()
    if existing:
        conn.execute(
            text(
                "UPDATE embeddings SET embeddings_content=:c, doc_type=:d, "
                "embedding_model_id=:m, embedding_dim=:dim, "
                "embedding_vec=CAST(:v AS vector) "
                "WHERE id=:id"
            ),
            {
                "c": content,
                "d": doc_type,
                "m": model_id,
                "dim": dim,
                "v": literal,
                "id": existing.id,
            },
        )
    else:
        conn.execute(
            text(
                "INSERT INTO embeddings "
                "(id, doc_type, cre_id, node_id, embeddings_url, embeddings_content, "
                "embedding_model_id, embedding_dim, embedding_vec, source_channel) "
                "VALUES (:id, :d, NULL, NULL, :url, :c, :m, :dim, CAST(:v AS vector), "
                "'owasp_agent_meta')"
            ),
            {
                "id": str(uuid.uuid4()),
                "d": doc_type,
                "url": url,
                "c": content,
                "m": model_id,
                "dim": dim,
                "v": literal,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-evidence", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Commit every N meta rows (default 10)",
    )
    args = parser.parse_args()

    try:
        from application.utils.owasp_agent.meta_embeddings import (
            DOC_TYPE_EVIDENCE,
            DOC_TYPE_META,
            evidence_documents,
            evidence_url,
            meta_entity_url,
        )
    except Exception:
        DOC_TYPE_META = "OWASP_AGENT_META"
        DOC_TYPE_EVIDENCE = "OWASP_AGENT_EVIDENCE"

        def meta_entity_url(kind: str, key: str, source: str) -> str:
            return f"owasp-agent://meta/{kind}/{key}/{source}"

        def evidence_url(slug: str) -> str:
            return f"owasp-agent://evidence/{slug}"

        def evidence_documents():
            return []

    embed = _embed_factory()
    model_id = (os.environ.get("CRE_EMBED_MODEL") or "").strip() or (
        "gemini-embedding-001"
    )
    engine = create_engine(_db_url(), pool_pre_ping=True)
    written = 0
    skipped = 0
    kinds = (
        "chapter",
        "project",
        "project_leader",
        "board_member",
        "board_candidate",
        "event",
        "person",
        "membership_country",
    )
    batch_size = max(1, int(args.batch_size))

    for kind in kinds:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT kind, key, name, source, payload FROM meta_entity "
                    "WHERE kind = :k"
                ),
                {"k": kind},
            ).fetchall()
        print(f"meta kind={kind} rows={len(rows)}", flush=True)
        pending: List[Dict[str, Any]] = []

        def flush() -> None:
            if not pending:
                return
            with engine.begin() as conn:
                for item in pending:
                    _upsert(conn, **item)
            pending.clear()

        for row in rows:
            if args.limit and written >= args.limit:
                break
            payload_raw = row.payload
            try:
                payload = json.loads(payload_raw) if payload_raw else {}
            except json.JSONDecodeError:
                payload = {"raw": payload_raw}
            key = str(row.key or "")
            if not key:
                skipped += 1
                continue
            content = _text_for_row(kind, key, str(row.name or ""), payload)
            if not content.strip():
                skipped += 1
                continue
            url = meta_entity_url(kind, key, str(row.source or "site"))
            try:
                vec = embed(content)
            except Exception as e:
                print(
                    f"embed_fail {kind}/{key}: {type(e).__name__}: {e}",
                    flush=True,
                )
                skipped += 1
                continue
            pending.append(
                {
                    "url": url,
                    "doc_type": DOC_TYPE_META,
                    "content": content,
                    "vec": vec,
                    "model_id": model_id,
                }
            )
            written += 1
            if len(pending) >= batch_size:
                flush()
                print(f"  written={written}", flush=True)
        flush()
        if args.limit and written >= args.limit:
            break

    evidence_n = 0
    if not args.skip_evidence:
        docs = list(evidence_documents())
        if not docs:
            docs = [
                (
                    "lethal-trifecta",
                    (
                        "According to the OWASP AI Exchange, for leaking sensitive "
                        "data in agentic AI you need three things together (the "
                        "lethal trifecta): (1) attacker-influenced data that "
                        "reaches the model (often via indirect prompt injection), "
                        "(2) access of that model or connected agents to sensitive "
                        "data, and (3) the ability to send data out to an attacker. "
                        "The impact is data exfiltration. Removing any one leg "
                        "blocks the attack path.\n\nTopics: lethal trifecta"
                    ),
                    ["https://owaspai.org/docs/ai_security_overview/"],
                )
            ]
        with engine.begin() as conn:
            for slug, embed_text, citations in docs:
                body = embed_text
                if citations:
                    body += "\n\nCitations: " + ", ".join(citations)
                url = evidence_url(slug)
                vec = embed(body)
                _upsert(
                    conn,
                    url=url,
                    doc_type=DOC_TYPE_EVIDENCE,
                    content=body,
                    vec=vec,
                    model_id=model_id,
                )
                evidence_n += 1
                print(f"evidence_ok {slug}", flush=True)

    print(
        "owasp_agent_embed_meta",
        {
            "meta": written,
            "evidence": evidence_n if not args.skip_evidence else 0,
            "skipped": skipped,
        },
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
