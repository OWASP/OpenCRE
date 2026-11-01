"""Curated node metadata facts for standards/resources (no keyword Q&A gate).

Facts are written into ``document_metadata["facts"]`` on ingest/seed and
surfaced via meta/evidence similarity + generic formatters.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Registry: family / resource name → metadata.facts blocks
# ---------------------------------------------------------------------------

_ASVS_STRUCTURE: Dict[str, Any] = {
    "kind": "verification_levels",
    "count": 3,
    "labels": ["L1", "L2", "L3"],
    "summary": (
        "OWASP ASVS defines three verification levels (L1, L2, L3). "
        "L1 is for low-assurance applications, L2 for most applications "
        "handling sensitive data, and L3 for high-assurance / critical systems."
    ),
    "citations": [
        "https://owasp.org/www-project-application-security-verification-standard/",
    ],
    "topics": [
        "ASVS levels",
        "ASVS verification levels",
        "How many levels does OWASP ASVS have",
        "OWASP ASVS L1 L2 L3",
        "verification levels",
        "L1 L2 L3",
    ],
}

_MASVS_STRUCTURE: Dict[str, Any] = {
    "kind": "verification_levels",
    "count": 2,
    "labels": ["L1", "L2"],
    "summary": (
        "OWASP MASVS (Mobile Application Security Verification Standard) "
        "defines two verification levels: L1 (standard security) and L2 "
        "(defense-in-depth) for mobile apps."
    ),
    "citations": [
        "https://mas.owasp.org/MASVS/",
    ],
    "topics": [
        "MASVS levels",
        "MASVS verification levels",
        "How many levels does OWASP MASVS define",
        "OWASP MASVS L1 L2",
        "mobile verification levels",
    ],
}

_SAMM_STRUCTURE: Dict[str, Any] = {
    "kind": "maturity_levels",
    "count": 3,
    "labels": ["1", "2", "3"],
    "summary": (
        "OWASP SAMM (Software Assurance Maturity Model) uses three maturity "
        "levels (1, 2, and 3) for each security practice, describing "
        "increasing assurance and sophistication."
    ),
    "citations": [
        "https://owaspsamm.org/",
    ],
    "topics": [
        "SAMM maturity levels",
        "How many maturity levels does OWASP SAMM use",
        "OWASP SAMM levels 1 2 3",
        "SAMM maturity",
        "software assurance maturity levels",
    ],
}

_AIX_LAYERS: Dict[str, Any] = {
    "kind": "architecture_layers",
    "count": 7,
    "labels": [
        "Model alignment",
        "Prompt injection defense",
        "Human oversight",
        "Automated oversight",
        "User-based least privilege",
        "Intent-based least privilege",
        "Just-in-time authorization",
    ],
    "summary": (
        "The OWASP AI Exchange (AIX) presents seven protection layers for "
        "agentic AI: (1) Model alignment, (2) Prompt injection defense, "
        "(3) Human oversight, (4) Automated oversight, "
        "(5) User-based least privilege, (6) Intent-based least privilege, "
        "and (7) Just-in-time authorization. Weak alone; strong together."
    ),
    "citations": [
        "https://owaspai.org/docs/ai_security_overview/",
    ],
    "topics": [
        "AIX layers",
        "AI Exchange layers",
        "How many layers are in the OWASP AI Exchange",
        "What are the 7 layers of the OWASP AI Exchange",
        "OWASP AI Exchange seven layers",
        "seven protection layers agentic AI",
        "AIX model layers",
    ],
}

_AIX_TRIFECTA: Dict[str, Any] = {
    "kind": "concept",
    "count": 3,
    "labels": [
        "attacker-influenced data",
        "access to sensitive data",
        "ability to send data out",
    ],
    "summary": (
        "According to the OWASP AI Exchange, for leaking sensitive data in "
        "agentic AI you need three things together (the lethal trifecta): "
        "(1) attacker-influenced data that reaches the model (often via "
        "indirect prompt injection), (2) access of that model or connected "
        "agents to sensitive data, and (3) the ability to send data out to "
        "an attacker. The impact is data exfiltration. Removing any one leg "
        "blocks the attack path."
    ),
    "citations": [
        "https://owaspai.org/docs/ai_security_overview/",
    ],
    "topics": [
        "lethal trifecta",
        "agentic AI",
        "OWASP AI Exchange",
        "AI Exchange",
        "prompt injection",
        "exfiltration",
        "sensitive data",
        "data leakage",
        "three things together",
    ],
}

_CRE_844_486: Dict[str, Any] = {
    "kind": "cre_note",
    "cre_id": "CRE-844-486",
    "title": "Perform output encoding",
    "summary": (
        'The CRE `CRE-844-486` which is titled "Perform output encoding" '
        "covers this control. Primary CRE for encoding untrusted data before "
        "rendering to prevent XSS."
    ),
    "citations": ["https://opencre.org/cre/CRE-844-486"],
    "topics": [
        "output encoding",
        "XSS",
        "CRE-844-486",
        "Perform output encoding",
    ],
}

# Canonical family keys → facts dict (possibly multiple blocks).
NODE_FACTS_BY_FAMILY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "ASVS": {"structure": copy.deepcopy(_ASVS_STRUCTURE)},
    "MASVS": {"structure": copy.deepcopy(_MASVS_STRUCTURE)},
    "SAMM": {"structure": copy.deepcopy(_SAMM_STRUCTURE)},
    "OWASP AI Exchange": {
        "structure": copy.deepcopy(_AIX_LAYERS),
        "concept": copy.deepcopy(_AIX_TRIFECTA),
    },
}

# CRE id (normalized CRE-NNN-NNN) → facts blocks.
NODE_FACTS_BY_CRE: Dict[str, Dict[str, Dict[str, Any]]] = {
    "CRE-844-486": {"control": copy.deepcopy(_CRE_844_486)},
}

# Aliases for family / resource name matching (lowercase).
_FAMILY_ALIASES: Dict[str, str] = {
    "asvs": "ASVS",
    "owasp asvs": "ASVS",
    "owasp application security verification standard": "ASVS",
    "application security verification standard": "ASVS",
    "application-security-verification-standard": "ASVS",
    "masvs": "MASVS",
    "owasp masvs": "MASVS",
    "mobile application security verification standard": "MASVS",
    "samm": "SAMM",
    "owasp samm": "SAMM",
    "software assurance maturity model": "SAMM",
    "owasp ai exchange": "OWASP AI Exchange",
    "ai exchange": "OWASP AI Exchange",
    "aix": "OWASP AI Exchange",
    "owaspai": "OWASP AI Exchange",
    "ai-exchange": "OWASP AI Exchange",
    "ai security and privacy": "OWASP AI Exchange",
}


def _normalize_family(name: str) -> Optional[str]:
    raw = (name or "").strip()
    if not raw:
        return None
    if raw in NODE_FACTS_BY_FAMILY:
        return raw
    key = raw.lower().replace("_", " ").strip()
    key = re.sub(r"\s+", " ", key)
    # Strip common OWASP prefix noise for slug-like keys.
    aliased = _FAMILY_ALIASES.get(key)
    if aliased:
        return aliased
    # Hyphenated Nest project keys.
    slug = key.replace(" ", "-")
    aliased = _FAMILY_ALIASES.get(slug)
    if aliased:
        return aliased
    return None


def _normalize_cre_id(cre_id: str) -> Optional[str]:
    t = (cre_id or "").strip()
    if not t:
        return None
    m = re.match(r"(?i)^cre[-\s]?(\d{3})[-\s]?(\d{3})$", t)
    if m:
        return f"CRE-{m.group(1)}-{m.group(2)}"
    m = re.match(r"^(\d{3})-(\d{3})$", t)
    if m:
        return f"CRE-{m.group(1)}-{m.group(2)}"
    return None


def facts_for_name(family_or_resource: str) -> Dict[str, Dict[str, Any]]:
    """Return a deep copy of curated facts for a standard/resource name, or {}."""
    canon = _normalize_family(family_or_resource)
    if not canon:
        return {}
    return copy.deepcopy(NODE_FACTS_BY_FAMILY.get(canon) or {})


def facts_for_cre_id(cre_id: str) -> Dict[str, Dict[str, Any]]:
    """Return curated facts for a CRE id, or {}."""
    key = _normalize_cre_id(cre_id)
    if not key:
        return {}
    return copy.deepcopy(NODE_FACTS_BY_CRE.get(key) or {})


def merge_facts_into_metadata(
    existing: Optional[Dict[str, Any]], facts: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Merge ``facts`` into ``existing["facts"]`` (block keys overwrite)."""
    meta: Dict[str, Any] = dict(existing or {})
    if not facts:
        return meta
    current = meta.get("facts")
    if not isinstance(current, dict):
        current = {}
    else:
        current = dict(current)
    for block_key, block in facts.items():
        if isinstance(block, dict):
            current[block_key] = copy.deepcopy(block)
    meta["facts"] = current
    return meta


