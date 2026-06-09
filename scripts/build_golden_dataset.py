#!/usr/bin/env python
"""Build the Module C golden dataset from standards_cache.sqlite.

Derives ground-truth CRE labels by joining ``node`` -> ``cre_node_links`` -> ``cre``
in OpenCRE's own cache. The 5 slices are populated as follows:

  positive       : all 277 ASVS requirements (1:1 mapping)
                 + multi-link rows from OWASP Top 10 and CWE (2-4 CREs)
  hard_negative  : ASVS requirements whose text contains a negation phrase
                   ("do not", "does not", "shall not", "should not"), with
                   their real DB CRE mapping (cross-encoder must beat cosine
                   on these without losing the right CRE)
  explicit       : synthesized text that literally cites a real cre.external_id
  update         : synthesized before/after pairs of real ASVS requirements,
                   ground-truth CRE pulled from DB at build time
  ambiguous      : broad ASVS V1.x SDLC/governance requirements, decision=review

Output is deterministic (every query has an explicit ORDER BY and stable
formatting), so ``--check`` can verify the committed JSON has not drifted from
the DB-derived form.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "standards_cache.sqlite"
DEFAULT_OUT = REPO_ROOT / "application/tests/librarian/fixtures/golden_dataset.json"

SCHEMA_VERSION = "0.1.0"


# ---- Curated rows that need a real CRE id resolved at build time ----------
# Each entry pins a real ASVS section_id; the build script pulls that section's
# ground-truth CRE from the DB. Text is synthesised; ground truth stays real.

CURATED_EXPLICIT = [
    {
        "id": "gold:explicit:V2.1.1",
        "asvs_section_id": "V2.1.1",
        "text_template": (
            "Per CRE {cre}, verify that user-set passwords are at least 12 "
            "characters in length after removing leading and trailing whitespace."
        ),
        "title_hint": "Password length policy",
    },
    {
        "id": "gold:explicit:V3.4.1",
        "asvs_section_id": "V3.4.1",
        "text_template": (
            "Refer to CRE {cre}. Verify that cookie-based session tokens have "
            "the Secure attribute set."
        ),
        "title_hint": "Session cookie security",
    },
    {
        "id": "gold:explicit:V2.4.1",
        "asvs_section_id": "V2.4.1",
        "text_template": (
            "This control corresponds to CRE {cre}: passwords shall be stored "
            "using an approved key derivation function."
        ),
        "title_hint": "Credential storage",
    },
    {
        "id": "gold:explicit:V4.1.1",
        "asvs_section_id": "V4.1.1",
        "text_template": (
            "See CRE {cre} for the canonical guidance on enforcing access "
            "control rules at a trusted service layer."
        ),
        "title_hint": "Access control enforcement",
    },
    {
        "id": "gold:explicit:V8.3.1",
        "asvs_section_id": "V8.3.1",
        "text_template": (
            "Per CRE {cre}, sensitive data shall be sent to the server in the "
            "HTTP message body or headers, never in the URL query string."
        ),
        "title_hint": "Sensitive data in transit",
    },
]

CURATED_UPDATE = [
    {
        "id": "gold:update:V2.1.1",
        "asvs_section_id": "V2.1.1",
        "text": (
            "Verify that user-set passwords are at least 12 characters in "
            "length after removing leading and trailing spaces."
        ),
        "prior_text": (
            "Verify that user-set passwords are at least 12 characters in length."
        ),
    },
    {
        "id": "gold:update:V3.4.1",
        "asvs_section_id": "V3.4.1",
        "text": (
            "Verify that cookie-based session tokens have the Secure and "
            "SameSite attributes set."
        ),
        "prior_text": (
            "Verify that cookie-based session tokens have the Secure attribute set."
        ),
    },
    {
        "id": "gold:update:V2.2.1",
        "asvs_section_id": "V2.2.1",
        "text": (
            "Verify that anti-automation controls are effective at mitigating "
            "breached credential testing, brute force, account lockout, and "
            "credential stuffing attacks."
        ),
        "prior_text": (
            "Verify that anti-automation controls are effective at mitigating "
            "breached credential testing, brute force, and account lockout attacks."
        ),
    },
    {
        "id": "gold:update:V4.1.1",
        "asvs_section_id": "V4.1.1",
        "text": (
            "Verify that the application enforces access control rules on a "
            "trusted service layer, with mandatory denials on missing context."
        ),
        "prior_text": (
            "Verify that the application enforces access control rules on a "
            "trusted service layer."
        ),
    },
    {
        "id": "gold:update:V8.3.1",
        "asvs_section_id": "V8.3.1",
        "text": (
            "Verify that sensitive data is sent to the server in the HTTP "
            "message body or headers, and that any URL-borne parameters do "
            "not contain sensitive data."
        ),
        "prior_text": (
            "Verify that sensitive data is sent to the server in the HTTP "
            "message body or headers."
        ),
    },
]

CURATED_AMBIGUOUS = [
    {
        "id": "gold:ambiguous:sdlc",
        "text": (
            "Verify the use of a secure software development lifecycle that "
            "addresses security in all stages of development."
        ),
        "title_hint": "Secure SDLC",
        "reason_code": "BELOW_THRESHOLD",
    },
    {
        "id": "gold:ambiguous:culture",
        "text": (
            "Security is everyone's responsibility and should be considered "
            "throughout the organization."
        ),
        "reason_code": "NO_CANDIDATES",
    },
    {
        "id": "gold:ambiguous:governance",
        "text": (
            "Verify that the organization has a documented information "
            "security policy approved by senior management."
        ),
        "title_hint": "Governance",
        "reason_code": "BELOW_THRESHOLD",
    },
    {
        "id": "gold:ambiguous:training",
        "text": (
            "Verify that developers receive security training appropriate to "
            "their role and responsibilities."
        ),
        "reason_code": "BELOW_THRESHOLD",
    },
    {
        "id": "gold:ambiguous:risk",
        "text": (
            "Risk assessment processes are followed at every major design " "decision."
        ),
        "reason_code": "BELOW_THRESHOLD",
    },
]


def _fetch_asvs_cre(conn: sqlite3.Connection, section_id: str) -> Optional[str]:
    row = conn.execute(
        """
        SELECT c.external_id
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.name LIKE '%ASVS%' AND n.section_id = ?
        ORDER BY c.external_id
        LIMIT 1
        """,
        (section_id,),
    ).fetchone()
    return row[0] if row else None


def build_positive_asvs(conn: sqlite3.Connection) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT n.section_id, n.section, c.external_id
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.name LIKE '%ASVS%'
        ORDER BY n.section_id, c.external_id
        """
    ).fetchall()
    out = []
    for section_id, text, ext_id in rows:
        out.append(
            {
                "id": f"gold:asvs:{section_id}:positive",
                "schema_version": SCHEMA_VERSION,
                "slice": "positive",
                "input": {"text": text, "source_standard": "ASVS"},
                "expected": {"decision": "linked", "cre_ids": [ext_id]},
                "provenance": {
                    "standard_version": "4.0",
                    "section_path": section_id,
                    "ground_truth_source": "OpenCRE DB mapping (cre_node_links)",
                },
            }
        )
    return out


