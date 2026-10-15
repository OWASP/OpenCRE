"""Hidden CRE summaries for Librarian C.2 (optional C.1 summary vectors).

Each CRE is summarized from its name/id/description plus linked Standard/Tool
``embeddings_content`` *prose* (junk chrome skipped via
``embedding_quality.usable_embedding_text``). The blurb is for the categorizer
pair text only — it is never written to public ``CRE.description``.

First-class store (preferred):
  ``CRE.document_metadata.oie.summary`` — hidden text
  ``CRE.document_metadata.oie.embedding_id`` — FK to ``embeddings.id``
  ``embeddings`` row with ``doc_type=CRE_SUMMARY`` (pgvector), never hub ``CRE``

JSON under ``CRE_LIBRARIAN_CRE_SUMMARY_CACHE`` remains an optional local/eval
cache and migration source. REST/UI must use ``public_cre_metadata`` /
``CREfromDB`` redaction so ``summary`` / ``embedding_id`` never leave the API.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from application.utils.librarian.cre_text import LinkedStandardRef
from application.utils.librarian.embedding_quality import (
    classify_content,
    usable_embedding_text,
)

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]
EmbedFn = Callable[[str], Sequence[float]]

DEFAULT_CACHE_DIR = "tmp/oie_cre_summaries"
DOC_TYPE_CRE_SUMMARY = "CRE_SUMMARY"
OIE_SUMMARY_KEY = "summary"
OIE_EMBEDDING_ID_KEY = "embedding_id"
OIE_PRIVATE_KEYS = frozenset({OIE_SUMMARY_KEY, OIE_EMBEDDING_ID_KEY})
# Linked prose budget for the LLM prompt (not MiniLM pair text).
MAX_LINKED_PROMPT_CHARS = 8000
MAX_LEAF_CHARS = 900
MAX_SUMMARY_CHARS = 1200

_SYSTEM = (
    "You write a hidden librarian blurb for OpenCRE retrieval and categorization. "
    "This text is NOT the public CRE.description and must never be treated as one. "
    "The CRE name is the topic. Linked Standard/Tool prose is supporting evidence. "
    "Do not redefine a broad CRE as a single NIST, PCI, or ASVS control. "
    "Summarize what the CRE is about in 2-4 concrete sentences using the CRE name "
    "and any linked Standard/Tool requirement prose. "
    "Ignore website chrome and scanner junk: NIST 'official website of the United "
    "States government' banners, skip-to-content navigation, JavaScript-disabled "
    "frame-buster pages, ZAP HUD/redirect warnings, ASVS nav dumps. "
    "Do not copy NIST/ASVS/ZAP chrome into the summary. Do not invent CRE ids. "
    'Return ONLY JSON: {"summary": "..."}.'
)


@dataclass(frozen=True)
class CreRecord:
    cre_id: str
    name: str
    description: str
    external_id: str = ""


def default_cache_dir() -> Optional[Path]:
    """Opt-in JSON cache dir only (unset → Postgres ``oie.summary`` only)."""
    raw = (os.environ.get("CRE_LIBRARIAN_CRE_SUMMARY_CACHE") or "").strip()
    return Path(raw) if raw else None


def public_cre_metadata(meta: Any) -> Dict[str, Any]:
    """Copy metadata with librarian-private ``oie`` keys removed for REST/UI."""
    if not isinstance(meta, Mapping):
        return {}
    out = dict(meta)
    oie = out.get("oie")
    if isinstance(oie, Mapping):
        redacted = {k: v for k, v in oie.items() if k not in OIE_PRIVATE_KEYS}
        out["oie"] = redacted
    return out


def read_oie_summary(meta: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(summary_text, embedding_id)`` from CRE ``document_metadata``."""
    if not isinstance(meta, Mapping):
        return None, None
    oie = meta.get("oie")
    if not isinstance(oie, Mapping):
        return None, None
    summary = str(oie.get(OIE_SUMMARY_KEY) or "").strip() or None
    emb_id = str(oie.get(OIE_EMBEDDING_ID_KEY) or "").strip() or None
    return summary, emb_id


