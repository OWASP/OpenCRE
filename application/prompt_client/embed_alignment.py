"""
Smart embedding excerpt alignment (RFC: docs/rfc/improve-embedding-accuracy.md).

Builds DOM blocks from fetched HTML, asks an LLM to pick the span that best matches
the node's section / subsection / section_id, validates URL fragments, and returns
excerpt text plus a resolved ``embeddings_url`` (``hyperlink`` is never modified here).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urldefrag
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

SMART_EXTRACT_POLICY_VERSION = os.environ.get("CRE_EMBED_SMART_POLICY_VERSION", "1")

DEFAULT_FRAGMENT_ID_DENYLIST = frozenset(
    {
        "search-toggle",
        "searchOverlay",
        "search-close",
        "mobileMenu",
        "pagefind-search",
        "TableOfContents",
        "contact-form",
        "contact-form-desktop",
        "contact-form-mobile",
        "main",
    }
)


@dataclass
class AlignmentResult:
    start_bid: str
    end_bid: str
    suggested_fragment: Optional[str]
    confidence: float
    should_fallback_full_page: bool
    rationale: str


@dataclass
class SmartExtractOutcome:
    """Result of smart extract for one node (``on`` or ``shadow`` mode)."""

    embed_plain_text: str
    resolved_embeddings_url: str
    rationale: str
    used_excerpt: bool
    shadow_only: bool
    marker_start_bid: str = ""
    marker_end_bid: str = ""


class AlignmentPayload(BaseModel):
    """
    Strict schema for LLM alignment output.

    This keeps provider output deterministic and lets us fail closed to full-page
    fallback when malformed JSON slips through.
    """

    model_config = ConfigDict(extra="ignore")

    start_bid: str = Field(pattern=r"^b\d+$")
    end_bid: str = Field(pattern=r"^b\d+$")
    suggested_fragment: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    should_fallback_full_page: bool
    rationale: str = ""


def alignment_response_json_schema() -> Dict[str, Any]:
    """
    Provider-friendly JSON schema for strict structured outputs.
    """
    return AlignmentPayload.model_json_schema()


def _denylist_ids() -> Set[str]:
    extra = os.environ.get("CRE_EMBED_FRAGMENT_ID_DENYLIST", "")
    parts = {p.strip().lower() for p in extra.split(",") if p.strip()}
    return set(DEFAULT_FRAGMENT_ID_DENYLIST) | parts


def normalize_page_cache_key(url: str) -> str:
    base, _frag = urldefrag(url.strip())
    return base.lower().rstrip("/")


def html_body_inner_text(html: str) -> str:
    """Plain text of ``body`` from HTML (same role as Playwright ``body.inner_text``)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    if not body:
        return ""
    return body.get_text(" ", strip=True)


def section_key_from_node(node: Any) -> str:
    """Stable key for alignment cache: same URL + same key shares one LLM result."""
    name = getattr(node, "name", None) or ""
    section = getattr(node, "section", None) or ""
    subsection = getattr(node, "subsection", None) or ""
    sid = getattr(node, "sectionID", None) or getattr(node, "section_id", None) or ""
    parts = (str(name), str(section), str(subsection), str(sid))
    return json.dumps(parts, sort_keys=False, separators=(",", ":"))


def _parse_bid(bid: str) -> Optional[int]:
    bid = (bid or "").strip().lower()
    if bid.startswith("b") and bid[1:].isdigit():
        return int(bid[1:])
    return None


def _collect_fragment_targets(soup: Any) -> Set[str]:
    """Valid URL fragment targets: element ``id`` and ``a name`` (HTML4)."""
    from bs4 import BeautifulSoup  # lazy

    if not isinstance(soup, BeautifulSoup):
        return set()
    targets: Set[str] = set()
    deny = _denylist_ids()
    for tag in soup.find_all(True):
        tid = tag.get("id")
        if tid and str(tid).strip():
            t = str(tid).strip()
            if t.lower() not in deny:
                targets.add(t)
        nm = tag.get("name")
        if nm and tag.name == "a" and str(nm).strip():
            targets.add(str(nm).strip())
    return targets


