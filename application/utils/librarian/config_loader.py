"""Loads CRE_LIBRARIAN_* environment variables into a typed config.

Loader only — nothing consumes these yet. Defaults match the OIE design doc so
later weeks (retriever W3, cross-encoder W4, SafetyGuard W5) read one source.
"""

import os
from dataclasses import dataclass

# Retrieval backends (see candidate_retriever.RetrieverBackend). Kept as a
# plain set here so the loader stays dependency-free; the retriever owns the
# enum it maps to.
_RETRIEVER_BACKENDS = frozenset({"in_memory", "pgvector"})


@dataclass(frozen=True)
class LibrarianConfig:
    crossencoder_model: str
    retriever_backend: str
    top_k_retrieval: int
    top_k_rerank: int
    link_threshold: float
    batch_size: int
    ece_target: float
    conformal_alpha: float


def load_config() -> LibrarianConfig:
    crossencoder_model = os.getenv(
        "CRE_LIBRARIAN_CROSSENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    retriever_backend = os.getenv("CRE_LIBRARIAN_RETRIEVER_BACKEND", "in_memory")
    top_k_retrieval = int(os.getenv("CRE_LIBRARIAN_TOP_K_RETRIEVAL", "20"))
    top_k_rerank = int(os.getenv("CRE_LIBRARIAN_TOP_K_RERANK", "5"))
    link_threshold = float(os.getenv("CRE_LIBRARIAN_LINK_THRESHOLD", "0.8"))
    batch_size = int(os.getenv("CRE_LIBRARIAN_BATCH_SIZE", "32"))
    ece_target = float(os.getenv("CRE_LIBRARIAN_ECE_TARGET", "0.10"))
    conformal_alpha = float(os.getenv("CRE_LIBRARIAN_CONFORMAL_ALPHA", "0.10"))

    if retriever_backend not in _RETRIEVER_BACKENDS:
        raise ValueError(
            f"CRE_LIBRARIAN_RETRIEVER_BACKEND must be one of "
            f"{sorted(_RETRIEVER_BACKENDS)}, got {retriever_backend!r}"
        )
    if top_k_retrieval <= 0:
        raise ValueError(
            f"CRE_LIBRARIAN_TOP_K_RETRIEVAL must be > 0, got {top_k_retrieval}"
        )
    if top_k_rerank <= 0:
        raise ValueError(f"CRE_LIBRARIAN_TOP_K_RERANK must be > 0, got {top_k_rerank}")
    if top_k_rerank > top_k_retrieval:
        raise ValueError(
            f"CRE_LIBRARIAN_TOP_K_RERANK ({top_k_rerank}) must be <= "
            f"CRE_LIBRARIAN_TOP_K_RETRIEVAL ({top_k_retrieval})"
        )
    if batch_size <= 0:
        raise ValueError(f"CRE_LIBRARIAN_BATCH_SIZE must be > 0, got {batch_size}")
    if not 0.0 <= link_threshold <= 1.0:
        raise ValueError(
            f"CRE_LIBRARIAN_LINK_THRESHOLD must be in [0.0, 1.0], got {link_threshold}"
        )
    if not 0.0 <= ece_target <= 1.0:
        raise ValueError(
            f"CRE_LIBRARIAN_ECE_TARGET must be in [0.0, 1.0], got {ece_target}"
        )
    if not 0.0 <= conformal_alpha <= 1.0:
        raise ValueError(
            f"CRE_LIBRARIAN_CONFORMAL_ALPHA must be in [0.0, 1.0], got {conformal_alpha}"
        )

    return LibrarianConfig(
        crossencoder_model=crossencoder_model,
        retriever_backend=retriever_backend,
        top_k_retrieval=top_k_retrieval,
        top_k_rerank=top_k_rerank,
        link_threshold=link_threshold,
        batch_size=batch_size,
        ece_target=ece_target,
        conformal_alpha=conformal_alpha,
    )
