"""Hidden CRE summaries for Librarian C.2 (optional in-memory C.1).

Each CRE is summarized from its name/id/description plus linked Standard/Tool
``embeddings_content`` *prose* (junk chrome skipped via
``embedding_quality.usable_embedding_text``). The blurb is for the categorizer
pair text only — it is never written to public ``CRE.description``.
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
# Linked prose budget for the LLM prompt (not MiniLM pair text).
MAX_LINKED_PROMPT_CHARS = 8000
MAX_SUMMARY_CHARS = 1200

_SYSTEM = (
    "You write a hidden librarian blurb for OpenCRE retrieval and categorization. "
    "This text is NOT the public CRE.description and must never be treated as one. "
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


def default_cache_dir() -> Path:
    return Path(os.environ.get("CRE_LIBRARIAN_CRE_SUMMARY_CACHE", DEFAULT_CACHE_DIR))


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
    leaves = prose_leaves(refs)
    packed: List[str] = []
    used = 0
    for leaf in sorted(leaves, key=len, reverse=True):
        remaining = MAX_LINKED_PROMPT_CHARS - used
        if remaining <= 80:
            break
        piece = leaf if len(leaf) <= remaining else leaf[:remaining].rstrip()
        packed.append(piece)
        used += len(piece) + 1
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


def _load_cache(cache_dir: Path, cre_id: str) -> Optional[Dict[str, Any]]:
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


def _write_cache(cache_dir: Path, payload: Mapping[str, Any]) -> None:
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


def inject_cre_summaries(
    *,
    cre_texts: Mapping[str, str],
    records: Mapping[str, CreRecord],
    linked: Mapping[str, Sequence[LinkedStandardRef]],
    llm_fn: Optional[LlmFn],
    cache_dir: Path,
    embed_fn: Optional[EmbedFn] = None,
) -> Tuple[Dict[str, str], Optional[Dict[str, List[float]]]]:
    """Fill C.2 texts from cached/LLM summaries. Optional in-memory C.1 vectors.

    Never writes ``CRE.description``. ``embed_fn`` failures yield ``vectors=None``
    (C.2-text-only) rather than a partial hub.
    """
    summaries: Dict[str, str] = {}
    cached_vectors: Dict[str, List[float]] = {}
    for cre_key in cre_texts:
        record = _record_lookup(cre_key, records)
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
            cached = _load_cache(cache_dir, record.cre_id) or {}
            if cached.get("summary"):
                cached["embedding"] = vectors[cre_key]
                _write_cache(cache_dir, cached)
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


__all__ = [
    "CreRecord",
    "DEFAULT_CACHE_DIR",
    "apply_summaries_to_cre_texts",
    "build_summary_prompt",
    "default_cache_dir",
    "default_llm_fn",
    "inject_cre_summaries",
    "load_cre_records",
    "parse_summary_text",
    "prose_leaves",
]
