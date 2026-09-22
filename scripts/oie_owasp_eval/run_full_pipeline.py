#!/usr/bin/env python3
"""Full OIE pipeline from GitHub repo tarballs → B → C → gold score.

Repos (default)::

    OWASP/ASVS          (5.0/en)
    OWASP/AISVS         (1.0/en)
    OWASP/CheatSheetSeries
    AIX                 (not GitHub — scores LLM Top10 / hub CRE gold via B2)

Also supported as B2/source arms (cached ``b2_sources``)::

    nist                NIST SP 800-53 Rev. 5 (hub Links + OSCAL prose)
    top10               OWASP Top 10 2025
    api                 OWASP API Top 10 2023

Module A uses GitHub tarballs (no ``.git``) for ASVS/AISVS/CheatSheets.
Modules B and C run through ``run_oie_pipeline`` with the promoted librarian
stack (``CRE_SUMMARY=1``, ``MARGIN_GAMMA=0.85``) unless overridden.

Examples::

    PYTHONPATH=. python scripts/oie_owasp_eval/run_full_pipeline.py \\
        --repos asvs,aisvs,cheatsheets,aix \\
        --keep-all-knowledge --neighborhood

    PYTHONPATH=. python scripts/oie_owasp_eval/run_full_pipeline.py \\
        --repos nist,top10,api --keep-all-knowledge --neighborhood
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval" / "full_pipeline"
EXP = ROOT / "tmp" / "oie_owasp_eval" / "experiments"
TARBALL_DIR = ART / "tarballs"
FIXTURES = ROOT / "application" / "tests" / "fixtures" / "owasp_mappings"

# Logical name → (github repo, branch, include globs, gold fixture stem or None)
GITHUB_TARGETS: Dict[str, Tuple[str, str, List[str], Optional[str]]] = {
    "asvs": (
        "ASVS",
        "master",
        ["5.0/en/**/*.md"],
        "owasp_asvs_5_0_provisional",
    ),
    "aisvs": (
        "AISVS",
        "main",
        ["1.0/en/**/*.md"],
        "owasp_aisvs_1_0",
    ),
    "cheatsheets": (
        "CheatSheetSeries",
        "master",
        ["cheatsheets/**/*.md"],
        "owasp_cheatsheets_supplement",
    ),
}

# AIX has no GitHub Module A source in this repo; B2 LLM gold is the CRE proxy.
AIX_GOLD = "owasp_llm_top10_2025"

# Logical name → B2 fixture stem(s) run via run_b2_pr_mappings --only-fixtures
B2_ARMS: Dict[str, List[str]] = {
    "aix": ["owasp_llm_top10_2025"],
    "nist": ["nist_800_53_v5"],
    "top10": ["owasp_top10_2025"],
    "api": ["owasp_api_top10_2023"],
}

EXCLUDE = [
    "**/archive/**",
    "**/.github/**",
    "**/node_modules/**",
    "**/LICENSE*",
    "**/CHANGELOG*",
    "**/CONTRIBUTING*",
]

ASVS_SID_RE = re.compile(r"\b(V\d+\.\d+(?:\.\d+)?)\b", re.IGNORECASE)
# ASVS 5.0 chapter tables often omit the leading "V" (e.g. **1.1.2**).
ASVS_BARE_REQ_RE = re.compile(r"(?<![\w.])(\d+\.\d+\.\d+)(?![\d.])")
AISVS_SID_RE = re.compile(r"\b(AISVS\d+)\b", re.IGNORECASE)


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


def _match(path: str, patterns: Sequence[str]) -> bool:
    posix = PurePosixPath(path)
    expanded: List[str] = []
    for pat in patterns:
        expanded.append(pat)
        if "/**/" in pat:
            expanded.append(pat.replace("/**/", "/"))
        if pat.startswith("**/"):
            expanded.append(pat[3:])
    for pat in expanded:
        try:
            if posix.match(pat):
                return True
        except ValueError:
            pass
        import fnmatch

        if fnmatch.fnmatch(path, pat):
            return True
    return False


def _download_tarball(repo: str, branch: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        try:
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return branch
        except Exception:
            dest.unlink(missing_ok=True)
    for try_branch in (branch, "main" if branch == "master" else "master"):
        url = (
            f"https://codeload.github.com/OWASP/{repo}/tar.gz/refs/heads/{try_branch}"
        )
        print(f"GET {url}", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return try_branch
        except Exception as exc:  # noqa: BLE001
            print(f"  fail {try_branch}: {exc}", flush=True)
            dest.unlink(missing_ok=True)
    raise RuntimeError(f"could not download tarball for {repo}")


def _iter_md(tgz: Path, includes: Sequence[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    with tarfile.open(tgz, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            rel = str(Path(*parts[1:]))
            if not rel.lower().endswith(".md"):
                continue
            if _match(rel, EXCLUDE):
                continue
            if not _match(rel, includes):
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")
            if len(text.strip()) < 40:
                continue
            out.append((rel, text))
    return out


def _apply_promoted_flags() -> None:
    os.environ.setdefault("CRE_LIBRARIAN_CRE_SUMMARY", "1")
    os.environ.setdefault("CRE_LIBRARIAN_MARGIN_GAMMA", "0.85")
    os.environ.setdefault("CRE_LIBRARIAN_RETRIEVER_BACKEND", "pgvector")
    os.environ.setdefault("CRE_LIBRARIAN_SHORTLIST_JUDGE", "0")
    os.environ.setdefault("CRE_LIBRARIAN_DEVICE", "cpu")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")


def _make_tarball_harvester(
    targets: Dict[str, Tuple[str, str, List[str], Optional[str]]],
) -> Any:
    """Return a run_harvester-compatible callable that pulls GitHub tarballs."""

    def run_harvester(
        session: Any,
        rid: str,
        *,
        dry_run: bool = False,
        sync_repos: bool = True,
    ) -> Any:
        from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
        from application.utils.harvester.harvest_writer import write_harvest_input
        from application.utils.harvester.heading_extractor import HeadingExtractor
        from application.utils.harvester.models import Document, Locator, SourceInfo
        from application.utils.harvester.pipeline import RunSummary
        from application.utils.harvester.schemas import ChunkingConfig

        summary = RunSummary(run_id=rid, dry_run=dry_run, repositories=0)
        if dry_run:
            return summary

        chunking = ChunkingConfig(
            strategy="markdown_heading",
            max_tokens=1200,
            overlap_tokens=100,
            merge_profile="requirements",
            requirement_extract="auto",
        )
        pipeline = DocumentChunkPipeline(chunking=chunking)
        headings = HeadingExtractor()
        committed_at = datetime.now(timezone.utc)
        sha = "fullpipe0000000000000000000000000000001"
        TARBALL_DIR.mkdir(parents=True, exist_ok=True)

        for logical, (repo, branch, includes, _gold) in targets.items():
            summary.repositories += 1
            try:
                tgz = TARBALL_DIR / f"{repo}.tgz"
                _download_tarball(repo, branch, tgz)
                files = _iter_md(tgz, includes)
                records = []
                for rel, text in files:
                    artifact_id = f"art:OWASP/{repo}:{rel}"
                    doc = Document(
                        schema_version="0.2.0",
                        artifact_id=artifact_id,
                        pipeline_run_id=rid,
                        text=text,
                        heading_structure=headings.extract(text),
                        source=SourceInfo(
                            type="github",
                            repository=f"OWASP/{repo}",
                            commit_sha=sha,
                            committed_at=committed_at,
                        ),
                        locator=Locator(kind="repo_path", id=rel, path=rel),
                    )
                    records.extend(pipeline.chunk(doc))
                written = write_harvest_input(session, rid, records)
                summary.chunks_written += written
                print(
                    f"  [{logical}] OWASP/{repo}: files={len(files)} chunks={written}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                summary.errors += 1
                print(f"  [{logical}] ERROR {exc}", flush=True)

        if summary.errors and summary.chunks_written == 0:
            summary.status = "degraded"
        elif summary.errors:
            summary.status = "degraded"
        return summary

    return run_harvester


def _keep_all_noise_filter(session: Any, pipeline_run_id: str, **_kwargs: Any) -> Any:
    """Eval-only: promote every harvest chunk to KNOWLEDGE (score Module C)."""
    from application.database.db import HarvestInput
    from application.utils.noise_filter.hashing import compute_content_hash
    from application.utils.noise_filter.pipeline import RunSummary as BSummary
    from application.utils.noise_filter.queue_writer import write_verdicts
    from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult

    summary = BSummary(run_id=pipeline_run_id)
    rows = (
        session.query(HarvestInput)
        .filter_by(pipeline_run_id=pipeline_run_id, status="pending")
        .all()
    )
    summary.read = len(rows)
    triples = []
    for row in rows:
        try:
            record = ChangeRecord.model_validate(row.payload)
        except Exception:  # noqa: BLE001
            summary.parse_errors += 1
            continue
        verdict = ClassifyResult(
            label="KNOWLEDGE",
            confidence=1.0,
            reasoning="full-pipeline-keep-all-knowledge",
        )
        triples.append((record, verdict, compute_content_hash(record.text)))
        row.status = "processed"
        summary.kept_knowledge += 1
    stats = write_verdicts(session, triples)
    summary.inserted = stats.inserted
    summary.deduped = stats.deduped
    session.commit()
    summary.status = "ok"
    return summary


def _load_gold(stem: str) -> List[Dict[str, Any]]:
    path = FIXTURES / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"gold {stem} must be a list")
    return data


def _cheatsheet_section_id(row: Dict[str, Any]) -> str:
    sid = str(row.get("section_id") or "").strip()
    if sid:
        return sid
    href = str(row.get("hyperlink") or "")
    name = Path(href).stem or str(row.get("section") or "sheet")
    return name.replace(" ", "_")


def _top2_cre_ids(envelope: Dict[str, Any], uuid_to_ext: Dict[str, str]) -> List[str]:
    ordered: List[str] = []

    def add(raw: Any) -> None:
        if raw is None:
            return
        s = str(raw).strip()
        if not s:
            return
        ext = uuid_to_ext.get(s, s)
        if ext not in ordered:
            ordered.append(ext)

    for field in ("links", "suggested_links"):
        for link in envelope.get(field) or []:
            if isinstance(link, dict):
                add(link.get("cre_id"))
            if len(ordered) >= 2:
                return ordered[:2]
    retrieval = envelope.get("retrieval") or {}
    for field in ("rerank_top", "vector_top", "shortlist"):
        for item in retrieval.get(field) or []:
            if isinstance(item, dict):
                add(item.get("cre_id") or item.get("id"))
            else:
                add(item)
            if len(ordered) >= 2:
                return ordered[:2]
    return ordered


def _guess_keys_for_decision(
    *,
    path: str,
    text: str,
    repo: str,
) -> Set[str]:
    """Map a decision to gold keys ``{resource}::{section_id}``."""
    keys: Set[str] = set()
    blob = f"{path}\n{text}"
    repo_l = repo.lower()
    path_l = path.lower()
    # Infer family from path when source.repo is missing/odd.
    is_asvs = "asvs" in repo_l or "/asvs" in path_l or "asvs" in path_l
    is_aisvs = "aisvs" in repo_l or "aisvs" in path_l
    is_cs = "cheatsheet" in repo_l or "cheatsheet" in path_l

    if is_asvs and not is_aisvs:
        for m in ASVS_SID_RE.finditer(blob):
            sid = m.group(1).upper()
            # Prefer requirement grain (V1.1.2); keep V1.1 for rare gold rows
            keys.add(f"asvs::{sid}")
        for m in ASVS_BARE_REQ_RE.finditer(blob):
            keys.add(f"asvs::V{m.group(1)}")
        for m in re.finditer(
            r"Section-ID:\s*([^\n]+)", blob, flags=re.IGNORECASE
        ):
            for part in re.split(r"[,;\s]+", m.group(1)):
                part = part.strip()
                if ASVS_SID_RE.fullmatch(part):
                    keys.add(f"asvs::{part.upper()}")
                elif ASVS_BARE_REQ_RE.fullmatch(part):
                    keys.add(f"asvs::V{part}")
    if is_aisvs:
        for m in AISVS_SID_RE.finditer(blob):
            keys.add(f"aisvs::{m.group(1).upper()}")
        m = re.search(r"C(\d+)", path)
        if m:
            keys.add(f"aisvs::AISVS{int(m.group(1))}")
    if is_cs:
        stem = Path(path).stem
        keys.add(f"cheatsheets::{stem}")
    return keys


def score_github_decisions(
    run_id: str,
    cache: str,
    github_targets: Dict[str, Tuple[str, str, List[str], Optional[str]]],
) -> Dict[str, Any]:
    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import CRE, DecisionQueueItem

    db_connect(cache)
    uuid_to_ext = {
        row.id: (row.external_id or row.id)
        for row in sqla.session.query(CRE.id, CRE.external_id).all()
    }
    decisions = (
        sqla.session.query(DecisionQueueItem).filter_by(pipeline_run_id=run_id).all()
    )

    # gold key → cre set
    gold_map: Dict[str, Set[str]] = {}
    gold_meta: Dict[str, Dict[str, Any]] = {}
    for logical, (_repo, _br, _inc, stem) in github_targets.items():
        if not stem:
            continue
        for row in _load_gold(stem):
            if logical == "cheatsheets":
                sid = _cheatsheet_section_id(row)
            else:
                sid = str(row.get("section_id") or "").strip()
            if not sid:
                continue
            key = f"{logical}::{sid.upper() if logical != 'cheatsheets' else sid}"
            gold_map[key] = {c for c in (row.get("cre_ids") or []) if c}
            gold_meta[key] = {"logical": logical, "section_id": sid, "row": row}

    # Accumulate predictions per gold key.
    # Chapter-sized harvest: union all preds from a path onto every section id
    # seen in any chunk of that same path (ASVS requirement grain).
    path_preds: Dict[str, Set[str]] = {}
    path_keys: Dict[str, Set[str]] = {}
    for row in decisions:
        env = row.envelope if isinstance(row.envelope, dict) else {}
        knowledge = env.get("knowledge") or {}
        loc = knowledge.get("locator") or {}
        path = str(loc.get("path") or loc.get("id") or "")
        text = str(knowledge.get("text") or knowledge.get("body") or "")
        src = knowledge.get("source") or {}
        repo = str(
            src.get("repository") or src.get("repo") or src.get("name") or ""
        )
        if not repo:
            repo = str(env.get("artifact_id") or path)
        suggested = set(_top2_cre_ids(env, uuid_to_ext))
        if not suggested and not path:
            continue
        keys = _guess_keys_for_decision(path=path, text=text, repo=repo)
        # Normalize cheatsheet keys against gold
        norm_keys: Set[str] = set()
        for key in keys:
            if key.startswith("cheatsheets::"):
                stem = key.split("::", 1)[1]
                matched = None
                for gk in gold_map:
                    if gk.startswith("cheatsheets::") and gk.split("::", 1)[
                        1
                    ].casefold() == stem.casefold():
                        matched = gk
                        break
                if matched:
                    norm_keys.add(matched)
            else:
                norm_keys.add(key)
        path_preds.setdefault(path, set()).update(suggested)
        path_keys.setdefault(path, set()).update(norm_keys)

    pred: Dict[str, Set[str]] = {}
    for path, keys in path_keys.items():
        suggested = path_preds.get(path) or set()
        if not suggested:
            continue
        for key in keys:
            pred.setdefault(key, set()).update(suggested)

    details: List[Dict[str, Any]] = []
    by_resource: Dict[str, Dict[str, int]] = {}
    hits = scorable = unaligned = 0
    for key, gold in gold_map.items():
        logical = gold_meta[key]["logical"]
        bucket = by_resource.setdefault(
            logical, {"scorable": 0, "hits": 0, "unaligned": 0}
        )
        suggested = pred.get(key) or set()
        scorable += 1
        bucket["scorable"] += 1
        hit = bool(suggested & gold)
        aligned = key in pred
        if not aligned:
            unaligned += 1
            bucket["unaligned"] += 1
        if hit:
            hits += 1
            bucket["hits"] += 1
        details.append(
            {
                "resource": logical,
                "section_id": gold_meta[key]["section_id"],
                "aligned": aligned,
                "gold": sorted(gold),
                "predicted": sorted(suggested),
                "hit": hit,
            }
        )

    for bucket in by_resource.values():
        s = bucket["scorable"]
        bucket["accuracy"] = (bucket["hits"] / s) if s else 0.0

    return {
        "run_id": run_id,
        "mode": "github_aligned",
        "decisions_total": len(decisions),
        "scorable": scorable,
        "unaligned": unaligned,
        "hits": hits,
        "accuracy": (hits / scorable) if scorable else 0.0,
        "by_resource": by_resource,
        "details": details,
    }


def _write_b2_shaped_report(report: Dict[str, Any], out: Path) -> None:
    """Write a report score_b2_hop_distance can consume (details + predicted)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")


