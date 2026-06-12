#!/usr/bin/env python
"""Module C regression harness — Week 1 skeleton.

Loads + validates the golden dataset, applies the TRACT hub-firewall (on by
default), and prints per-slice counts. No linking yet: predictions are empty, so
this only proves the dataset, scorer, and firewall wire together. Later weeks
plug the C.0 -> C.4 pipeline in where ``predict()`` is stubbed below, and swap
the stub hub for the real CRE vector hub.
"""

import argparse
import json
import os
import sys
from collections import Counter
from typing import List

# Bootstrap project root onto sys.path so this runs as a standalone script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from application.utils.librarian.config_loader import load_config
from application.utils.librarian.hub_firewall import HubRep, firewall, leaks
from application.utils.librarian.schemas import GoldenDatasetRow
from application.utils.librarian.scoring import score_case


def load_dataset(path: str) -> List[GoldenDatasetRow]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [GoldenDatasetRow.model_validate(row) for row in raw]


def build_stub_hub(rows: List[GoldenDatasetRow]) -> List[HubRep]:
    # W1 stub: the golden standards are already linked into OpenCRE, so seed the
    # hub from their own text. This is the leakage the firewall must strip.
    # W3 replaces this with the real CRE vector hub.
    return [HubRep(row.id, row.input.text) for row in rows]


def predict(row: GoldenDatasetRow, hub: List[HubRep]) -> List[str]:
    # W1 stub: no retriever/ranker yet. Returns no predictions.
    return []


def main(argv: List[str]) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Module C eval harness (W1 skeleton)")
    parser.add_argument("--dataset", required=True, help="path to golden_dataset.json")
    parser.add_argument("--slice", help="only evaluate this slice")
    parser.add_argument("--limit", type=int, help="cap number of rows")
    parser.add_argument("--threshold", type=float, default=cfg.link_threshold)
    parser.add_argument("--top_k_retrieval", type=int, default=cfg.top_k_retrieval)
    parser.add_argument("--top_k_rerank", type=int, default=cfg.top_k_rerank)
    parser.add_argument(
        "--dry_run", action="store_true", help="no writes (always true in W1)"
    )
    parser.add_argument(
        "--no_hub_firewall",
        action="store_true",
        help="disable the leakage firewall (firewall is ON by default)",
    )
    args = parser.parse_args(argv)

    rows = load_dataset(args.dataset)
    if args.slice:
        rows = [r for r in rows if r.slice.value == args.slice]
    if args.limit is not None:
        rows = rows[: args.limit]

    hub = build_stub_hub(rows)
    firewall_on = not args.no_hub_firewall

    per_slice = Counter(r.slice.value for r in rows)
    correct = 0
    stripped = 0
    for row in rows:
        hub_view = firewall(row.input.text, hub) if firewall_on else hub
        if firewall_on and leaks(row.input.text, hub):
            stripped += 1
        if score_case(row.expected.cre_ids or [], predict(row, hub_view)):
            correct += 1

    print(f"loaded {len(rows)} golden rows from {args.dataset}")
    for slice_name in sorted(per_slice):
        print(f"  {slice_name:<14} {per_slice[slice_name]}")
    print(
        f"hub-firewall: {'ON' if firewall_on else 'OFF'}; "
        f"stripped {stripped} leaking hub entries"
    )
    print(f"correct (W1 stub, no predictions): {correct}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