def default_llm_fn(model: Optional[str] = None) -> LlmFn:
    """Same LiteLLM helper the metadata enricher already uses."""
    from application.utils.librarian.metadata_enricher import default_metadata_llm_fn

    return default_metadata_llm_fn(model)


def prose_leaves(refs: Sequence[LinkedStandardRef]) -> List[str]:
    """Linked Standard/Tool embeddings_content prose only — skip junk/stubs."""
    leaves: List[str] = []
    for ref in refs:
        body = usable_embedding_text(ref.prose)
        if not body or classify_content(body) != "prose":
            continue
        leaves.append(body)
    return leaves


def _record_lookup(cre_key: str, records: Mapping[str, CreRecord]) -> CreRecord:
    rec = records.get(cre_key)
    if rec is not None:
        return rec
    for candidate in records.values():
        if candidate.external_id == cre_key or candidate.cre_id == cre_key:
            return candidate
    return CreRecord(cre_id=cre_key, name="", description="", external_id=cre_key)


def _linked_for(
    cre_key: str, record: CreRecord, linked: Mapping[str, Sequence[LinkedStandardRef]]
) -> Sequence[LinkedStandardRef]:
    for key in (record.cre_id, cre_key, record.external_id):
        if key and key in linked:
            return linked[key]
    return ()


def build_summary_prompt(
    record: CreRecord,
    refs: Sequence[LinkedStandardRef] = (),
) -> Tuple[str, str]:
    """CRE name is always in the user prompt, even with no description/leaves."""
    packed = pack_linked_prose(prose_leaves(refs))
    user = json.dumps(
        {
            "cre_id": record.cre_id,
            "external_id": record.external_id,
            "name": record.name,
            "description": (record.description or "").strip(),
            "linked_prose": packed,
        },
        indent=2,
        ensure_ascii=False,
    )
    return _SYSTEM, user


def pack_linked_prose(leaves: Sequence[str]) -> List[str]:
    """Name stays in the JSON envelope; leaves are shortest-first and capped.

    Longest-first packing let one PCI/NIST dump fill the 8k budget and drop
    short distinctive titles (ISO 27001 8.5 vs PCI A3.4).
    """
    capped: List[str] = []
    for leaf in leaves:
        blob = (leaf or "").strip()
        if not blob:
            continue
        if len(blob) > MAX_LEAF_CHARS:
            blob = blob[:MAX_LEAF_CHARS].rstrip()
        capped.append(blob)
    packed: List[str] = []
    used = 0
    for leaf in sorted(capped, key=len):
        remaining = MAX_LINKED_PROMPT_CHARS - used
        if remaining <= 80:
            break
        piece = leaf if len(leaf) <= remaining else leaf[:remaining].rstrip()
        packed.append(piece)
        used += len(piece) + 1
    return packed


def parse_summary_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text[:MAX_SUMMARY_CHARS].strip()
    if isinstance(data, dict):
        summary = str(data.get("summary") or "").strip()
        return summary[:MAX_SUMMARY_CHARS]
    return text[:MAX_SUMMARY_CHARS].strip()


def apply_summaries_to_cre_texts(
    cre_texts: Mapping[str, str],
    summaries: Mapping[str, str],
) -> Dict[str, str]:
    """Replace C.2 pair text. Does not write public CRE.description."""
    out = dict(cre_texts)
    for cre_id, summary in summaries.items():
        blob = (summary or "").strip()
        if blob:
            out[cre_id] = blob
    return out


