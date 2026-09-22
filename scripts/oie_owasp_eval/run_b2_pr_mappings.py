#!/usr/bin/env python3
"""B2: score Module C against OWASP mapping-fixture gold (harness only).

Canonical gold is ``application/tests/fixtures/owasp_mappings`` via
``application.utils.mapping_fixtures``. The agentic-AI stub (no hub Links)
stays under ``scripts/oie_owasp_eval/fixtures/b2_gold/``. Source material is
each row's ``hyperlink``, cached under
``scripts/oie_owasp_eval/fixtures/b2_sources/``. Alignment is
**section grain** (one gold row = one section_id). Hit if ≥1 of the union of
top-2 suggested CRE external_ids across that section's chunks is in the gold
``cre_ids``.

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/run_b2_pr_mappings.py
  PYTHONPATH=. python scripts/oie_owasp_eval/run_b2_pr_mappings.py --score-only --run-id <id>
  PYTHONPATH=. python scripts/oie_owasp_eval/run_b2_pr_mappings.py --include-agentic
  PYTHONPATH=. python scripts/oie_owasp_eval/run_b2_pr_mappings.py --local-gold
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLD_DIR = FIXTURES / "b2_gold"
SOURCES_DIR = FIXTURES / "b2_sources"

# Mapping-fixture gold (landed via #953/#960). Agentic stub is harness-only.
# local_gold=False → application/tests/fixtures/owasp_mappings (canonical gate).
# local_gold=True → scripts/oie_owasp_eval/fixtures/b2_gold/ (Related-expanded
# orphan umbrellas / stub-only families). Gate reports force canonical via
# apply_canonical_gold() / --canonical-gold.
AGENTIC_STUB_LABEL = "OWASP Agentic AI (stub, no hub Links)"
AGENTIC_STUB_FOOTNOTE = (
    "Agentic AI stub has no hub Links; exclude from headline denominator "
    "(footnote only)."
)

HARNESSES: List[Dict[str, Any]] = [
    {
        "fixture_name": "owasp_top10_2025",
        "gold_file": "owasp_top10_2025.json",
        "local_gold": False,
        "label": "OWASP Top 10 2025",
        "pr": 960,
    },
    {
        "fixture_name": "owasp_api_top10_2023",
        "gold_file": "owasp_api_top10_2023.json",
        "local_gold": False,
        "label": "OWASP API Top 10 2023",
        "pr": 960,
    },
    {
        "fixture_name": "owasp_llm_top10_2025",
        "gold_file": "owasp_llm_top10_2025.json",
        "local_gold": False,
        "label": "OWASP LLM Top 10 2025",
        "pr": 960,
    },
    {
        "fixture_name": "owasp_aisvs_1_0",
        "gold_file": "owasp_aisvs_1_0.json",
        "local_gold": False,
        "label": "OWASP AISVS 1.0",
        "pr": 960,
    },
    {
        # Provisional: CRE gold remapped from prod ASVS 4 via official YAML.
        # Not mentor-verified ASVS 5 Links — label clearly in reports.
        "fixture_name": "owasp_asvs_5_0_provisional",
        "gold_file": "owasp_asvs_5_0_provisional.json",
        "local_gold": False,
        "label": "OWASP ASVS 5.0 (provisional v4→v5 gold)",
        "pr": 0,
        "provisional": True,
    },
    {
        "fixture_name": "owasp_kubernetes_top10_2025",
        "gold_file": "owasp_kubernetes_top10_2025.json",
        "local_gold": False,
        "label": "OWASP Kubernetes Top 10 2025",
        "pr": 953,
    },
    {
        "fixture_name": "owasp_kubernetes_top10_2022",
        "gold_file": "owasp_kubernetes_top10_2022.json",
        "local_gold": False,
        # Cached hyperlink text still lives under the pre-merge PR #927 folder.
        "source_dir": "owasp_kubernetes_top10_2022_pr927",
        "label": "OWASP Kubernetes Top 10 2022",
        "pr": 953,
    },
    {
        # Harness-only: brand-new family with no hub Nodes/Links → expect weak accuracy.
        "pr": 0,
        "local_gold": True,
        "gold_file": "owasp_agentic_ai_stub.json",
        "label": AGENTIC_STUB_LABEL,
        "local_sources": True,
        "footnote_only": True,
    },
]


def apply_canonical_gold(harnesses: Optional[List[Dict[str, Any]]] = None) -> None:
    """Force fixture families onto canonical mapping gold (local_gold=False).

    Agentic stub stays local_gold=True (no application fixture).
    """
    target = harnesses if harnesses is not None else HARNESSES
    for harness in target:
        if harness.get("fixture_name"):
            harness["local_gold"] = False


def active_harnesses(
    *,
    exclude_agentic: bool = False,
    exclude_fixtures: Optional[Sequence[str]] = None,
    harnesses: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return harness list, optionally dropping agentic and named fixtures."""
    src = list(harnesses) if harnesses is not None else list(HARNESSES)
    skip = {str(s).strip() for s in (exclude_fixtures or []) if str(s).strip()}
    out: List[Dict[str, Any]] = []
    for h in src:
        if exclude_agentic and (
            h.get("label") == AGENTIC_STUB_LABEL or h.get("footnote_only")
        ):
            continue
        fixture = str(h.get("fixture_name") or "")
        stem = gold_stem(h) if (h.get("fixture_name") or h.get("gold_file")) else ""
        if fixture in skip or stem in skip:
            continue
        out.append(h)
    return out


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


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


