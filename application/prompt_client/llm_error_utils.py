from cre_logging import get_logger

logger = get_logger(__name__)

from typing import Any


def is_rate_limit_error(err: BaseException) -> bool:
    msg = str(err).lower()
    if "rate limit" in msg or "too many requests" in msg:
        return True
    if "resource exhausted" in msg or "quota" in msg or "exceeded quota" in msg:
        return True
    if "429" in msg:
        return True

    status = (
        getattr(err, "status", None)
        or getattr(err, "status_code", None)
        or getattr(err, "http_status", None)
        or getattr(err, "code", None)
    )
    if status == 429:
        return True

    if isinstance(getattr(err, "args", None), tuple):
        # Some SDKs nest details in args[0]/args[1].
        nested: Any = err.args[0] if err.args else None
        if isinstance(nested, dict):
            code = nested.get("code") or nested.get("status_code")
            if code == 429:
                return True
    return False


def is_transient_llm_error(err: BaseException) -> bool:
    """Connection / timeout blips that are safe to retry (not model refusal)."""
    if is_rate_limit_error(err):
        return True
    name = type(err).__name__.lower()
    if any(
        tok in name
        for tok in (
            "connect",
            "timeout",
            "apiconnection",
            "remoteprotocol",
            "network",
        )
    ):
        return True
    msg = str(err).lower()
    return any(
        tok in msg
        for tok in (
            "connection reset",
            "connection aborted",
            "connection refused",
            "temporarily unavailable",
            "broken pipe",
            "timed out",
            "timeout",
            "errno 54",
            "errno 104",
            "server disconnected",
            "remote end closed",
        )
    )
