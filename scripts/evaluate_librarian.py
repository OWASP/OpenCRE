#!/usr/bin/env python
"""Module C regression harness — Week 2: C.0 deterministic input boundary.

On top of the W1 skeleton (golden dataset + scorer + TRACT hub-firewall),
the harness now runs every golden row through the C.0 boundary:

1. SectionValidator — each row is adapted to a synthetic knowledge_queue row
   and must validate into an internal ``Section``; the harness prints the
   validation pass rate per slice.
2. ExplicitLinkResolver — sections citing a CRE id resolve deterministically
   (no ML); the explicit slice is gated at 100% correctness.

The semantic path (retriever W3, cross-encoder W4) is still stubbed: rows
without an explicit reference yield no predictions.
"""

import argparse
import json
import os
import sys
from collections import Counter
from typing import List, Set

# Bootstrap project root onto sys.path so this runs as a standalone script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from application.utils.librarian.config_loader import load_config
from application.utils.librarian.explicit_link_resolver import (
    ResolutionOutcome,
    resolve,
)
from application.utils.librarian.hub_firewall import HubRep, firewall, leaks
from application.utils.librarian.schemas import GoldenDatasetRow
from application.utils.librarian.scoring import score_case
from application.utils.librarian.section_validator import (
    Section,
    SectionValidationError,
    section_from_queue_row,
)

# Harness-only synthetic provenance: golden rows are not queue rows, so we
# synthesize the minimum B-shaped row needed to exercise the C.0 boundary.
_SYNTHETIC_SHA = "0" * 40
_SYNTHETIC_CREATED_AT = "2026-06-01T00:00:00Z"


def load_dataset(path: str) -> List[GoldenDatasetRow]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [GoldenDatasetRow.model_validate(row) for row in raw]


def queue_row_from_golden(row: GoldenDatasetRow) -> dict:
    """Adapt a golden row into the knowledge_queue shape C.0 validates."""
    standard = row.input.source_standard.value if row.input.source_standard else "OTHER"
    return {
        "id": row.id,
        "source_repo": f"golden/{standard}",
        "source_path": row.provenance.section_path or "unknown.md",
        "source_commit_sha": _SYNTHETIC_SHA,
        "text": row.input.text,
        "confidence": 0.99,
        "llm_label": "KNOWLEDGE",
        "created_at": _SYNTHETIC_CREATED_AT,
        "consumed_at": None,
    }


def build_stub_hub(rows: List[GoldenDatasetRow]) -> List[HubRep]:
    # The golden standards are already linked into OpenCRE, so seed the hub
    # from their own text. This is the leakage the firewall must strip.
    # W3 replaces this with the real CRE vector hub.
    return [HubRep(row.id, row.input.text) for row in rows]


def known_cre_ids(rows: List[GoldenDatasetRow]) -> Set[str]:
    # Harness registry stub: every CRE id the golden set references is a real
    # cre.external_id (see provenance). W3 swaps in the DB-backed id set.
    ids: Set[str] = set()
    for row in rows:
        ids.update(row.expected.cre_ids or [])
        if row.input.explicit_cre_ref:
            ids.add(row.input.explicit_cre_ref)
    return ids


def predict(section: Section, registry: Set[str], hub: List[HubRep]) -> List[str]:
    # C.0.5: deterministic explicit path. Unknown/conflicting references route
    # to review (no auto-link), so they predict nothing here.
    resolution = resolve(section.text, registry)
    if resolution.outcome == ResolutionOutcome.resolved:
        return list(resolution.cre_ids)
    # Semantic path (C.1 retriever + C.2 ranker) lands W3/W4.
    return []


def report_retrieval_recall(
    rows: List[GoldenDatasetRow],
    cache_file: str,
    top_k: int,
    threshold: float,
    top_n_rerank: int,
    crossencoder_model: str,
) -> None:
    """Measure the live C.1 -> C.2 pipeline over the positive slice (v1).

    Two metrics, both live — there is no honest offline value: the candidate
    pool must be the real CRE-node vectors, and seeding it from the golden text
    is exactly the leakage the hub firewall strips.

    - retrieval recall@k (C.1): does the expected CRE id make it into the top-K
      shortlist the reranker will see? A miss here is unrecoverable downstream.
    - rerank top-1 (C.2): after the cross-encoder re-reads each pair and re-sorts
      the shortlist, is the #1 candidate an expected CRE? This is the first
      end-to-end accuracy number for the search path (W4 target >= 0.80).
    """
    # Live deps are imported lazily so the offline harness needs neither a DB,
    # an embedding model, nor the cross-encoder stack.
    from application.cmd.cre_main import db_connect
    from application.defs import cre_defs
    from application.prompt_client import prompt_client
    from application.utils.librarian.candidate_retriever import (
        CandidatePool,
        CandidateRetriever,
    )
    from sqlalchemy import text as _sql_text
    from application.utils.librarian.cross_encoder import (
        CrossEncoderReranker,
        build_cross_encoder_score_fn,
    )

    database = db_connect(path=cache_file)
    ph = prompt_client.PromptHandler(database=database)

    # The embeddings pool is keyed by the CRE's internal UUID (add_embedding
    # stores cre_id=db_object.id), but the golden dataset and the explicit
    # resolver both speak external_ids ("616-305"). Translate the pool/reranker
    # keys to external_id so recall/top-1 compare in the same id-space. Keys not
    # in the map (a DB that already stores external_ids) pass through unchanged.
    id_to_ext = {
        row[0]: row[1]
        for row in database.session.execute(
            _sql_text("SELECT id, external_id FROM cre")
        )
        if row[1]
    }

    def _to_ext(mapping):
        return {id_to_ext.get(k, k): v for k, v in mapping.items()}

    pool = CandidatePool.from_mapping(
        _to_ext(database.get_embeddings_by_doc_type(cre_defs.Credoctypes.CRE.value))
    )
    retriever = CandidateRetriever(
        embed_fn=ph.get_text_embeddings,
        pool=pool,
        top_k=top_k,
        threshold=threshold,
    )
    reranker = CrossEncoderReranker(
        score_fn=build_cross_encoder_score_fn(crossencoder_model),
        top_n=top_n_rerank,
        cre_texts=_to_ext(
            database.get_embedding_contents_by_doc_type(cre_defs.Credoctypes.CRE.value)
        ),
    )

    positives = [r for r in rows if r.slice.value == "positive" and r.expected.cre_ids]
    if not positives:
        print("retrieval recall: no positive rows with expected ids in this selection")
        return
    any_hit = all_hit = top1_hit = 0
    for row in positives:
        audit = retriever.retrieve(row.input.text)
        audit = reranker.rerank(row.input.text, audit)
        retrieved = {c.cre_id for c in audit.candidates}
        expected = set(row.expected.cre_ids or [])
        if expected & retrieved:
            any_hit += 1
        if expected <= retrieved:
            all_hit += 1
        if audit.reranked and audit.reranked[0].cre_id in expected:
            top1_hit += 1
    n = len(positives)
    print(
        f"retrieval recall@{top_k} (live, {n} positive rows): "
        f"any-hit {any_hit}/{n} ({any_hit / n:.0%}), "
        f"all-hit {all_hit}/{n} ({all_hit / n:.0%})"
    )
    print(
        f"rerank top-1 (C.2, top_n={top_n_rerank}): "
        f"{top1_hit}/{n} ({top1_hit / n:.0%})"
    )


