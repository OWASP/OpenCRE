#!/usr/bin/env python3
"""Six-lever product-d1 ablations vs MIN_SECTIONS=20 baseline.

Arms (each alone vs baseline, then one combo of positive levers)::

  E1  CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB=1
  E2  CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST=1
  E3  B2 summary-cache fork (tmp/oie_cre_summaries_b2)
  E4  CRE_LIBRARIAN_SHORTLIST_JUDGE=1
  E5  CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP=8
  E6  Offline score top_k=3 (rerank[:3] ∪ vector[:3]) — no Module C re-run

Writes ``tmp/oie_owasp_eval/experiments/d1_levers/summary.json`` and prints
the winning combo env. Pick winner by highest product d1, then exact, with
hard floor exact ≥ 17%.

Usage::

  PYTHONPATH=. python scripts/oie_owasp_eval/run_d1_lever_experiments.py \\
    --cache_file postgresql://cre:password@127.0.0.1:5432/cre_prodclone

  # Offline E6 only (needs decision envelopes for --baseline-run-id):
  PYTHONPATH=. python scripts/oie_owasp_eval/run_d1_lever_experiments.py \\
    --only E6 --baseline-run-id fullpipe-minsec-20260930T121607Z
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
ART = ROOT / "tmp" / "oie_owasp_eval"
OUT_DIR = ART / "experiments" / "d1_levers"
GITHUB_CACHE = ROOT / "tmp" / "oie_cre_summaries"
B2_CACHE = ROOT / "tmp" / "oie_cre_summaries_b2"
MINSEC_REPORT = ART / "full_pipeline_min_sections" / "github_arms.b2_report.json"
MINSEC_METRICS = ART / "experiments" / "product_metric_min_sections.json"

EXACT_FLOOR = 0.17
BASELINE_D1 = 0.4603960396039604
BASELINE_EXACT = 0.18316831683168316

BASELINE_ENV: Dict[str, str] = {
    "CRE_LIBRARIAN_CRE_SUMMARY": "1",
    "CRE_LIBRARIAN_MARGIN_GAMMA": "0.85",
    "CRE_LIBRARIAN_RETRIEVER_BACKEND": "pgvector",
    "CRE_LIBRARIAN_SHORTLIST_JUDGE": "0",
    "CRE_LIBRARIAN_DEVICE": "cpu",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN": "1",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_SECTIONS": "20",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_CHILDREN": "3",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB": "0",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST": "0",
    "CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP": "4",
    "NO_LOAD_GRAPH_DB": "1",
    "CRE_LIBRARIAN_CRE_SUMMARY_CACHE": str(GITHUB_CACHE),
}

# Lever id → env overrides (relative to baseline). E3/E6 handled specially.
LEVER_ENV: Dict[str, Dict[str, str]] = {
    "E1": {"CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB": "1"},
    "E2": {"CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST": "1"},
    "E4": {"CRE_LIBRARIAN_SHORTLIST_JUDGE": "1"},
    "E5": {"CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP": "8"},
}


def _load_dotenv() -> None:
    for env_path in (ROOT / ".env", ROOT / "tmp" / "oie.env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if env_path.name == "oie.env" and (
                k.startswith("CRE_LIBRARIAN_") or k.startswith("DEV_DATABASE")
            ):
                os.environ[k.strip()] = v.strip()
            else:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _py() -> str:
    venv = ROOT / "venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _merge_env(overrides: Mapping[str, str]) -> Dict[str, str]:
    env = os.environ.copy()
    for k, v in BASELINE_ENV.items():
        env[k] = v
    for k, v in overrides.items():
        env[k] = v
    env["PYTHONPATH"] = str(ROOT)
    env.setdefault("FLASK_CONFIG", "development")
    return env


def _hop_metrics(report_path: Path) -> Dict[str, float]:
    """Exact + product d1 from a b2-shaped report via hop_distance."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(SCRIPT_DIR))
    from hop_distance import load_adjacency, score_details  # noqa: E402
    from score_b2_hop_distance import ensure_adjacency  # noqa: E402

    adj_path = ART / "experiments" / "hop_analysis" / "cre_adjacency.json.gz"
    if adj_path.is_file():
        adj = load_adjacency(adj_path)
    else:
        adj = ensure_adjacency(force=False, db_url=os.environ.get("DEV_DATABASE_URL"))
    report = json.loads(report_path.read_text())
    scored = score_details(report.get("details") or [], adj)
    rates = scored.get("rates") or {}
    return {
        "exact": float(rates.get("exact") or 0.0),
        "d1": float(rates.get("distance1_hit") or 0.0),
        "scorable": float(scored.get("scorable") or 0),
        "b2_accuracy": float(report.get("accuracy") or 0.0),
        "b2_hits": float(report.get("hits") or 0),
    }