def format_facts_message(
    facts: Dict[str, Any],
) -> Tuple[str, List[str]]:
    """Build a user-facing message + citations from a facts dict (generic)."""
    if not facts:
        return "", []
    # Accept either {"structure": {...}, ...} or a single block.
    blocks: List[Dict[str, Any]] = []
    if "summary" in facts and isinstance(facts.get("summary"), str):
        blocks.append(facts)  # type: ignore[arg-type]
    else:
        for _key, block in facts.items():
            if isinstance(block, dict) and block.get("summary"):
                blocks.append(block)
    if not blocks:
        return "", []

    parts: List[str] = []
    citations: List[str] = []
    for block in blocks:
        summary = str(block.get("summary") or "").strip()
        if summary:
            parts.append(summary)
        for cite in block.get("citations") or []:
            if isinstance(cite, str) and cite.strip():
                citations.append(cite.strip())

    message = " ".join(p for p in parts if p).strip()
    return message, list(dict.fromkeys(citations))


def evidence_docs_from_facts() -> List[Tuple[str, str, List[str]]]:
    """Return (slug, embed_text, citations) derived from the registry."""
    out: List[Tuple[str, str, List[str]]] = []
    # Family facts — one evidence doc per fact block.
    for family, facts in NODE_FACTS_BY_FAMILY.items():
        for block_key, block in facts.items():
            if not isinstance(block, dict):
                continue
            message, citations = format_facts_message({block_key: block})
            if not message:
                continue
            topics = block.get("topics") or []
            topic_bits = [str(t) for t in topics if t]
            topic_bits.extend([family, block_key, str(block.get("kind") or "")])
            slug_base = family.lower().replace(" ", "-")
            slug = f"{slug_base}-{block_key}"
            embed_text = message
            if topic_bits:
                embed_text += "\n\nTopics: " + ", ".join(dict.fromkeys(topic_bits))
            out.append((slug, embed_text, list(citations)))
    # CRE-linked notes as evidence (optional retrieve path).
    for cre_id, facts in NODE_FACTS_BY_CRE.items():
        for block_key, block in facts.items():
            if not isinstance(block, dict):
                continue
            message, citations = format_facts_message({block_key: block})
            if not message:
                continue
            topics = block.get("topics") or []
            topic_bits = [str(t) for t in topics if t] + [cre_id]
            slug = f"cre-{cre_id.lower()}-{block_key}"
            embed_text = message
            if topic_bits:
                embed_text += "\n\nTopics: " + ", ".join(dict.fromkeys(topic_bits))
            out.append((slug, embed_text, list(citations)))
    return out


def facts_embed_appendix(facts: Dict[str, Dict[str, Any]]) -> str:
    """Prose appendix for meta/standard embed text when facts are present."""
    if not facts:
        return ""
    message, _ = format_facts_message(facts)
    topics: List[str] = []
    for block in facts.values():
        if isinstance(block, dict):
            for t in block.get("topics") or []:
                if t:
                    topics.append(str(t))
    bits = []
    if message:
        bits.append(message)
    if topics:
        bits.append("Topics: " + ", ".join(dict.fromkeys(topics)))
    return "\n".join(bits)


def extract_cre_id_from_text(text: str) -> Optional[str]:
    """Return first CRE-NNN-NNN mentioned in text, or None."""
    t = text or ""
    m = re.search(r"(?i)\bcre[-\s]?(\d{3})[-\s]?(\d{3})\b", t)
    if m:
        return f"CRE-{m.group(1)}-{m.group(2)}"
    return None
