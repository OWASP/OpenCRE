"""Module B Stage 2 prompt: recall-first security-knowledge classification.

The system prompt pins the recall-first rule agreed with the maintainer
(2026-06-01): bias hard toward KNOWLEDGE; NOISE is only for chunks with no
security signal at all; UNCERTAIN is rare. NOISE rows are dropped before
Module C, so a misclassified security chunk is lost forever while a
misclassified noise chunk merely wastes downstream compute that Module C
re-judges -- recall matters more than precision.

The few-shot block deliberately includes the cases that were NOISE under the
old novelty-first rule and are KNOWLEDGE under recall-first (clarifications,
typo fixes, added examples/links inside security sections), so the model
learns the bias from worked examples, not only the instruction.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You are classifying chunks of OWASP repository content for a \
security-knowledge pipeline.

Label each chunk as exactly one of:

- KNOWLEDGE: ANY chunk with a security signal -- vulnerabilities, attack \
vectors, testing methodology, mitigations, code samples, advisories, security \
configurations, EVEN clarifications, typo fixes, expanded examples, \
restatements of well-known material, added reference links, or restructured \
security sections. When in doubt, choose KNOWLEDGE.
- NOISE: ONLY chunks with no security-knowledge content at all -- sponsorship \
pages, meeting notes, CI/build configuration, release tags, website layout, \
contributor onboarding, project governance. This includes content *about* a \
security project rather than security knowledge itself: version/release \
announcements, licenses, translation notes, citation/reference-format \
instructions, tables of contents, project titles/banners, and event/talk \
teasers -- even when they name a security standard or project (e.g. "ASVS", \
"SAMM"). Naming a security project is not the same as containing security \
knowledge.
- UNCERTAIN: only when genuinely 50/50 even after applying the bias above. \
This label is rare.

Recall matters more than precision: NOISE rows are dropped from the pipeline, \
so a misclassified security chunk is lost forever, while a misclassified noise \
chunk just wastes downstream compute that a later stage re-judges.

Respond with a single JSON object of the form:
{"results": [{"index": <int>, "label": "KNOWLEDGE"|"NOISE"|"UNCERTAIN", \
"confidence": <float between 0.0 and 1.0>, "reasoning": "<one short sentence>"}]}
Return exactly one result object per input chunk, with `index` matching the \
chunk's number. Do not output any text outside the JSON object."""


