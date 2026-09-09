"""Module C.2 — cross-encoder + hybrid reranker (Week 4).

C.1 (the bi-encoder) cosine-ranks the hub; C.2 re-orders that shortlist. For
**small cages** (≤ ``hybrid_when_le``, typical prior-caged retrieval) we use a
hybrid score so the cross-encoder cannot erase a strong vector/name hit:

    score = α·vector + β·title_overlap(name+text) + γ·minmax(CE)

With small cages, α/β dominate and γ is small. Larger shortlists keep CE-led
ordering (legacy behaviour) with a lighter title boost on the CE logits.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from application.utils.librarian.schemas import RetrievalAudit
from application.utils.librarian.title_boost import (
    apply_title_boost,
    hybrid_rank_scores,
    title_overlap_boost,
)

# A function that scores a batch of (query_text, candidate_text) pairs.
RerankFn = Callable[[Sequence[Tuple[str, str]]], Sequence[float]]

RERANKER_NAME = "cross-encoder-ms-marco-MiniLM-L-6-v2/0.1.0"
DEFAULT_CROSSENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Small-cage hybrid (prior cages are typically ≤20).
HYBRID_WHEN_LE = 20
HYBRID_ALPHA = 1.0
HYBRID_BETA = 3.0
HYBRID_GAMMA = 0.15
# Large-shortlist: CE-led + light title boost on logits.
LARGE_TITLE_BOOST_WEIGHT = 2.0


class RerankerError(ValueError):
    """Base class for reranker construction/usage failures."""


class MissingCandidateTextError(RerankerError):
    """A shortlisted CRE has no text to score against — cannot rerank fairly."""


class CrossEncoderReranker:
    """Re-score a C.1 shortlist; hybrid when the shortlist is a small cage."""

    def __init__(
        self,
        score_fn: RerankFn,
        top_n: int,
        *,
        cre_texts: Mapping[str, str],
        cre_names: Optional[Mapping[str, str]] = None,
        hybrid_when_le: int = HYBRID_WHEN_LE,
        hybrid_alpha: float = HYBRID_ALPHA,
        hybrid_beta: float = HYBRID_BETA,
        hybrid_gamma: float = HYBRID_GAMMA,
        large_title_boost_weight: float = LARGE_TITLE_BOOST_WEIGHT,
    ) -> None:
        if top_n <= 0:
            raise RerankerError(f"top_n must be > 0, got {top_n}")
        self._score_fn = score_fn
        self._top_n = top_n
        self._cre_texts = dict(cre_texts)
        self._cre_names = dict(cre_names or {})
        self._hybrid_when_le = hybrid_when_le
        self._hybrid_alpha = hybrid_alpha
        self._hybrid_beta = hybrid_beta
        self._hybrid_gamma = hybrid_gamma
        self._large_title_boost_weight = large_title_boost_weight

    def _cre_blob(self, cre_id: str, cre_text: str) -> str:
        name = self._cre_names.get(cre_id) or ""
        return f"{name}\n{cre_text}".strip()

    def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit:
        """Return a copy of ``audit`` with ``reranked`` filled from ``candidates``."""
        candidates = audit.candidates
        if not candidates:
            return audit.model_copy(update={"reranked": []})

        pairs: List[Tuple[str, str]] = []
        blobs: List[str] = []
        vectors: List[float] = []
        for c in candidates:
            cre_text = self._cre_texts.get(c.cre_id)
            if not cre_text:
                raise MissingCandidateTextError(
                    f"no text for candidate CRE {c.cre_id!r}; the reranker needs "
                    "the CRE's embeddings_content to score the pair"
                )
            pairs.append((text, cre_text))
            blobs.append(self._cre_blob(c.cre_id, cre_text))
            vectors.append(float(c.score_vector or 0.0))

        ce_scores = [float(s) for s in self._score_fn(pairs)]
        if len(ce_scores) != len(candidates):
            raise RerankerError(
                f"score_fn returned {len(ce_scores)} scores for {len(candidates)} "
                "candidates; the reranker expects exactly one score per pair"
            )

        use_hybrid = (
            self._hybrid_when_le > 0 and len(candidates) <= self._hybrid_when_le
        )
        if use_hybrid:
            title_boosts = [
                title_overlap_boost(text, blob, weight=1.0) for blob in blobs
            ]
            final = hybrid_rank_scores(
                vectors=vectors,
                ce_scores=ce_scores,
                title_boosts=title_boosts,
                alpha=self._hybrid_alpha,
                beta=self._hybrid_beta,
                gamma=self._hybrid_gamma,
            )
        else:
            final = apply_title_boost(
                text,
                ce_scores,
                blobs,
                weight=self._large_title_boost_weight,
            )

        reranked = [
            c.model_copy(update={"score_rerank": float(s)})
            for c, s in zip(candidates, final, strict=True)
        ]
        reranked.sort(key=lambda c: c.score_rerank, reverse=True)
        return audit.model_copy(update={"reranked": reranked[: self._top_n]})


def build_cross_encoder_score_fn(
    model_name: str = DEFAULT_CROSSENCODER_MODEL,
) -> RerankFn:
    """Load a sentence-transformers CrossEncoder and adapt it to ``RerankFn``."""
    from sentence_transformers import CrossEncoder  # lazy, heavy

    model = CrossEncoder(model_name)

    def score_fn(pairs: Sequence[Tuple[str, str]]) -> List[float]:
        return [float(s) for s in model.predict([list(p) for p in pairs])]

    return score_fn


def vector_rerank_union_ids(
    audit: RetrievalAudit, *, vector_top: int = 2, rerank_top: int = 5
) -> List[str]:
    """Ordered unique CRE ids: reranked[:rerank_top] then vector top-N not already in."""
    ordered: List[str] = []
    seen: set[str] = set()

    def add(cre_id: str) -> None:
        if cre_id and cre_id not in seen:
            seen.add(cre_id)
            ordered.append(cre_id)

    for c in (audit.reranked or [])[:rerank_top]:
        add(c.cre_id)
    by_vec = sorted(
        audit.candidates or [],
        key=lambda c: float(c.score_vector or 0.0),
        reverse=True,
    )
    for c in by_vec[:vector_top]:
        add(c.cre_id)
    return ordered
