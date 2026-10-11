#!/usr/bin/env python3
"""Exhaustive main ``repos.yaml`` incremental OIE reingest via RQ.

Loads only ``application/utils/harvester/repos.yaml``. Harvestable targets
(standard/project/other) skip when SHA unchanged + prior success (or queues
drained). **Default:** enqueue all due targets in one RQ batch so the worker
fleet runs many repos in parallel; after the queue drains, evaluate each
target and retry failures ≤5 times. ``--serial`` restores one-repo-at-a-time
waits. Writes status + FAILURES; optionally scores vs golden_mac_admin.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_REPOS = ROOT / "application" / "utils" / "harvester" / "repos.yaml"
DEFAULT_OUT = ROOT / "tmp" / "oie_exhaustive"
CACHE_DEFAULT = (
    os.environ.get("DEV_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql://cre:password@127.0.0.1:5432/cre"
)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _apply_promoted_flags() -> None:
    os.environ.setdefault("CRE_LIBRARIAN_CRE_SUMMARY", "1")
    os.environ.setdefault("CRE_LIBRARIAN_MARGIN_GAMMA", "0.85")
    os.environ.setdefault("CRE_LIBRARIAN_RETRIEVER_BACKEND", "pgvector")
    os.environ.setdefault("CRE_LIBRARIAN_SAFETY_GUARD", "1")
    os.environ.setdefault("CRE_LIBRARIAN_EMBED_BATCH", "8")
    os.environ.setdefault("CRE_EMBED_EXPECTED_DIM", "3072")
    os.environ.setdefault("CRE_LIBRARIAN_SHORTLIST_JUDGE", "1")
    os.environ.setdefault("CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS", "3")
    os.environ.setdefault("CRE_LIBRARIAN_LEAF_DRILLDOWN", "1")
    os.environ.setdefault("CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_SECTIONS", "20")
    os.environ.setdefault("CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_CHILDREN", "3")
    os.environ.setdefault("CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB", "0")
    os.environ.setdefault("CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST", "0")
    os.environ.setdefault("CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP", "8")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault(
        "CRE_LIBRARIAN_CRE_SUMMARY_CACHE",
        str(ROOT / "tmp" / "oie_cre_summaries"),
    )


def _probe_head_sha(owner: str, repo: str, branch: str) -> str:
    """Best-effort HEAD SHA via GitHub API (optional token)."""
    import urllib.error
    import urllib.request

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "opencre-oie-exhaustive",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            data = json.load(resp)
        return str(data.get("sha") or "").strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return ""


def _target_success(session: Any, source_repo: str, pipeline_run_id: str) -> bool:
    """True when this run left no pending HI for the source and no open KQ."""
    from application.database.db import HarvestInput
    from application.utils.oie_rq.incremental_targets import _unconsumed_kq_for_source

    pending = (
        session.query(HarvestInput)
        .filter_by(
            pipeline_run_id=pipeline_run_id,
            source_repo=source_repo,
            status="pending",
        )
        .count()
    )
    if pending:
        return False
    # Also require global drain for this source (prior runs' leftovers block skip).
    return _unconsumed_kq_for_source(session, source_repo) == 0


def _evaluate_after_run(
    session: Any, *, repo_id: str, source_repo: str, pipeline_run_id: str
) -> tuple[bool, str, str]:
    """Return (ok, error, checkpoint_sha) after A→B→C for one source."""
    from application.utils.oie_rq.incremental_targets import (
        _pending_hi_count,
        load_checkpoint_sha,
    )

    session.expire_all()
    cp = load_checkpoint_sha(session, repo_id)
    if _target_success(session, source_repo, pipeline_run_id):
        return True, "", cp
    pending = _pending_hi_count(session, source_repo)
    if pending == 0:
        # A finished with nothing pending (unchanged docs / empty harvest).
        return True, "", cp
    return False, f"pending_hi={pending} after wait", cp


def _enqueue_repos(
    *,
    repo_ids: List[str],
    pipeline_run_id: str,
    cache: str,
    repos_yaml: str,
    wait_idle: bool,
) -> None:
    from application.utils.oie_rq.fanout import (
        enqueue_oie_batch,
        wait_for_oie_queue_idle,
    )

    if not repo_ids:
        return
    enqueue_oie_batch(
        pipeline_run_id=pipeline_run_id,
        db_connection_str=cache,
        repos_yaml=repos_yaml,
        repo_ids=repo_ids,
        sync_repos=True,
        dry_run=False,
        wait=False,
    )
    if wait_idle:
        wait_for_oie_queue_idle(poll_seconds=15.0, stable_polls=3)


def _score_mac(pipeline_run_id: str, cache: str, out_dir: Path) -> Dict[str, Any]:
    """Score ASVS/AISVS/CS vs gold; hop-compare to golden_mac_admin (no queue wipe).

    B2 arms (top10/llm/k8s/api) that delete queues are a separate follow-up —
    this pass stays no-TRUNCATE / no targeted queue wipe.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "oie_owasp_eval"))
    from hop_distance import load_adjacency, score_details  # type: ignore
    from run_full_pipeline import (  # type: ignore
        GITHUB_TARGETS,
        _write_b2_shaped_report,
        score_github_decisions,
    )

    github = {k: GITHUB_TARGETS[k] for k in ("asvs", "aisvs", "cheatsheets")}
    report = score_github_decisions(pipeline_run_id, cache, github, top_k=3)
    details = list(report.get("details") or [])

    adj_path = (
        ROOT
        / "tmp"
        / "oie_owasp_eval"
        / "experiments"
        / "hop_analysis"
        / "cre_adjacency.json.gz"
    )
    adj = load_adjacency(adj_path) if adj_path.is_file() else None
    hop = score_details(details, adj) if adj and details else {}

    golden_path = (
        ROOT / "tmp" / "oie_owasp_eval" / "experiments" / "golden_mac_scorecard.json"
    )
    golden = {}
    if golden_path.is_file():
        golden = json.loads(golden_path.read_text(encoding="utf-8"))

    rates = hop.get("rates") or {}
    shaped = {
        "mode": "exhaustive_incremental_github",
        "pipeline_run_id": pipeline_run_id,
        "by_resource": report.get("by_resource"),
        "accuracy": report.get("accuracy"),
        "hop_rates": rates,
        "hop_counts": hop.get("counts"),
        "scorable": hop.get("scorable") or report.get("scorable"),
        "compare_golden_mac_admin": {
            "golden_exact": golden.get("b2_exact_accuracy"),
            "golden_d1": golden.get("b2_distance1_hit"),
            "ours_exact": rates.get("exact"),
            "ours_d1": rates.get("distance1_hit"),
            "golden_scorable": 251,
            "ours_github_scorable": hop.get("scorable") or report.get("scorable"),
            "note": "github arms only this pass; B2 arms deferred (no queue wipe)",
        },
        "golden_by_resource": golden.get("b2_by_resource"),
    }
    # Compact score for status/canvas (omit huge details).
    (out_dir / "mac_scorecard.json").write_text(
        json.dumps(shaped, indent=2) + "\n", encoding="utf-8"
    )
    _write_b2_shaped_report(
        {
            "details": details,
            "by_resource": report.get("by_resource"),
            "accuracy": report.get("accuracy"),
        },
        out_dir / "exhaustive.b2_report.json",
    )
    return shaped


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos_yaml", default=str(DEFAULT_REPOS))
    parser.add_argument("--cache_file", default=CACHE_DEFAULT)
    parser.add_argument("--run_id", default="")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--max-targets",
        type=int,
        default=0,
        help="cap targets for dry/smoke (0 = all)",
    )
    parser.add_argument("--skip-score", action="store_true")
    parser.add_argument(
        "--regenerate-yaml",
        action="store_true",
        help="run oie_generate_repos_yaml.py before ingest",
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="enqueue one repo at a time and wait for idle (slow; debug only)",
    )
    args = parser.parse_args(argv)

    _load_dotenv()
    _apply_promoted_flags()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "status.json"
    failures_path = out_dir / "FAILURES.json"

    if args.regenerate_yaml:
        token = (
            os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        ).strip()
        if not token:
            try:
                token = subprocess.check_output(
                    ["gh", "auth", "token"], text=True
                ).strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                token = ""
        env = os.environ.copy()
        if token:
            env["GITHUB_TOKEN"] = token
        cmd = [sys.executable, str(ROOT / "scripts" / "oie_generate_repos_yaml.py")]
        print("regenerating repos.yaml…", flush=True)
        subprocess.check_call(cmd, cwd=str(ROOT), env=env)

    from application.cmd.cre_main import db_connect
    from application.utils.harvester.config_loader import load_repo_config
    from application.utils.oie_rq.fanout import oie_queue_inflight_counts
    from application.utils.oie_rq.incremental_targets import (
        FailureReport,
        RunStatus,
        TargetOutcome,
        estimate_eta_utc,
        harvestable_targets,
        record_attempt,
        should_skip_target,
        source_repo_for,
        utc_now_iso,
        write_failure_report,
        write_status,
    )

    run_id = args.run_id.strip() or (
        "exhaustive-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    (out_dir / "run_id.txt").write_text(run_id + "\n", encoding="utf-8")

    repos_file = load_repo_config(Path(args.repos_yaml))
    targets = harvestable_targets(repos_file.repositories)
    if args.max_targets and args.max_targets > 0:
        targets = targets[: args.max_targets]

    database = db_connect(path=args.cache_file)
    session = database.session
    report = FailureReport(run_id=run_id)
    started = time.monotonic()

    def snap(
        *,
        phase: str,
        done: int,
        in_progress: str = "",
        attempts: int = 0,
        note: str = "",
        score: Optional[Dict[str, Any]] = None,
    ) -> None:
        counts = oie_queue_inflight_counts()
        eta, eta_note = estimate_eta_utc(
            started_monotonic=started,
            done=done,
            total=len(targets),
            now_monotonic=time.monotonic(),
        )
        status = RunStatus(
            run_id=run_id,
            phase=phase,
            as_of_utc=utc_now_iso(),
            total_targets=len(targets),
            done=done,
            skipped=len(report.skipped),
            succeeded=len(report.succeeded),
            failed=sum(1 for f in report.failures if f.status == "failed"),
            exhausted=sum(1 for f in report.failures if f.status == "exhausted"),
            in_progress=in_progress,
            attempts_on_current=attempts,
            queue_queued=counts.get("queued", 0),
            queue_started=counts.get("started", 0),
            eta_utc=eta,
            eta_note=eta_note,
            failures=[o.__dict__ for o in report.failures],
            score=score,
            note=note,
        )
        # dataclass fields — use asdict via to_dict
        write_status(status_path, status)
        write_failure_report(failures_path, report)

    mode = "serial" if args.serial else "batch"
    snap(
        phase="starting",
        done=0,
        note=f"targets={len(targets)} mode={mode}",
    )
    print(
        f"run_id={run_id} harvestable_targets={len(targets)} mode={mode}",
        flush=True,
    )

    # Classify skip vs due once up front.
    due: List[tuple[Any, TargetOutcome]] = []
    for index, cfg in enumerate(targets):
        source = source_repo_for(cfg)
        head = _probe_head_sha(cfg.owner, cfg.repo, cfg.branch)
        outcome = TargetOutcome(
            repo_id=cfg.id,
            source_repo=source,
            status="pending",
            head_sha=head,
            checkpoint_sha="",
        )
        skip, reason = should_skip_target(
            session,
            repo_id=cfg.id,
            source_repo=source,
            head_sha=head,
        )
        if skip:
            outcome.status = "skipped"
            outcome.skip_reason = reason
            report.skipped.append(outcome)
            print(f"[{index+1}/{len(targets)}] SKIP {cfg.id} ({reason})", flush=True)
            continue
        due.append((cfg, outcome))
        print(
            f"[{index+1}/{len(targets)}] DUE {cfg.id} head={(head[:8] if head else '')}",
            flush=True,
        )

    snap(
        phase="ingest",
        done=len(report.skipped),
        note=f"skipped={len(report.skipped)} due={len(due)} mode={mode}",
        in_progress=f"{len(due)} due",
    )

    if args.serial:
        for index, (cfg, outcome) in enumerate(due):
            last_err = ""
            while outcome.attempts < 5 and outcome.status not in ("ok", "exhausted"):
                snap(
                    phase="ingest",
                    done=len(report.skipped) + index,
                    in_progress=cfg.id,
                    attempts=outcome.attempts + 1,
                )
                try:
                    _enqueue_repos(
                        repo_ids=[cfg.id],
                        pipeline_run_id=run_id,
                        cache=args.cache_file,
                        repos_yaml=args.repos_yaml,
                        wait_idle=True,
                    )
                    ok, last_err, cp = _evaluate_after_run(
                        session,
                        repo_id=cfg.id,
                        source_repo=outcome.source_repo,
                        pipeline_run_id=run_id,
                    )
                    outcome.checkpoint_sha = cp
                    outcome = record_attempt(outcome, ok=ok, error=last_err)
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    outcome = record_attempt(outcome, ok=False, error=last_err)
                    print(
                        f"  attempt {outcome.attempts} failed: {last_err}",
                        flush=True,
                    )
            if outcome.status == "ok":
                report.succeeded.append(outcome)
            else:
                report.failures.append(outcome)
                print(f"  EXHAUSTED {cfg.id}: {outcome.error}", flush=True)
            snap(phase="ingest", done=len(report.skipped) + index + 1)
    else:
        # Default: fan out all due A jobs, wait once, retry only failures.
        pending_round = list(due)
        round_no = 0
        while pending_round:
            round_no += 1
            repo_ids = [cfg.id for cfg, _ in pending_round]
            print(
                f"=== batch round {round_no}: enqueue {len(repo_ids)} repos ===",
                flush=True,
            )
            snap(
                phase="ingest",
                done=len(report.skipped) + len(report.succeeded),
                in_progress=f"batch×{len(repo_ids)}",
                attempts=round_no,
                note=f"batch round {round_no}",
            )
            batch_error = ""
            try:
                _enqueue_repos(
                    repo_ids=repo_ids,
                    pipeline_run_id=run_id,
                    cache=args.cache_file,
                    repos_yaml=args.repos_yaml,
                    wait_idle=True,
                )
            except Exception as exc:  # noqa: BLE001
                batch_error = str(exc)
                print(f"batch enqueue/wait failed: {batch_error}", flush=True)

            next_round: List[tuple[Any, TargetOutcome]] = []
            for cfg, outcome in pending_round:
                try:
                    if batch_error:
                        ok, err, cp = False, batch_error, outcome.checkpoint_sha
                    else:
                        ok, err, cp = _evaluate_after_run(
                            session,
                            repo_id=cfg.id,
                            source_repo=outcome.source_repo,
                            pipeline_run_id=run_id,
                        )
                    outcome.checkpoint_sha = cp
                    outcome = record_attempt(outcome, ok=ok, error=err)
                except Exception as exc:  # noqa: BLE001
                    outcome = record_attempt(outcome, ok=False, error=str(exc))

                if outcome.status == "ok":
                    report.succeeded.append(outcome)
                    print(f"  OK {cfg.id}", flush=True)
                elif outcome.status == "exhausted":
                    report.failures.append(outcome)
                    print(f"  EXHAUSTED {cfg.id}: {outcome.error}", flush=True)
                else:
                    next_round.append((cfg, outcome))
                    print(
                        f"  RETRY {cfg.id} attempt={outcome.attempts}: {outcome.error}",
                        flush=True,
                    )

            snap(
                phase="ingest",
                done=len(report.skipped) + len(report.succeeded) + len(report.failures),
                in_progress=f"retry×{len(next_round)}" if next_round else "",
                attempts=round_no,
                note=f"after round {round_no}: ok={len(report.succeeded)} fail={len(report.failures)} retry={len(next_round)}",
            )
            pending_round = next_round

    score_payload = None
    if not args.skip_score:
        snap(phase="scoring", done=len(targets), note="mac scorecard")
        try:
            score_payload = _score_mac(run_id, args.cache_file, out_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"score failed: {exc}", flush=True)
            score_payload = {"error": str(exc)}

    snap(
        phase="done",
        done=len(targets),
        note="complete",
        score=score_payload,
    )
    write_failure_report(failures_path, report)
    print(json.dumps(report.to_dict(), indent=2), flush=True)
    return 0 if report.to_dict()["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