def _baseline_from_disk() -> Dict[str, Any]:
    if MINSEC_METRICS.is_file():
        data = json.loads(MINSEC_METRICS.read_text())
        gh = (data.get("arms") or {}).get("github") or {}
        return {
            "id": "baseline",
            "exact": float(gh.get("exact") or BASELINE_EXACT),
            "d1": float(gh.get("d1") or BASELINE_D1),
            "scorable": float(gh.get("scorable") or 202),
            "source": str(MINSEC_METRICS.relative_to(ROOT)),
        }
    return {
        "id": "baseline",
        "exact": BASELINE_EXACT,
        "d1": BASELINE_D1,
        "scorable": 202.0,
        "source": "hardcoded",
    }


def _run_github_arm(
    *,
    arm_id: str,
    cache: str,
    overrides: Mapping[str, str],
    out_dir: Path,
    top_k: int = 2,
) -> Dict[str, Any]:
    """Run Module A→B→C for ASVS+AISVS and score (+ hop d1)."""
    run_id = f"d1-{arm_id.lower()}-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    arm_out = out_dir / arm_id.lower()
    arm_out.mkdir(parents=True, exist_ok=True)
    env = _merge_env(overrides)
    env["DEV_DATABASE_URL"] = cache
    env["DATABASE_URL"] = cache
    env["CRE_LIBRARIAN_CRE_SUMMARY_CACHE"] = str(GITHUB_CACHE)
    GITHUB_CACHE.mkdir(parents=True, exist_ok=True)

    cmd = [
        _py(),
        str(SCRIPT_DIR / "run_full_pipeline.py"),
        "--repos",
        "asvs,aisvs",
        "--cache_file",
        cache,
        "--run-id",
        run_id,
        "--keep-all-knowledge",
        "--out-dir",
        str(arm_out),
    ]
    print(f"=== {arm_id} GitHub C  run_id={run_id} ===", flush=True)
    print(" ".join(cmd), flush=True)
    ret = subprocess.call(cmd, cwd=str(ROOT), env=env, start_new_session=True)
    report_path = arm_out / "github_arms.b2_report.json"
    if not report_path.is_file():
        return {
            "id": arm_id,
            "run_id": run_id,
            "error": f"no github report (exit={ret})",
            "exact": None,
            "d1": None,
        }

    # Re-score when ≠ pipeline default (d1-winner gate is top_k=3).
    if top_k != 3:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(SCRIPT_DIR))
        import run_full_pipeline as rfp  # noqa: E402

        github = {k: rfp.GITHUB_TARGETS[k] for k in ("asvs", "aisvs")}
        report = rfp.score_github_decisions(run_id, cache, github, top_k=top_k)
        alt = arm_out / f"github_arms.topk{top_k}.b2_report.json"
        rfp._write_b2_shaped_report(report, alt)
        report_path = alt

    metrics = _hop_metrics(report_path)
    return {
        "id": arm_id,
        "run_id": run_id,
        "exit_code": ret,
        "report": str(report_path.relative_to(ROOT)),
        "top_k": top_k,
        "env_overrides": dict(overrides),
        **metrics,
    }


