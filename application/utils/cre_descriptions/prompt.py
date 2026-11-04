"""Prompt building for one-shot CRE description generation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import List, Sequence, Tuple

MAX_DESCRIPTION_CHARS = 1200
MAX_LEAF_CHARS = 900
MAX_LINKED_PROMPT_CHARS = 8000

_SYSTEM = (
    "You write a proposed CRE.description for OpenCRE, a fail-closed standards "
    "mapping into a fixed CRE taxonomy. "
    "The CRE name is the topic. Linked Standard/Tool prose is supporting evidence. "
    "Neighbour CRE names show nearby taxonomy context — do not redefine this CRE "
    "as a single NIST, PCI, or ASVS control. "
    "Summarize what the CRE is about in 2-4 concrete sentences using the CRE name "
    "and any linked Standard/Tool requirement prose. "
    "Ignore website chrome and scanner junk: NIST 'official website of the United "
    "States government' banners, skip-to-content navigation, JavaScript-disabled "
    "frame-buster pages, ZAP HUD/redirect warnings, ASVS nav dumps. "
    "Do not copy NIST/ASVS/ZAP chrome into the description. Do not invent CRE ids. "
    'Return ONLY JSON: {"description": "..."}.'
)


def _pack_linked_prose(leaves: Sequence[str]) -> List[str]:
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


def build_description_prompt(
    *,
    cre_id: str,
    name: str,
    linked_prose: Sequence[str] = (),
    neighbour_names: Sequence[str] = (),
) -> Tuple[str, str]:
    """Return ``(system, user)`` messages for the description LLM call."""
    neighbours = [n.strip() for n in neighbour_names if (n or "").strip()]
    user = json.dumps(
        {
            "cre_id": cre_id,
            "name": name,
            "linked_prose": _pack_linked_prose(linked_prose),
            "neighbour_names": neighbours,
        },
        indent=2,
        ensure_ascii=False,
    )
    return _SYSTEM, user


def parse_description_text(raw: str) -> str:
    """Extract description text from model output (JSON preferred)."""
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
        return text[:MAX_DESCRIPTION_CHARS].strip()
    if isinstance(data, dict):
        description = str(data.get("description") or "").strip()
        return description[:MAX_DESCRIPTION_CHARS]
    return text[:MAX_DESCRIPTION_CHARS].strip()


def compute_prompt_hash(system: str, user: str) -> str:
    """Stable SHA-256 over system + user for approval-table provenance."""
    payload = f"{system}\n---\n{user}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
