"""RAG/OIE parity adapters (Phases 2–7).

Frameworks assist retrieve/ingest/observability. OpenCRE ``decide()`` / τ remain
the only auto-link policy. Optional imports keep hermetic CI free of paid paths.
"""

from application.utils.rag_parity.flags import RagParityFlags, load_flags

__all__ = ["RagParityFlags", "load_flags"]
