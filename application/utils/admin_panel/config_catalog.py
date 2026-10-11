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
    #: When True, PUT /admin/config may set this key on the running process env.
    writable: bool = False


def _normalize_bool_env(value: Optional[str]) -> Optional[str]:
    """Return ``1`` / ``0`` for truthy/falsey strings, else None."""
    if value is None:
        return "0"
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return "1"
    if text in ("0", "false", "no", "off", ""):
        return "0"
    return None


CATALOG: Dict[str, ConfigKey] = {
    k.key: k
    for k in (
        ConfigKey(
            "OIE_GRAPH_FILING_ENABLED",
            "Module C.1: when on, auto-add high-confidence Librarian links "
            "(Automatically linked to). Default off — linked/review rows stay "
            "in decision_queue for review.",
            DOCS_LIBRARIAN,
            writable=True,
        ),
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
ENV_DOTENV = Path(__file__).resolve().parents[3] / ".env"
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
                "writable": bool(spec.writable) if spec else False,
            }
        )
    return rows


def parse_dotenv_file(path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE lines from a dotenv file (no export, no interpolation)."""
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def _redact_value(
    key: str, raw: Optional[str], spec: Optional[ConfigKey]
) -> Optional[str]:
    if raw is None:
        return None
    if raw == "":
        return ""
    secret = _is_secret_key(key, spec)
    if secret:
        return "***"
    if _should_redact_url(key):
        return redact_postgres_url(raw)
    return raw


def _normalize_compare(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return "1"
    if text in ("0", "false", "no", "off", ""):
        return "0"
    return str(value).strip()


def present_config_diff(
    environ: Mapping[str, str],
    *,
    dotenv_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Compare process env to ``.env`` (fallback: empty) for catalog + dotenv keys."""
    path = dotenv_path if dotenv_path is not None else ENV_DOTENV
    dotenv = parse_dotenv_file(path)
    keys = list(_ordered_keys())
    seen = set(keys)
    for key in dotenv:
        if key not in seen:
            keys.append(key)
            seen.add(key)
    rows: List[Dict[str, Any]] = []
    for key in keys:
        spec = CATALOG.get(key)
        proc_raw = environ.get(key)
        file_raw = dotenv.get(key) if key in dotenv else None
        in_process = key in environ
        in_file = key in dotenv
        if in_process and not in_file:
            status = "process_only"
        elif in_file and not in_process:
            status = "missing"
        elif _normalize_compare(proc_raw) == _normalize_compare(file_raw):
            status = "match"
        else:
            status = "diff"
        rows.append(
            {
                "key": key,
                "process": _redact_value(key, proc_raw if in_process else None, spec),
                "dotenv": _redact_value(key, file_raw if in_file else None, spec),
                "status": status,
                "help_text": (
                    spec.help_text if spec else "Declared in .env / .env.example."
                ),
                "help_url": spec.help_url if spec else DOCS_ENV,
                "secret": _is_secret_key(key, spec),
            }
        )
    return rows


def apply_updates(
    environ: MutableMapping[str, str], updates: Mapping[str, Optional[str]]
) -> tuple[list[str], list[str]]:
    """Apply allowlisted writable keys to ``environ`` (process-local)."""
    applied: List[str] = []
    rejected: List[str] = []
    for key, value in updates.items():
        spec = CATALOG.get(key)
        if spec is None or not spec.writable or spec.secret:
            rejected.append(key)
            continue
        if key == "OIE_GRAPH_FILING_ENABLED":
            normalized = _normalize_bool_env(value)
            if normalized is None:
                rejected.append(key)
                continue
            environ[key] = normalized
            applied.append(key)
            continue
        rejected.append(key)
    return applied, rejected