def main(argv: List[str]) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Module C eval harness (W2: C.0)")
    parser.add_argument("--dataset", required=True, help="path to golden_dataset.json")
    parser.add_argument("--slice", help="only evaluate this slice")
    parser.add_argument("--limit", type=int, help="cap number of rows")
    parser.add_argument("--threshold", type=float, default=cfg.link_threshold)
    parser.add_argument("--top_k_retrieval", type=int, default=cfg.top_k_retrieval)
    parser.add_argument("--top_k_rerank", type=int, default=cfg.top_k_rerank)
    parser.add_argument(
        "--no_hub_firewall",
        action="store_true",
        help="disable the leakage firewall (firewall is ON by default)",
    )
    parser.add_argument(
        "--use_live_embeddings",
        action="store_true",
        help="connect to the OpenCRE DB + embedding model and measure the live "
        "C.1 retrieval recall@k and C.2 rerank top-1 over the positive slice "
        "(needs an LLM + populated DB)",
    )
    parser.add_argument(
        "--cache_file",
        default="standards_cache.sqlite",
        help="OpenCRE cache DB path for --use_live_embeddings",
    )
    args = parser.parse_args(argv)

    rows = load_dataset(args.dataset)
    if args.slice:
        rows = [r for r in rows if r.slice.value == args.slice]
    if args.limit is not None:
        rows = rows[: args.limit]

    hub = build_stub_hub(rows)
    registry = known_cre_ids(rows)
    firewall_on = not args.no_hub_firewall

    per_slice = Counter(r.slice.value for r in rows)
    validated_per_slice: Counter = Counter()
    correct = 0
    stripped = 0
    explicit_total = 0
    explicit_correct = 0
    for row in rows:
        try:
            section = section_from_queue_row(queue_row_from_golden(row))
        except SectionValidationError:
            continue  # rejected at the boundary; counts against the pass rate
        validated_per_slice[row.slice.value] += 1

        hub_view = firewall(section.text, hub) if firewall_on else hub
        if firewall_on and leaks(section.text, hub):
            stripped += 1
        case_correct = score_case(
            row.expected.cre_ids or [], predict(section, registry, hub_view)
        )
        if case_correct:
            correct += 1
        if row.slice.value == "explicit":
            explicit_total += 1
            if case_correct:
                explicit_correct += 1

    print(f"loaded {len(rows)} golden rows from {args.dataset}")
    print("validation pass rate (C.0 boundary):")
    for slice_name in sorted(per_slice):
        passed = validated_per_slice[slice_name]
        total = per_slice[slice_name]
        print(f"  {slice_name:<14} {passed}/{total} ({passed / total:.0%})")
    print(
        f"hub-firewall: {'ON' if firewall_on else 'OFF'}; "
        f"stripped {stripped} leaking hub entries"
    )
    if explicit_total:
        gate_ok = explicit_correct == explicit_total
        print(
            f"explicit slice (C.0.5 resolver): {explicit_correct}/{explicit_total} "
            f"— gate 100%: {'PASS' if gate_ok else 'FAIL'}"
        )
        if not gate_ok:
            return 1
    if args.use_live_embeddings:
        report_retrieval_recall(
            rows,
            args.cache_file,
            args.top_k_retrieval,
            args.threshold,
            args.top_k_rerank,
            cfg.crossencoder_model,
        )
    else:
        print(
            "semantic pipeline (C.1 retrieve + C.2 rerank): wired; recall@k and "
            "rerank top-1 need --use_live_embeddings (no CRE vectors offline — "
            "seeding from golden text would be leakage)"
        )
    print(f"correct overall (semantic path still stubbed): {correct}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
