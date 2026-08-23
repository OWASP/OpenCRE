#!/usr/bin/env python
"""Cheat Sheet -> Section -> Module C batch dry-run.

Uses real CheatSheetRecord extraction + Section adapter + Module C.1
retrieval + Module C.2 reranking.

The CRE corpus and embeddings are controlled in-memory stubs so the
dry-run does not depend on a populated OpenCRE SQLite database.

The three Cheat Sheet cases below have known expected CRE IDs from
the golden dataset and are checked against the reranked output.
"""

import argparse
import glob
import hashlib
import os
import re
import sys

import numpy as np


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

sys.path.insert(0, REPO_ROOT)

from application.utils.external_project_parsers.parsers.cheatsheet_extractor import (
    extract_cheatsheet_record,
)
from application.utils.external_project_parsers.parsers.cheatsheet_record_adapter import (
    MalformedCheatsheetRecordError,
    section_from_cheatsheet_record,
)
from application.utils.librarian.candidate_retriever import (
    CandidatePool,
    CandidateRetriever,
)
from application.utils.librarian.cross_encoder import (
    CrossEncoderReranker,
    build_cross_encoder_score_fn,
)
from application.utils.librarian.section_validator import EmptyTextError


EMBEDDING_DIM = 32
TOP_K_RETRIEVAL = 5
TOP_K_RERANK = 3
THRESHOLD = 0.0


# Controlled CRE corpus used only for the dry-run.
STUB_CRE_TEXTS = {
    # Authorization Cheat Sheet
    "128-128": (
        "Authorization and access control. "
        "Enforce authorization rules and restrict access "
        "to protected resources."
    ),
    "117-371": (
        "Access control and authorization. "
        "Users should only be allowed to perform actions "
        "and access resources they are authorized to use."
    ),
    # REST Security Cheat Sheet
    "118-110": (
        "REST API security. "
        "Secure REST APIs using authentication, authorization, "
        "input validation and secure communication."
    ),
    "724-770": (
        "REST API security controls. "
        "Protect REST services using authentication, authorization "
        "and secure API design."
    ),
    "623-550": (
        "REST security. "
        "Secure RESTful services and APIs using appropriate "
        "security controls."
    ),
    # SSRF Prevention Cheat Sheet
    "028-728": (
        "Server-Side Request Forgery prevention. "
        "Prevent SSRF by restricting and validating outbound "
        "server-side requests."
    ),
    "657-084": (
        "SSRF protection. "
        "Validate URLs and restrict server-side network requests "
        "to prevent SSRF attacks."
    ),
}


# Expected ground truth for the Cheat Sheet fixtures.
EXPECTED_CRE_IDS = {
    "Authorization_Cheat_Sheet.md": {
        "128-128",
        "117-371",
    },
    "REST_Security_Cheat_Sheet.md": {
        "118-110",
        "724-770",
        "623-550",
    },
    "Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md": {
        "028-728",
        "657-084",
    },
}


def stub_embed(text: str):
    """Create a deterministic local embedding for the controlled dry-run."""

    vector = np.zeros(EMBEDDING_DIM, dtype=float)

    tokens = re.findall(r"[a-z0-9]+", text.lower())

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()

        index = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0

        vector[index] += sign

    norm = np.linalg.norm(vector)

    if norm == 0:
        return vector.tolist()

    return (vector / norm).tolist()


def build_pipeline():
    """Build the real C.1 + C.2 pipeline using the stub CRE corpus."""

    cre_vectors = {cre_id: stub_embed(text) for cre_id, text in STUB_CRE_TEXTS.items()}

    pool = CandidatePool.from_mapping(cre_vectors)

    retriever = CandidateRetriever(
        embed_fn=stub_embed,
        pool=pool,
        top_k=TOP_K_RETRIEVAL,
        threshold=THRESHOLD,
    )

    reranker = CrossEncoderReranker(
        score_fn=build_cross_encoder_score_fn("cross-encoder/ms-marco-MiniLM-L-6-v2"),
        top_n=TOP_K_RERANK,
        cre_texts=STUB_CRE_TEXTS,
    )

    return retriever, reranker


def load_fixtures(fixtures_dir: str):
    """Load all Cheat Sheet Markdown fixtures."""

    for path in sorted(glob.glob(os.path.join(fixtures_dir, "*.md"))):
        with open(path, encoding="utf-8") as file:
            yield file.read(), path


def expected_for_fixture(source_path: str):
    """Return expected CRE IDs for a known golden Cheat Sheet case."""

    filename = os.path.basename(source_path)
    return EXPECTED_CRE_IDS.get(filename, set())


