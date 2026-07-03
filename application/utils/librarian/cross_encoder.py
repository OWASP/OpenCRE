"""Module C.2 — cross-encoder reranker (Week 4). The careful re-reader.

C.1 (the bi-encoder, W3) fingerprints the section and each CRE *separately* and
cosine-ranks the whole hub — fast enough to scan every CRE, but it never reads a
section and a candidate *together*, so the ordering inside the top-K shortlist is
rough: the right CRE can sit at #7, not #1. C.2 fixes that ordering. It reads
each ``(section text, candidate CRE text)`` *pair* together as one input, scores
"do these two actually match?", re-sorts the shortlist by that score, and keeps
the best N. Slow per pair, so it runs only over the K candidates C.1 already
narrowed to — never the whole hub.

Like C.1, the reranker is a thin dependency-injected seam over its model:

  - ``score_fn(pairs) -> Sequence[float]`` — scores a batch of
    ``(query_text, candidate_text)`` pairs, higher = better match. Prod wires a
    pinned cross-encoder (``ms-marco-MiniLM-L-6-v2``); the harness and tests
    inject a deterministic stub. C.2 never imports the model directly, so it
    stays import-light and hermetically testable (mirrors C.1's ``embed_fn``).

The text a candidate CRE is scored against is its ``embeddings_content`` — the
same signal the hub vectors were built from — supplied as a ``{cre_id -> text}``
map. The RFC is silent on ranking tech; it mandates only the
``candidates[]``/``reranked[]`` audit trail. C.2 fills ``reranked[]`` (the slot
C.1 deliberately left empty), populating ``score_rerank`` and re-ordering, while
leaving ``candidates[]`` untouched so the pre-rerank shortlist stays auditable.
"""

from typing import Callable, List, Mapping, Sequence, Tuple

from application.utils.librarian.schemas import RetrievalAudit

# A function that scores a batch of (query_text, candidate_text) pairs.
RerankFn = Callable[[Sequence[Tuple[str, str]]], Sequence[float]]

# Identify the reranker in the RFC audit trail. Bumped when the model or the
# scoring changes so a stored proposal is traceable to the code that ranked it.
RERANKER_NAME = "cross-encoder-ms-marco-MiniLM-L-6-v2/0.1.0"
DEFAULT_CROSSENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RerankerError(ValueError):
    """Base class for reranker construction/usage failures."""


class MissingCandidateTextError(RerankerError):
    """A shortlisted CRE has no text to score against — cannot rerank fairly."""


class CrossEncoderReranker:
    """Re-score a C.1 shortlist by reading each (section, CRE) pair together.

    ``top_n`` is ``CRE_LIBRARIAN_TOP_K_RERANK`` (default 5). ``rerank`` reads
    ``audit.candidates`` (C.1's shortlist), scores every pair, re-sorts by the
    cross-encoder score, keeps the best ``top_n``, and returns a copy of the
    audit with ``reranked`` filled and ``candidates`` preserved.
    """

    def __init__(
        self,
        score_fn: RerankFn,
        top_n: int,
        *,
        cre_texts: Mapping[str, str],
    ) -> None:
        if top_n <= 0:
            raise RerankerError(f"top_n must be > 0, got {top_n}")
        self._score_fn = score_fn
        self._top_n = top_n
        self._cre_texts = dict(cre_texts)

    def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit:
        """Return a copy of ``audit`` with ``reranked`` filled from ``candidates``.

        Raises ``MissingCandidateTextError`` if a shortlisted CRE has no text to
        score (a silent-quality trap otherwise) and ``RerankerError`` if the
        model returns the wrong number of scores.
        """
        candidates = audit.candidates
        if not candidates:
            # Nothing to rerank (e.g. an empty hub upstream); keep the audit
            # shape consistent — an explicit, empty reranked list.
            return audit.model_copy(update={"reranked": []})

        pairs: List[Tuple[str, str]] = []
        for c in candidates:
            cre_text = self._cre_texts.get(c.cre_id)
            if not cre_text:
                raise MissingCandidateTextError(
                    f"no text for candidate CRE {c.cre_id!r}; the reranker needs "
                    "the CRE's embeddings_content to score the pair"
                )
            pairs.append((text, cre_text))

        scores = list(self._score_fn(pairs))
        if len(scores) != len(candidates):
            raise RerankerError(
                f"score_fn returned {len(scores)} scores for {len(candidates)} "
                "candidates; the reranker expects exactly one score per pair"
            )

        reranked = [
            c.model_copy(update={"score_rerank": float(s)})
            for c, s in zip(candidates, scores)
        ]
        # Highest cross-encoder score first, then keep only the best top_n.
        # Python's sort is stable, so ties preserve C.1's cosine order.
        reranked.sort(key=lambda c: c.score_rerank, reverse=True)
        return audit.model_copy(update={"reranked": reranked[: self._top_n]})


def build_cross_encoder_score_fn(
    model_name: str = DEFAULT_CROSSENCODER_MODEL,
) -> RerankFn:
    """Load a sentence-transformers CrossEncoder and adapt it to ``RerankFn``.

    ``sentence_transformers`` (and torch) is imported lazily so this module —
    and CI/tests that inject a stub score_fn — never need the heavy ML stack
    loaded (mirrors C.1 keeping the embedding model out of module import).
    """
    from sentence_transformers import CrossEncoder  # lazy, heavy

    model = CrossEncoder(model_name)

    def score_fn(pairs: Sequence[Tuple[str, str]]) -> List[float]:
        # CrossEncoder.predict takes a list of [a, b] pairs, returns an ndarray.
        return [float(s) for s in model.predict([list(p) for p in pairs])]

    return score_fn
