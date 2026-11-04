"""Phase 5: knowledge_claim structured extract + quote verify.

Failures drop or go to review queue — never unsupervised CRE graph writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

LlmFn = Callable[[str, str], str]

_SYSTEM = (
    "Extract atomic knowledge claims from standards prose. "
    'Return ONLY JSON: {"claims":[{"claim":"...","quote":"...",'
    '"confidence":0.0}]}. '
    "Each quote MUST be a verbatim substring of the source. "
    "Do not invent CRE ids or propose graph links."
)


@dataclass(frozen=True)
class KnowledgeClaimDraft:
    claim: str
    quote: str
    confidence: float
    source_ref: str = ""
    status: str = "pending_review"  # pending_review | dropped | verified


def quote_verified(quote: str, source: str) -> bool:
    q = (quote or "").strip()
    if len(q) < 12:
        return False
    return q in (source or "")


def parse_claims_payload(
    raw: str, *, source: str, source_ref: str = ""
) -> List[KnowledgeClaimDraft]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        return []
    out: List[KnowledgeClaimDraft] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        quote = str(item.get("quote") or "").strip()
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if not claim or not quote:
            continue
        if not quote_verified(quote, source):
            out.append(
                KnowledgeClaimDraft(
                    claim=claim,
                    quote=quote,
                    confidence=confidence,
                    source_ref=source_ref,
                    status="dropped",
                )
            )
            continue
        out.append(
            KnowledgeClaimDraft(
                claim=claim,
                quote=quote,
                confidence=max(0.0, min(1.0, confidence)),
                source_ref=source_ref,
                status="verified",
            )
        )
    return out


def extract_claims(
    source: str,
    *,
    llm_fn: LlmFn,
    source_ref: str = "",
) -> List[KnowledgeClaimDraft]:
    user = json.dumps({"source": source, "source_ref": source_ref}, ensure_ascii=False)
    raw = llm_fn(_SYSTEM, user)
    return parse_claims_payload(raw, source=source, source_ref=source_ref)


def claims_for_persist(
    drafts: Sequence[KnowledgeClaimDraft],
) -> List[KnowledgeClaimDraft]:
    """Only verified claims may be queued; still no CRE graph writes here."""
    return [d for d in drafts if d.status == "verified"]