def build_positive_multilink(conn: sqlite3.Connection) -> List[Dict]:
    # OWASP Top 10 2021 + CWE rows with 2-4 CRE mappings and real text.
    rows = conn.execute(
        """
        SELECT n.id, n.name, n.section_id, n.section,
               GROUP_CONCAT(c.external_id, '|')
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.section IS NOT NULL AND length(n.section) > 20
          AND (n.name LIKE '%Top 10 2021%' OR n.name LIKE '%CWE%')
        GROUP BY n.id
        HAVING COUNT(DISTINCT c.external_id) BETWEEN 2 AND 4
        ORDER BY n.name, n.section_id
        LIMIT 15
        """
    ).fetchall()
    out = []
    for node_id, name, section_id, text, cre_concat in rows:
        cre_ids = sorted(set(cre_concat.split("|")))
        std = "OTHER"
        if "Top 10" in name:
            std = "OTHER"  # closest enum; not strictly ASVS/WSTG/NIST
        prefix = "top10" if "Top 10" in name else "cwe"
        out.append(
            {
                "id": f"gold:{prefix}:{section_id}:positive_multi",
                "schema_version": SCHEMA_VERSION,
                "slice": "positive",
                "input": {"text": text, "source_standard": std},
                "expected": {"decision": "linked", "cre_ids": cre_ids},
                "provenance": {
                    "section_path": section_id,
                    "ground_truth_source": (
                        "OpenCRE DB mapping (multi-CRE node from " + name + ")"
                    ),
                },
            }
        )
    return out


