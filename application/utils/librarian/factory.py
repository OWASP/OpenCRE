"""Builds the live C.1/C.2/C.3 components from config + the OpenCRE database.

Until now the only place that knew how to construct a real retriever and
reranker was ``cre_main.run_librarian``, inline. That is why the OIE
orchestrator (#996) could not drive ``LibrarianPipeline`` — it had the pipeline
class but no way to produce the components it takes. This module is that seam.

Everything here is *construction only*: no rows are read, no run is executed.
Callers that want a run use ``queue_runner.run_librarian_queue``.

The DB and embedding imports are deliberately function-local. The rest of the
librarian package is hermetically testable precisely because it never imports
the database at module scope, and this module is the boundary where that stops
being true — keeping the imports inside the call preserves it for everyone else.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, FrozenSet, Optional, Sequence

from application.utils.librarian.config_loader import LibrarianConfig, load_config
from application.utils.librarian.pipeline import Reranker, Retriever, Scaler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LibrarianComponents:
    """The three live stages plus the CRE id registry, built once and reused.

    ``known_cre_ids`` is the set of ids present in the embedding hub — the only
    ids C is allowed to link to, and what the explicit-reference fast path (C.0.5)
    validates a cited id against.
    """

    retriever: Retriever
    reranker: Reranker
    scaler: Scaler
    known_cre_ids: FrozenSet[str]


def build_scaler(config: Optional[LibrarianConfig] = None) -> Scaler:
    """The C.3 calibrator at the configured temperature.

    ``T`` is not learned here. It is fitted offline by
    ``scripts/evaluate_librarian.py --use_live_embeddings`` and set as
    ``CRE_LIBRARIAN_TEMPERATURE``; the default 1.0 means *uncalibrated*, so a
    deployment that never ran the fit gets a plain softmax rather than a
    confidence dressed up as calibrated.
    """
    from application.utils.librarian.calibration.temperature import TemperatureScaler

    config = config or load_config()
    if config.temperature == 1.0:
        logger.warning(
            "CRE_LIBRARIAN_TEMPERATURE is 1.0 (uncalibrated). Fit it with "
            "scripts/evaluate_librarian.py --use_live_embeddings and set the "
            "value it prints, or the C.4 threshold is being applied to an "
            "uncalibrated confidence."
        )
    return TemperatureScaler(config.temperature)


def build_components(
    database: Any,
    *,
    config: Optional[LibrarianConfig] = None,
    embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
) -> LibrarianComponents:
    """Construct C.1 + C.2 + C.3 against a connected OpenCRE database.

    Args:
        database: a connected ``db.Node_collection`` (the caller owns it, the
            same way Module B's ``run_noise_filter`` takes a session it did not
            open).
        config: Module C settings; defaults to ``load_config()``.
        embed_fn: text -> embedding. Defaults to the prompt handler's embedder,
            which calls the paid embedding API; injectable so a caller can
            supply a local or fake embedder.

    Raises whatever the pgvector guard raises when that backend is configured
    but unavailable — deliberately, rather than falling back to a different
    retrieval path and producing silently different rankings.
    """
    from application.defs import cre_defs as defs
    from application.utils.librarian.candidate_retriever import (
        CandidatePool,
        RetrieverBackend,
        build_retriever,
    )
    from application.utils.librarian.cross_encoder import (
        CrossEncoderReranker,
        build_cross_encoder_score_fn,
    )

    config = config or load_config()
    backend = RetrieverBackend(config.retriever_backend)

    if backend is RetrieverBackend.pgvector:
        from application.database.pgvector_utils import fail_pgvector_unavailable

        if not database.can_use_pgvector_similarity():
            fail_pgvector_unavailable(
                context="CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector"
            )

    if embed_fn is None:
        from application.prompt_client import prompt_client

        embed_fn = prompt_client.PromptHandler(database=database).get_text_embeddings

    cre_embeddings = database.get_embeddings_by_doc_type(defs.Credoctypes.CRE.value)
    # in_memory holds the hub matrix in RAM; pgvector ranks in the DB over the
    # embedding_vec column and needs no pool. Both satisfy the same retrieve().
    pool = (
        CandidatePool.from_mapping(cre_embeddings)
        if backend is RetrieverBackend.in_memory
        else None
    )
    retriever = build_retriever(
        backend,
        embed_fn=embed_fn,
        top_k=config.top_k_retrieval,
        threshold=config.link_threshold,
        pool=pool,
        connection=(
            database.session.connection()
            if backend is RetrieverBackend.pgvector
            else None
        ),
    )

    # C.2 scores each (section, candidate) pair against the CRE's
    # embeddings_content — the same text the hub vectors were built from.
    reranker = CrossEncoderReranker(
        score_fn=build_cross_encoder_score_fn(config.crossencoder_model),
        top_n=config.top_k_rerank,
        cre_texts=database.get_embedding_contents_by_doc_type(
            defs.Credoctypes.CRE.value
        ),
    )

    return LibrarianComponents(
        retriever=retriever,
        reranker=reranker,
        scaler=build_scaler(config),
        known_cre_ids=frozenset(cre_embeddings.keys()),
    )


__all__ = ["LibrarianComponents", "build_components", "build_scaler"]
