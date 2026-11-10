#!/usr/bin/env python
"""Build the Module C golden dataset from committed JSON fixture inputs.

The builder derives the dataset from
``application/tests/librarian/fixtures/dataset_inputs/`` and does not require
a database at build time.

The fixture inputs contain source-node mappings and curated examples for the
five dataset slices:

  positive       : ASVS requirements and multi-link rows from OWASP Top 10
                   and CWE, plus OWASP Cheat Sheet examples

  hard_negative  : ASVS requirements whose text contains a negation phrase
                   ("do not", "does not", "shall not", "should not")

  explicit       : synthesized text that literally cites a real CRE external ID

  update         : synthesized before/after pairs of ASVS requirements

  ambiguous      : broad ASVS V1.x SDLC/governance requirements, decision=review

Use ``scripts/refresh_golden_dataset_inputs.py`` to refresh the fixture inputs
from ``standards_cache.sqlite``. The refresh utility preserves historical
multi-link pins by default.

Output is deterministic, so ``--check`` verifies that the committed JSON
matches the fixture derivation while ignoring whitespace differences only.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUTS = REPO_ROOT / "application/tests/librarian/fixtures/dataset_inputs"
DEFAULT_OUT = REPO_ROOT / "application/tests/librarian/fixtures/golden_dataset.json"
SCHEMA_VERSION = "0.1.0"


# ---- Fixture inputs --------------------------------------------------------

SOURCE_NODES = []
CURATED_EXPLICIT = []
CURATED_UPDATE = []
CURATED_AMBIGUOUS = []
CHEATSHEET_FIXTURES = []
MULTILINK_PINS = []


def load_fixture_inputs() -> None:
    global SOURCE_NODES
    global CURATED_EXPLICIT
    global CURATED_UPDATE
    global CURATED_AMBIGUOUS
    global CHEATSHEET_FIXTURES
    global MULTILINK_PINS

    curated_data = json.loads(
        (DEFAULT_INPUTS / "curated.json").read_text(encoding="utf-8")
    )
    SOURCE_NODES = json.loads(
        (DEFAULT_INPUTS / "source_nodes.json").read_text(encoding="utf-8")
    )

    CURATED_EXPLICIT = curated_data["explicit"]
    CURATED_UPDATE = curated_data["update"]
    CURATED_AMBIGUOUS = curated_data["ambiguous"]
    CHEATSHEET_FIXTURES = curated_data["cheatsheet_fixtures"]
    MULTILINK_PINS = curated_data["multilink_pins"]


def _fetch_asvs_cre(section_id: str) -> str | None:
    matches = [
        node
        for node in SOURCE_NODES
        if node["standard"] == "ASVS" and node["section_id"] == section_id
    ]

    if not matches:
        return None

    cre_ids = sorted({cre_id for node in matches for cre_id in node["cre_ids"]})

    if len(cre_ids) > 1:
        raise ValueError(
            f"ASVS section {section_id!r} maps to multiple CREs "
            f"({', '.join(cre_ids)}); cannot pick a golden CRE"
        )

    return cre_ids[0]


def build_positive_asvs() -> List[Dict]:
    pairs = sorted(
        {
            (node["section_id"], cre_id, node["section"])
            for node in SOURCE_NODES
            if node["standard"] == "ASVS"
            for cre_id in node["cre_ids"]
        },
        key=lambda item: (item[0], item[1]),
    )

    out = []
    for section_id, ext_id, text in pairs:
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


def build_positive_multilink() -> List[Dict]:
    nodes_by_key = {(node["name"], node["section_id"]): node for node in SOURCE_NODES}

    pins = sorted(
        MULTILINK_PINS,
        key=lambda pin: (pin["name"], pin["section_id"]),
    )

    out = []
    for pin in pins:
        key = (pin["name"], pin["section_id"])
        node = nodes_by_key.get(key)

        if node is None:
            raise ValueError(f"Pinned multi-link node not found: {key!r}")

        name = node["name"]
        section_id = node["section_id"]
        text = node["section"]
        cre_ids = sorted(set(node["cre_ids"]))

        if text is None or len(text) <= 20:
            raise ValueError(f"Pinned multi-link node {key!r} has invalid section text")

        if not 2 <= len(cre_ids) <= 4:
            raise ValueError(
                f"Pinned multi-link node {key!r} must have 2-4 CRE IDs; "
                f"found {len(cre_ids)}"
            )

        std = "OTHER"
        if "Top 10" in name:
            std = "OTHER"

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


def build_positive_cheatsheets() -> List[Dict]:
    """Build positive golden rows from the OWASP Cheat Sheet supplement."""
    supplement_path = (
        REPO_ROOT
        / "application/tests/fixtures/owasp_mappings/owasp_cheatsheets_supplement.json"
    )

    supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
    mappings = {entry["section"]: entry["cre_ids"] for entry in supplement}

    out = []
    for entry in CHEATSHEET_FIXTURES:
        cre_ids = mappings.get(entry["section"])
        if not cre_ids:
            raise ValueError(
                f"No CRE mapping found for Cheat Sheet {entry['section']!r}"
            )

        out.append(
            {
                "id": entry["id"],
                "schema_version": SCHEMA_VERSION,
                "slice": "positive",
                "input": {
                    "text": entry["text"],
                    "title_hint": entry["title_hint"],
                    "source_standard": "OWASP_CHEATSHEET",
                },
                "expected": {
                    "decision": "linked",
                    "cre_ids": cre_ids,
                },
                "provenance": {
                    "section_path": entry["section_path"],
                    "ground_truth_source": "owasp_cheatsheets_supplement.json",
                },
            }
        )

    return out


def build_hard_negative() -> List[Dict]:
    rows = []

    negation_phrases = (
        "do not",
        "does not",
        "shall not",
        "should not",
    )

    for node in SOURCE_NODES:
        if node["standard"] != "ASVS":
            continue

        text = node["section"]
        if text is None:
            continue

        lowered = text.lower()
        if not any(phrase in lowered for phrase in negation_phrases):
            continue

        for cre_id in node["cre_ids"]:
            rows.append((node["section_id"], text, cre_id))

    rows.sort(key=lambda row: (row[0], row[2]))
    rows = rows[:12]

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


def build_explicit() -> List[Dict]:
    out = []
    for entry in CURATED_EXPLICIT:
        cre = _fetch_asvs_cre(entry["asvs_section_id"])
        if cre is None:
            raise ValueError(
                f"no CRE mapping found for explicit row {entry['id']} "
                f"(ASVS section {entry['asvs_section_id']})"
            )

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


def build_update() -> List[Dict]:
    out = []
    for entry in CURATED_UPDATE:
        cre = _fetch_asvs_cre(entry["asvs_section_id"])
        if cre is None:
            raise ValueError(
                f"no CRE mapping found for update row {entry['id']} "
                f"(ASVS section {entry['asvs_section_id']})"
            )

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


def build() -> List[Dict]:
    load_fixture_inputs()
    rows: List[Dict] = []

    rows.extend(build_explicit())
    rows.extend(build_positive_asvs())
    rows.extend(build_positive_multilink())
    rows.extend(build_hard_negative())
    rows.extend(build_update())
    rows.extend(build_ambiguous())
    rows.extend(build_positive_cheatsheets())

    return rows


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive and verify --out matches (ignoring whitespace only); exit non-zero on drift",
    )
    args = parser.parse_args(argv)

    rows = build()
    text = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not Path(args.out).exists():
            print(f"--check: output file not found: {args.out}", file=sys.stderr)
            return 1

        existing_text = Path(args.out).read_text(encoding="utf-8")
        canonical = (
            json.dumps(
                json.loads(existing_text),
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )

        if canonical != text:
            print(
                "DRIFT: golden dataset content or record order differs from fixture "
                "derivation (comparison ignores whitespace only). "
                "Re-run without --check.",
                file=sys.stderr,
            )
            return 1

        print(f"OK: golden dataset matches fixture derivation ({len(rows)} rows)")
        return 0

    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
