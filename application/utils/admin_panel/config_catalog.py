"""Allowlisted admin config keys: help text and secret redaction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional
from urllib.parse import urlsplit, urlunsplit


DOCS_ENV = "https://github.com/OWASP/OpenCRE/blob/main/.env.example"
DOCS_NOISE = "https://github.com/OWASP/OpenCRE/blob/main/docs/gsoc_2026_module_b/module_b_runbook.md"
DOCS_LIBRARIAN = (
    "https://github.com/OWASP/OpenCRE/blob/main/application/utils/librarian/README.md"
)


@dataclass(frozen=True)
class ConfigKey:
    key: str
    help_text: str
    help_url: str
    secret: bool = False


CATALOG: Dict[str, ConfigKey] = {
    k.key: k
    for k in (
        ConfigKey(
            "CRE_ALLOW_IMPORT",
            "Kill switch for import/admin APIs. Set in process env, not HTTP.",
            DOCS_ENV,
        ),
        ConfigKey(
            "CRE_ENABLE_MYOPENCRE",
            "Expose MyOpenCRE UI (separate /myopencre route).",
            DOCS_ENV,
        ),
        ConfigKey(
            "CRE_ENABLE_LOGIN",
            "Expose login UI; admin APIs still need CRE_ALLOW_IMPORT.",
            DOCS_ENV,
        ),
        ConfigKey(
            "CRE_NOISE_FILTER_LLM_MODEL",
            "Module B classifier model id.",
            DOCS_NOISE,
        ),
        ConfigKey(
            "CRE_NOISE_FILTER_BATCH_SIZE",
            "Module B batch size.",
            DOCS_NOISE,
        ),
        ConfigKey(
            "CRE_NOISE_FILTER_MAX_CHARS",
            "Max chars per noise-filter chunk.",
            DOCS_NOISE,
        ),
        ConfigKey(
            "CRE_NOISE_FILTER_CONFIDENCE_THRESHOLD",
            "Module B confidence cutoff.",
            DOCS_NOISE,
        ),
        ConfigKey(
            "CRE_LIBRARIAN_TOP_K_RETRIEVAL",
            "Module C retrieval shortlist size.",
            DOCS_LIBRARIAN,
        ),
        ConfigKey(
            "OWASP_AGENT_ENABLED",
            "Route chat completions through the OWASP metadata agent "
            "(uses the main app Postgres URL).",
            DOCS_ENV,
        ),
        ConfigKey(
            "VERTEX_CHAT_MODEL",
            "Chat model when the agent does not handle the prompt.",
            DOCS_ENV,
        ),
        ConfigKey(
            "GEMINI_API_KEY",
            "LLM API key (never returned or writable via admin).",
            DOCS_ENV,
            secret=True,
        ),
        ConfigKey(
            "GOOGLE_CLIENT_SECRET",
            "OAuth client secret (never returned or writable via admin).",
            DOCS_ENV,
            secret=True,
        ),
        ConfigKey(
            "GOOGLE_SECRET_JSON",
            "Path to Google service-account JSON (never returned).",
            DOCS_ENV,
            secret=True,
        ),
        ConfigKey(
            "OpenCRE_gspread_Auth",
            "Spreadsheet credentials path (never returned).",
            DOCS_ENV,
            secret=True,
        ),
        ConfigKey(
            "DEV_DATABASE_URL",
            "Main app Postgres URL (CRE graph, embeddings/pgvector, OWASP agent).",
            DOCS_ENV,
        ),
        ConfigKey(
            "NEO4J_URL",
            "Neo4j bolt URL.",
            DOCS_ENV,
        ),
        ConfigKey(
            "REDIS_URL",
            "Redis URL.",
            DOCS_ENV,
        ),
    )
}

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"
_SECRET_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "_AUTH")
_URL_KEYS = ("_URL", "_DB", "DATABASE_URL")


def _is_secret_key(key: str, spec: Optional[ConfigKey] = None) -> bool:
    if spec and spec.secret:
        return True
    upper = key.upper()
    return any(marker in upper for marker in _SECRET_MARKERS)


def _should_redact_url(key: str) -> bool:
    upper = key.upper()
    return any(upper.endswith(suffix) or suffix in upper for suffix in _URL_KEYS)


def keys_from_env_example(text: Optional[str] = None) -> List[str]:
    if text is None:
        if not ENV_EXAMPLE.is_file():
            return []
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
    keys: List[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _ordered_keys() -> List[str]:
    ordered = keys_from_env_example()
    seen = set(ordered)
    for key in CATALOG:
        if key not in seen:
            ordered.append(key)
            seen.add(key)
    return ordered


def redact_postgres_url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.password:
        return value
    user = parts.username or ""
    host = parts.hostname or ""
    netloc = f"{user}:***@{host}" if user else f"***@{host}"
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def present_config(environ: Mapping[str, str]) -> List[Dict[str, Any]]:
    rows = []
    for key in _ordered_keys():
        spec = CATALOG.get(key)
        raw = environ.get(key)
        secret = _is_secret_key(key, spec)
        if secret:
            shown = "***" if raw else None
        elif raw and _should_redact_url(key):
            shown = redact_postgres_url(raw)
        else:
            shown = raw
        rows.append(
            {
                "key": key,
                "value": shown,
                "help_text": spec.help_text if spec else "Declared in .env.example.",
                "help_url": spec.help_url if spec else DOCS_ENV,
                "secret": secret,
            }
        )
    return rows


def apply_updates(
    _environ: MutableMapping[str, str], updates: Mapping[str, Optional[str]]
) -> tuple[list[str], list[str]]:
    return [], list(updates.keys())
