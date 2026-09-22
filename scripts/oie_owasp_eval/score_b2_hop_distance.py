#!/usr/bin/env python3
"""Score cached B2 reports with CRE hop-distance buckets (GA-style weights).

Reads existing ``*.b2_report.json`` ``details`` (gold/predicted); does not re-run
Module C. Builds/caches CRE Related+Contains adjacency from local Postgres.

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/score_b2_hop_distance.py
  PYTHONPATH=. python scripts/oie_owasp_eval/score_b2_hop_distance.py --force
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from hop_distance import (  # noqa: E402
    BUCKETS,
    build_adjacency_from_db,
    load_adjacency,
    save_adjacency,
    score_details,
)

EXP = ROOT / "tmp" / "oie_owasp_eval" / "experiments"
OUT_DIR = EXP / "hop_analysis"
ADJ_PATH = OUT_DIR / "cre_adjacency.json.gz"
HIGHLIGHT = (
    "g_1_0_0_0_0.85_0_0_lawrence_0",
    "stack_winners",
    "cre_summary",
    "baseline",
)


def _connect_session(db_url: Optional[str]) -> Any:
    url = (
        db_url
        or os.environ.get("SQLALCHEMY_DATABASE_URI")
        or os.environ.get("DATABASE_URL")
        or "postgresql://cre:password@127.0.0.1:5432/cre"
    )
    # Heroku-style postgres:// → postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    return Session()


def ensure_adjacency(*, force: bool, db_url: Optional[str]) -> Any:
    if ADJ_PATH.is_file() and not force:
        print(f"Loading adjacency cache {ADJ_PATH}")
        return load_adjacency(ADJ_PATH)
    print(f"Building CRE adjacency from DB → {ADJ_PATH}")
    session = _connect_session(db_url)
    try:
        adj = build_adjacency_from_db(session)
    finally:
        session.close()
    if len(adj.known_ids) < 10:
        raise SystemExit(
            f"CRE adjacency too small ({len(adj.known_ids)} ids) — wrong DB?"
        )
    save_adjacency(adj, ADJ_PATH)
    n_edges = sum(len(adj.neighbors(n)) for n in adj.known_ids)
    print(f"  known_cres={len(adj.known_ids)} directed_edges={n_edges}")
    return adj


def discover_reports(glob_pat: str) -> List[Path]:
    paths = sorted(EXP.glob(glob_pat))
    # Also grid subdir if pattern is only top-level
    if "grid" not in glob_pat:
        paths += sorted((EXP / "grid").glob("*.b2_report.json"))
    # de-dupe
    seen = set()
    out: List[Path] = []
    for p in paths:
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        out.append(p)
    return out


def score_report(path: Path, adj: Any, *, force: bool) -> Optional[Dict[str, Any]]:
    stem = path.name.replace(".b2_report.json", "")
    out_path = OUT_DIR / f"{stem}.hop.json"
    if out_path.is_file() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))

    report = json.loads(path.read_text(encoding="utf-8"))
    details = report.get("details") or []
    if not details:
        print(f"  skip {path.name}: no details")
        return None

    scored = score_details(details, adj)
    payload = {
        "source_report": str(path.relative_to(ROOT)),
        "experiment_id": stem,
        "b2_exact_hits": report.get("hits"),
        "b2_scorable": report.get("scorable"),
        "b2_accuracy": report.get("accuracy"),
        "scorable": scored["scorable"],
        "counts": scored["counts"],
        "rates": scored["rates"],
        "pred_ids_total": scored["pred_ids_total"],
        "invented_ids_total": scored["invented_ids_total"],
        "rows": scored["rows"],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def write_summary(results: List[Dict[str, Any]]) -> None:
    results = sorted(
        results,
        key=lambda r: (
            -float((r.get("rates") or {}).get("distance1_hit") or 0),
            -float((r.get("rates") or {}).get("exact") or 0),
            r.get("experiment_id") or "",
        ),
    )
    csv_path = OUT_DIR / "summary.csv"
    md_path = OUT_DIR / "SUMMARY.md"
    fields = [
        "experiment_id",
        "scorable",
        "exact",
        "one_hop_related",
        "one_hop_contains",
        "multi_hop",
        "hallucination",
        "irrelevant",
        "pct_exact",
        "pct_one_hop_related",
        "pct_one_hop_contains",
        "pct_multi_hop",
        "pct_hallucination",
        "pct_irrelevant",
        "pct_distance1_hit",
        "pct_within_2_hops",
        "pct_within_3_hops",
        "pct_ga_path_hit",
        "pct_invented_pred",
        "b2_accuracy",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            c = r.get("counts") or {}
            rates = r.get("rates") or {}
            w.writerow(
                {
                    "experiment_id": r.get("experiment_id"),
                    "scorable": r.get("scorable"),
                    **{b: c.get(b, 0) for b in BUCKETS},
                    "pct_exact": rates.get("exact"),
                    "pct_one_hop_related": rates.get("one_hop_related"),
                    "pct_one_hop_contains": rates.get("one_hop_contains"),
                    "pct_multi_hop": rates.get("multi_hop"),
                    "pct_hallucination": rates.get("hallucination"),
                    "pct_irrelevant": rates.get("irrelevant"),
                    "pct_distance1_hit": rates.get("distance1_hit"),
                    "pct_within_2_hops": rates.get("within_2_hops"),
                    "pct_within_3_hops": rates.get("within_3_hops"),
                    "pct_ga_path_hit": rates.get("ga_path_hit"),
                    "pct_invented_pred": rates.get("invented_pred"),
                    "b2_accuracy": r.get("b2_accuracy"),
                }
            )

    lines = [
        "# B2 hop-distance analysis",
        "",
        "Exclusive buckets per scorable section (canonical gold). "
        "Weights from gap_analysis PENALTIES (RELATED=2, CONTAINS_UP=2, CONTAINS_DOWN=1).",
        "",
        "- **exact** — predicted ∩ gold",
        "- **one_hop_related** / **one_hop_contains** — distance-1 CRE edge",
        "- **multi_hop** — path length ≥ 2 (GA-useful but weaker)",
        "- **hallucination** — all predicted CRE ids invented (not in DB)",
        "- **irrelevant** — known CREs but no path to gold",
        "",
        f"- `distance1_hit` = exact + 1-hop related + 1-hop contains (good enough for precise-ish RAG / soft link)",
        f"- `within_2_hops` / `within_3_hops` = hop-capped soft hits (prefer these over unbounded `ga_path_hit`)",
        f"- `ga_path_hit` = any CRE path (often ~100% because the CRE Related+Contains graph is one component)",
        "",
        f"Reports scored: **{len(results)}**",
        f"Adjacency cache: `{ADJ_PATH.relative_to(ROOT)}`",
        "",
        "## Highlights",
        "",
        "| id | exact | d1 | ≤2 hops | ≤3 hops | related1 | contains1 | multi | halluc |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    by_id = {r["experiment_id"]: r for r in results}
    for hid in HIGHLIGHT:
        r = by_id.get(hid)
        if not r:
            continue
        c = r["counts"]
        rates = r["rates"]
        lines.append(
            f"| `{hid}` | {rates['exact']:.1%} | {rates['distance1_hit']:.1%} | "
            f"{rates.get('within_2_hops', 0):.1%} | {rates.get('within_3_hops', 0):.1%} | "
            f"{c['one_hop_related']} | {c['one_hop_contains']} | "
            f"{c['multi_hop']} | {c['hallucination']} |"
        )
    lines += [
        "",
        "## Top 15 by distance1_hit",
        "",
        "| rank | id | exact | d1 | ≤2 | ≤3 | halluc |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(results[:15], 1):
        rates = r["rates"]
        lines.append(
            f"| {i} | `{r['experiment_id']}` | {rates['exact']:.1%} | "
            f"{rates['distance1_hit']:.1%} | {rates.get('within_2_hops', 0):.1%} | "
            f"{rates.get('within_3_hops', 0):.1%} | {rates['hallucination']:.1%} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--reports-glob",
        default="*.b2_report.json",
        help="Glob under tmp/oie_owasp_eval/experiments/ (grid/ also scanned)",
    )
    ap.add_argument("--force", action="store_true", help="Rebuild adj + rescore")
    ap.add_argument("--db-url", default=None, help="Postgres URL for CRE graph")
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Score only first N reports (debug)",
    )
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    adj = ensure_adjacency(force=args.force, db_url=args.db_url)
    reports = discover_reports(args.reports_glob)
    if args.limit > 0:
        reports = reports[: args.limit]
    print(f"Scoring {len(reports)} reports…")

    results: List[Dict[str, Any]] = []
    for i, path in enumerate(reports, 1):
        if i % 50 == 0 or i == 1:
            print(f"  [{i}/{len(reports)}] {path.name}")
        payload = score_report(path, adj, force=args.force)
        if payload:
            # drop rows from summary aggregate memory — keep counts only in csv;
            # full rows already on disk
            slim = {k: v for k, v in payload.items() if k != "rows"}
            results.append(slim)

    write_summary(results)

    # Print winner spotlight
    for hid in HIGHLIGHT[:2]:
        p = OUT_DIR / f"{hid}.hop.json"
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        rates = data["rates"]
        counts = data["counts"]
        print(
            f"\n{hid}: exact={rates['exact']:.1%} d1={rates['distance1_hit']:.1%} "
            f"≤2={rates.get('within_2_hops', 0):.1%} ≤3={rates.get('within_3_hops', 0):.1%} "
            f"rel1={counts['one_hop_related']} contains1={counts['one_hop_contains']} "
            f"multi={counts['multi_hop']} halluc={counts['hallucination']} "
            f"/ {data['scorable']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
