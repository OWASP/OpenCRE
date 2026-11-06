"""Optional LlamaIndex query transforms / rerank over LiteLLM (all gated, default off).

* ``LI_HYDE``    — public ``HyDEQueryTransform``: the hypothetical answer is embedded as an extra query.
* ``LI_REWRITE`` — one LLM rewrite of the question as an extra query.
* ``LI_RERANK``  — public ``LLMRerank`` postprocessor over the top hits.

The LlamaIndex components run on a thin ``CustomLLM`` adapter over the interactive LiteLLM
router, so no ``llama-index-llms-*`` package is needed. Every entry point returns its input
unchanged on any failure.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Sequence

logger = logging.getLogger(__name__)


def helper_model() -> str:
    return os.environ.get("OWASP_CX_LI_HELPER_MODEL", "gemini/gemini-2.5-flash-lite")


def _complete_text(prompt: str) -> str:
    from application.prompt_client import litellm_router

    resp = litellm_router.resilient_completion(
        model=helper_model(),
        messages=[{"role": "user", "content": prompt}],
        context="li extras",
        temperature=0,
    )
    return (resp.choices[0].message.content or "").strip()


def _adapter() -> Any:
    """LlamaIndex ``CustomLLM`` backed by the interactive LiteLLM router."""
    from llama_index.core.llms import (
        CompletionResponse,
        CustomLLM,
        LLMMetadata,
    )
    from llama_index.core.llms.callbacks import llm_completion_callback

    class _LiteLLMAdapter(CustomLLM):
        @property
        def metadata(self) -> LLMMetadata:
            return LLMMetadata(model_name=helper_model(), is_chat_model=False)

        @llm_completion_callback()
        def complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
            return CompletionResponse(text=_complete_text(prompt))

        @llm_completion_callback()
        def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
            yield CompletionResponse(text=_complete_text(prompt))

    return _LiteLLMAdapter()


def hyde_queries(question: str) -> List[str]:
    """[hypothetical answer] via ``HyDEQueryTransform`` ([] on failure)."""
    try:
        from llama_index.core.indices.query.query_transform import HyDEQueryTransform

        bundle = HyDEQueryTransform(llm=_adapter(), include_original=False).run(
            question
        )
        out = [s.strip() for s in (bundle.custom_embedding_strs or []) if s.strip()]
        return [s for s in out if s != question][:1]
    except Exception:  # noqa: BLE001
        logger.warning("LI HyDE failed; continuing without it", exc_info=True)
        return []


def rewrite_queries(question: str) -> List[str]:
    """[one standalone search-friendly rewrite] ([] on failure)."""
    try:
        text = _complete_text(
            "Rewrite this question as a short, self-contained search query for "
            "OWASP documentation. Reply with only the query.\n\nQuestion: " + question
        )
        text = text.strip().strip('"')
        return [text] if text and text != question and len(text) < 400 else []
    except Exception:  # noqa: BLE001
        logger.warning("LI rewrite failed; continuing without it", exc_info=True)
        return []


def rerank_hits(question: str, hits: Sequence[Any], top: int = 20) -> List[Any]:
    """Reorder the first ``top`` hits with ``LLMRerank``; the tail keeps its order."""
    hits = list(hits)
    head, tail = hits[:top], hits[top:]
    if len(head) < 3:
        return hits
    try:
        from llama_index.core.postprocessor import LLMRerank
        from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

        by_id = {}
        nodes = []
        for i, h in enumerate(head):
            by_id[str(i)] = h
            body = (getattr(h, "content", "") or "")[:700]
            nodes.append(
                NodeWithScore(
                    node=TextNode(id_=str(i), text=body),
                    score=float(getattr(h, "score", 0.0) or 0.0),
                )
            )
        rr = LLMRerank(llm=_adapter(), top_n=len(nodes), choice_batch_size=10)
        ranked = rr.postprocess_nodes(nodes, QueryBundle(query_str=question))
        ordered = [
            by_id[str(n.node.node_id)] for n in ranked if str(n.node.node_id) in by_id
        ]
        seen = {id(h) for h in ordered}
        ordered += [h for h in head if id(h) not in seen]
        return ordered + tail
    except Exception:  # noqa: BLE001
        logger.warning("LI rerank failed; keeping original order", exc_info=True)
        return hits
