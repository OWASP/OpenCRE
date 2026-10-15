"""Embed OWASP agent meta (+ optional evidence notes) into shared ``embeddings``.

Rows use ``source_channel='owasp_agent_meta'``, nullable cre/node FKs, and a
stable ``embeddings_url`` key for upsert. Curated factoid text is stored as
*evidence* (same channel) — scored by similarity, never used as a keyword
classifier.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from application.utils.owasp_agent.aix_facts import AIX_FACTOIDS
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT

EmbedFn = Callable[[str], Sequence[float]]

DOC_TYPE_META = "OWASP_AGENT_META"
DOC_TYPE_EVIDENCE = "OWASP_AGENT_EVIDENCE"


def meta_entity_url(kind: str, key: str, source: str) -> str:
    return f"owasp-agent://meta/{kind}/{key}/{source}"


def evidence_url(slug: str) -> str:
    return f"owasp-agent://evidence/{slug}"


def text_for_meta_entity(row: Dict[str, Any]) -> str:
    kind = str(row.get("kind") or "")
    key = str(row.get("key") or "")
    name = str(row.get("name") or "")
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"raw": payload}
    if not isinstance(payload, dict):
        payload = {}
    # list_entities returns the payload dict itself (fields at top level).
    merged = {**payload, **{k: v for k, v in row.items() if k != "payload"}}
    # Prefer prebuilt ontology prose when present (board_roster cards).
    prebuilt = str(merged.get("embed_text") or merged.get("message") or "").strip()
    if prebuilt and kind in ("board_roster",):
        return prebuilt
    bits = [f"OWASP {kind}: {name}".strip(), f"key={key}"]
    for field in (
        "description",
        "level",
        "url",
        "group",
        "city",
        "country",
        "region",
        "role",
        "year",
        "statement",
        "email",
    ):
        val = merged.get(field)
        if val:
            bits.append(f"{field}: {val}")
    leaders = merged.get("leaders")
    if isinstance(leaders, list) and leaders:
        bits.append("leaders: " + ", ".join(str(x) for x in leaders if x))
    tags = merged.get("tags")
    if isinstance(tags, list) and tags:
        bits.append("tags: " + ", ".join(str(x) for x in tags if x))
    # Chapter paraphrase anchors for retrieve (no keyword router at ask time).
    if kind == "chapter":
        city = str(merged.get("city") or "").strip()
        country = str(merged.get("country") or "").strip()
        short = name.replace("OWASP", "").strip() or key.replace("-", " ")
        topics = [
            f"OWASP {short} chapter",
            f"What is the OWASP {short} chapter",
            f"{short} chapter",
        ]
        if city:
            topics.append(f"chapter in {city}")
            topics.append(f"OWASP chapter {city}")
        if country:
            topics.append(f"OWASP chapter {country}")
        bits.append("Topics: " + ", ".join(topics))
    return "\n".join(bits)


_BOARD_HISTORY_URL = (
    "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml"
)


def materialize_board_ontology(store: IndexStore) -> int:
    """Write board_roster cards into the agent index (ontology in data, not code).

    Built from indexed ``board_member`` rows so chat/retrieve answer from corpus
    cards instead of assembling rosters in query methods.
    """
    members = store.list_entities("board_member") or []
    by_year: Dict[int, List[Dict[str, Any]]] = {}
    for m in members:
        try:
            year = int(m.get("year") or 0)
        except (TypeError, ValueError):
            year = 0
        if year:
            by_year.setdefault(year, []).append(dict(m))
    written = 0
    for year, rows in sorted(by_year.items()):
        names = sorted(
            {str(r.get("name") or "").strip() for r in rows if r.get("name")}
        )
        if not names:
            continue
        msg = f"OWASP board members for {year}: " + ", ".join(names) + "."
        embed_text = "\n".join(
            [
                f"OWASP board roster for {year}",
                f"OWASP board members in {year}: {', '.join(names)}",
                msg,
                (
                    "Topics: OWASP board, board roster, board members, board history, "
                    f"board for {year}, tell me about OWASP board, "
                    "OWASP foundation board of directors"
                ),
            ]
        )
        store.upsert_entity(
            kind="board_roster",
            key=str(year),
            name=f"OWASP Board {year}",
            source="github",
            payload={
                "key": str(year),
                "name": f"OWASP Board {year}",
                "kind": "board_roster",
                "source": "github",
                "year": year,
                "members": names,
                "message": msg,
                "embed_text": embed_text,
                "url": _BOARD_HISTORY_URL,
            },
        )
        written += 1
    if by_year:
        latest = max(by_year)
        names = sorted(
            {str(r.get("name") or "").strip() for r in by_year[latest] if r.get("name")}
        )
        msg = (
            "The OWASP board is the foundation board of directors. "
            f"Latest indexed year {latest}: " + ", ".join(names) + "."
        )
        embed_text = "\n".join(
            [
                "OWASP board overview",
                "Tell me about OWASP board",
                "Tell me about the OWASP board at OWASP",
                msg,
                (
                    "Topics: OWASP board, board history, board members, "
                    "foundation board, board of directors, board roster"
                ),
            ]
        )
        store.upsert_entity(
            kind="board_roster",
            key="overview",
            name="OWASP Board",
            source="github",
            payload={
                "key": "overview",
                "name": "OWASP Board",
                "kind": "board_roster",
                "source": "github",
                "year": latest,
                "members": names,
                "message": msg,
                "embed_text": embed_text,
                "url": _BOARD_HISTORY_URL,
            },
        )
        written += 1
    return written


def evidence_documents() -> List[Tuple[str, str, List[str]]]:
    """Return (slug, embed_text, citations) for optional evidence notes."""
    out: List[Tuple[str, str, List[str]]] = []
    for keys, message, citations in AIX_FACTOIDS:
        slug = "-".join(k.replace(" ", "-") for k in keys)
        # Broad paraphrase anchors so retrieve finds AIX notes without intent code.
        topic_bits = list(keys) + [
            "lethal trifecta",
            "agentic AI",
            "OWASP AI Exchange",
            "AI Exchange",
            "prompt injection",
            "exfiltration",
            "sensitive data",
            "data leakage",
            "three things together",
        ]
        embed_text = message + "\n\nTopics: " + ", ".join(dict.fromkeys(topic_bits))
        out.append((slug, embed_text, list(citations)))
    return out


def upsert_channel_embedding(
    database: Any,
    *,
    source_channel: str,
    doc_type: str,
    embeddings_url: str,
    embedding_text: str,
    embeddings: Sequence[float],
) -> Any:
    """Insert/update an embeddings row keyed by ``embeddings_url`` + channel."""
    from application.database import db as db_mod
    from application.database.pgvector_utils import (
        require_embedding_vec_store,
        to_pgvector_literal,
    )

    session = database.session
    require_embedding_vec_store(session.get_bind(), context="upsert_channel_embedding")
    model_id = (os.environ.get("CRE_EMBED_MODEL", "") or "").strip() or (
        "gemini/gemini-embedding-001"
    )
    dim = len(embeddings)
    expected_raw = (os.environ.get("CRE_EMBED_EXPECTED_DIM", "") or "").strip()
    if expected_raw and dim != int(expected_raw):
        raise ValueError(
            f"embedding dimension mismatch for {embeddings_url}: "
            f"expected {expected_raw}, got {dim}"
        )
    literal = to_pgvector_literal(list(embeddings))
    existing = (
        session.query(db_mod.Embeddings)
        .filter_by(embeddings_url=embeddings_url, source_channel=source_channel)
        .all()
    )
    if existing:
        emb = existing[0]
        # Skip LLM waste if content unchanged (caller may still re-embed).
        emb.embeddings_content = embedding_text
        emb.doc_type = doc_type
        emb.embedding_model_id = model_id
        emb.embedding_dim = dim
        emb.embedding_vec = literal
        emb.source_channel = source_channel
        session.commit()
        return emb
    emb = db_mod.Embeddings(
        doc_type=doc_type,
        cre_id=None,
        node_id=None,
        embeddings_url=embeddings_url,
        embeddings_content=embedding_text,
        embedding_model_id=model_id,
        embedding_dim=dim,
        embedding_vec=literal,
        source_channel=source_channel,
    )
    session.add(emb)
    session.commit()
    return emb


def sync_meta_embeddings(
    store: IndexStore,
    database: Any,
    embed_fn: EmbedFn,
    *,
    include_evidence: bool = True,
) -> Dict[str, int]:
    """Embed all meta_entity rows (+ optional evidence) into shared embeddings."""
    # Ensure board roster ontology cards exist before embedding.
    try:
        materialize_board_ontology(store)
    except Exception:
        pass
    written = 0
    skipped = 0
    kinds = (
        "chapter",
        "project",
        "project_leader",
        "board_member",
        "board_candidate",
        "board_roster",
        "event",
        "person",
    )
    for kind in kinds:
        try:
            items = store.list_entities(kind) or []
        except Exception:
            continue
        print(f"meta kind={kind} rows={len(items)}", flush=True)
        for item in items:
            row = dict(item)
            row["kind"] = kind
            key = str(row.get("key") or "")
            source = str(row.get("source") or row.get("_index_source") or "site")
            if not key:
                # Leaders sometimes key by name::group in store; fall back to name.
                key = str(row.get("name") or "").strip().lower()
            if not key:
                skipped += 1
                continue
            row["key"] = key
            url = meta_entity_url(kind, key, source)
            text = text_for_meta_entity(row)
            if not text.strip():
                skipped += 1
                continue
            vec = list(embed_fn(text))
            upsert_channel_embedding(
                database,
                source_channel=CHANNEL_AGENT,
                doc_type=DOC_TYPE_META,
                embeddings_url=url,
                embedding_text=text,
                embeddings=vec,
            )
            written += 1
            if written % 25 == 0:
                print(f"  written={written}", flush=True)

    evidence_n = 0
    if include_evidence:
        for slug, embed_text, citations in evidence_documents():
            url = evidence_url(slug)
            # Stash citations in content footer for retrieval display.
            body = embed_text
            if citations:
                body += "\n\nCitations: " + ", ".join(citations)
            vec = list(embed_fn(body))
            upsert_channel_embedding(
                database,
                source_channel=CHANNEL_AGENT,
                doc_type=DOC_TYPE_EVIDENCE,
                embeddings_url=url,
                embedding_text=body,
                embeddings=vec,
            )
            evidence_n += 1

    return {"meta": written, "evidence": evidence_n, "skipped": skipped}