def _cache_file(cache_dir: Path, cre_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", cre_id) or "unknown"
    return cache_dir / f"{safe}.json"


def _load_cache(cache_dir: Optional[Path], cre_id: str) -> Optional[Dict[str, Any]]:
    if cache_dir is None:
        return None
    path = _cache_file(cache_dir, cre_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and str(data.get("summary") or "").strip():
        return data
    return None


def _write_cache(cache_dir: Optional[Path], payload: Mapping[str, Any]) -> None:
    if cache_dir is None:
        return
    cre_id = str(payload.get("cre_id") or "")
    if not cre_id:
        return
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_file(cache_dir, cre_id).write_text(
            json.dumps(dict(payload), indent=2, ensure_ascii=False)
        )
    except OSError:
        logger.debug("CRE summary cache write failed", exc_info=True)


def load_cre_records(database: object) -> Dict[str, CreRecord]:
    """``cre.id`` (and ``external_id``) → name/description. Read-only."""
    session = getattr(database, "session", None)
    if session is None:
        return {}
    try:
        from application.database.db import CRE
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, CreRecord] = {}
    for row in session.query(CRE.id, CRE.external_id, CRE.name, CRE.description).all():
        if not row.id:
            continue
        rec = CreRecord(
            cre_id=str(row.id),
            name=str(row.name or ""),
            description=str(row.description or ""),
            external_id=str(row.external_id or "").strip(),
        )
        out[rec.cre_id] = rec
        if rec.external_id:
            out[rec.external_id] = rec
    return out


def _load_summary_from_db(
    database: object, cre_id: str
) -> Tuple[Optional[str], Optional[str], Optional[List[float]]]:
    """Return ``(summary, embedding_id, vector_or_None)`` from Postgres metadata."""
    getter = getattr(database, "get_cre_oie_summary", None)
    if not callable(getter):
        return None, None, None
    try:
        return getter(cre_id)
    except Exception:  # noqa: BLE001
        logger.debug("CRE summary DB load failed for %s", cre_id, exc_info=True)
        return None, None, None


def _persist_summary_to_db(
    database: object,
    *,
    cre_id: str,
    summary: str,
    embedding: Optional[Sequence[float]] = None,
) -> Optional[str]:
    """Write ``oie.summary`` (+ optional ``CRE_SUMMARY`` embedding). Return embedding_id."""
    writer = getattr(database, "upsert_cre_oie_summary", None)
    if not callable(writer):
        return None
    try:
        return writer(cre_id, summary, embedding=embedding)
    except Exception:  # noqa: BLE001
        logger.warning("CRE summary DB persist failed for %s", cre_id, exc_info=True)
        return None


def inject_cre_summaries(
    *,
    cre_texts: Mapping[str, str],
    records: Mapping[str, CreRecord],
    linked: Mapping[str, Sequence[LinkedStandardRef]],
    llm_fn: Optional[LlmFn],
    cache_dir: Optional[Path] = None,
    embed_fn: Optional[EmbedFn] = None,
    database: Optional[object] = None,
) -> Tuple[Dict[str, str], Optional[Dict[str, List[float]]]]:
    """Fill C.2 texts from DB / JSON cache / LLM. Optional C.1 summary vectors.

    Preference order per CRE: Postgres ``oie.summary`` → JSON cache → LLM.
    When ``database`` is set, new summaries (and optional vectors) persist as
    ``oie.summary`` + ``embeddings(doc_type=CRE_SUMMARY)``; JSON cache is also
    written for local/eval reuse. Never writes ``CRE.description`` or hub
    ``doc_type=CRE`` embeddings. ``embed_fn`` failures yield ``vectors=None``
    (C.2-text-only) rather than a partial hub.
    """
    summaries: Dict[str, str] = {}
    cached_vectors: Dict[str, List[float]] = {}
    for cre_key in cre_texts:
        record = _record_lookup(cre_key, records)
        db_summary, _db_emb_id, db_vec = (None, None, None)
        if database is not None:
            db_summary, _db_emb_id, db_vec = _load_summary_from_db(
                database, record.cre_id
            )
            if not db_summary and cre_key != record.cre_id:
                db_summary, _db_emb_id, db_vec = _load_summary_from_db(
                    database, cre_key
                )
        if db_summary:
            summaries[cre_key] = db_summary
            if db_vec:
                cached_vectors[cre_key] = db_vec
            continue

        cached = _load_cache(cache_dir, record.cre_id) or _load_cache(
            cache_dir, cre_key
        )
        if cached is not None:
            summary = str(cached.get("summary") or "").strip()
            summaries[cre_key] = summary
            vec = cached.get("embedding")
            if (
                isinstance(vec, list)
                and vec
                and all(isinstance(x, (int, float)) for x in vec)
            ):
                cached_vectors[cre_key] = [float(x) for x in vec]
            if database is not None and summary:
                emb = cached_vectors.get(cre_key)
                _persist_summary_to_db(
                    database, cre_id=record.cre_id, summary=summary, embedding=emb
                )
            continue
        refs = _linked_for(cre_key, record, linked)
        summary = ""
        if llm_fn is not None:
            try:
                system, user = build_summary_prompt(record, refs)
                summary = parse_summary_text(llm_fn(system, user))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "CRE summary LLM failed for %s", record.cre_id, exc_info=True
                )
        if not summary:
            continue
        summaries[cre_key] = summary
        _write_cache(
            cache_dir,
            {
                "cre_id": record.cre_id,
                "external_id": record.external_id,
                "name": record.name,
                "summary": summary,
            },
        )
        if database is not None:
            _persist_summary_to_db(
                database, cre_id=record.cre_id, summary=summary, embedding=None
            )

    out = apply_summaries_to_cre_texts(cre_texts, summaries)
    if embed_fn is None:
        return out, None

    vectors: Dict[str, List[float]] = {}
    try:
        for cre_key, text in out.items():
            if cre_key in cached_vectors and len(cached_vectors[cre_key]) > 0:
                vectors[cre_key] = cached_vectors[cre_key]
                continue
            vec = list(embed_fn(text))
            if not vec:
                raise ValueError(f"empty embedding for {cre_key}")
            vectors[cre_key] = [float(x) for x in vec]
            record = _record_lookup(cre_key, records)
            cached = _load_cache(cache_dir, record.cre_id) or {
                "cre_id": record.cre_id,
                "external_id": record.external_id,
                "name": record.name,
                "summary": text,
            }
            if cached.get("summary"):
                cached["embedding"] = vectors[cre_key]
                _write_cache(cache_dir, cached)
            if database is not None:
                _persist_summary_to_db(
                    database,
                    cre_id=record.cre_id,
                    summary=str(cached.get("summary") or text),
                    embedding=vectors[cre_key],
                )
        widths = {len(v) for v in vectors.values()}
        if len(vectors) != len(out) or len(widths) != 1:
            logger.warning(
                "CRE summary in-memory embed incomplete (%s/%s, widths=%s); C.2-text-only",
                len(vectors),
                len(out),
                sorted(widths),
            )
            return out, None
    except Exception:  # noqa: BLE001
        logger.warning(
            "CRE summary in-memory embed failed; C.2-text-only", exc_info=True
        )
        return out, None
    return out, vectors


