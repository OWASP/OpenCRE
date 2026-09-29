#!/usr/bin/env python3
"""OIE experiment runner: named flag configs → scorers → comparison table.

Same canonical answer key every run (``local_gold: false`` for gate reports).
One lever per config; writes ``tmp/oie_owasp_eval/experiments/<id>.json`` and
refreshes ``comparison.md``.

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/run_experiment.py \\
    --config scripts/oie_owasp_eval/experiments/baseline.yaml

  PYTHONPATH=. python scripts/oie_owasp_eval/run_experiment.py \\
    --experiment-id cre_summary --flags CRE_LIBRARIAN_CRE_SUMMARY=1

  PYTHONPATH=. python scripts/oie_owasp_eval/run_experiment.py \\
    --config scripts/oie_owasp_eval/experiments/baseline.yaml --dry-run

  PYTHONPATH=. python scripts/oie_owasp_eval/run_experiment.py \\
    --config scripts/oie_owasp_eval/experiments/baseline.yaml \\
    --score-only --run-id orch-b2-<id>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENTS_DIR = SCRIPT_DIR / "experiments"
ART = ROOT / "tmp" / "oie_owasp_eval"
EXP_ART = ART / "experiments"
COMPARISON_MD = EXP_ART / "comparison.md"

# Experiment levers from the OIE prod-accuracy plan (defaults stay off in prod).
KNOWN_FLAGS: Tuple[str, ...] = (
    "CRE_LIBRARIAN_CRE_SUMMARY",
    "CRE_LIBRARIAN_DUAL_INDEX",
    "CRE_LIBRARIAN_USE_RRF",
    "CRE_LIBRARIAN_CONTEXT_ENRICH",
    "CRE_LIBRARIAN_MARGIN_GAMMA",
    "CRE_LIBRARIAN_HUB_LEAF_CAGE",
    "CRE_LIBRARIAN_CROSSENCODER_MODEL",
)

# Previously unwired levers; Phase 2 landed them in config_loader. Keep empty
# unless a future experiment flag is env-only before wiring.
FLAGS_NOT_YET_WIRED: Tuple[str, ...] = ()

ASVS5_FIXTURE = (
    ROOT
    / "application"
    / "tests"
    / "fixtures"
    / "owasp_mappings"
    / "owasp_asvs_5_0_provisional.json"
)
ASVS5_SCORER_CANDIDATES = (
    SCRIPT_DIR / "run_asvs5_score.py",
    SCRIPT_DIR / "score_asvs5.py",
    SCRIPT_DIR / "run_b2_asvs5.py",
)


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


def parse_flag_pairs(pairs: Sequence[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise ValueError(f"flag must be KEY=VAL, got {raw!r}")
        k, _, v = raw.partition("=")
        key = k.strip()
        if not key:
            raise ValueError(f"empty flag key in {raw!r}")
        out[key] = v.strip()
    return out


def load_config(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config {path} must be a mapping")
    return data


def resolve_experiment(
    *,
    config_path: Optional[Path],
    experiment_id: Optional[str],
    flag_pairs: Sequence[str],
) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    """Return (experiment_id, flags, raw_config_meta)."""
    meta: Dict[str, Any] = {}
    flags: Dict[str, str] = {}
    exp_id = (experiment_id or "").strip()

    if config_path is not None:
        meta = load_config(config_path)
        exp_id = str(meta.get("experiment_id") or exp_id or config_path.stem).strip()
        raw_flags = meta.get("flags") or {}
        if not isinstance(raw_flags, Mapping):
            raise ValueError(f"{config_path}: flags must be a mapping")
        flags = {str(k): "" if v is None else str(v) for k, v in raw_flags.items()}

    cli_flags = parse_flag_pairs(flag_pairs)
    flags.update(cli_flags)

    if not exp_id:
        raise ValueError("experiment_id required (--experiment-id or config experiment_id)")

    return exp_id, flags, meta


def apply_flags(flags: Mapping[str, str]) -> List[str]:
    """Set os.environ from flag vector; return warnings for unwired flags."""
    warnings: List[str] = []
    for key, val in flags.items():
        os.environ[key] = str(val)
        if key in FLAGS_NOT_YET_WIRED:
            warnings.append(
                f"{key} set in env but not yet read by librarian config_loader"
            )
    return warnings


def clear_known_experiment_flags() -> None:
    """Unset known experiment levers so baseline is not polluted by the shell."""
    for key in KNOWN_FLAGS:
        os.environ.pop(key, None)


def headline_from_b2(
    report: Mapping[str, Any],
    *,
    exclude_agentic: bool,
) -> Dict[str, Any]:
    """Build headline totals; agentic stub footnoted / excludeable."""
    by_resource = dict(report.get("by_resource") or {})
    agentic_label = "OWASP Agentic AI (stub, no hub Links)"
    agentic = by_resource.get(agentic_label)
    footnote = (
        "Agentic AI stub has no hub Links; exclude from headline denominator "
        "(footnote only)."
    )

    if exclude_agentic and agentic is not None:
        hits = scorable = 0
        families: Dict[str, Any] = {}
        for label, bucket in by_resource.items():
            if label == agentic_label:
                continue
            families[label] = bucket
            hits += int(bucket.get("hits") or 0)
            scorable += int(bucket.get("scorable") or 0)
        accuracy = round((hits / scorable) if scorable else 0.0, 4)
        return {
            "hits": hits,
            "scorable": scorable,
            "accuracy": accuracy,
            "by_resource": families,
            "excluded_resources": [agentic_label],
            "agentic_stub": {
                **dict(agentic),
                "footnote": footnote,
            },
            "footnote": footnote,
        }

    return {
        "hits": int(report.get("hits") or 0),
        "scorable": int(report.get("scorable") or 0),
        "accuracy": float(report.get("accuracy") or 0.0),
        "by_resource": by_resource,
        "excluded_resources": [],
        "agentic_stub": (
            {**dict(agentic), "footnote": footnote} if agentic is not None else None
        ),
        "footnote": footnote if agentic is not None else None,
    }


def discover_asvs5_hook() -> Dict[str, Any]:
    """ASVS5 is primarily a B2 harness arm; dedicated scorer is optional."""
    scorers = [p for p in ASVS5_SCORER_CANDIDATES if p.is_file()]
    fixture_ok = ASVS5_FIXTURE.is_file()
    sources_dir = SCRIPT_DIR / "fixtures" / "b2_sources" / "owasp_asvs_5_0_provisional"
    sources_ok = sources_dir.is_dir() and any(sources_dir.glob("*.txt"))
    base: Dict[str, Any] = {
        "fixture": (
            str(ASVS5_FIXTURE.relative_to(ROOT)) if fixture_ok else None
        ),
        "b2_harness_arm": True,
        "sources_dir": str(sources_dir.relative_to(ROOT)),
        "sources_present": sources_ok,
    }
    if scorers and fixture_ok:
        return {
            **base,
            "status": "available",
            "scorer": str(scorers[0].relative_to(ROOT)),
        }
    if fixture_ok and not sources_ok:
        return {
            **base,
            "status": "blocked",
            "reason": (
                "ASVS5 provisional fixture present and listed in B2 harness, "
                "but no harvested b2_sources/owasp_asvs_5_0_provisional/*.txt "
                "(rows stay unaligned until Test A harvest)"
            ),
        }
    reasons: List[str] = []
    if not fixture_ok:
        reasons.append(f"missing fixture {ASVS5_FIXTURE.relative_to(ROOT)}")
    if not scorers:
        reasons.append(
            "no dedicated ASVS5 scorer (B2 harness arm still applies when fixture+sources exist)"
        )
    return {**base, "status": "unavailable", "reason": "; ".join(reasons)}


def invoke_b2(
    *,
    run_id: str,
    score_only: bool,
    keep_all_knowledge: bool,
    include_agentic: bool,
    out_path: Path,
    extra_env: Mapping[str, str],
    exclude_fixtures: Optional[Sequence[str]] = None,
) -> Tuple[int, Path]:
    """Subprocess B2 with canonical gold forced (no --local-gold)."""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "run_b2_pr_mappings.py"),
        "--out",
        str(out_path),
    ]
    if score_only:
        cmd.extend(["--score-only", "--run-id", run_id])
    elif run_id:
        cmd.extend(["--run-id", run_id])
    if keep_all_knowledge:
        cmd.append("--keep-all-knowledge")
    if include_agentic:
        cmd.append("--include-agentic")
    if exclude_fixtures:
        cmd.append("--exclude-fixtures")
        cmd.extend(list(exclude_fixtures))
    # Never pass --local-gold: gate reports stay on canonical fixtures.

    env = os.environ.copy()
    env.update({k: str(v) for k, v in extra_env.items()})
    env.setdefault("PYTHONPATH", str(ROOT))
    if "PYTHONPATH" in env and str(ROOT) not in env["PYTHONPATH"].split(os.pathsep):
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env["PYTHONPATH"]

    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)
    return proc.returncode, out_path


def invoke_b1_hook(*, run_id: str, out_path: Path) -> Dict[str, Any]:
    scorer = SCRIPT_DIR / "score_b1_opencre_api.py"
    if not scorer.is_file():
        return {"status": "unavailable", "reason": "score_b1_opencre_api.py missing"}
    if not run_id:
        return {"status": "skipped", "reason": "no run_id for B1"}
    cmd = [
        sys.executable,
        str(scorer),
        "--run-id",
        run_id,
        "--out",
        str(out_path),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)
    result: Dict[str, Any] = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "report_path": str(out_path.relative_to(ROOT)) if out_path.is_file() else None,
    }
    if out_path.is_file():
        try:
            payload = json.loads(out_path.read_text())
            result["summary"] = {
                k: payload.get(k)
                for k in ("hits", "scorable", "accuracy", "by_resource")
                if k in payload
            }
        except json.JSONDecodeError:
            result["summary"] = None
    return result


def invoke_asvs5_hook(*, run_id: str, flags: Mapping[str, str]) -> Dict[str, Any]:
    info = discover_asvs5_hook()
    if info["status"] != "available":
        return info
    # Hook reserved for when ASVS5 scorer lands; do not invent a long job here.
    return {
        "status": "skipped",
        "reason": (
            "ASVS5 scorer present but experiment runner only hooks it; "
            "invoke scorer separately until matrix job wires it"
        ),
        "scorer": info.get("scorer"),
        "fixture": info.get("fixture"),
        "run_id": run_id or None,
        "flags": dict(flags),
    }


def write_experiment_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _family_bucket(headline: Mapping[str, Any], label: str) -> Dict[str, Any]:
    by = headline.get("by_resource") or {}
    bucket = by.get(label)
    return dict(bucket) if isinstance(bucket, Mapping) else {}


def rebuild_comparison_md(art_dir: Path, out_path: Path) -> None:
    rows: List[Dict[str, Any]] = []
    for path in sorted(art_dir.glob("*.json")):
        # Skip nested scorer dumps (*.b2_report.json / *.b1_report.json).
        if path.name.endswith("_report.json"):
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or not data.get("experiment_id"):
            continue
        rows.append(data)

    lines = [
        "# OIE experiment comparison",
        "",
        "Canonical gold (`local_gold: false`). Agentic stub footnoted / excluded "
        "from headline unless an experiment sets `include_agentic: true`.",
        "",
        "## Headline",
        "",
        "| experiment_id | accuracy | hits/scorable | flags | notes |",
        "|---|---:|---:|---|---|",
    ]
    family_labels: List[str] = []
    seen_families: set = set()
    for data in rows:
        exp_id = data.get("experiment_id", path_stem_fallback(data))
        headline = data.get("headline") or {}
        for label in (headline.get("by_resource") or {}):
            if label not in seen_families:
                seen_families.add(label)
                family_labels.append(label)
        acc = headline.get("accuracy")
        hits = headline.get("hits")
        scorable = headline.get("scorable")
        if acc is None and data.get("dry_run"):
            acc_s, hs = "—", "dry-run"
        elif acc is None and (data.get("b2") or {}).get("status") == "blocked":
            acc_s, hs = "—", "blocked"
        else:
            acc_s = f"{acc:.4f}" if isinstance(acc, (int, float)) else "—"
            hs = (
                f"{hits}/{scorable}"
                if hits is not None and scorable is not None
                else "—"
            )
        flags = data.get("flags") or {}
        flag_s = ", ".join(f"{k}={v}" for k, v in sorted(flags.items())) or "(none)"
        notes: List[str] = []
        if data.get("dry_run"):
            notes.append("dry-run")
        if (data.get("b2") or {}).get("status") == "blocked":
            notes.append(str((data.get("b2") or {}).get("reason") or "blocked"))
        if headline.get("footnote"):
            notes.append("agentic excluded")
        if data.get("flag_warnings"):
            notes.append("unwired flags")
        b1 = data.get("b1") or {}
        if b1.get("status") and b1.get("status") not in ("skipped", None):
            notes.append(f"b1={b1.get('status')}")
        asvs5 = data.get("asvs5") or {}
        if asvs5.get("status") == "unavailable":
            notes.append("asvs5 n/a")
        elif asvs5.get("status") == "blocked":
            notes.append(f"asvs5 blocked: {asvs5.get('reason', '')}")
        elif asvs5.get("status") and asvs5.get("status") != "skipped":
            notes.append(f"asvs5={asvs5.get('status')}")
        lines.append(
            f"| `{exp_id}` | {acc_s} | {hs} | `{flag_s}` | {'; '.join(notes) or '—'} |"
        )

    if family_labels:
        lines.extend(
            [
                "",
                "## Per-family accuracy (agentic excluded from headline)",
                "",
                "| experiment_id | "
                + " | ".join(f"`{lab}`" for lab in family_labels)
                + " |",
                "|---|" + "|".join(["---:"] * len(family_labels)) + "|",
            ]
        )
        for data in rows:
            exp_id = data.get("experiment_id", "?")
            headline = data.get("headline") or {}
            cells: List[str] = []
            for lab in family_labels:
                bucket = _family_bucket(headline, lab)
                if not bucket:
                    cells.append("—")
                    continue
                h = bucket.get("hits")
                s = bucket.get("scorable")
                a = bucket.get("accuracy")
                if isinstance(a, (int, float)) and s is not None:
                    cells.append(f"{a:.2f} ({h}/{s})")
                elif s is not None:
                    cells.append(f"{h}/{s}")
                else:
                    cells.append("—")
            lines.append(f"| `{exp_id}` | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Blockers / provenance",
            "",
            "- Score-only reuse of one `run_id` only re-scores the **same** "
            "Module C decisions; flag ablations require a fresh pipeline run "
            "(queues are cleared each B2 invoke).",
            "- ASVS5 provisional gold is in the B2 harness list when the "
            "fixture exists; without `b2_sources/owasp_asvs_5_0_provisional/` "
            "texts those rows stay unaligned (not in scorable denominator).",
            "",
            f"_Updated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}_",
            "",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))


def path_stem_fallback(_data: Mapping[str, Any]) -> str:
    return "?"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        help="YAML under scripts/oie_owasp_eval/experiments/*.yaml",
    )
    p.add_argument("--experiment-id", default="", help="Override / set experiment id")
    p.add_argument(
        "--flags",
        nargs="*",
        default=[],
        metavar="KEY=VAL",
        help="Extra CRE_LIBRARIAN_* flags (override config)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Load config, apply flag vector in-process, write stub JSON + comparison.md",
    )
    p.add_argument(
        "--score-only",
        action="store_true",
        help="Pass through to B2 (requires --run-id)",
    )
    p.add_argument("--run-id", default="", help="Pipeline run id for B2/B1")
    p.add_argument(
        "--keep-all-knowledge",
        action="store_true",
        help="Pass through to B2",
    )
    p.add_argument(
        "--include-agentic",
        action="store_true",
        help="Include agentic stub in B2 denominator (default: exclude / footnote)",
    )
    p.add_argument(
        "--run-b1",
        action="store_true",
        help="Also invoke B1 scorer when a run_id is available",
    )
    p.add_argument(
        "--run-asvs5",
        action="store_true",
        help="Attempt ASVS5 hook when scorer/fixture exist",
    )
    p.add_argument(
        "--include-asvs5",
        action="store_true",
        help=(
            "Include ASVS5 provisional in B2 harvest+score. Default excludes it "
            "(chapter-level HTML sources OOM Module C until proper md harvest)."
        ),
    )
    p.add_argument(
        "--skip-b2",
        action="store_true",
        help="Do not invoke B2 (still write experiment JSON / comparison)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    _load_dotenv()

    config_path = args.config
    if config_path is not None:
        if not config_path.is_file():
            # Allow bare names relative to experiments/
            alt = EXPERIMENTS_DIR / config_path
            if alt.is_file():
                config_path = alt
            elif (EXPERIMENTS_DIR / f"{config_path}.yaml").is_file():
                config_path = EXPERIMENTS_DIR / f"{config_path}.yaml"
            else:
                print(f"config not found: {args.config}", file=sys.stderr)
                return 2
        config_path = config_path.resolve()

    try:
        exp_id, flags, meta = resolve_experiment(
            config_path=config_path,
            experiment_id=args.experiment_id or None,
            flag_pairs=args.flags,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    include_agentic = bool(args.include_agentic) or bool(meta.get("include_agentic"))
    exclude_agentic = not include_agentic

    clear_known_experiment_flags()
    flag_warnings = apply_flags(flags)

    run_id = (args.run_id or str(meta.get("run_id") or "")).strip()
    if not run_id and not args.dry_run and not args.score_only and not args.skip_b2:
        run_id = "orch-exp-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload: Dict[str, Any] = {
        "experiment_id": exp_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flags": flags,
        "flag_warnings": flag_warnings,
        "local_gold": False,
        "exclude_agentic_from_headline": exclude_agentic,
        "config_path": (
            str(config_path.relative_to(ROOT)) if config_path is not None else None
        ),
        "description": meta.get("description"),
        "dry_run": bool(args.dry_run),
        "run_id": run_id or None,
        "b2": None,
        "headline": None,
        "b1": {"status": "skipped", "reason": "--run-b1 not set"},
        "asvs5": discover_asvs5_hook(),
        "decision_fp": None,
    }

    if "CRE_LIBRARIAN_MARGIN_GAMMA" in flags:
        payload["decision_fp"] = {
            "status": "pending",
            "note": (
                "Margin experiment should report B2 hit and decision-FP; "
                "FP metric hook not yet implemented in B2 scorer"
            ),
        }

    EXP_ART.mkdir(parents=True, exist_ok=True)
    out_json = EXP_ART / f"{exp_id}.json"
    b2_out = EXP_ART / f"{exp_id}.b2_report.json"

    if args.dry_run:
        payload["headline"] = {
            "hits": None,
            "scorable": None,
            "accuracy": None,
            "by_resource": {},
            "excluded_resources": (
                ["OWASP Agentic AI (stub, no hub Links)"] if exclude_agentic else []
            ),
            "footnote": (
                "Agentic AI stub has no hub Links; exclude from headline denominator "
                "(footnote only)."
                if exclude_agentic
                else None
            ),
        }
        payload["b2"] = {"status": "skipped", "reason": "dry-run"}
        if args.run_asvs5:
            payload["asvs5"] = invoke_asvs5_hook(run_id=run_id, flags=flags)
        write_experiment_json(out_json, payload)
        rebuild_comparison_md(EXP_ART, COMPARISON_MD)
        print(json.dumps(payload, indent=2))
        print(f"wrote {out_json}", flush=True)
        print(f"wrote {COMPARISON_MD}", flush=True)
        return 0

    if not args.skip_b2:
        exclude_fixtures: List[str] = []
        if not args.include_asvs5:
            exclude_fixtures.append("owasp_asvs_5_0_provisional")
            payload["asvs5"] = {
                **discover_asvs5_hook(),
                "status": "blocked",
                "reason": (
                    "excluded from B2 harvest for matrix stability "
                    "(chapter HTML OOMs Module C; pass --include-asvs5 to force)"
                ),
            }
        rc, report_path = invoke_b2(
            run_id=run_id,
            score_only=bool(args.score_only),
            keep_all_knowledge=bool(args.keep_all_knowledge),
            include_agentic=include_agentic,
            out_path=b2_out,
            extra_env=flags,
            exclude_fixtures=exclude_fixtures,
        )
        b2_block: Dict[str, Any] = {
            "status": "ok" if rc == 0 else "failed",
            "returncode": rc,
            "report_path": (
                str(report_path.relative_to(ROOT)) if report_path.is_file() else None
            ),
            "local_gold": False,
        }
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            b2_block["hits"] = report.get("hits")
            b2_block["scorable"] = report.get("scorable")
            b2_block["accuracy"] = report.get("accuracy")
            b2_block["by_resource"] = report.get("by_resource")
            b2_block["agentic_footnote"] = report.get("agentic_footnote")
            payload["run_id"] = report.get("run_id") or run_id
            payload["headline"] = headline_from_b2(
                report, exclude_agentic=exclude_agentic
            )
            # Surface ASVS5 provisional family from B2 when present.
            asvs_label = "OWASP ASVS 5.0 (provisional v4→v5 gold)"
            by_res = report.get("by_resource") or {}
            if asvs_label in by_res:
                payload["asvs5"] = {
                    **discover_asvs5_hook(),
                    "status": "b2_arm",
                    "family": by_res[asvs_label],
                }
        else:
            payload["headline"] = None
        payload["b2"] = b2_block
        if rc != 0 and not report_path.is_file():
            write_experiment_json(out_json, payload)
            rebuild_comparison_md(EXP_ART, COMPARISON_MD)
            print(f"B2 failed rc={rc}; wrote partial {out_json}", file=sys.stderr)
            return rc or 2
    else:
        payload["b2"] = {"status": "skipped", "reason": "--skip-b2"}

    effective_run_id = str(payload.get("run_id") or run_id or "")
    if args.run_b1:
        b1_out = EXP_ART / f"{exp_id}.b1_report.json"
        payload["b1"] = invoke_b1_hook(run_id=effective_run_id, out_path=b1_out)
    if args.run_asvs5 and (payload.get("asvs5") or {}).get("status") != "b2_arm":
        payload["asvs5"] = invoke_asvs5_hook(run_id=effective_run_id, flags=flags)

    write_experiment_json(out_json, payload)
    rebuild_comparison_md(EXP_ART, COMPARISON_MD)
    print(json.dumps({k: payload[k] for k in payload if k != "b2"}, indent=2))
    if payload.get("b2"):
        print(json.dumps({"b2": payload["b2"]}, indent=2))
    print(f"wrote {out_json}", flush=True)
    print(f"wrote {COMPARISON_MD}", flush=True)
    if payload.get("b2", {}).get("status") == "failed":
        return int(payload["b2"].get("returncode") or 2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
