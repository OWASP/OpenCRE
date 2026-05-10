"""
Live LLM + network tests for smart embedding alignment (OWASP AI Exchange pages).

Run with: ``pytest -m llm_e2e application/tests/test_smart_embeddings_e2e_llm.py``

Requires ``OPENAI_API_KEY`` or ``GEMINI_API_KEY`` (or set ``CRE_EMBED_ALIGN_E2E=0`` to skip).
"""

from __future__ import annotations

import os
import re
import json
from typing import Any, Tuple

import pytest
import requests
import litellm
from pydantic import ValidationError

from application.defs import cre_defs
from application.prompt_client import embed_alignment

pytestmark = pytest.mark.llm_e2e


def _skip_no_llm() -> None:
    if os.environ.get("CRE_EMBED_ALIGN_E2E", "1").lower() in ("0", "false", "no"):
        pytest.skip("CRE_EMBED_ALIGN_E2E disabled")
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        pytest.skip("No LLM credentials (set OPENAI_API_KEY or GEMINI_API_KEY)")


def _alignment_llm_client() -> Tuple[Any, str]:
    """Return (client, provider_label) for LiteLLM structured alignment."""

    class _LiteLLMAlignClient:
        def __init__(self, model: str):
            self.model = model

        def align_embedding_span_json(
            self, system_instruction: str, user_payload: str
        ) -> dict[str, Any]:
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_payload},
            ]
            strict_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "opencre_alignment_payload",
                    "strict": True,
                    "schema": embed_alignment.alignment_response_json_schema(),
                },
            }
            try:
                resp = litellm.completion(
                    model=self.model,
                    messages=messages,
                    response_format=strict_format,
                    temperature=0.2,
                )
            except Exception:
                resp = litellm.completion(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
            text = (resp.choices[0].message.content or "").strip()
            try:
                payload = embed_alignment.AlignmentPayload.model_validate_json(text)
                return payload.model_dump()
            except ValidationError:
                return embed_alignment.AlignmentPayload.model_validate(
                    json.loads(text)
                ).model_dump()

    if os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("CRE_EMBED_ALIGN_MODEL", "openai/gpt-4o-mini")
        return _LiteLLMAlignClient(model), "litellm-openai"
    if os.environ.get("GEMINI_API_KEY"):
        model = os.environ.get("CRE_EMBED_ALIGN_MODEL", "gemini/gemini-2.5-flash")
        return _LiteLLMAlignClient(model), "litellm-gemini"
    pytest.fail("unreachable: _skip_no_llm should have skipped")


def _simple_clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize(
    "hyperlink,section,section_id,expected_fragment",
    [
        (
            "https://owaspai.org/go/aiprogram/",
            "AI Program",
            "aiprogram",
            "ai-program",
        ),
        (
            "https://owaspai.org/go/aitransparency/",
            "AI transparency",
            "aitransparency",
            "ai-transparency",
        ),
    ],
)
def test_owasp_ai_exchange_live_alignment(
    hyperlink: str, section: str, section_id: str, expected_fragment: str
):
    """
    Fetch real AI Exchange ``/go/...`` pages (multi-section HTML) and verify the
    alignment model picks a scoped excerpt and a validated ``#fragment``.
    """
    _skip_no_llm()
    client, provider = _alignment_llm_client()

    headers = {
        "User-Agent": os.environ.get(
            "CRE_EMBED_E2E_USER_AGENT", "OpenCRE-embed-e2e/1.0 (+https://opencre.org)"
        )
    }
    resp = requests.get(hyperlink, timeout=90, headers=headers)
    resp.raise_for_status()
    html = resp.text
    full_clean = _simple_clean(embed_alignment.html_body_inner_text(html))
    assert len(full_clean) > 500, "expected substantial AI Exchange page body"

    node = cre_defs.Standard(
        name="OWASP AI Exchange",
        section=section,
        sectionID=section_id,
        subsection="",
        hyperlink=hyperlink,
    )
    out = embed_alignment.run_smart_extract(
        html=html,
        full_cleaned_body_text=full_clean,
        node=node,
        ai_client=client,
        mode="on",
        page_cache_key=embed_alignment.normalize_page_cache_key(hyperlink),
        alignment_cache={},
        confidence_threshold=float(
            os.environ.get("CRE_EMBED_SMART_CONFIDENCE", "0.55")
        ),
    )
    assert out.used_excerpt, f"expected excerpt mode ({provider}): {out.rationale!r}"
    assert (
        expected_fragment in out.resolved_embeddings_url
    ), f"expected #{expected_fragment} in resolved URL ({provider}), got {out.resolved_embeddings_url!r}"
    assert (
        len(out.embed_plain_text) < len(full_clean) * 0.98
    ), f"excerpt should be materially shorter than full cleaned body ({provider})"