def _run_b2_arm(
    *,
    run_id: str,
    cache: str,
    keep_all: bool,
    fixtures: Sequence[str],
    arm_name: str,
    out_name: str,
) -> Dict[str, Any]:
    """Score one or more B2 fixture families (cached sources under b2_sources/)."""
    import subprocess

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )

    stems = [str(s).strip() for s in fixtures if str(s).strip()]
    if not stems:
        raise ValueError(f"B2 arm {arm_name!r} has no fixtures")

    db_connect(cache)
    # content_hash is unique — leftover KQ rows from prior arms block replay.
    for stem in stems:
        for pattern in (f"%{stem}%", f"%{arm_name}%"):
            sqla.session.query(KnowledgeQueueItem).filter(
                KnowledgeQueueItem.artifact_id.like(pattern)
            ).delete(synchronize_session=False)
            sqla.session.query(KnowledgeQueueItem).filter(
                KnowledgeQueueItem.chunk_id.like(pattern)
            ).delete(synchronize_session=False)
            sqla.session.query(HarvestInput).filter(
                HarvestInput.pipeline_run_id.like(f"%{arm_name}%")
            ).delete(synchronize_session=False)
    sqla.session.query(KnowledgeQueueItem).filter(
        KnowledgeQueueItem.pipeline_run_id.like(f"%{arm_name}%")
    ).delete(synchronize_session=False)
    sqla.session.query(HarvestInput).filter(
        HarvestInput.pipeline_run_id.like(f"%{arm_name}%")
    ).delete(synchronize_session=False)
    sqla.session.query(DecisionQueueItem).filter(
        DecisionQueueItem.pipeline_run_id.like(f"%{arm_name}%")
    ).delete(synchronize_session=False)
    sqla.session.commit()

    arm_run = f"{run_id}-{arm_name}"
    out = EXP / out_name
    EXP.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ROOT / "venv" / "bin" / "python"),
        str(ROOT / "scripts" / "oie_owasp_eval" / "run_b2_pr_mappings.py"),
        "--run-id",
        arm_run,
        "--out",
        str(out),
        "--only-fixtures",
        *stems,
    ]
    if keep_all:
        cmd.append("--keep-all-knowledge")
    env = os.environ.copy()
    env["DEV_DATABASE_URL"] = cache
    env["DATABASE_URL"] = cache
    print(" ".join(cmd), flush=True)
    ret = subprocess.call(cmd, cwd=str(ROOT), env=env)
    if not out.is_file():
        raise RuntimeError(f"B2 arm {arm_name} produced no report (exit={ret})")
    report = json.loads(out.read_text())
    report["arm"] = arm_name
    report["fixtures"] = stems
    report["b2_exit_code"] = ret
    return report


