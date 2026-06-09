"""Loads CRE_LIBRARIAN_* environment variables into a typed config.

Loader only — nothing consumes these yet. Defaults match the OIE design doc so
later weeks (retriever W3, cross-encoder W4, SafetyGuard W5) read one source.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LibrarianConfig:
    crossencoder_model: str
    top_k_retrieval: int
    top_k_rerank: int
    link_threshold: float
    batch_size: int
    ece_target: float
    conformal_alpha: float


def load_config() -> LibrarianConfig:
    return LibrarianConfig(
        crossencoder_model=os.getenv(
            "CRE_LIBRARIAN_CROSSENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        ),
        top_k_retrieval=int(os.getenv("CRE_LIBRARIAN_TOP_K_RETRIEVAL", "20")),
        top_k_rerank=int(os.getenv("CRE_LIBRARIAN_TOP_K_RERANK", "5")),
        link_threshold=float(os.getenv("CRE_LIBRARIAN_LINK_THRESHOLD", "0.8")),
        batch_size=int(os.getenv("CRE_LIBRARIAN_BATCH_SIZE", "32")),
        ece_target=float(os.getenv("CRE_LIBRARIAN_ECE_TARGET", "0.10")),
        conformal_alpha=float(os.getenv("CRE_LIBRARIAN_CONFORMAL_ALPHA", "0.10")),
    )
