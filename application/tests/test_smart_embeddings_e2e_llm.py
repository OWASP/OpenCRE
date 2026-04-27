"""
Live LLM + network tests for smart embedding alignment (OWASP AI Exchange pages).

Run with: ``pytest -m llm_e2e application/tests/test_smart_embeddings_e2e_llm.py``
Requires ``OPENAI_API_KEY`` (or set ``CRE_EMBED_ALIGN_E2E=0`` to skip entire module).
"""

from __future__ import annotations

import os
import re

import pytest
import requests

from application.defs import cre_defs
from application.prompt_client import embed_alignment

pytestmark = pytest.mark.llm_e2e


def _skip_no_openai():
    if os.environ.get("CRE_EMBED_ALIGN_E2E", "1").lower() in ("0", "false", "no"):
        pytest.skip("CRE_EMBED_ALIGN_E2E disabled")
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


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
def test_owasp_ai_exchange_live_alignment_openai(
    hyperlink: str, section: str, section_id: str, expected_fragment: str
):
    """
    Fetch real AI Exchange ``/go/...`` pages (multi-section HTML) and verify the
    alignment model picks a scoped excerpt and a validated ``#fragment``.
    """
    _skip_no_openai()
    from application.prompt_client.openai_prompt_client import OpenAIPromptClient

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
    client = OpenAIPromptClient(os.environ["OPENAI_API_KEY"])
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
    assert out.used_excerpt, f"expected excerpt mode: {out.rationale!r}"
    assert expected_fragment in out.resolved_embeddings_url, (
        f"expected #{expected_fragment} in resolved URL, got {out.resolved_embeddings_url!r}"
    )
    assert len(out.embed_plain_text) < len(full_clean) * 0.98, (
        "excerpt should be materially shorter than full cleaned body"
    )