def normalize_source_url(url: str) -> str:
    """Prefer raw markdown for GitHub blob/tree links."""
    u = (url or "").strip()
    if not u:
        return u
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/(?:blob|tree)/([^/]+)/(.+)$",
        u,
    )
    if m:
        owner, repo, ref, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    return u


def fetch_url(url: str, *, timeout: int = 45) -> Tuple[str, str]:
    """Return (content_type_hint, text). Raises on hard failure."""
    url = normalize_source_url(url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenCRE-OIE-B2/1.0", "Accept": "text/*,*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()
    text = raw.decode("utf-8", errors="replace")
    if (
        "html" in ctype
        or text.lstrip().lower().startswith("<!doctype")
        or text.lstrip().startswith("<html")
    ):
        parser = _HTMLTextExtractor()
        parser.feed(text)
        extracted = parser.text()
        if len(extracted) > 200:
            return "html_text", extracted
    return "text", text


# PR #927 hyperlinks use outdated path slugs; GitHub still has the markdown.
_K8S_2022_RAW = {
    "K01": "K01-insecure-workload-configurations.md",
    "K02": "K02-supply-chain-vulnerabilities.md",
    "K03": "K03-overly-permissive-rbac.md",
    "K04": "K04-policy-enforcement.md",
    "K05": "K05-inadequate-logging.md",
    "K06": "K06-broken-authentication.md",
    "K07": "K07-network-segmentation.md",
    "K08": "K08-secrets-management.md",
    "K09": "K09-misconfigured-cluster-components.md",
    "K10": "K10-vulnerable-components.md",
}


def source_url_candidates(row: Dict[str, Any], harness: Dict[str, Any]) -> List[str]:
    href = str(row.get("hyperlink") or "").strip()
    sid = str(row.get("section_id") or "").strip()
    out: List[str] = []
    if href:
        out.append(href)
        if not href.endswith(".html"):
            out.append(href.rstrip("/") + ".html")
    if (
        harness.get("gold_file", "").startswith("owasp_kubernetes_top10_2022")
        and sid in _K8S_2022_RAW
    ):
        out.append(
            "https://raw.githubusercontent.com/OWASP/www-project-kubernetes-top-ten/"
            f"main/2022/en/src/{_K8S_2022_RAW[sid]}"
        )
    # dedupe preserve order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def fetch_row_source(row: Dict[str, Any], harness: Dict[str, Any]) -> Tuple[str, str]:
    last_exc: Optional[BaseException] = None
    for url in source_url_candidates(row, harness):
        try:
            return fetch_url(url)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def gold_filename(harness: Dict[str, Any]) -> str:
    if harness.get("gold_file"):
        return str(harness["gold_file"])
    name = str(harness.get("fixture_name") or "")
    return name if name.endswith(".json") else f"{name}.json"


def gold_stem(harness: Dict[str, Any]) -> str:
    name = gold_filename(harness)
    return name[:-5] if name.endswith(".json") else name


def source_stem(harness: Dict[str, Any]) -> str:
    return str(harness.get("source_dir") or gold_stem(harness))


def load_gold(harness: Dict[str, Any]) -> List[Dict[str, Any]]:
    if harness.get("local_gold"):
        path = GOLD_DIR / gold_filename(harness)
        if not path.is_file():
            raise FileNotFoundError(f"missing local gold file {path}")
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError(f"gold {path} must be a list of section mappings")
        return data
    from application.utils.mapping_fixtures import load_owasp_mapping_fixture

    return load_owasp_mapping_fixture(str(harness["fixture_name"]))


def top2_cre_external_ids(
    envelope: Dict[str, Any], uuid_to_ext: Dict[str, str]
) -> List[str]:
    """Union of rerank top-2 and vector top-2 (up to 4 ids).

    Hit if ≥1 of this union is in gold — CE cannot erase a strong cosine hit.
    """
    ordered: List[str] = []

    def add(cre_id: Optional[str]) -> None:
        if not cre_id:
            return
        ext = uuid_to_ext.get(cre_id, cre_id)
        if ext not in ordered:
            ordered.append(ext)

    retrieval = envelope.get("retrieval") or {}
    reranked = list(retrieval.get("reranked") or [])
    candidates = list(retrieval.get("candidates") or [])

    for cand in reranked[:2]:
        if isinstance(cand, dict):
            add(cand.get("cre_id"))

    by_vec = sorted(
        (c for c in candidates if isinstance(c, dict)),
        key=lambda c: float(c.get("score_vector") or 0.0),
        reverse=True,
    )
    for cand in by_vec[:2]:
        add(cand.get("cre_id"))

    if ordered:
        return ordered

    for field in ("links", "suggested_links"):
        for link in envelope.get(field) or []:
            if isinstance(link, dict):
                add(link.get("cre_id"))
            if len(ordered) >= 2:
                return ordered[:2]
    return ordered


def ensure_sources(harnesses: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Download each gold row's hyperlink into b2_sources/<gold_file>/<section_id>.txt."""
    report: Dict[str, Any] = {"files": 0, "errors": []}
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    for harness in harnesses:
        gold = load_gold(harness)
        dest_dir = SOURCES_DIR / source_stem(harness)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for row in gold:
            sid = str(row.get("section_id") or "").strip()
            href = str(row.get("hyperlink") or "").strip()
            if not sid or not href:
                continue
            out = dest_dir / f"{sid}.txt"
            if out.is_file() and out.stat().st_size > 200:
                report["files"] += 1
                continue
            try:
                kind, text = fetch_row_source(row, harness)
                # Prefix identity so Module C sees section_id even after HTML strip.
                body = (
                    f"Source: {sid}\n"
                    f"Section: {row.get('section') or sid}\n"
                    f"Section-ID: {sid}\n\n"
                    f"{text}"
                )
                out.write_text(body)
                report["files"] += 1
                print(
                    f"  fetched {harness['gold_file']} {sid} ({kind}, {len(text)} chars)",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"{harness['gold_file']}:{sid}: {exc}"
                report["errors"].append(msg)
                print(f"  FAIL {msg}", flush=True)
    return report


def run_pipeline(
    run_id: str, cache: str, *, keep_all_knowledge: bool = False
) -> Dict[str, Any]:
    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )
    from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
    from application.utils.harvester.harvest_writer import write_harvest_input
    from application.utils.harvester.heading_extractor import HeadingExtractor
    from application.utils.harvester.models import Document, Locator, SourceInfo
    from application.utils.harvester.pipeline import RunSummary
    from application.utils.harvester.schemas import ChunkingConfig
    from application.utils.oie_orchestrator import run_oie_pipeline

    headings = HeadingExtractor()
    committed_at = datetime.now(timezone.utc)
    sha = "b2source0000000000000000000000000000001"
    chunking = ChunkingConfig(
        strategy="docling",
        max_tokens=1000,
        overlap_tokens=80,
        merge_profile="narrative",
    )
    pipeline = DocumentChunkPipeline(chunking=chunking)

    def run_harvester(
        session: Any, rid: str, *, dry_run: bool = False, sync_repos: bool = True
    ):
        summary = RunSummary(run_id=rid, dry_run=dry_run, repositories=0)
        all_records = []
        for harness in HARNESSES:
            gold = load_gold(harness)
            summary.repositories += 1
            src_dir = SOURCES_DIR / source_stem(harness)
            for row in gold:
                sid = str(row.get("section_id") or "").strip()
                if not sid:
                    continue
                if not (row.get("cre_ids") or []):
                    continue
                path = src_dir / f"{sid}.txt"
                if not path.is_file():
                    continue
                text = path.read_text()
                if len(text.strip()) < 80:
                    continue
                rel = f"b2/{source_stem(harness)}/{sid}.txt"
                doc = Document(
                    schema_version="0.2.0",
                    artifact_id=f"art:B2/{source_stem(harness)}:{sid}",
                    pipeline_run_id=rid,
                    text=text,
                    heading_structure=headings.extract(text),
                    source=SourceInfo(
                        type="github",
                        repository=f"B2/{source_stem(harness)}",
                        commit_sha=sha,
                        committed_at=committed_at,
                    ),
                    locator=Locator(kind="repo_path", id=rel, path=rel),
                )
                recs = pipeline.chunk(doc)
                all_records.extend(recs)
                summary.files_seen += 1
                summary.files_retained += 1
                print(
                    f"  {harness['label']} {sid}: chunks={len(recs)}",
                    flush=True,
                )
            summary.documents_emitted += sum(
                1
                for r in gold
                if (r.get("cre_ids") or [])
                and (src_dir / f"{r['section_id']}.txt").is_file()
            )
        if dry_run:
            summary.chunks_written = len(all_records)
            summary.status = "ok"
            return summary
        written = write_harvest_input(session, rid, all_records)
        summary.chunks_written = written
        summary.status = "ok" if written else "degraded: no chunks"
        return summary

    def keep_all_noise_filter(session: Any, pipeline_run_id: str, **_kwargs: Any):
        """Harness-only: promote every harvest chunk to KNOWLEDGE (score Module C)."""
        from application.utils.noise_filter.hashing import compute_content_hash
        from application.utils.noise_filter.pipeline import RunSummary as BSummary
        from application.utils.noise_filter.queue_writer import write_verdicts
        from application.utils.noise_filter.schemas import (
            ChangeRecord,
            ClassifyResult,
        )

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
                reasoning="b2-keep-all-knowledge",
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

    db_connect(cache)
    for model in (HarvestInput, KnowledgeQueueItem, DecisionQueueItem):
        deleted = sqla.session.query(model).delete(synchronize_session=False)
        print(f"cleared {model.__tablename__}: {deleted}", flush=True)
    sqla.session.commit()

    result = run_oie_pipeline(
        cache_file=cache,
        pipeline_run_id=run_id,
        sync_repos=False,
        run_harvester_fn=run_harvester,
        run_noise_filter_fn=keep_all_noise_filter if keep_all_knowledge else None,
        use_langgraph=True,
    )
    return json.loads(result.to_json())


def score_run(
    run_id: str,
    cache: str,
    *,
    exclude_agentic: bool = False,
    harnesses: Optional[Sequence[Dict[str, Any]]] = None,
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

    # section_key → predicted CRE set
    pred: Dict[str, Set[str]] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    for row in decisions:
        env = row.envelope if isinstance(row.envelope, dict) else {}
        knowledge = env.get("knowledge") or {}
        loc = knowledge.get("locator") or {}
        path = str(loc.get("path") or loc.get("id") or "")
        # b2/<resource>/<SECTION>.txt
        parts = Path(path).parts
        if len(parts) < 3 or parts[0] != "b2":
            # also try artifact_id art:B2/<gold_file>:<sid>
            chunk_id = row.chunk_id or ""
            m = re.search(r"art:B2/([^:]+):([^:]+)", chunk_id)
            if not m:
                continue
            resource, sid = m.group(1), m.group(2)
        else:
            resource = parts[1]
            sid = Path(parts[-1]).stem
        key = f"{resource}::{sid}"
        top2 = top2_cre_external_ids(env, uuid_to_ext)
        pred.setdefault(key, set()).update(t for t in top2 if t)
        meta[key] = {"resource": resource, "section_id": sid, "path": path}

    details: List[Dict[str, Any]] = []
    by_resource: Dict[str, Dict[str, int]] = {}
    hits = scorable = unaligned = 0
    selected = active_harnesses(exclude_agentic=exclude_agentic, harnesses=harnesses)

    for harness in selected:
        resource = source_stem(harness)
        gold_rows = load_gold(harness)
        bucket = by_resource.setdefault(
            harness["label"],
            {"scorable": 0, "hits": 0, "unaligned": 0, "pr": harness["pr"]},
        )
        for row in gold_rows:
            sid = str(row.get("section_id") or "").strip()
            gold = {c for c in (row.get("cre_ids") or []) if c}
            if not gold:
                continue
            key = f"{resource}::{sid}"
            suggested = pred.get(key) or set()
            if key not in pred:
                unaligned += 1
                bucket["unaligned"] += 1
                details.append(
                    {
                        "resource": harness["label"],
                        "pr": harness["pr"],
                        "section_id": sid,
                        "aligned": False,
                        "gold": sorted(gold),
                        "predicted": [],
                        "hit": False,
                    }
                )
                continue
            scorable += 1
            bucket["scorable"] += 1
            hit = bool(suggested & gold)
            if hit:
                hits += 1
                bucket["hits"] += 1
            details.append(
                {
                    "resource": harness["label"],
                    "pr": harness["pr"],
                    "section_id": sid,
                    "aligned": True,
                    "gold": sorted(gold),
                    "predicted": sorted(suggested),
                    "hit": hit,
                }
            )

    rate = (hits / scorable) if scorable else 0.0
    for label, bucket in by_resource.items():
        s = bucket["scorable"]
        bucket["accuracy"] = round((bucket["hits"] / s) if s else 0.0, 4)

    report: Dict[str, Any] = {
        "run_id": run_id,
        "gate": "B2 PR JSON gold (section grain, ≥1 of union(rerank top-2 ∪ vector top-2) ∈ gold cre_ids)",
        "local_gold": False,
        "exclude_agentic": exclude_agentic,
        "harnesses": [
            {
                "pr": h["pr"],
                "label": h["label"],
                "gold_file": gold_filename(h),
                "fixture_name": h.get("fixture_name"),
                "local_gold": bool(h.get("local_gold")),
                "footnote_only": bool(h.get("footnote_only")),
            }
            for h in selected
        ],
        "decisions_total": len(decisions),
        "scorable": scorable,
        "unaligned": unaligned,
        "hits": hits,
        "accuracy": round(rate, 4),
        "pass_gt_60": rate > 0.60,
        "by_resource": by_resource,
        "details": details,
    }
    if exclude_agentic:
        report["agentic_footnote"] = AGENTIC_STUB_FOOTNOTE
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--keep-all-knowledge",
        action="store_true",
        help=(
            "Bypass Gemini noise filter; enqueue every harvest chunk as "
            "KNOWLEDGE so Module C is scored (HTML nav pages often false-NOISE)."
        ),
    )
    parser.add_argument(
        "--local-gold",
        action="store_true",
        help=(
            "Use remapped scripts/.../fixtures/b2_gold for fixture families. "
            "Default is canonical application/tests/fixtures (gate reports)."
        ),
    )
    parser.add_argument(
        "--include-agentic",
        action="store_true",
        help=(
            f"Include {AGENTIC_STUB_LABEL} in the scored denominator. "
            "Default excludes it (footnoted)."
        ),
    )
    parser.add_argument(
        "--exclude-fixtures",
        nargs="*",
        default=[],
        metavar="STEM",
        help=(
            "Skip named fixture stems from harvest+score "
            "(e.g. owasp_asvs_5_0_provisional when chapter HTML OOMs Module C)."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ART / "b2_accuracy_report.json",
    )
    args = parser.parse_args()

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("CRE_LIBRARIAN_RETRIEVER_BACKEND", "pgvector")
    _load_dotenv()
    cache = os.environ.get(
        "DEV_DATABASE_URL", "postgresql://cre:password@127.0.0.1:5432/cre"
    )

    if args.local_gold:
        for harness in HARNESSES:
            if harness.get("fixture_name") or harness.get("gold_file"):
                harness["local_gold"] = True
    else:
        apply_canonical_gold()

    exclude_agentic = not bool(args.include_agentic)
    exclude_fixtures = list(args.exclude_fixtures or [])
    if exclude_fixtures:
        skip = {str(s).strip() for s in exclude_fixtures if str(s).strip()}
        HARNESSES[:] = [
            h
            for h in HARNESSES
            if str(h.get("fixture_name") or "") not in skip
            and (
                not (h.get("fixture_name") or h.get("gold_file"))
                or gold_stem(h) not in skip
            )
        ]
    selected = active_harnesses(
        exclude_agentic=exclude_agentic, exclude_fixtures=exclude_fixtures
    )

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for harness in selected:
        try:
            load_gold(harness)
        except FileNotFoundError:
            missing.append(gold_filename(harness))
    if missing:
        print(
            "missing gold files — mapping fixtures or local stub not found:",
            missing,
            file=sys.stderr,
        )
        return 2

    if not args.score_only:
        print("fetching source pages…", flush=True)
        # Always harvest from the full harness list (incl. stub sources if present).
        src_report = ensure_sources(HARNESSES)
        print(json.dumps(src_report, indent=2), flush=True)
        run_id = args.run_id or (
            "orch-b2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        print(json.dumps({"run_id": run_id, "cache": cache}, indent=2), flush=True)
        orch = run_pipeline(run_id, cache, keep_all_knowledge=args.keep_all_knowledge)
        (ART / "b2_phase_status.json").write_text(json.dumps(orch, indent=2) + "\n")
        print(json.dumps(orch, indent=2), flush=True)
    else:
        run_id = args.run_id
        if not run_id:
            print("--run-id required with --score-only", file=sys.stderr)
            return 2

    report = score_run(
        run_id, cache, exclude_agentic=exclude_agentic, harnesses=selected
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in report if k != "details"}, indent=2))
    print(f"wrote {args.out}", flush=True)
    return 0 if report["scorable"] else 2


if __name__ == "__main__":
    sys.exit(main())