def _run_aix_b2_arm(*, run_id: str, cache: str, keep_all: bool) -> Dict[str, Any]:
    """Score AIX via existing LLM Top10 B2 gold (hub CRE proxy)."""
    return _run_b2_arm(
        run_id=run_id,
        cache=cache,
        keep_all=keep_all,
        fixtures=B2_ARMS["aix"],
        arm_name="aix-b2",
        out_name="full_pipeline_aix_llm.b2_report.json",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos",
        default="asvs,aisvs,cheatsheets,aix",
        help=(
            "Comma list: asvs,aisvs,cheatsheets,aix,nist,top10,api "
            "(nist/top10/api are B2 source arms)"
        ),
    )
    parser.add_argument(
        "--cache_file",
        default=os.environ.get("DEV_DATABASE_URL")
        or "postgresql://cre:password@127.0.0.1:5432/cre",
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--keep-all-knowledge",
        action="store_true",
        help="Skip Module B noise filter; forward all harvest chunks as KNOWLEDGE",
    )
    parser.add_argument(
        "--skip-score",
        action="store_true",
        help="Run A→B→C only; do not align to gold",
    )
    parser.add_argument(
        "--neighborhood",
        action="store_true",
        help="After exact score, run score_b2_hop_distance on reports",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ART,
        help="Report directory (default tmp/oie_owasp_eval/full_pipeline)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _load_dotenv()
    _apply_promoted_flags()
    os.environ.setdefault("FLASK_CONFIG", "development")
    sys.path.insert(0, str(ROOT))

    wanted = [x.strip().lower() for x in args.repos.split(",") if x.strip()]
    known = set(GITHUB_TARGETS) | set(B2_ARMS)
    unknown = [x for x in wanted if x not in known]
    if unknown:
        print(f"unknown --repos entries: {unknown}", file=sys.stderr)
        return 2

    github = {k: GITHUB_TARGETS[k] for k in wanted if k in GITHUB_TARGETS}
    b2_wanted = [k for k in wanted if k in B2_ARMS]
    run_id = args.run_id or (
        "fullpipe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )
    from application.utils.oie_orchestrator import run_oie_pipeline

    cache = args.cache_file
    orch_result = None
    github_report: Optional[Dict[str, Any]] = None
    b2_reports: Dict[str, Dict[str, Any]] = {}

    if github:
        print(f"=== Module A (tarball) + B + C  run_id={run_id} ===", flush=True)
        db_connect(cache)
        for model in (HarvestInput, KnowledgeQueueItem, DecisionQueueItem):
            deleted = (
                sqla.session.query(model)
                .filter_by(pipeline_run_id=run_id)
                .delete(synchronize_session=False)
            )
            print(f"cleared {model.__tablename__} for {run_id}: {deleted}", flush=True)
        sqla.session.commit()

        harvester = _make_tarball_harvester(github)
        orch_result = run_oie_pipeline(
            cache_file=cache,
            pipeline_run_id=run_id,
            sync_repos=False,
            run_harvester_fn=harvester,
            run_noise_filter_fn=_keep_all_noise_filter
            if args.keep_all_knowledge
            else None,
            use_langgraph=True,
        )
        orch_path = out_dir / "orchestrator_result.json"
        orch_path.write_text(orch_result.to_json() + "\n")
        print(f"wrote {orch_path}", flush=True)

        if not args.skip_score:
            print("=== Score GitHub arms vs gold ===", flush=True)
            github_report = score_github_decisions(run_id, cache, github)
            gh_out = EXP / "full_pipeline_github.b2_report.json"
            EXP.mkdir(parents=True, exist_ok=True)
            _write_b2_shaped_report(github_report, gh_out)
            # Mirror under ART for humans browsing full_pipeline/
            _write_b2_shaped_report(github_report, out_dir / "github_arms.b2_report.json")
            print(
                json.dumps(
                    {k: github_report[k] for k in github_report if k != "details"},
                    indent=2,
                ),
                flush=True,
            )
            print(f"wrote {gh_out}", flush=True)

    if b2_wanted and not args.skip_score:
        for arm in b2_wanted:
            stems = B2_ARMS[arm]
            print(f"=== B2 arm {arm} ({', '.join(stems)}) ===", flush=True)
            out_name = f"full_pipeline_{arm}.b2_report.json"
            report = _run_b2_arm(
                run_id=run_id,
                cache=cache,
                keep_all=args.keep_all_knowledge,
                fixtures=stems,
                arm_name=arm,
                out_name=out_name,
            )
            b2_reports[arm] = report
            _write_b2_shaped_report(report, out_dir / out_name)
            print(
                json.dumps(
                    {k: report[k] for k in report if k != "details"},
                    indent=2,
                ),
                flush=True,
            )

    summary: Dict[str, Any] = {
        "run_id": run_id,
        "repos": wanted,
        "github_accuracy": (github_report or {}).get("accuracy"),
        "github_hits": (github_report or {}).get("hits"),
        "github_scorable": (github_report or {}).get("scorable"),
        "orchestrator_ok": None
        if orch_result is None
        else orch_result.to_dict().get("ok"),
        "b2_arms": {
            name: {
                "accuracy": rep.get("accuracy"),
                "hits": rep.get("hits"),
                "scorable": rep.get("scorable"),
                "fixtures": rep.get("fixtures"),
            }
            for name, rep in b2_reports.items()
        },
    }
    # Back-compat keys for AIX-only consumers.
    if "aix" in b2_reports:
        summary["aix_accuracy"] = b2_reports["aix"].get("accuracy")
        summary["aix_hits"] = b2_reports["aix"].get("hits")
        summary["aix_scorable"] = b2_reports["aix"].get("scorable")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)

    if args.neighborhood and not args.skip_score:
        print("=== Neighborhood hop score ===", flush=True)
        import subprocess

        hop_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "oie_owasp_eval" / "score_b2_hop_distance.py"),
            "--reports-glob",
            "full_pipeline_*.b2_report.json",
            "--force",
        ]
        subprocess.check_call(hop_cmd, cwd=str(ROOT), env=os.environ.copy())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
