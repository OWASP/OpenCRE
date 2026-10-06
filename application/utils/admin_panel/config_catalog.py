"""Allowlisted admin config keys: help text and secret redaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional


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
            "Route chat completions through the OWASP metadata agent.",
            DOCS_ENV,
        ),
        ConfigKey(
            "OWASP_AGENT_DB",
            "SQLite path for the OWASP agent index (not the CRE graph).",
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
    )
}


def present_config(environ: Mapping[str, str]) -> List[Dict[str, Any]]:
    rows = []
    for key, spec in CATALOG.items():
        raw = environ.get(key)
        rows.append(
            {
                "key": key,
                "value": ("***" if raw else None) if spec.secret else raw,
                "help_text": spec.help_text,
                "help_url": spec.help_url,
                "secret": spec.secret,
            }
        )
    return rows


def apply_updates(
    environ: MutableMapping[str, str], updates: Mapping[str, Optional[str]]
) -> tuple[list[str], list[str]]:
    """Runtime env is read-only over HTTP; every key is rejected."""
    del environ
    return [], list(updates.keys())
