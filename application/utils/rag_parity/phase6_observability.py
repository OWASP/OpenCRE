"""Phase 6: optional Langfuse + OpenTelemetry wiring (no-op without keys/deps)."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from application.utils.rag_parity.flags import RagParityFlags, load_flags

logger = logging.getLogger(__name__)


def langfuse_enabled(flags: Optional[RagParityFlags] = None) -> bool:
    cfg = flags or load_flags()
    if not cfg.langfuse:
        return False
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def try_create_langfuse_handler() -> Optional[Any]:
    """Return a Langfuse callback handler or None if unavailable."""
    if not langfuse_enabled():
        return None
    try:
        from langfuse.callback import CallbackHandler  # type: ignore

        return CallbackHandler()
    except Exception:  # noqa: BLE001
        logger.debug("Langfuse handler unavailable", exc_info=True)
        return None


def configure_otel_exporter(flags: Optional[RagParityFlags] = None) -> bool:
    """Best-effort OTel tracer provider setup; returns True if configured."""
    cfg = flags or load_flags()
    if not cfg.otel:
        return False
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import (  # type: ignore
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        provider = TracerProvider(
            resource=Resource.create({"service.name": "opencre-rag-parity"})
        )
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        return True
    except Exception:  # noqa: BLE001
        logger.debug("OTel configure failed", exc_info=True)
        return False


@contextmanager
def traced_span(
    name: str, attributes: Optional[Dict[str, Any]] = None
) -> Iterator[None]:
    """No-op span when OTel is off; real span when a provider is present."""
    try:
        from opentelemetry import trace  # type: ignore

        tracer = trace.get_tracer("opencre.rag_parity")
        with tracer.start_as_current_span(name) as span:
            for k, v in (attributes or {}).items():
                try:
                    span.set_attribute(k, v)
                except Exception:  # noqa: BLE001
                    pass
            yield
    except Exception:  # noqa: BLE001
        yield
