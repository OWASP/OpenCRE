"""Point-and-shoot GitHub URL ingest: harvest → Module B → print knowledge.

Not an eval scorer. Operational path for ``cre.py --ingest_github`` /
``make ingest <url>``.
"""

from __future__ import annotations

import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
TARBALL_DIR = ROOT / "tmp" / "oie_ingest" / "tarballs"

EXCLUDE = [
    "**/archive/**",
    "**/.github/**",
    "**/node_modules/**",
    "**/LICENSE*",
    "**/CHANGELOG*",
    "**/CONTRIBUTING*",
]

_GITHUB_HOSTS = {"github.com", "www.github.com"}


@dataclass(frozen=True)
class ParsedGitHubUrl:
    owner: str
    repo: str
    branch: Optional[str] = None
    path_prefix: Optional[str] = None  # e.g. 5.0/en from /tree/master/5.0/en


@dataclass
class IngestCounts:
    files: int = 0
    chunks: int = 0
    knowledge: int = 0
    uncertain: int = 0
    noise: int = 0
    deduped: int = 0
    errors: int = 0


def parse_github_url(url: str) -> ParsedGitHubUrl:
    """Parse ``https://github.com/owner/repo[/tree/branch[/path…]]``."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("GitHub URL is empty")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in _GITHUB_HOSTS:
        raise ValueError(f"only github.com URLs are supported (got host {host!r})")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError("URL must look like https://github.com/owner/repo")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    branch: Optional[str] = None
    path_prefix: Optional[str] = None
    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        branch = parts[3]
        if len(parts) > 4:
            path_prefix = "/".join(parts[4:])
    return ParsedGitHubUrl(
        owner=owner, repo=repo, branch=branch, path_prefix=path_prefix
    )


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


def _download_tarball(owner: str, repo: str, branch: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tried: List[str] = []
    candidates = [branch]
    for alt in ("main", "master"):
        if alt not in candidates:
            candidates.append(alt)
    last_err: Optional[BaseException] = None
    for try_branch in candidates:
        url = (
            f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{try_branch}"
        )
        tried.append(try_branch)
        print(f"GET {url}", file=sys.stderr, flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return try_branch
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            dest.unlink(missing_ok=True)
            print(f"  fail {try_branch}: {exc}", file=sys.stderr, flush=True)
    raise RuntimeError(
        f"could not download tarball for {owner}/{repo} "
        f"(tried branches {tried}): {last_err}"
    )


def _iter_md(tgz: Path, *, path_prefix: Optional[str]) -> List[Tuple[str, str]]:
    includes = ["**/*.md"]
    if path_prefix:
        pref = path_prefix.strip("/")
        includes = [f"{pref}/**/*.md", f"{pref}/*.md"]
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


def format_knowledge_item(
    *,
    path: str,
    label: str,
    confidence: float,
    text: str,
    reasoning: Optional[str] = None,
    max_chars: int = 4000,
) -> str:
    """Human-readable block for one knowledge chunk."""
    body = (
        text if len(text) <= max_chars else text[: max_chars - 20] + "\n… [truncated]"
    )
    lines = [
        "=" * 72,
        f"path: {path}",
        f"label: {label}  confidence: {confidence:.2f}",
    ]
    if reasoning:
        lines.append(f"reason: {reasoning}")
    lines.append("-" * 72)
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def _keep_all_noise_filter(session: Any, pipeline_run_id: str, **_kwargs: Any) -> Any:
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
            reasoning="ingest-keep-all",
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


def ingest_github_url(
    url: str,
    *,
    session: Any,
    cache_file: str,
    branch_override: Optional[str] = None,
    keep_all: bool = False,
    model_override: Optional[str] = None,
    run_id: Optional[str] = None,
) -> IngestCounts:
    """Harvest ``url``, classify, print knowledge to stdout. Returns counts."""
    from application.database.db import HarvestInput, KnowledgeQueueItem
    from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
    from application.utils.harvester.harvest_writer import write_harvest_input
    from application.utils.harvester.heading_extractor import HeadingExtractor
    from application.utils.harvester.models import Document, Locator, SourceInfo
    from application.utils.harvester.schemas import ChunkingConfig
    from application.utils.noise_filter.pipeline import run_noise_filter

    parsed = parse_github_url(url)
    _ = cache_file  # reserved; session is already bound via db_connect
    branch_hint = branch_override or parsed.branch or "main"
    rid = run_id or ("ingest-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    counts = IngestCounts()

    # Clear prior rows for this repo so content_hash dedupe does not hide output.
    repo_key = f"{parsed.owner}/{parsed.repo}"
    deleted_kq = (
        session.query(KnowledgeQueueItem)
        .filter(
            (KnowledgeQueueItem.source_repo == repo_key)
            | (KnowledgeQueueItem.artifact_id.like(f"%{repo_key}%"))
        )
        .delete(synchronize_session=False)
    )
    session.query(HarvestInput).filter_by(pipeline_run_id=rid).delete(
        synchronize_session=False
    )
    session.commit()
    if deleted_kq:
        print(
            f"cleared {deleted_kq} prior knowledge_queue rows for {repo_key}",
            file=sys.stderr,
            flush=True,
        )

    tgz = TARBALL_DIR / f"{parsed.owner}_{parsed.repo}.tgz"
    try:
        used_branch = _download_tarball(parsed.owner, parsed.repo, branch_hint, tgz)
    except Exception as exc:  # noqa: BLE001
        counts.errors += 1
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return counts

    files = _iter_md(tgz, path_prefix=parsed.path_prefix)
    counts.files = len(files)
    if not files:
        print(
            "ERROR: no markdown files matched " f"(prefix={parsed.path_prefix!r})",
            file=sys.stderr,
            flush=True,
        )
        counts.errors += 1
        return counts

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
    sha = "ingest000000000000000000000000000000001"
    records = []
    for rel, text in files:
        artifact_id = f"art:{repo_key}:{rel}"
        doc = Document(
            schema_version="0.2.0",
            artifact_id=artifact_id,
            pipeline_run_id=rid,
            text=text,
            heading_structure=headings.extract(text),
            source=SourceInfo(
                type="github",
                repository=repo_key,
                commit_sha=sha,
                committed_at=committed_at,
            ),
            locator=Locator(kind="repo_path", id=rel, path=rel),
        )
        records.extend(pipeline.chunk(doc))
    written = write_harvest_input(session, rid, records)
    session.commit()
    counts.chunks = written
    print(
        f"harvested {repo_key}@{used_branch}: files={len(files)} chunks={written} "
        f"run_id={rid}",
        file=sys.stderr,
        flush=True,
    )

    if keep_all:
        print(
            "Module B: --ingest_keep_all (no LLM; all chunks → KNOWLEDGE)",
            file=sys.stderr,
            flush=True,
        )
        b_summary = _keep_all_noise_filter(session, rid)
    else:
        import os

        from application.prompt_client.litellm_router import (
            has_credentials_for_model,
            missing_credentials_hint,
        )
        from application.utils.noise_filter.config_loader import load_config

        if model_override:
            os.environ["CRE_NOISE_FILTER_LLM_MODEL"] = model_override.strip()
        cfg = load_config()
        if not has_credentials_for_model(cfg.llm_model):
            print(
                "ERROR: " + missing_credentials_hint(cfg.llm_model),
                file=sys.stderr,
                flush=True,
            )
            counts.errors += 1
            return counts
        print(
            f"Module B: noise filter via LiteLLM model={cfg.llm_model!r}…",
            file=sys.stderr,
            flush=True,
        )
        b_summary = run_noise_filter(session, rid)

    counts.knowledge = getattr(b_summary, "kept_knowledge", 0) or 0
    counts.uncertain = getattr(b_summary, "kept_uncertain", 0) or 0
    counts.noise = getattr(b_summary, "dropped_noise", 0) or 0
    counts.deduped = getattr(b_summary, "deduped", 0) or 0

    rows = (
        session.query(KnowledgeQueueItem)
        .filter_by(pipeline_run_id=rid)
        .order_by(KnowledgeQueueItem.locator_path, KnowledgeQueueItem.span_index)
        .all()
    )
    # If dedupe skipped inserts, fall back to any KQ rows we refreshed for repo.
    if not rows:
        rows = (
            session.query(KnowledgeQueueItem)
            .filter(KnowledgeQueueItem.source_repo == repo_key)
            .order_by(KnowledgeQueueItem.locator_path, KnowledgeQueueItem.span_index)
            .all()
        )

    printed = 0
    for row in rows:
        if row.llm_label not in ("KNOWLEDGE", "UNCERTAIN"):
            continue
        sys.stdout.write(
            format_knowledge_item(
                path=row.locator_path or row.artifact_id,
                label=row.llm_label,
                confidence=float(row.confidence or 0.0),
                text=row.text or "",
                reasoning=row.llm_reasoning,
            )
        )
        printed += 1
    sys.stdout.flush()

    print(
        f"files={counts.files} chunks={counts.chunks} "
        f"knowledge={counts.knowledge} uncertain={counts.uncertain} "
        f"noise={counts.noise} printed={printed} deduped={counts.deduped} "
        f"run_id={rid}",
        file=sys.stderr,
        flush=True,
    )
    return counts


__all__ = [
    "IngestCounts",
    "ParsedGitHubUrl",
    "format_knowledge_item",
    "ingest_github_url",
    "parse_github_url",
]
