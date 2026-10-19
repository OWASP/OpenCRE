"""Top-k retrieval for OpenCRE Chat (#1075, implements #962).

Chat used to stuff the single nearest Standard embedding into the prompt
(``argmax-1``). This module replaces that with a small two-lane retriever that
reuses the Librarian seams instead of inventing a second RAG stack:

- **pgvector lane** (prod / Heroku): ``db.find_top_k_similar_embedding_ids``,
  the ``LIMIT :k`` sibling of the top-1 query chat already used. No torch.
- **in-memory lane** (SQLite dev / CI): the same paginated embedding walk chat
  already had, ranked with ``candidate_retriever.top_k_cosine`` so Module C
  and Chat order candidates identically.

Two lanes run on one question embedding: Standards (what Rob's SAMM example
needs) and CREs (the hub). Hits are merged, de-duplicated per document, cut
at a **break-off** (keep anything within ``delta`` of the best score and above
the existing ``CHATBOT_SIMILARITY_THRESHOLD`` floor), capped, and loaded into
``ChatPassage`` objects with a per-passage character budget.

Rerank is a one-function hook (``rerank_fn``) so the cross-encoder (dev) and
``title_boost`` (when #1088 lands) slot in without touching this file again.

Environment (all optional):
    CHATBOT_TOPK_RETRIEVE   candidates per lane before break-off (default 8)
    CHATBOT_TOPK_CRE        CRE-lane candidates (default 4)
    CHATBOT_TOPK_PROMPT     passages sent to the model (default 5)
    CHATBOT_BREAKOFF_DELTA  keep score >= best - delta (default 0.08)
    CHATBOT_SIMILARITY_THRESHOLD  absolute floor (existing, default 0.7)
    CHATBOT_PROMPT_CHAR_BUDGET    total chars for all passages (default 8000)
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from application.defs import cre_defs
from application.utils.librarian.candidate_retriever import top_k_cosine

Scored = Tuple[str, float]  # (object_id, cosine similarity)
RerankFn = Callable[[str, List["ChatPassage"]], List["ChatPassage"]]

KIND_STANDARD = "standard"
KIND_CRE = "cre"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        logger.warning("%s=%r is not an int; using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        logger.warning("%s=%r is not a float; using %s", name, raw, default)
        return default


@dataclass
class ChatPassage:
    """One retrieved passage, ready for the prompt and the references table."""

    object_id: str
    kind: str  # KIND_STANDARD | KIND_CRE
    score: float
    rank: int = 0
    title: str = ""
    content: str = ""
    url: Optional[str] = None
    row: Dict[str, Any] = field(default_factory=dict)

    def table_row(self) -> Dict[str, Any]:
        """Shape the frontend reference card already understands, plus rank/score."""
        out = dict(self.row)
        if self.url:
            out["embeddingsUrl"] = self.url
        out["rank"] = self.rank
        out["score"] = round(self.score, 4)
        return out


def apply_breakoff(
    scored: Sequence[Scored], *, floor: float, delta: float, cap: int
) -> List[Scored]:
    """Rob's break-off rule from #962, as one pure function.

    Keep a candidate when ``score >= max(floor, best - delta)``; stop at
    ``cap``. ``scored`` may be unsorted and may contain duplicates; output is
    sorted best-first with duplicate ids removed (first occurrence wins).
    """
    if cap <= 0 or not scored:
        return []
    ordered = sorted(scored, key=lambda s: -s[1])
    best = ordered[0][1]
    cut = max(floor, best - delta)
    out: List[Scored] = []
    seen = set()
    for oid, score in ordered:
        if score < cut:
            break
        if oid in seen:
            continue
        seen.add(oid)
        out.append((oid, score))
        if len(out) >= cap:
            break
    return out


def split_budget(total_chars: int, n: int) -> int:
    """Per-passage character budget: the model limit shared evenly."""
    if n <= 0:
        return total_chars
    return max(200, total_chars // n)


def passage_header(p: ChatPassage) -> str:
    """The ``[n] title (url)`` line that precedes a passage in the prompt."""
    head = f"[{p.rank}] {p.title}".rstrip()
    if p.url:
        head += f" ({p.url})"
    return head


def rendered_overhead(passages: Sequence[ChatPassage]) -> int:
    """Characters ``render_passages`` adds on top of passage content."""
    if not passages:
        return 0
    per_passage = sum(len(passage_header(p)) + 1 for p in passages)  # +1 newline
    return per_passage + 2 * (len(passages) - 1)  # blank-line separators


def content_budget(total_chars: int, passages: Sequence[ChatPassage]) -> int:
    """Per-passage content budget so the rendered block fits ``total_chars``."""
    if not passages:
        return total_chars
    remaining = max(0, total_chars - rendered_overhead(passages))
    return max(1, remaining // len(passages))


def render_passages(passages: Sequence[ChatPassage]) -> str:
    """Numbered passage block for ``chat_prompt.j2`` (cite as ``[n]``)."""
    parts: List[str] = []
    for p in passages:
        parts.append(f"{passage_header(p)}\n{p.content}".strip())
    return "\n\n".join(parts)


class ChatRetriever:
    """Two-lane top-k retrieval over the ``embeddings`` table for Chat."""

    def __init__(
        self,
        database: Any,
        *,
        top_k_retrieve: Optional[int] = None,
        top_k_cre: Optional[int] = None,
        top_k_prompt: Optional[int] = None,
        floor: Optional[float] = None,
        breakoff_delta: Optional[float] = None,
        char_budget: Optional[int] = None,
        rerank_fn: Optional[RerankFn] = None,
    ) -> None:
        self.database = database
        self.top_k_retrieve = (
            top_k_retrieve
            if top_k_retrieve is not None
            else _env_int("CHATBOT_TOPK_RETRIEVE", 8)
        )
        self.top_k_cre = (
            top_k_cre if top_k_cre is not None else _env_int("CHATBOT_TOPK_CRE", 4)
        )
        self.top_k_prompt = (
            top_k_prompt
            if top_k_prompt is not None
            else _env_int("CHATBOT_TOPK_PROMPT", 5)
        )
        self.floor = (
            floor
            if floor is not None
            else _env_float("CHATBOT_SIMILARITY_THRESHOLD", 0.7)
        )
        self.breakoff_delta = (
            breakoff_delta
            if breakoff_delta is not None
            else _env_float("CHATBOT_BREAKOFF_DELTA", 0.08)
        )
        self.char_budget = (
            char_budget
            if char_budget is not None
            else _env_int("CHATBOT_PROMPT_CHAR_BUDGET", 8000)
        )
        self.rerank_fn: RerankFn = rerank_fn or (lambda _q, ps: ps)
        for name, val in (
            ("top_k_retrieve", self.top_k_retrieve),
            ("top_k_cre", self.top_k_cre),
            ("top_k_prompt", self.top_k_prompt),
        ):
            if val <= 0:
                raise ValueError(f"{name} must be > 0, got {val}")

    # ------------------------------------------------------------------ lanes
    def _lane(
        self, question_embedding: List[float], *, doc_type: str, id_column: str, k: int
    ) -> List[Scored]:
        if self.database.can_use_pgvector_similarity():
            rows = self.database.find_top_k_similar_embedding_ids(
                question_embedding,
                doc_type=doc_type,
                id_column=id_column,
                k=k,
                similarity_threshold=self.floor,
            )
            return [(str(oid), float(score)) for oid, score in rows]
        return self._lane_in_memory(question_embedding, doc_type=doc_type, k=k)

    def _lane_in_memory(
        self, question_embedding: List[float], *, doc_type: str, k: int
    ) -> List[Scored]:
        """SQLite / no-pgvector path: walk every page, keep a running top-k."""
        query = np.asarray(question_embedding, dtype=float)
        embeddings, total_pages, page = (
            self.database.get_embeddings_by_doc_type_paginated(
                doc_type=doc_type, page=1
            )
        )
        running: List[Scored] = []
        while True:
            if embeddings:
                ids = list(embeddings.keys())
                matrix = np.asarray([list(embeddings[i]) for i in ids], dtype=float)
                running.extend(top_k_cosine(query, matrix, ids, k))
                running = sorted(running, key=lambda s: -s[1])[:k]
            if page >= total_pages:
                break
            page += 1
            embeddings, _, _ = self.database.get_embeddings_by_doc_type_paginated(
                doc_type=doc_type, page=page
            )
        return [(oid, s) for oid, s in running if s >= self.floor]

    # --------------------------------------------------------------- loading
    def _load(self, oid: str, kind: str, score: float) -> Optional[ChatPassage]:
        node: Any = None
        if kind == KIND_STANDARD:
            nodes = self.database.get_nodes(db_id=oid)
            node = nodes[0] if nodes else None
        else:
            try:
                node = self.database.get_cre_by_db_id(oid)
            except Exception as exc:  # noqa: BLE001 - a missing CRE must not kill chat
                logger.warning("chat retrieval: cannot load CRE %s (%s)", oid, exc)
                node = None
        if node is None:
            return None
        content = ""
        url: Optional[str] = None
        embs = self.database.get_embedding(oid)
        if embs:
            emb = embs[0]
            content = (getattr(emb, "embeddings_content", None) or "").strip()
            url = (getattr(emb, "embeddings_url", None) or "").strip() or None
        try:
            row = node.shallow_copy().todict()
        except Exception:  # noqa: BLE001 - defensive: never 500 on a malformed node
            row = {"name": getattr(node, "name", oid), "doctype": kind}
        title = str(row.get("name") or getattr(node, "name", oid))
        section = row.get("section") or row.get("sectionID")
        if section:
            title = f"{title} §{section}"
        if kind == KIND_CRE and row.get("id"):
            title = f"CRE {row['id']}: {title}"
        if not content:
            # Fall back to the node's own fields, as the old single-hit path did.
            content = "\n".join(f"{k}:{v}" for k, v in row.items() if v)
        return ChatPassage(
            object_id=oid,
            kind=kind,
            score=score,
            title=title,
            content=content,
            url=url,
            row=row,
        )

    # ------------------------------------------------------------------ main
    def retrieve(
        self, question: str, question_embedding: List[float]
    ) -> List[ChatPassage]:
        """Return the passages to ground the answer on, best first, ranked 1..n.

        Empty list means nothing cleared the floor: the caller keeps the old
        ``query_llm`` fallback and reports ``accurate=False``.
        """
        standards = self._lane(
            question_embedding,
            doc_type=cre_defs.Credoctypes.Standard.value,
            id_column="node_id",
            k=self.top_k_retrieve,
        )
        cres = self._lane(
            question_embedding,
            doc_type=cre_defs.Credoctypes.CRE.value,
            id_column="cre_id",
            k=self.top_k_cre,
        )
        kinds = {oid: KIND_STANDARD for oid, _ in standards}
        kinds.update({oid: KIND_CRE for oid, _ in cres if oid not in kinds})
        kept = apply_breakoff(
            standards + cres,
            floor=self.floor,
            delta=self.breakoff_delta,
            cap=self.top_k_prompt
            * 2,  # over-fetch: per-document dedupe below may drop some
        )
        passages: List[ChatPassage] = []
        seen_docs = set()
        for oid, score in kept:
            p = self._load(oid, kinds[oid], score)
            if p is None:
                continue
            doc_key = (p.kind, str(p.row.get("name") or p.object_id))
            if doc_key in seen_docs:
                # one passage per document until #1076 gives section-level rows
                continue
            seen_docs.add(doc_key)
            passages.append(p)
            if len(passages) >= self.top_k_prompt:
                break
        passages = self.rerank_fn(question, passages)[: self.top_k_prompt]
        for i, p in enumerate(passages, start=1):
            p.rank = i
        # Budget the *rendered* block (headers, URLs, separators included), so
        # what the model sees is exactly what the references table advertises.
        per = content_budget(self.char_budget, passages)
        for p in passages:
            if len(p.content) > per:
                p.content = p.content[:per]
        if passages:
            logger.info(
                "chat retrieval: %d passages (%s), best=%.3f, cut=%.3f",
                len(passages),
                ",".join(f"{p.kind}:{p.score:.2f}" for p in passages),
                passages[0].score,
                max(self.floor, passages[0].score - self.breakoff_delta),
            )
        else:
            logger.info("chat retrieval: nothing above floor %.2f", self.floor)
        return passages