def build_hard_negative(conn: sqlite3.Connection) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT n.section_id, n.section, c.external_id
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.name LIKE '%ASVS%'
          AND (LOWER(n.section) LIKE '%do not%'
            OR LOWER(n.section) LIKE '%does not%'
            OR LOWER(n.section) LIKE '%shall not%'
            OR LOWER(n.section) LIKE '%should not%')
        ORDER BY n.section_id, c.external_id
        LIMIT 12
        """
    ).fetchall()
    out = []
    for section_id, text, ext_id in rows:
        out.append(
            {
                "id": f"gold:asvs:{section_id}:hard_negative",
                "schema_version": SCHEMA_VERSION,
                "slice": "hard_negative",
                "input": {"text": text, "source_standard": "ASVS"},
                "expected": {"decision": "linked", "cre_ids": [ext_id]},
                "provenance": {
                    "section_path": section_id,
                    "ground_truth_source": (
                        "OpenCRE DB mapping; negation phrasing (cross-encoder "
                        "must beat cosine without losing the correct CRE)"
                    ),
                },
            }
        )
    return out


def build_explicit(conn: sqlite3.Connection) -> List[Dict]:
    out = []
    for entry in CURATED_EXPLICIT:
        cre = _fetch_asvs_cre(conn, entry["asvs_section_id"])
        if cre is None:
            continue  # silently skip if the section isn't mapped (shouldn't happen)
        text = entry["text_template"].format(cre=cre)
        out.append(
            {
                "id": entry["id"],
                "schema_version": SCHEMA_VERSION,
                "slice": "explicit",
                "input": {
                    "text": text,
                    "title_hint": entry["title_hint"],
                    "explicit_cre_ref": cre,
                    "source_standard": "ASVS",
                },
                "expected": {"decision": "linked", "cre_ids": [cre]},
                "provenance": {
                    "section_path": entry["asvs_section_id"],
                    "ground_truth_source": (
                        "synthesised text citing the real cre.external_id "
                        "from the OpenCRE DB"
                    ),
                },
            }
        )
    return out


def build_update(conn: sqlite3.Connection) -> List[Dict]:
    out = []
    for entry in CURATED_UPDATE:
        cre = _fetch_asvs_cre(conn, entry["asvs_section_id"])
        if cre is None:
            continue
        out.append(
            {
                "id": entry["id"],
                "schema_version": SCHEMA_VERSION,
                "slice": "update",
                "input": {
                    "text": entry["text"],
                    "prior_text": entry["prior_text"],
                    "source_standard": "ASVS",
                },
                "expected": {
                    "decision": "linked",
                    "cre_ids": [cre],
                    "is_update": True,
                },
                "provenance": {
                    "section_path": entry["asvs_section_id"],
                    "ground_truth_source": (
                        "synthesised before/after wording of the real ASVS "
                        "requirement; ground-truth CRE from the OpenCRE DB"
                    ),
                },
            }
        )
    return out


def build_ambiguous() -> List[Dict]:
    out = []
    for entry in CURATED_AMBIGUOUS:
        row = {
            "id": entry["id"],
            "schema_version": SCHEMA_VERSION,
            "slice": "ambiguous",
            "input": {"text": entry["text"]},
            "expected": {
                "decision": "review",
                "reason_code": entry["reason_code"],
            },
            "provenance": {
                "ground_truth_source": (
                    "manually synthesised broad statement that should route "
                    "to human review (no single clear CRE target)"
                ),
            },
        }
        if "title_hint" in entry:
            row["input"]["title_hint"] = entry["title_hint"]
        out.append(row)
    return out


def build(conn: sqlite3.Connection) -> List[Dict]:
    rows: List[Dict] = []
    rows.extend(build_explicit(conn))
    rows.extend(build_positive_asvs(conn))
    rows.extend(build_positive_multilink(conn))
    rows.extend(build_hard_negative(conn))
    rows.extend(build_update(conn))
    rows.extend(build_ambiguous())
    return rows


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive and verify --out matches; exit non-zero on drift",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    try:
        rows = build(conn)
    finally:
        conn.close()

    text = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        existing = Path(args.out).read_text(encoding="utf-8")
        if existing != text:
            print(
                "DRIFT: golden dataset is out of sync with the DB derivation. "
                "Re-run without --check.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: golden dataset matches derivation ({len(rows)} rows)")
        return 0

    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
