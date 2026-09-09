"""LLM service: enrich Node ``document_metadata.oie`` for neighbor transfer.

Writes verbose, path-B-friendly metadata (summaries, aliases, related topics)
onto existing hub standards (CCM, ASVS, Top10, NIST, …). Does **not** create
K8s/API Links — only makes organic neighbors easier to match dynamically.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]

DEFAULT_METADATA_MODEL = "gemini/gemini-2.5-pro"

# Standards we enrich for cross-catalog transfer (Node.name matchers).
DEFAULT_TARGET_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"cloud\s*controls\s*matrix", re.I),
    re.compile(r"^ASVS$", re.I),
    re.compile(r"owasp\s*top\s*10(?!.*\b(llm|api|ml)\b)", re.I),
    re.compile(r"nist\s*800-53", re.I),
    re.compile(r"cheat\s*sheets?", re.I),
    re.compile(r"proactive\s*controls", re.I),
    re.compile(r"ai\s*exchange", re.I),
    re.compile(r"top\s*10\s*for\s*llm", re.I),
)

_ENRICH_VERSION = 3


def default_metadata_llm_fn(model: Optional[str] = None) -> LlmFn:
    """LiteLLM completion for metadata enrichment (defaults to Gemini 2.5 Pro)."""
    model_name = model or os.environ.get(
        "CRE_LIBRARIAN_METADATA_MODEL",
        os.environ.get(
            "CRE_LIBRARIAN_EDITION_REMAP_MODEL",
            DEFAULT_METADATA_MODEL,
        ),
    )
    fallback = os.environ.get(
        "CRE_LIBRARIAN_METADATA_FALLBACK_MODEL",
        "gemini/gemini-2.5-flash",
    )

    def _once(name: str, system: str, user: str) -> str:
        import litellm

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            resp = litellm.completion(
                model=name,
                messages=messages,
                temperature=0.2,
                reasoning_effort="minimal",
            )
        except Exception:  # noqa: BLE001
            resp = litellm.completion(
                model=name,
                messages=messages,
                temperature=0.2,
            )
        return str(resp.choices[0].message.content or "")

    def _call(system: str, user: str) -> str:
        import time

        last_exc: Optional[BaseException] = None
        for attempt in range(4):
            try:
                return _once(model_name, system, user)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = str(exc).lower()
                if "503" in msg or "unavailable" in msg or "high demand" in msg:
                    time.sleep(2 ** attempt)
                    continue
                break
        if fallback and fallback != model_name:
            logger.warning(
                "metadata model %s failed (%s); falling back to %s",
                model_name,
                last_exc,
                fallback,
            )
            return _once(fallback, system, user)
        assert last_exc is not None
        raise last_exc

    return _call


def build_enrichment_prompt(
    *,
    standard_name: str,
    section_id: str,
    section_title: str,
    description: str = "",
) -> Tuple[str, str]:
    system = (
        "You enrich OpenCRE hub standard sections with verbose OIE metadata so a "
        "retrieval system can match brand-new catalogs (Kubernetes Top 10, API "
        "Top 10, etc.) to this section without hand-written CRE maps. "
        "Return ONLY JSON with keys: summary (string, 2-5 sentences), "
        "aliases (string array), phrases (string array), related_topics "
        "(string array), anti_topics (string array), applies_to (string array "
        "from: kubernetes, api, cloud, appsec, ai, auth, network, secrets, "
        "logging, supply_chain, configuration), transfer_hints (string array "
        "of catalog families e.g. owasp_k8s_top10, owasp_api_top10, "
        "owasp_top10, owasp_llm_top10). Be verbose and concrete; include "
        "synonyms practitioners use. Never invent CRE ids."
    )
    user = json.dumps(
        {
            "standard": standard_name,
            "section_id": section_id,
            "section_title": section_title,
            "description": (description or "")[:2000],
        },
        indent=2,
    )
    return system, user


def parse_enrichment_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("enrichment JSON must be an object")
    return data


def _as_str_list(val: Any, *, limit: int = 40) -> List[str]:
    if not isinstance(val, list):
        return []
    out: List[str] = []
    seen = set()
    for item in val:
        s = str(item or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def merge_oie_enrichment(
    existing: Mapping[str, Any],
    llm_blob: Mapping[str, Any],
    *,
    section_title: str = "",
) -> Dict[str, Any]:
    """Merge LLM enrichment into an existing ``oie`` block (non-destructive)."""
    out = dict(existing or {})
    summary = str(llm_blob.get("summary") or "").strip()
    if summary:
        out["summary"] = summary
    if section_title and not out.get("section_title"):
        out["section_title"] = section_title

    for key, lim in (
        ("aliases", 40),
        ("phrases", 50),
        ("related_topics", 40),
        ("anti_topics", 20),
        ("applies_to", 12),
        ("transfer_hints", 12),
    ):
        incoming = _as_str_list(llm_blob.get(key), limit=lim)
        prior = _as_str_list(out.get(key), limit=lim)
        merged: List[str] = []
        seen = set()
        for s in prior + incoming:
            k = s.lower()
            if k not in seen:
                seen.add(k)
                merged.append(s)
        if merged:
            out[key] = merged[:lim]

    out["enrichment_version"] = _ENRICH_VERSION
    out["enrichment_source"] = "llm_metadata_enricher"
    return out


def match_text_blob(oie: Mapping[str, Any]) -> str:
    """Flatten verbose oie fields into one match blob for title/topic scoring."""
    parts: List[str] = []
    for key in (
        "section_title",
        "summary",
        "aliases",
        "phrases",
        "related_topics",
        "applies_to",
        "transfer_hints",
    ):
        val = oie.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
        elif isinstance(val, list):
            parts.extend(str(x).strip() for x in val if x)
    return "\n".join(parts)


@dataclass
class MetadataEnrichmentStats:
    considered: int = 0
    enriched: int = 0
    skipped_rich: int = 0
    skipped_filter: int = 0
    errors: int = 0
    error_messages: List[str] = field(default_factory=list)


@dataclass
class MetadataEnrichmentService:
    """Populate ``Node.document_metadata.oie`` via LLM for neighbor transfer."""

    session: Any
    llm_fn: LlmFn
    target_patterns: Sequence[re.Pattern[str]] = field(
        default_factory=lambda: DEFAULT_TARGET_PATTERNS
    )
    force: bool = False
    dry_run: bool = False
    limit: int = 0  # 0 = no limit

    def _is_target(self, name: str) -> bool:
        return any(p.search(name or "") for p in self.target_patterns)

    def _already_rich(self, oie: Mapping[str, Any]) -> bool:
        if self.force:
            return False
        summary = str(oie.get("summary") or "").strip()
        ver = int(oie.get("enrichment_version") or 0)
        return bool(summary) and ver >= _ENRICH_VERSION

    def enrich_node(self, node: Any) -> bool:
        """Enrich one Node. Returns True if metadata changed (or would)."""
        from application.utils.librarian.oie_taxonomy import oie_block

        meta = dict(node.metadata_json or {}) if isinstance(node.metadata_json, dict) else {}
        oie = dict(oie_block(meta))
        if self._already_rich(oie):
            return False

        system, user = build_enrichment_prompt(
            standard_name=str(node.name or ""),
            section_id=str(node.section_id or ""),
            section_title=str(node.section or node.section_id or ""),
            description=str(getattr(node, "description", None) or ""),
        )
        raw = self.llm_fn(system, user)
        blob = parse_enrichment_json(raw)
        merged = merge_oie_enrichment(
            oie, blob, section_title=str(node.section or "")
        )
        meta["oie"] = merged
        if not self.dry_run:
            node.metadata_json = meta
        return True

    def run(self) -> MetadataEnrichmentStats:
        from application.database.db import Node

        stats = MetadataEnrichmentStats()
        q = self.session.query(Node).order_by(Node.name, Node.section_id)
        for node in q:
            if not self._is_target(str(node.name or "")):
                stats.skipped_filter += 1
                continue
            stats.considered += 1
            if self.limit and stats.enriched >= self.limit:
                break
            meta = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            from application.utils.librarian.oie_taxonomy import oie_block

            if self._already_rich(oie_block(meta)):
                stats.skipped_rich += 1
                continue
            try:
                changed = self.enrich_node(node)
                if changed:
                    stats.enriched += 1
                    if stats.enriched % 10 == 0:
                        if not self.dry_run:
                            self.session.commit()
                        logger.info("metadata enrich progress: %s", stats.enriched)
            except Exception as exc:  # noqa: BLE001
                stats.errors += 1
                msg = f"{node.name}|{node.section_id}: {exc}"
                stats.error_messages.append(msg)
                logger.warning("metadata enrich failed: %s", msg, exc_info=True)
                try:
                    self.session.rollback()
                except Exception:  # noqa: BLE001
                    pass
        if not self.dry_run:
            self.session.commit()
        return stats


__all__ = [
    "DEFAULT_METADATA_MODEL",
    "MetadataEnrichmentService",
    "MetadataEnrichmentStats",
    "build_enrichment_prompt",
    "default_metadata_llm_fn",
    "match_text_blob",
    "merge_oie_enrichment",
    "parse_enrichment_json",
]