def migrate_json_cache_to_db(*, database: object, cache_dir: Path) -> int:
    """Copy JSON cache blurbs (+ optional vectors) into ``oie`` / ``CRE_SUMMARY``.

    Returns the number of CRE rows updated. Skips files without a usable summary
    or without a matching CRE id in the database.
    """
    if not cache_dir.is_dir():
        return 0
    n = 0
    for path in sorted(cache_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(data, Mapping):
            continue
        summary = str(data.get("summary") or "").strip()
        cre_id = str(data.get("cre_id") or "").strip()
        if not summary or not cre_id:
            continue
        emb_raw = data.get("embedding")
        embedding: Optional[List[float]] = None
        if (
            isinstance(emb_raw, list)
            and emb_raw
            and all(isinstance(x, (int, float)) for x in emb_raw)
        ):
            embedding = [float(x) for x in emb_raw]
        # ``upsert`` returns embedding_id, "" for text-only success, or None on miss/fail.
        result = _persist_summary_to_db(
            database, cre_id=cre_id, summary=summary, embedding=embedding
        )
        if result is not None:
            n += 1
    return n


__all__ = [
    "CreRecord",
    "DEFAULT_CACHE_DIR",
    "DOC_TYPE_CRE_SUMMARY",
    "MAX_LEAF_CHARS",
    "OIE_EMBEDDING_ID_KEY",
    "OIE_PRIVATE_KEYS",
    "OIE_SUMMARY_KEY",
    "apply_summaries_to_cre_texts",
    "build_summary_prompt",
    "pack_linked_prose",
    "default_cache_dir",
    "default_llm_fn",
    "inject_cre_summaries",
    "load_cre_records",
    "migrate_json_cache_to_db",
    "parse_summary_text",
    "prose_leaves",
    "public_cre_metadata",
    "read_oie_summary",
]
