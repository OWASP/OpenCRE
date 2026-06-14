"""
Workstream C: Categorization and Optional Grouping
===================================================
Provides:
  - categorize_cheatsheet(record)  -> list[str]
  - group_cheatsheets(records)     -> list[CheatsheetGroup]

Design rules
------------
* All labels come ONLY from TAXONOMY (a controlled vocabulary).
* Deterministic mode (default): pure keyword/rule matching — no LLM, no randomness.
* Same input always returns the same output.
* Unknown/ambiguous inputs map to [UNCATEGORIZED] — never raise.
* LLM path is opt-in and always has a safe deterministic fallback.
* Group IDs are stable: sha256(sorted category labels) so they survive
  re-ordering of the input list.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1.  Controlled taxonomy
# ---------------------------------------------------------------------------

#: Sentinel returned when no category matches.
UNCATEGORIZED = "uncategorized"

#: Complete approved label set.  Add new labels HERE and nowhere else.
TAXONOMY: List[str] = [
    "authentication",
    "authorization",
    "session-management",
    "cryptography",
    "secrets-management",
    "input-validation",
    "output-encoding",
    "injection",
    "api-security",
    "logging-and-monitoring",
    "error-handling",
    "file-upload",
    "xml-security",
    "deserialization",
    "supply-chain",
    "infrastructure-security",
    "network-security",
    "container-security",
    "cloud-security",
    "microservices-security",
    "access-control",
    "privacy",
    "threat-modeling",
    "incident-response",
    "vulnerability-disclosure",
    "secure-coding",
    "operations",
    "mobile-security",
    "browser-security",
    UNCATEGORIZED,
]

# Keyword → taxonomy label map.
# Keys are lowercase substrings matched against title + headings + category_hints.
# Evaluated in order; first match wins for each label (multiple labels allowed).
_KEYWORD_RULES: List[tuple[str, str]] = [
    # secrets / key management
    ("secret",          "secrets-management"),
    ("key management",  "secrets-management"),
    ("credential",      "secrets-management"),
    # authentication
    ("authentication",  "authentication"),
    ("password",        "authentication"),
    ("multi-factor",    "authentication"),
    ("mfa",             "authentication"),
    ("saml",            "authentication"),
    ("oauth",           "authentication"),
    ("oidc",            "authentication"),
    ("jwt",             "authentication"),
    ("forgot password", "authentication"),
    # authorization / access control
    ("authorization",   "authorization"),
    ("access control",  "access-control"),
    ("privilege",       "access-control"),
    ("rbac",            "access-control"),
    # session
    ("session",         "session-management"),
    # cryptography
    ("cryptograph",     "cryptography"),
    ("encrypt",         "cryptography"),
    ("tls",             "cryptography"),
    ("hashing",         "cryptography"),
    ("cipher",          "cryptography"),
    # input validation / output encoding
    ("input validation","input-validation"),
    ("sanitiz",         "input-validation"),
    ("output encoding", "output-encoding"),
    ("xss",             "output-encoding"),
    ("cross-site scrip","output-encoding"),
    # injection
    ("sql injection",   "injection"),
    ("injection",       "injection"),
    ("ldap injection",  "injection"),
    ("xxe",             "xml-security"),
    # api
    ("api security",    "api-security"),
    ("graphql",         "api-security"),
    ("rest security",   "api-security"),
    # logging / monitoring
    ("logging",         "logging-and-monitoring"),
    ("monitoring",      "logging-and-monitoring"),
    ("audit",           "logging-and-monitoring"),
    # error handling
    ("error handling",  "error-handling"),
    ("exception",       "error-handling"),
    # file upload
    ("file upload",     "file-upload"),
    # xml
    ("xml",             "xml-security"),
    ("xpath",           "xml-security"),
    # deserialization
    ("deserializ",      "deserialization"),
    # supply chain
    ("dependency",      "supply-chain"),
    ("third-party",     "supply-chain"),
    ("software composition", "supply-chain"),
    # infrastructure / network
    ("infrastructure",  "infrastructure-security"),
    ("network security","network-security"),
    ("firewall",        "network-security"),
    # container / cloud / microservices
    ("container",       "container-security"),
    ("docker",          "container-security"),
    ("kubernetes",      "container-security"),
    ("cloud",           "cloud-security"),
    ("microservice",    "microservices-security"),
    ("serverless",      "cloud-security"),
    # privacy / threat modeling / incident response
    ("privacy",         "privacy"),
    ("gdpr",            "privacy"),
    ("threat model",    "threat-modeling"),
    ("incident response","incident-response"),
    ("disclosure",      "vulnerability-disclosure"),
    # mobile / browser
    ("mobile",          "mobile-security"),
    ("android",         "mobile-security"),
    ("ios",             "mobile-security"),
    ("browser",         "browser-security"),
    ("cors",            "browser-security"),
    ("content security policy", "browser-security"),
    ("csp",             "browser-security"),
    # operations / secure coding (broad catch-alls — keep near the bottom)
    ("operational",     "operations"),
    ("rotation",        "operations"),
    ("secure coding",   "secure-coding"),
    ("secure development", "secure-coding"),
]


# ---------------------------------------------------------------------------
# 2.  CheatsheetRecord (minimal interface expected by this module)
# ---------------------------------------------------------------------------

@dataclass
class CheatsheetRecord:
    """
    Typed representation of a parsed cheat sheet.
    Workstream B owns the full implementation; this definition covers
    exactly the fields Workstream C needs so C can be developed and
    tested independently.

    Required fields must be non-empty strings / lists after normalisation.
    """
    source: str                           # always "owasp_cheatsheets"
    source_id: str                        # e.g. "Secrets_Management_Cheat_Sheet"
    title: str                            # human-readable title
    hyperlink: str                        # canonical cheatsheetseries URL
    summary: str                          # bounded summary text
    headings: List[str]                   # ordered headings from markdown
    raw_markdown_path: str                # path in the source repo
    category_hints: List[str] = field(default_factory=list)   # optional lightweight hints
    metadata: dict = field(default_factory=dict)              # trace data


# ---------------------------------------------------------------------------
# 3.  CheatsheetGroup
# ---------------------------------------------------------------------------

@dataclass
class CheatsheetGroup:
    """
    A stable group of cheat sheet records sharing the same category labels.

    group_id is deterministic: sha256 of the sorted, pipe-joined labels
    truncated to 12 hex chars.  It stays stable across repeated runs with
    the same input.
    """
    group_id: str
    labels: List[str]
    members: List[CheatsheetRecord] = field(default_factory=list)

    @staticmethod
    def make_group_id(labels: List[str]) -> str:
        key = "|".join(sorted(labels))
        return hashlib.sha256(key.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 4.  Core public functions
# ---------------------------------------------------------------------------

def categorize_cheatsheet(
    record: CheatsheetRecord,
    *,
    use_llm: bool = False,
    llm_categorize_fn=None,
) -> List[str]:
    """
    Return a list of taxonomy labels for *record*.

    Labels are drawn exclusively from TAXONOMY.
    If no label matches, returns [UNCATEGORIZED].

    Parameters
    ----------
    record:
        A CheatsheetRecord (from Workstream B or the stub above).
    use_llm:
        When True, attempt to call *llm_categorize_fn* first.
        Falls back to deterministic categorisation on any failure.
    llm_categorize_fn:
        Optional callable(record) -> list[str].  Injected for testability.
        Must return a subset of TAXONOMY values.

    Returns
    -------
    list[str]
        Ordered, deduplicated taxonomy labels.  Always at least [UNCATEGORIZED].
    """
    if use_llm and llm_categorize_fn is not None:
        try:
            llm_labels = llm_categorize_fn(record)
            validated = _validate_labels(llm_labels)
            if validated:
                logger.debug("LLM categorization used for %s", record.source_id)
                return validated
            logger.warning(
                "LLM returned no valid labels for %s, falling back to deterministic",
                record.source_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM categorization failed for %s (%s), falling back to deterministic",
                record.source_id,
                exc,
            )

    return _deterministic_categorize(record)


def group_cheatsheets(
    records: List[CheatsheetRecord],
    *,
    use_llm: bool = False,
    llm_categorize_fn=None,
) -> List[CheatsheetGroup]:
    """
    Assign every record to a CheatsheetGroup based on its category labels.

    Group IDs are stable: same set of labels → same group_id regardless of
    the order records appear in *records*.

    Parameters
    ----------
    records:
        List of CheatsheetRecord objects.
    use_llm / llm_categorize_fn:
        Forwarded to categorize_cheatsheet.

    Returns
    -------
    list[CheatsheetGroup]
        Groups sorted by group_id for deterministic output order.
    """
    bucket: dict[str, CheatsheetGroup] = {}

    for record in records:
        labels = categorize_cheatsheet(
            record, use_llm=use_llm, llm_categorize_fn=llm_categorize_fn
        )
        gid = CheatsheetGroup.make_group_id(labels)
        if gid not in bucket:
            bucket[gid] = CheatsheetGroup(group_id=gid, labels=sorted(labels))
        bucket[gid].members.append(record)

    return sorted(bucket.values(), key=lambda g: g.group_id)


# ---------------------------------------------------------------------------
# 5.  Internal helpers
# ---------------------------------------------------------------------------

def _build_searchable_text(record: CheatsheetRecord) -> str:
    """Combine title, headings, and category_hints into one lowercase string."""
    parts = [record.title] + record.headings + record.category_hints
    return " ".join(parts).lower()


def _deterministic_categorize(record: CheatsheetRecord) -> List[str]:
    """
    Pure keyword-matching categoriser.  No external calls.
    Returns sorted, deduplicated labels from TAXONOMY.
    Falls back to [UNCATEGORIZED] when nothing matches.
    """
    text = _build_searchable_text(record)
    found: List[str] = []
    seen: set[str] = set()

    for keyword, label in _KEYWORD_RULES:
        if label not in seen and keyword in text:
            found.append(label)
            seen.add(label)

    if not found:
        return [UNCATEGORIZED]

    return sorted(found)


def _validate_labels(labels) -> List[str]:
    """
    Filter an LLM-returned label list to only approved TAXONOMY entries.
    Returns [] if nothing valid remains (caller should fall back).
    """
    if not isinstance(labels, list):
        return []
    valid = [l for l in labels if isinstance(l, str) and l in TAXONOMY]
    seen: set[str] = set()
    deduped: List[str] = []
    for l in valid:
        if l not in seen:
            deduped.append(l)
            seen.add(l)
    return deduped