def _run_e6_offline(
    *,
    cache: str,
    baseline_run_id: str,
    out_dir: Path,
) -> Dict[str, Any]:
    """Rescore existing decisions with top_k=3 (no Module C)."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(SCRIPT_DIR))
    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import DecisionQueueItem
    import run_full_pipeline as rfp  # noqa: E402

    db_connect(cache)
    n = (
        sqla.session.query(DecisionQueueItem)
        .filter_by(pipeline_run_id=baseline_run_id)
        .count()
    )
    if n <= 0:
        return {
            "id": "E6",
            "error": f"no decisions for run_id={baseline_run_id!r}; need refresh C",
            "exact": None,
            "d1": None,
            "needs_refresh": True,
        }

    github = {k: rfp.GITHUB_TARGETS[k] for k in ("asvs", "aisvs")}
    report = rfp.score_github_decisions(baseline_run_id, cache, github, top_k=3)
    arm_out = out_dir / "e6"
    arm_out.mkdir(parents=True, exist_ok=True)
    report_path = arm_out / "github_arms.topk3.b2_report.json"
    rfp._write_b2_shaped_report(report, report_path)
    metrics = _hop_metrics(report_path)
    return {
        "id": "E6",
        "run_id": baseline_run_id,
        "report": str(report_path.relative_to(ROOT)),
        "top_k": 3,
        "offline": True,
        **metrics,
    }


def _run_e3_b2_fork(
    *,
    cache: str,
    out_dir: Path,
    github_run_id: str,
) -> Dict[str, Any]:
    """After a GitHub pass, fork summary cache and score Top10+API B2."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(SCRIPT_DIR))
    import run_full_pipeline as rfp  # noqa: E402

    arm_out = out_dir / "e3"
    arm_out.mkdir(parents=True, exist_ok=True)
    # Fresh fork from GitHub cache after GitHub pass warmed it.
    if B2_CACHE.exists():
        shutil.rmtree(B2_CACHE)
    rfp.ensure_b2_summary_cache(
        github_cache=GITHUB_CACHE, b2_cache=B2_CACHE, force=True
    )

    results: Dict[str, Any] = {
        "id": "E3",
        "b2_arms": {},
        "github_run_id": github_run_id,
    }
    env_before = os.environ.get("CRE_LIBRARIAN_CRE_SUMMARY_CACHE")
    try:
        os.environ["CRE_LIBRARIAN_CRE_SUMMARY_CACHE"] = str(B2_CACHE)
        os.environ["DEV_DATABASE_URL"] = cache
        os.environ["DATABASE_URL"] = cache
        for arm, stems, out_name in (
            ("top10", ["owasp_top10_2025"], "full_pipeline_top10.b2_report.json"),
            ("api", ["owasp_api_top10_2023"], "full_pipeline_api.b2_report.json"),
        ):
            try:
                report = rfp._run_b2_arm(
                    run_id=github_run_id,
                    cache=cache,
                    keep_all=True,
                    fixtures=stems,
                    arm_name=f"e3-{arm}",
                    out_name=out_name,
                )
            except Exception as exc:  # noqa: BLE001
                results["b2_arms"][arm] = {"error": str(exc)}
                continue
            path = arm_out / out_name
            path.write_text(json.dumps(report, indent=2) + "\n")
            try:
                metrics = _hop_metrics(path)
            except Exception as exc:  # noqa: BLE001
                metrics = {"error": str(exc), "b2_accuracy": report.get("accuracy")}
            results["b2_arms"][arm] = {
                "accuracy": report.get("accuracy"),
                "hits": report.get("hits"),
                "scorable": report.get("scorable"),
                **{k: metrics.get(k) for k in ("exact", "d1") if k in metrics},
            }
    finally:
        rfp.restore_github_summary_cache(github_cache=GITHUB_CACHE)
        if env_before is not None:
            os.environ["CRE_LIBRARIAN_CRE_SUMMARY_CACHE"] = env_before

    # E3 is a B2 isolation lever; GitHub exact/d1 unchanged vs its parent run.
    results["exact"] = None
    results["d1"] = None
    results["note"] = "B2 cache fork; GitHub metrics unchanged vs parent arm"
    return results


