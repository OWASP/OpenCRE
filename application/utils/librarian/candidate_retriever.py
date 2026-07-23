"""Module C.1 — semantic candidate retriever (Week 3). The search step.

For sections with no explicit CRE id (the majority — most chunks just
describe a security concept in plain English), C must *find* which of
OpenCRE's nodes the text is about. That is a search problem: embed the
section text, cosine-match it against the CRE-node vector hub, and return
the top-K rank-ordered candidates — the shortlist W4's cross-encoder
reranks and later weeks turn into a confident yes/no.

The retriever is a thin, dependency-injected seam over two collaborators:

  - ``embed_fn(text) -> Sequence[float]`` — turns text into a vector. Prod
    wires ``PromptHandler.get_text_embeddings``; the harness and tests inject
    a deterministic stub. C never embeds directly, so it stays import-light
    and hermetically testable (mirrors W2's resolver taking an injected
    known-id set).
  - a ``CandidatePool`` — the ``{cre_id -> vector}`` hub for every CRE node.
    Prod loads ``db.get_embeddings_by_doc_type(CRE)``; the pool is prevalidated
    to one common width so the dim gate below is meaningful.

Two interchangeable backends behind one ``retrieve()`` seam, selected by
``CRE_LIBRARIAN_RETRIEVER_BACKEND``:

  - ``in_memory`` — sklearn cosine over an in-RAM matrix. Works on SQLite
    (CI / harness) by reading stored ``embedding_vec`` Text literals into a
    hub matrix. Does not use the pgvector ``<=>`` operator.
  - ``pgvector`` — pushes the cosine into Postgres via the ``<=>`` operator
    over an ``embedding_vec vector(dim)`` column; never loads the hub into
    RAM. Requires the ``vector`` extension + that column (Alembic
    ``c7d8e9f0a1b2`` / #977). On SQLite (or Postgres without the column)
    construction/use raises ``SystemExit`` with a clear message — never
    silently falls back.

The RFC is silent on retrieval tech — it mandates only the
``candidates[]``/``reranked[]`` audit trail — so the backend choice is ours;
both emit the same ``RetrievalAudit``.

Gate (PR 3): dim assertion — the query-vector width must equal the stored
CRE-vector width, or every cosine score is silently meaningless. (Enforced
in-process for in_memory; Postgres enforces it structurally for pgvector via
the fixed-width ``vector(dim)`` column.)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from application.database.pgvector_utils import to_pgvector_literal
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

# A function that turns one piece of text into a single dense vector.
EmbedFn = Callable[[str], Sequence[float]]

# Identify the retriever in the RFC audit trail (RetrievalAudit.retriever).
# Bumped when the matching algorithm changes so a stored proposal is traceable
# to the code that produced it.
RETRIEVER_NAME = "in-memory-cosine/0.1.0"
PGVECTOR_RETRIEVER_NAME = "pgvector-cosine/0.1.0"


class RetrieverBackend(str, Enum):
    # sklearn cosine over an in-RAM matrix — SQLite dev, CI, and the harness.
    in_memory = "in_memory"
    # Postgres-side cosine via pgvector's ``<=>`` operator (needs the vector
    # extension + an embedding_vec column; Alembic c7d8e9f0a1b2 / #977).
    pgvector = "pgvector"


class RetrieverError(ValueError):
    """Base class for retriever construction/usage failures."""


class EmptyPoolError(RetrieverError):
    """No CRE vectors to search against — retrieval cannot run."""


class DimensionMismatchError(RetrieverError):
    """Query- and CRE-vector widths differ — cosine scores would be meaningless."""


@dataclass(frozen=True)
class CandidatePool:
    """An immutable ``{cre_id -> vector}`` hub, prevalidated to one width.

    ``matrix`` is ``(n_cre, dim)`` row-aligned with ``cre_ids`` so a single
    cosine call scores the whole hub at once.
    """

    cre_ids: Tuple[str, ...]
    matrix: np.ndarray
    dim: int

    @classmethod
    def from_mapping(cls, embeddings: Mapping[str, Sequence[float]]) -> "CandidatePool":
        """Build a pool from ``db.get_embeddings_by_doc_type``-shaped data.

        Rejects an empty hub and any ragged vector — both are silent-failure
        traps if they reach the cosine step.
        """
        if not embeddings:
            raise EmptyPoolError("candidate pool is empty; no CRE vectors to search")
        cre_ids = tuple(embeddings.keys())
        rows = [list(embeddings[cre_id]) for cre_id in cre_ids]
        widths = {len(r) for r in rows}
        if len(widths) != 1:
            raise DimensionMismatchError(
                f"CRE vectors have inconsistent widths {sorted(widths)}; "
                "the hub must be a single embedding model/dimension"
            )
        dim = widths.pop()
        if dim == 0:
            raise DimensionMismatchError("CRE vectors are zero-width")
        return cls(cre_ids=cre_ids, matrix=np.asarray(rows, dtype=float), dim=dim)


class CandidateRetriever:
    """Embed a section, cosine-rank the CRE hub, return the top-K shortlist.

    ``top_k`` is ``CRE_LIBRARIAN_TOP_K_RETRIEVAL`` (default 20). ``threshold``
    is the configured link threshold, carried verbatim into the audit so a
    stored proposal is self-describing; the retriever itself does **not**
    threshold — it always returns the top-K so W4 can rerank a full shortlist.
    """

    def __init__(
        self,
        embed_fn: EmbedFn,
        pool: CandidatePool,
        top_k: int,
        *,
        threshold: float,
        cre_names: Optional[Mapping[str, str]] = None,
    ) -> None:
        if top_k <= 0:
            raise RetrieverError(f"top_k must be > 0, got {top_k}")
        self._embed_fn = embed_fn
        self._pool = pool
        self._top_k = top_k
        self._threshold = threshold
        self._cre_names = dict(cre_names or {})

    def retrieve(self, text: str) -> RetrievalAudit:
        """Return the top-K CRE candidates for ``text`` as a RetrievalAudit.

        ``reranked`` is empty — the cross-encoder lands W4. Candidates are
        rank-ordered (highest cosine first) with ``score_vector`` populated.
        """
        query = np.asarray(list(self._embed_fn(text)), dtype=float)
        if query.shape[0] != self._pool.dim:
            raise DimensionMismatchError(
                f"query vector width {query.shape[0]} != CRE hub width "
                f"{self._pool.dim}; check the embedding model matches the hub"
            )

        scores = cosine_similarity(query.reshape(1, -1), self._pool.matrix)[0]
        # Top-K by descending score. argsort is ascending, so take the tail
        # and reverse; cap at pool size when the hub is smaller than K.
        k = min(self._top_k, len(self._pool.cre_ids))
        # Stable descending sort so tied cosine scores keep hub (index) order —
        # deterministic across runs. argsort(-scores) descends; kind="stable".
        top_idx = np.argsort(-scores, kind="stable")[:k]

        candidates: List[CreCandidate] = [
            CreCandidate(
                cre_id=self._pool.cre_ids[i],
                cre_name=self._cre_names.get(self._pool.cre_ids[i]),
                score_vector=float(scores[i]),
            )
            for i in top_idx
        ]
        return RetrievalAudit(
            retriever=RETRIEVER_NAME,
            candidates=candidates,
            reranked=[],
            threshold=self._threshold,
        )


class PgVectorRetriever:
    """Postgres-side top-K cosine via pgvector's ``<=>`` operator.

    The similarity is computed and ranked in the database against the
    ``embedding_vec`` column, so the hub is never loaded into RAM — the win
    over ``CandidateRetriever`` on a large CRE corpus. ``<=>`` is cosine
    *distance* (0 = identical), so the score is ``1 - distance`` to match the
    in-memory backend's cosine *similarity*.

    Needs the ``vector`` extension and an ``embedding_vec vector(dim)`` column
    (Alembic ``c7d8e9f0a1b2`` / #977). SQLite is refused at construct/execute time
    with ``SystemExit`` — never silently routed to ``in_memory``.
    """

    # Parameterized; :q is bound as a pgvector text literal and cast in-SQL.
    _SQL = (
        "SELECT cre_id, 1 - (embedding_vec <=> CAST(:q AS vector)) AS score "
        "FROM embeddings "
        "WHERE doc_type = :doc_type AND cre_id IS NOT NULL "
        "AND embedding_vec IS NOT NULL "
        "ORDER BY embedding_vec <=> CAST(:q AS vector) "
        "LIMIT :k"
    )

    def __init__(
        self,
        embed_fn: EmbedFn,
        connection: Any,
        top_k: int,
        *,
        threshold: float,
        doc_type: str = "CRE",
        cre_names: Optional[Mapping[str, str]] = None,
    ) -> None:
        if top_k <= 0:
            raise RetrieverError(f"top_k must be > 0, got {top_k}")
        from application.database.pgvector_utils import require_pgvector_connection

        require_pgvector_connection(
            connection, context="PgVectorRetriever / Module C.1"
        )
        self._embed_fn = embed_fn
        self._conn = connection
        self._top_k = top_k
        self._threshold = threshold
        self._doc_type = doc_type
        self._cre_names = dict(cre_names or {})

    def retrieve(self, text: str) -> RetrievalAudit:
        """Return the top-K CRE candidates for ``text`` as a RetrievalAudit.

        Rows arrive already rank-ordered by the SQL ``ORDER BY``; we preserve
        that order. ``sqlalchemy.text`` is imported lazily so the in-memory
        backend (and CI) never needs a DB driver loaded.
        """
        from sqlalchemy import text as sql_text

        from application.database.pgvector_utils import require_pgvector_connection

        require_pgvector_connection(self._conn, context="PgVectorRetriever.retrieve")
        query = to_pgvector_literal(list(self._embed_fn(text)))
        rows = self._conn.execute(
            sql_text(self._SQL),
            {"q": query, "doc_type": self._doc_type, "k": self._top_k},
        ).fetchall()

        candidates = [
            CreCandidate(
                cre_id=row.cre_id,
                cre_name=self._cre_names.get(row.cre_id),
                score_vector=float(row.score),
            )
            for row in rows
        ]
        return RetrievalAudit(
            retriever=PGVECTOR_RETRIEVER_NAME,
            candidates=candidates,
            reranked=[],
            threshold=self._threshold,
        )


def build_retriever(
    backend: RetrieverBackend,
    embed_fn: EmbedFn,
    *,
    top_k: int,
    threshold: float,
    pool: Optional[CandidatePool] = None,
    connection: Any = None,
    cre_names: Optional[Mapping[str, str]] = None,
) -> Any:
    """Construct the retriever for ``backend`` behind the shared ``retrieve()``.

    ``in_memory`` needs ``pool``; ``pgvector`` needs ``connection``. Mismatches
    fail loudly rather than silently doing nothing.
    """
    if backend is RetrieverBackend.in_memory:
        if pool is None:
            raise RetrieverError("in_memory backend requires a CandidatePool")
        return CandidateRetriever(
            embed_fn, pool, top_k, threshold=threshold, cre_names=cre_names
        )
    if backend is RetrieverBackend.pgvector:
        if connection is None:
            raise RetrieverError("pgvector backend requires a DB connection")
        return PgVectorRetriever(
            embed_fn, connection, top_k, threshold=threshold, cre_names=cre_names
        )
    raise RetrieverError(f"unknown retriever backend {backend!r}")
