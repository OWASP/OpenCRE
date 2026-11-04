"""Error alerts through Sentry (or any Sentry-compatible server), off unless SENTRY_DSN is set.

Privacy: ``send_default_pii`` is off and every event is scrubbed before it leaves the process, so no
question text, answer text, cookies, tokens or e-mail addresses are sent. Only stack traces, the route
and the release/environment tags travel.

  SENTRY_DSN          project DSN (empty/unset = disabled, nothing is imported or sent)
  SENTRY_ENVIRONMENT  defaults to FLASK_CONFIG ("production" / "staging" ...)
  SENTRY_RELEASE      defaults to HEROKU_SLUG_COMMIT / GIT_SHA when present
  SENTRY_TRACES_SAMPLE_RATE  defaults to 0 (errors only)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = re.compile(
    r"prompt|message|messages|question|answer|query|content|history|body|authorization|cookie|token|"
    r"secret|password|api[_-]?key|email|session",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_initialised = False


def _scrub_value(key: str, value: Any) -> Any:
    if _SENSITIVE_KEYS.search(key or ""):
        return "[removed]"
    if isinstance(value, dict):
        return {k: _scrub_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(key, v) for v in value]
    if isinstance(value, str):
        return _EMAIL.sub("[email]", value)
    return value


def _redact_emails(obj: Any) -> Any:
    """Belt and braces: replace any e-mail address in any string anywhere in the event."""
    if isinstance(obj, str):
        return _EMAIL.sub("[email]", obj)
    if isinstance(obj, dict):
        return {k: _redact_emails(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_emails(v) for v in obj]
    return obj


def scrub_event(
    event: Dict[str, Any], hint: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Remove request bodies, headers/cookies, user identity and personal data from a Sentry event."""
    request = event.get("request")
    if isinstance(request, dict):
        for field in ("data", "cookies", "query_string", "env"):
            request.pop(field, None)
        if isinstance(request.get("headers"), dict):
            request["headers"] = {
                k: (
                    "[removed]"
                    if _SENSITIVE_KEYS.search(k)
                    or k.lower() in ("x-forwarded-for", "x-real-ip")
                    else v
                )
                for k, v in request["headers"].items()
            }
    event.pop("user", None)
    for section in ("extra", "contexts", "tags"):
        if isinstance(event.get(section), dict):
            event[section] = (
                _scrub_value(section, event[section])
                if section == "extra"
                else {k: _scrub_value(str(k), v) for k, v in event[section].items()}
            )
    crumbs = (
        (event.get("breadcrumbs") or {}).get("values")
        if isinstance(event.get("breadcrumbs"), dict)
        else None
    )
    if crumbs:
        for crumb in crumbs:
            crumb.pop("data", None)
            if isinstance(crumb.get("message"), str):
                crumb["message"] = _EMAIL.sub("[email]", crumb["message"])[:200]
    for exc in (event.get("exception") or {}).get("values", []) or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = _EMAIL.sub("[email]", exc["value"])[:500]
        for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
            frame.pop("vars", None)  # local variables can hold prompts and tokens
    return _redact_emails(event)


def init_error_reporting(component: str = "web", *, transport: Any = None) -> bool:
    """Start error reporting when SENTRY_DSN is set. Returns True when active. Safe to call twice."""
    global _initialised
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn or _initialised:
        return _initialised
    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; error reporting stays off"
        )
        return False
    release = (
        os.environ.get("SENTRY_RELEASE")
        or os.environ.get("HEROKU_SLUG_COMMIT")
        or os.environ.get("GIT_SHA")
        or None
    )
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT")
        or os.environ.get("FLASK_CONFIG")
        or "production",
        release=release,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or 0),
        before_send=scrub_event,
        transport=transport,
    )
    sentry_sdk.set_tag("component", component)
    _initialised = True
    logger.info("error reporting enabled (%s)", component)
    return True


def reset_for_tests() -> None:
    global _initialised
    _initialised = False
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=None)
    except Exception:  # noqa: BLE001
        pass