def _positive(arm: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    exact = arm.get("exact")
    d1 = arm.get("d1")
    if exact is None or d1 is None:
        return False
    if float(exact) < EXACT_FLOOR:
        return False
    return float(d1) > float(baseline.get("d1") or 0.0)


def _pick_winner(
    arms: Sequence[Mapping[str, Any]], baseline: Mapping[str, Any]
) -> Dict[str, Any]:
    candidates: List[Mapping[str, Any]] = []
    for arm in arms:
        if arm.get("id") in ("baseline", "E3"):
            continue
        exact = arm.get("exact")
        d1 = arm.get("d1")
        if exact is None or d1 is None:
            continue
        if float(exact) < EXACT_FLOOR:
            continue
        candidates.append(arm)
    # Always consider baseline itself.
    candidates.append(baseline)
    ranked = sorted(
        candidates,
        key=lambda a: (
            float(a.get("d1") or 0.0),
            float(a.get("exact") or 0.0),
        ),
        reverse=True,
    )
    return dict(ranked[0])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache_file",
        default=os.environ.get("DEV_DATABASE_URL")
        or "postgresql://cre:password@127.0.0.1:5432/cre_prodclone",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma list of arms to run (E1,E2,E3,E4,E5,E6,combo). Empty=all.",
    )
    parser.add_argument(
        "--baseline-run-id",
        default="",
        help="Decision-queue run_id for offline E6 (default: from minsec summary).",
    )
    parser.add_argument(
        "--skip-combo",
        action="store_true",
        help="Do not run the combined positive-lever GitHub pass.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _load_dotenv()
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    sys.path.insert(0, str(ROOT))

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = args.cache_file
    os.environ["DEV_DATABASE_URL"] = cache
    os.environ["DATABASE_URL"] = cache

    only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
    want = lambda x: (not only) or (x.upper() in only)  # noqa: E731

    baseline = _baseline_from_disk()
    arms: List[Dict[str, Any]] = [baseline]
    github_parent_run_id = ""

    # --- E6 offline first (instant when decisions present) ---
    if want("E6"):
        baseline_run_id = args.baseline_run_id.strip()
        if not baseline_run_id and MINSEC_REPORT.is_file():
            baseline_run_id = str(
                json.loads(MINSEC_REPORT.read_text()).get("run_id") or ""
            )
        if not baseline_run_id:
            baseline_run_id = "fullpipe-minsec-20260930T121607Z"
        e6 = _run_e6_offline(
            cache=cache, baseline_run_id=baseline_run_id, out_dir=out_dir
        )
        if e6.get("needs_refresh"):
            # One baseline GitHub refresh → score k=2 confirm + k=3 as E6.
            print("E6: refreshing baseline GitHub C for envelopes…", flush=True)
            refresh = _run_github_arm(
                arm_id="baseline_refresh",
                cache=cache,
                overrides={},
                out_dir=out_dir,
                top_k=2,
            )
            arms.append(refresh)
            github_parent_run_id = str(refresh.get("run_id") or "")
            e6 = _run_e6_offline(
                cache=cache,
                baseline_run_id=github_parent_run_id,
                out_dir=out_dir,
            )
        arms.append(e6)
        print(
            f"E6 exact={e6.get('exact')} d1={e6.get('d1')} err={e6.get('error')}",
            flush=True,
        )

    # --- Sequential GitHub levers ---
    for lid in ("E1", "E2", "E4", "E5"):
        if not want(lid):
            continue
        result = _run_github_arm(
            arm_id=lid,
            cache=cache,
            overrides=LEVER_ENV[lid],
            out_dir=out_dir,
        )
        arms.append(result)
        github_parent_run_id = str(result.get("run_id") or github_parent_run_id)
        print(
            f"{lid} exact={result.get('exact')} d1={result.get('d1')} "
            f"err={result.get('error')}",
            flush=True,
        )

    # --- E3 B2 cache fork (needs a GitHub parent run) ---
    if want("E3"):
        parent = github_parent_run_id
        if not parent:
            # Run a cheap parent if nothing else produced one.
            parent_arm = _run_github_arm(
                arm_id="e3_parent",
                cache=cache,
                overrides={},
                out_dir=out_dir,
            )
            arms.append(parent_arm)
            parent = str(parent_arm.get("run_id") or "")
        e3 = _run_e3_b2_fork(cache=cache, out_dir=out_dir, github_run_id=parent)
        arms.append(e3)
        print(f"E3 b2_arms={json.dumps(e3.get('b2_arms'))}", flush=True)

    # --- Combo of positive GitHub levers ---
    positive_ids = [
        a["id"] for a in arms if a.get("id") in LEVER_ENV and _positive(a, baseline)
    ]
    # E6 positive? include score top_k=3 in combo via env note only (scorer flag).
    e6_arm = next((a for a in arms if a.get("id") == "E6"), None)
    combo_top_k = 3 if e6_arm and _positive(e6_arm, baseline) else 2

    combo_env: Dict[str, str] = {}
    for pid in positive_ids:
        combo_env.update(LEVER_ENV[pid])

    if want("COMBO") and not args.skip_combo and (combo_env or combo_top_k != 2):
        combo = _run_github_arm(
            arm_id="combo",
            cache=cache,
            overrides=combo_env,
            out_dir=out_dir,
            top_k=combo_top_k,
        )
        combo["combo_env"] = combo_env
        combo["positive_levers"] = positive_ids
        arms.append(combo)
        print(
            f"COMBO exact={combo.get('exact')} d1={combo.get('d1')} "
            f"env={combo_env} top_k={combo_top_k}",
            flush=True,
        )
    else:
        combo = {
            "id": "combo",
            "skipped": True,
            "combo_env": combo_env,
            "positive_levers": positive_ids,
            "top_k": combo_top_k,
        }
        arms.append(combo)

    winner = _pick_winner(
        [a for a in arms if a.get("id") not in ("E3",) or a.get("exact") is not None],
        baseline,
    )
    # Prefer combo when it beats baseline under the floor.
    combo_arm = next((a for a in arms if a.get("id") == "combo"), None)
    if (
        combo_arm
        and combo_arm.get("exact") is not None
        and float(combo_arm["exact"]) >= EXACT_FLOOR
        and float(combo_arm.get("d1") or 0) >= float(winner.get("d1") or 0)
    ):
        winner = dict(combo_arm)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "exact_floor": EXACT_FLOOR,
        "baseline": baseline,
        "arms": arms,
        "positive_levers": positive_ids,
        "combo_env": combo_env,
        "combo_top_k": combo_top_k,
        "winner": {
            "id": winner.get("id"),
            "exact": winner.get("exact"),
            "d1": winner.get("d1"),
            "env": winner.get("env_overrides")
            or winner.get("combo_env")
            or (combo_env if winner.get("id") == "combo" else {}),
            "top_k": winner.get("top_k")
            or (combo_top_k if winner.get("id") == "combo" else 2),
        },
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {summary_path}", flush=True)
    wenv = summary["winner"].get("env") or {}
    print(
        "WINNER_ENV:", " ".join(f"{k}={v}" for k, v in sorted(wenv.items())), flush=True
    )
    print(f"WINNER_TOP_K={summary['winner'].get('top_k')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