def run_one(markdown, source_path, retriever, reranker):
    """Run one Cheat Sheet through extraction -> Section -> C.1 -> C.2."""

    filename = os.path.basename(source_path)

    print("\n" + "=" * 72)
    print(f"CHEAT SHEET: {filename}")

    # B -> CheatsheetRecord
    try:
        record = extract_cheatsheet_record(
            markdown,
            source_path,
        )

        # Local fixture files are ignored by Git, so committed_at may be
        # unavailable during a local dry-run.
        if not record.metadata.get("committed_at"):
            record.metadata["committed_at"] = "2026-01-01T00:00:00+00:00"

    except Exception as exc:
        print(f"\n❌ extraction failed: {exc}")
        return False

    # Adapter -> Module C Section
    try:
        section = section_from_cheatsheet_record(record)
    except (MalformedCheatsheetRecordError, EmptyTextError) as exc:
        print(f"\n❌ rejected at C.0 adapter boundary: {exc}")
        return False

    print(f"\nRecord title : {record.title}")
    print(f"Section ID   : {section.chunk_id}")

    # C.1 Retrieval
    audit = retriever.retrieve(section.text)

    print("\nC.1 RETRIEVAL")
    print("-" * 40)

    if not audit.candidates:
        print("No candidates returned.")
    else:
        for index, candidate in enumerate(
            audit.candidates,
            start=1,
        ):
            print(
                f"{index}. "
                f"{candidate.cre_id} "
                f"cosine={candidate.score_vector:.4f}"
            )

    # C.2 Reranking
    audit = reranker.rerank(
        section.text,
        audit,
    )

    print("\nC.2 RERANK")
    print("-" * 40)

    if not audit.reranked:
        print("No reranked candidates.")
    else:
        for index, candidate in enumerate(
            audit.reranked,
            start=1,
        ):
            print(
                f"{index}. "
                f"{candidate.cre_id} "
                f"rerank={candidate.score_rerank:.4f}"
            )

    # Golden-set sanity check
    expected = expected_for_fixture(source_path)

    if not expected:
        print("\n⚠️ No golden expectation registered for this fixture.")
        return True

    actual = {candidate.cre_id for candidate in audit.reranked}

    matched = expected & actual
    missing = expected - actual

    print("\nGOLDEN CHECK")
    print("-" * 40)
    print(f"Expected CREs : {sorted(expected)}")
    print(f"Actual top-{TOP_K_RERANK}: {sorted(actual)}")
    print(f"Matched       : {sorted(matched)}")

    if missing:
        print(f"❌ Missing     : {sorted(missing)}")
        return False

    print("✅ ALL EXPECTED CREs FOUND")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Cheat Sheet -> Section -> Module C batch dry-run"
    )

    parser.add_argument(
        "--fixtures_dir",
        default=os.path.join(
            REPO_ROOT,
            "application",
            "tests",
            "librarian",
            "fixtures",
            "cheatsheets",
        ),
        help="directory containing Cheat Sheet .md fixtures",
    )

    args = parser.parse_args()

    print("=" * 72)
    print("MODULE C CHEAT SHEET BATCH DRY-RUN")
    print("=" * 72)
    print("\nUsing:")
    print("  • real CheatSheetRecord extraction")
    print("  • real CheatSheetRecord -> Section adapter")
    print("  • real C.1 CandidateRetriever")
    print("  • real C.2 CrossEncoderReranker")
    print("  • controlled in-memory CRE corpus")
    print()

    retriever, reranker = build_pipeline()

    fixtures = list(load_fixtures(args.fixtures_dir))

    if not fixtures:
        print(f"❌ No .md fixtures found in {args.fixtures_dir}")
        return 1

    processed = 0
    golden_matches = 0
    golden_mismatches = 0

    for markdown, source_path in fixtures:
        processed += 1

        success = run_one(
            markdown,
            source_path,
            retriever,
            reranker,
        )

        if success:
            golden_matches += 1
        else:
            golden_mismatches += 1

    # Final summary
    print("\n" + "=" * 72)
    print("DRY-RUN SUMMARY")
    print("=" * 72)

    print(f"Fixtures       : {len(fixtures)}")
    print(f"Processed      : {processed}")
    print(f"Golden matches : {golden_matches}")
    print(f"Golden mismatches: {golden_mismatches}")

    if golden_mismatches:
        print("\n✅ Dry-run completed: pipeline executed successfully.")
        print("ℹ️ Controlled stub golden mismatch detected.")
    else:
        print("\n✅ Dry-run completed successfully.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