def build_blocks_from_html(html: str) -> Tuple[List[Dict[str, str]], Set[str]]:
    """
    Linear blocks with stable ``bid`` for LLM selection.

    Each block is primarily one element with an ``id`` (content sections).
    Returns (blocks, valid_fragment_ids).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("#main") or soup.body
    if not root:
        return [], set()

    valid_targets = _collect_fragment_targets(soup)
    deny = _denylist_ids()
    blocks: List[Dict[str, str]] = []

    for el in root.find_all(True):
        if not getattr(el, "name", None) or el.name in ("script", "style", "noscript"):
            continue
        tid = el.get("id")
        if not tid:
            continue
        tid_s = str(tid).strip()
        if not tid_s or tid_s.lower() in deny:
            continue
        text = el.get_text(" ", strip=True)
        if len(text) < 12:
            continue
        bid = f"b{len(blocks)}"
        blocks.append(
            {
                "bid": bid,
                "tag": el.name or "",
                "fragment": tid_s,
                "text": text[:6000],
            }
        )

    return blocks, valid_targets


def _alignment_system_prompt() -> str:
    return (
        "You map OpenCRE standard rows to ONE contiguous span of HTML-derived blocks. "
        "English only. Prefer the structural SECTION whose heading and body are ABOUT the "
        "catalogued control—not the first paragraph that merely mentions the same words "
        "(e.g. overview or TOC). "
        "Return ONLY valid JSON with keys: start_bid, end_bid, suggested_fragment (string or null), "
        "confidence (0-1 number), should_fallback_full_page (boolean), rationale (short string). "
        "start_bid and end_bid must be block ids from the user message (e.g. b0, b3). "
        "If uncertain or blocks are a poor fit, set should_fallback_full_page true. "
        "suggested_fragment must equal the fragment id of the START of the intended section "
        "(the `fragment` field of that block), without a leading #, or null if none applies."
    )


def _alignment_user_payload(node: Any, blocks: List[Dict[str, str]]) -> str:
    labels = {
        "standard_name": getattr(node, "name", "") or "",
        "section": getattr(node, "section", "") or "",
        "subsection": getattr(node, "subsection", "") or "",
        "section_id": getattr(node, "sectionID", None)
        or getattr(node, "section_id", None)
        or "",
    }
    lines = [
        "NODE_LABELS_JSON:\n" + json.dumps(labels, ensure_ascii=False, indent=2),
        "\nBLOCKS (each line: bid | tag | fragment | text preview):",
    ]
    for b in blocks:
        frag = b.get("fragment") or ""
        lines.append(
            f"{b['bid']} | {b.get('tag','')} | {frag} | {b.get('text','')[:3500]}"
        )
    return "\n".join(lines)


def _call_alignment_llm(ai_client: Any, system: str, user: str) -> AlignmentResult:
    raw: Dict[str, Any]
    if hasattr(ai_client, "align_embedding_span_json"):
        raw = ai_client.align_embedding_span_json(system, user)
    else:
        raise RuntimeError("ai_client must implement align_embedding_span_json")

    try:
        payload = AlignmentPayload.model_validate(raw)
    except ValidationError as e:
        raise RuntimeError(f"invalid alignment payload: {e}") from e

    start_bid = payload.start_bid
    end_bid = payload.end_bid
    conf = payload.confidence
    frag = payload.suggested_fragment
    if frag is not None:
        frag = str(frag).strip().lstrip("#") or None
    fb = payload.should_fallback_full_page
    rationale = payload.rationale[:500]
    return AlignmentResult(
        start_bid=start_bid,
        end_bid=end_bid,
        suggested_fragment=frag,
        confidence=conf,
        should_fallback_full_page=fb,
        rationale=rationale,
    )


def _concat_excerpt(blocks: List[Dict[str, str]], start_bid: str, end_bid: str) -> str:
    si = _parse_bid(start_bid)
    ei = _parse_bid(end_bid)
    if si is None or ei is None:
        return ""
    if si > ei:
        si, ei = ei, si
    parts: List[str] = []
    for b in blocks:
        idx = _parse_bid(b["bid"])
        if idx is None:
            continue
        if si <= idx <= ei:
            parts.append(b.get("text") or "")
    return " ".join(parts).strip()


def _resolved_url(base_hyperlink: str, fragment: Optional[str]) -> str:
    base, _existing = urldefrag(base_hyperlink.strip())
    if fragment:
        return f"{base}#{fragment}"
    return base


def run_smart_extract(
    *,
    html: str,
    full_cleaned_body_text: str,
    node: Any,
    ai_client: Any,
    mode: str,
    page_cache_key: str,
    alignment_cache: Dict[Tuple[str, str], AlignmentResult],
    confidence_threshold: float,
) -> SmartExtractOutcome:
    """
    ``mode`` is ``on`` or ``shadow`` (caller handles ``off``).

    ``shadow``: same LLM + validation logic; embedding text should still be full page
    (caller passes ``full_cleaned_body_text`` into embed path); we set ``shadow_only``.
    """
    blocks, valid_frags = build_blocks_from_html(html)
    base_url = urldefrag((getattr(node, "hyperlink", None) or "").strip())[0]

    if len(blocks) < 1:
        return SmartExtractOutcome(
            embed_plain_text=full_cleaned_body_text,
            resolved_embeddings_url=base_url
            or (getattr(node, "hyperlink", None) or ""),
            rationale="no_blocks",
            used_excerpt=False,
            shadow_only=(mode == "shadow"),
            marker_start_bid="",
            marker_end_bid="",
        )

    skey = section_key_from_node(node)
    cache_key = (page_cache_key, skey)
    if cache_key in alignment_cache:
        align = alignment_cache[cache_key]
    else:
        try:
            align = _call_alignment_llm(
                ai_client,
                _alignment_system_prompt(),
                _alignment_user_payload(node, blocks),
            )
        except Exception as e:
            logger.warning("Smart extract LLM failed: %s", e)
            return SmartExtractOutcome(
                embed_plain_text=full_cleaned_body_text,
                resolved_embeddings_url=base_url
                or (getattr(node, "hyperlink", None) or ""),
                rationale=f"llm_error:{e!s}"[:200],
                used_excerpt=False,
                shadow_only=(mode == "shadow"),
                marker_start_bid="",
                marker_end_bid="",
            )
        alignment_cache[cache_key] = align

    if align.should_fallback_full_page or align.confidence < confidence_threshold:
        return SmartExtractOutcome(
            embed_plain_text=full_cleaned_body_text,
            resolved_embeddings_url=base_url
            or (getattr(node, "hyperlink", None) or ""),
            rationale=align.rationale or "fallback_low_confidence",
            used_excerpt=False,
            shadow_only=(mode == "shadow"),
            marker_start_bid="",
            marker_end_bid="",
        )

    excerpt = _concat_excerpt(blocks, align.start_bid, align.end_bid)
    min_excerpt = int(os.environ.get("CRE_EMBED_SMART_MIN_EXCERPT_CHARS", "30"))
    if len(excerpt) < min_excerpt:
        return SmartExtractOutcome(
            embed_plain_text=full_cleaned_body_text,
            resolved_embeddings_url=base_url
            or (getattr(node, "hyperlink", None) or ""),
            rationale="excerpt_too_short",
            used_excerpt=False,
            shadow_only=(mode == "shadow"),
            marker_start_bid="",
            marker_end_bid="",
        )

    fragment: Optional[str] = None
    if align.suggested_fragment and align.suggested_fragment in valid_frags:
        fragment = align.suggested_fragment
    elif align.suggested_fragment:
        logger.info(
            "Smart extract rejected unknown fragment %r (valid sample count=%s)",
            align.suggested_fragment,
            len(valid_frags),
        )

    resolved = _resolved_url(getattr(node, "hyperlink", "") or "", fragment)

    if mode == "shadow":
        return SmartExtractOutcome(
            embed_plain_text=full_cleaned_body_text,
            resolved_embeddings_url=base_url
            or (getattr(node, "hyperlink", None) or ""),
            rationale=f"shadow:{align.rationale}",
            used_excerpt=False,
            shadow_only=True,
            marker_start_bid=align.start_bid,
            marker_end_bid=align.end_bid,
        )

    return SmartExtractOutcome(
        embed_plain_text=excerpt,
        resolved_embeddings_url=resolved,
        rationale=align.rationale,
        used_excerpt=True,
        shadow_only=False,
        marker_start_bid=align.start_bid,
        marker_end_bid=align.end_bid,
    )


def embedding_cache_marker(
    *, used_excerpt: bool, start_bid: str, end_bid: str, resolved_url: str
) -> str:
    """Deterministic suffix so incremental embedding cache sees excerpt/url changes."""
    if not used_excerpt:
        return ""
    u = resolved_url or ""
    return (
        f"\n__opencre_embed__:policy={SMART_EXTRACT_POLICY_VERSION};"
        f"span={start_bid}-{end_bid};url={u}"
    )