# Worked examples. `heading_path` + `text` are what the model sees per chunk;
# label/confidence/reasoning are the expected verdict. Five KNOWLEDGE (including
# the recall-first hard cases), three NOISE (strictly organizational), two
# UNCERTAIN (genuine 50/50 anchors).
FEW_SHOT_EXAMPLES = [
    {
        "heading_path": ["Testing for JWT", "Signature Bypass"],
        "text": (
            "A `kid` header pointing at a SQL-backed key store can be abused: "
            "setting `kid` to `' UNION SELECT 'attacker-key' -- ` makes the "
            "verifier return an attacker-controlled HMAC secret, so a forged "
            "token validates."
        ),
        "label": "KNOWLEDGE",
        "confidence": 0.99,
        "reasoning": "Concrete JWT kid SQL-injection signature bypass.",
    },
    {
        "heading_path": ["Cross-Site Request Forgery", "Defenses"],
        "text": (
            "Note: SameSite=Lax does not fully protect older browsers that "
            "ignore the attribute; pair it with a synchronizer token for those "
            "clients."
        ),
        "label": "KNOWLEDGE",
        "confidence": 0.9,
        "reasoning": "Clarification inside a CSRF defenses section -- still security content.",
    },
    {
        "heading_path": ["OAuth", "Mitigation"],
        "text": (
            "Always validate the `redirect_uri` against an exact-match allowlist "
            "to prevent authorization-code callback abuse."
        ),
        "label": "KNOWLEDGE",
        "confidence": 0.92,
        "reasoning": "Typo fix inside an OAuth mitigation -- the chunk content is security.",
    },
    {
        "heading_path": ["Testing for SSRF"],
        "text": (
            "Example: `curl http://target/fetch?url=http://169.254.169.254/"
            "latest/meta-data/` to confirm the cloud metadata endpoint is "
            "reachable from the server."
        ),
        "label": "KNOWLEDGE",
        "confidence": 0.95,
        "reasoning": "Added curl example demonstrating SSRF testing methodology.",
    },
    {
        "heading_path": ["Authentication Testing", "References"],
        "text": (
            "See also: PortSwigger Web Security Academy -- Authentication "
            "vulnerabilities (https://portswigger.net/web-security/authentication)."
        ),
        "label": "KNOWLEDGE",
        "confidence": 0.8,
        "reasoning": "Reference link enriching a security testing section.",
    },
    {
        "heading_path": ["Sponsors"],
        "text": (
            "Gold sponsors receive logo placement on the conference site and two "
            "complimentary booth passes. Contact sponsorship@example.org."
        ),
        "label": "NOISE",
        "confidence": 0.97,
        "reasoning": "Pure sponsorship content, no security signal.",
    },
    {
        "heading_path": ["Supporting Resources", "Meetings"],
        "text": (
            "Attendees: A. Smith, B. Jones, C. Lee. Topics discussed: agenda for "
            "next quarter, budget review, schedule for the annual summit."
        ),
        "label": "NOISE",
        "confidence": 0.96,
        "reasoning": "Meeting notes; organizational, no security content.",
    },
    {
        "heading_path": [],
        "text": (
            "name: release\non:\n  push:\n    tags: ['v*']\njobs:\n  build:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4"
        ),
        "label": "NOISE",
        "confidence": 0.95,
        "reasoning": "CI release-tagging workflow; build infrastructure, not security knowledge.",
    },
    {
        "heading_path": [
            "OWASP Application Security Verification Standard",
            "Latest Stable Version",
        ],
        "text": (
            "The latest stable version is 5.0.0 (dated May 2025), available as a "
            "PDF and in the GitHub repository. See the release notes for changes "
            "since 4.0."
        ),
        "label": "NOISE",
        "confidence": 0.9,
        "reasoning": "Version/release announcement about a security standard -- content about the project, not security knowledge.",
    },
    {
        "heading_path": [
            "OWASP Application Security Verification Standard",
            "License",
        ],
        "text": (
            "The entire project content is under the Creative Commons "
            "Attribution-Share Alike v4.0 license."
        ),
        "label": "NOISE",
        "confidence": 0.95,
        "reasoning": "Licensing information about a security project -- organizational, no security methodology.",
    },
    {
        "heading_path": ["About"],
        "text": (
            "This project began in 2015 as a community effort. Our mission is to "
            "improve web application security for everyone."
        ),
        "label": "UNCERTAIN",
        "confidence": 0.5,
        "reasoning": "Half project history, half a generic security-mission statement.",
    },
    {
        "heading_path": ["Contributing"],
        "text": (
            "Report security issues privately to security@example.org. For "
            "everything else, open a pull request and sign the CLA before your "
            "first contribution."
        ),
        "label": "UNCERTAIN",
        "confidence": 0.5,
        "reasoning": "Mixes a security-reporting contact with general onboarding.",
    },
]


def _chunk_json(index: int, heading_path: list[str], text: str) -> str:
    """Render one chunk as the compact JSON the model sees."""
    return json.dumps(
        {"index": index, "heading_path": heading_path, "text": text},
        ensure_ascii=False,
    )


def _verdict_json(index: int, example: dict) -> str:
    """Render one few-shot's expected verdict as JSON."""
    return json.dumps(
        {
            "index": index,
            "label": example["label"],
            "confidence": example["confidence"],
            "reasoning": example["reasoning"],
        },
        ensure_ascii=False,
    )


def _build_few_shot_block() -> str:
    """Render all few-shot examples as INPUT/VERDICT pairs for the system prompt."""
    blocks = []
    for i, ex in enumerate(FEW_SHOT_EXAMPLES):
        blocks.append(
            f"INPUT: {_chunk_json(i, ex['heading_path'], ex['text'])}\n"
            f"VERDICT: {_verdict_json(i, ex)}"
        )
    return "Worked examples:\n\n" + "\n\n".join(blocks)


# System prompt + worked examples, assembled once at import time.
SYSTEM_PROMPT_WITH_EXAMPLES = SYSTEM_PROMPT + "\n\n" + _build_few_shot_block()


def build_user_prompt(items: list[tuple[list[str], str]]) -> str:
    """Build the user message: a numbered batch of chunks to classify.

    Args:
        items: (heading_path, text) per chunk, already truncated by the caller.

    Returns:
        A prompt instructing the model to return one verdict per chunk.
    """
    lines = ["Classify each of the following chunks and return the results JSON:\n"]
    for i, (heading_path, text) in enumerate(items):
        lines.append(_chunk_json(i, heading_path, text))
    return "\n".join(lines)


__all__ = [
    "FEW_SHOT_EXAMPLES",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_WITH_EXAMPLES",
    "build_user_prompt",
]
