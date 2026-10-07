from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import uuid
from typing import Any, Dict, List, Optional

from flask import current_app, has_app_context

import yaml
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from application import sqla  # type: ignore[attr-defined]
from application.database import db
from application.feature_flags import TRUE_VALUES
from application.utils import import_diff
from application.utils.admin_panel import config_catalog
from application.utils.harvester.github_sources import (
    parse_github_source,
    probe_github_source,
    probe_github_sources,
)
from application.utils.harvester.repos_validator import (
    RepositoryValidationError,
    validate_repositories,
)
from application.utils.harvester.schemas import ReposFile, validate_cron_line
from application.utils.owasp_agent.index_store import app_db_url_and_key
from application.utils.postgres_url import (
    is_postgres_url,
    sqlalchemy_postgres_url,
)

REPOS_YAML = Path(__file__).resolve().parents[1] / "harvester" / "repos.yaml"
REPO_ROOT = Path(__file__).resolve().parents[3]
RESTART_INSTRUCTIONS = (
    "HTTP cannot change process env. Set keys in .env or Heroku config vars, "
    "then restart the process."
)
IMPORT_STRIP = (
    ("queued", "Queued"),
    ("pending_review", "Review"),
    ("accepted", "Accepted"),
    ("applied", "Applied"),
)
YAML_MAX_BYTES = 4 * 1024 * 1024
YAML_MAX_LABEL = "4MiB"
AGENT_RESOURCE_ID = "owasp-agent"
HARVEST_KINDS = ("oie_repo", "owasp_agent")
TARGET_KINDS = ("oie_repo", "import_source")


def repos_yaml_source_name(custom_name: Optional[str], yaml_text: str) -> str:
    name = (custom_name or "").strip()
    if name:
        return name
    digest = hashlib.sha256((yaml_text or "").encode("utf-8")).hexdigest()[:12]
    return f"repos.yaml:{digest}"


def _dump_repos_mapping(data: Dict[str, Any]) -> str:
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    return dumped if dumped.endswith("\n") else dumped + "\n"


def load_repos_mapping(yaml_text: str, *, allow_empty: bool = False) -> Dict[str, Any]:
    if not isinstance(yaml_text, str):
        raise ValueError("yaml must be a string")
    if len(yaml_text.encode("utf-8")) > YAML_MAX_BYTES:
        raise ValueError(
            f"repos.yaml exceeds {YAML_MAX_LABEL}; add fewer repositories or "
            "trim paths/chunking blocks"
        )
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("repos.yaml must be a mapping")
    repos = data.get("repositories")
    if repos is None:
        data["repositories"] = []
        repos = data["repositories"]
    if not isinstance(repos, list):
        raise ValueError("repositories must be a list")
    sources = data.get("sources")
    if sources is None:
        data["sources"] = []
        sources = data["sources"]
    if sources and not isinstance(sources, list):
        raise ValueError("sources must be a list")
    if repos or sources or not allow_empty:
        try:
            parsed = ReposFile.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"invalid repos.yaml: {exc}") from exc
        try:
            validate_repositories(parsed)
        except RepositoryValidationError as exc:
            raise ValueError(str(exc)) from exc
    return data


def read_repos_yaml() -> Dict[str, Any]:
    if not REPOS_YAML.is_file():
        raise FileNotFoundError("repos.yaml not found")
    text = REPOS_YAML.read_text(encoding="utf-8")
    load_repos_mapping(text)
    return {
        "yaml": text,
        "source": repos_yaml_source_name(None, text),
        "path": "application/utils/harvester/repos.yaml",
    }


def write_repos_yaml(yaml_text: str) -> Dict[str, Any]:
    if not isinstance(yaml_text, str):
        raise ValueError("yaml must be a string")
    data = load_repos_mapping(yaml_text)
    probe_github_sources(data.get("sources") or [])
    REPOS_YAML.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(REPOS_YAML.parent), suffix=".yaml", prefix="repos."
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(yaml_text)
        os.replace(tmp_name, REPOS_YAML)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return {
        "yaml": yaml_text,
        "source": repos_yaml_source_name(None, yaml_text),
        "path": "application/utils/harvester/repos.yaml",
        "saved": True,
    }


def _source_url(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("url") or "").strip()
    return str(item).strip() if item is not None else ""


def _normalize_sources(items: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, str) and item.strip():
            out.append({"url": item.strip(), "enabled": True})
            continue
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        entry: Dict[str, Any] = {
            "url": url,
            "enabled": bool(item.get("enabled", True)),
        }
        cron = validate_cron_line(item.get("cron"))
        if cron:
            entry["cron"] = cron
        out.append(entry)
    return out


def add_github_source_to_yaml(
    yaml_text: str, owner: str, cron: Optional[str] = None
) -> Dict[str, Any]:
    parsed = parse_github_source(owner)
    data = load_repos_mapping(yaml_text, allow_empty=True)
    sources = _normalize_sources(data.get("sources"))
    existing = {
        parse_github_source(_source_url(item)).canonical.casefold() for item in sources
    }
    added = 0
    if parsed.canonical.casefold() not in existing:
        probe_github_source(parsed)
        entry: Dict[str, Any] = {"url": parsed.canonical, "enabled": True}
        cron_line = validate_cron_line(cron)
        if cron_line:
            entry["cron"] = cron_line
        sources.append(entry)
        added = 1
    ordered: Dict[str, Any] = {"sources": sources}
    repos = data.get("repositories") or []
    if repos:
        ordered["repositories"] = repos
    text = _dump_repos_mapping(ordered)
    load_repos_mapping(text)
    return {
        "yaml": text,
        "owner": parsed.owner,
        "source_url": parsed.canonical,
        "added": added,
        "skipped": 0 if added else 1,
        "source": repos_yaml_source_name(None, text),
    }


def expand_github_org_into_yaml(
    yaml_text: str, owner: str, cron: Optional[str] = None
) -> Dict[str, Any]:
    return add_github_source_to_yaml(yaml_text, owner, cron=cron)


def _int_field(value: Any, default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def add_repository_to_yaml(yaml_text: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    data = load_repos_mapping(yaml_text, allow_empty=True)
    owner = str(spec.get("owner") or "").strip()
    repo = str(spec.get("repo") or "").strip()
    if not owner or not repo:
        raise ValueError("owner and repo are required")
    repo_id = str(spec.get("id") or "").strip() or f"{owner}-{repo}".lower()
    include = spec.get("include")
    if isinstance(include, str):
        include = [part.strip() for part in include.splitlines() if part.strip()]
    if not include:
        paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
        include = paths.get("include") or ["**/*.md"]
    exclude = spec.get("exclude")
    if isinstance(exclude, str):
        exclude = [part.strip() for part in exclude.splitlines() if part.strip()]
    if exclude is None:
        paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
        exclude = paths.get("exclude") or []
    chunking = spec.get("chunking") if isinstance(spec.get("chunking"), dict) else {}
    polling = spec.get("polling") if isinstance(spec.get("polling"), dict) else {}
    repo_cfg: Dict[str, Any] = {
        "id": repo_id,
        "type": "github",
        "enabled": bool(spec.get("enabled", True)),
        "owner": owner,
        "repo": repo,
        "branch": str(spec.get("branch") or "main").strip() or "main",
        "paths": {"include": include, "exclude": exclude},
        "chunking": {
            "strategy": chunking.get("strategy")
            or spec.get("strategy")
            or "markdown_heading",
            "max_tokens": _int_field(
                chunking.get("max_tokens") or spec.get("max_tokens"),
                1200,
                "max_tokens",
            ),
            "overlap_tokens": _int_field(
                chunking.get("overlap_tokens") or spec.get("overlap_tokens"),
                100,
                "overlap_tokens",
            ),
        },
        "polling": {
            "mode": polling.get("mode") or spec.get("mode") or "incremental",
            "interval_minutes": _int_field(
                polling.get("interval_minutes") or spec.get("interval_minutes"),
                60,
                "interval_minutes",
            ),
        },
    }
    cron_line = validate_cron_line(spec.get("cron"))
    if cron_line:
        repo_cfg["cron"] = cron_line
    parsed = parse_github_source(f"github.com/{owner}/{repo}")
    probe_github_source(parsed)
    repos = list(data.get("repositories") or [])
    if any(
        str(r.get("id") or "").casefold() == repo_id.casefold()
        for r in repos
        if isinstance(r, dict)
    ):
        raise ValueError(f"target already exists: {repo_id}")
    repos.append(repo_cfg)
    ordered: Dict[str, Any] = {
        "sources": _normalize_sources(data.get("sources")),
        "repositories": repos,
    }
    text = _dump_repos_mapping(ordered)
    load_repos_mapping(text)
    return {
        "yaml": text,
        "added": repo_id,
        "source": repos_yaml_source_name(None, text),
        "repository": repo_cfg,
    }


def _write_temp_repos_yaml(yaml_text: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yaml",
        prefix="repos-oneoff-",
        delete=False,
    )
    try:
        handle.write(yaml_text)
    finally:
        handle.close()
    return Path(handle.name)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _main_db_url() -> tuple[Optional[str], Optional[str]]:
    """Return (raw_url, env_key) for the app's main database."""
    return app_db_url_and_key()


def _oie_cache_file() -> str:
    """Postgres URL for the admin OIE child (never sqlite)."""
    raw, key = _main_db_url()
    if not raw or not is_postgres_url(raw):
        raise RuntimeError(
            "Admin OIE requires Postgres (set DEV_DATABASE_URL or run "
            "`make admin-local` to start cre-postgres). "
            f"current={key or 'unset'}"
        )
    return sqlalchemy_postgres_url(raw)


def _agent_db_stats(db_url: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"db_exists": False, "counts": None, "last_sync": None}
    if not db_url:
        return out
    if not is_postgres_url(db_url):
        logger.warning("main app DB is not a Postgres URL; ignoring %r", db_url)
        return out
    engine = None
    try:
        engine = create_engine(
            sqlalchemy_postgres_url(db_url),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        with engine.connect() as conn:
            out["db_exists"] = True
            names = [
                str(row[0])
                for row in conn.execute(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public' ORDER BY tablename"
                    )
                ).fetchall()
            ]
            counts: Dict[str, int] = {}
            for name in names:
                if not name.replace("_", "").isalnum():
                    continue
                counts[name] = int(
                    conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0
                )
            out["counts"] = counts
            if "meta_entity" in names:
                last = conn.execute(
                    text("SELECT MAX(fetched_at) FROM meta_entity")
                ).scalar()
                if last is not None:
                    out["last_sync"] = (
                        last.isoformat() if hasattr(last, "isoformat") else str(last)
                    )
    except Exception:
        logger.warning("main app Postgres probe failed")
        return {"db_exists": False, "counts": None, "last_sync": None}
    finally:
        if engine is not None:
            engine.dispose()
    return out


def agent_status() -> Dict[str, Any]:
    enabled = os.getenv("OWASP_AGENT_ENABLED", "").strip().lower() in TRUE_VALUES
    raw_db, db_env_key = _main_db_url()
    db_url = raw_db if raw_db and is_postgres_url(raw_db) else None
    if raw_db and not db_url:
        logger.warning(
            "main app DB (%s) is not a Postgres URL; agent needs Postgres", db_env_key
        )
    pkg = importlib.util.find_spec("application.utils.owasp_agent") is not None
    stats = _agent_db_stats(db_url)
    params = []
    enabled_spec = config_catalog.CATALOG.get("OWASP_AGENT_ENABLED")
    if enabled_spec:
        params.append(
            {
                "key": "OWASP_AGENT_ENABLED",
                "value": os.getenv("OWASP_AGENT_ENABLED"),
                "help_text": enabled_spec.help_text,
                "help_url": enabled_spec.help_url,
            }
        )
    if db_env_key:
        db_spec = config_catalog.CATALOG.get(db_env_key)
        params.append(
            {
                "key": db_env_key,
                "value": (
                    config_catalog.redact_postgres_url(raw_db)
                    if raw_db and db_url
                    else raw_db
                ),
                "help_text": (
                    db_spec.help_text
                    if db_spec
                    else "Main app Postgres URL (shared with the OWASP agent)."
                ),
                "help_url": db_spec.help_url if db_spec else config_catalog.DOCS_ENV,
            }
        )
    return {
        "enabled": enabled,
        "db_url": config_catalog.redact_postgres_url(db_url) if db_url else None,
        "db_env_key": db_env_key if db_url else None,
        "db_configured": bool(db_url),
        "db_exists": stats["db_exists"],
        "counts": stats["counts"],
        "last_sync": stats["last_sync"],
        "params": params,
        "package_present": pkg,
        "demo_path": "/chatbot",
        "writes_cre_graph": False,
        "help_url": (
            "https://github.com/OWASP/OpenCRE/blob/main/"
            "application/utils/owasp_agent/README.md"
        ),
    }


def agent_resource() -> Dict[str, Any]:
    spec = agent_status()
    return {
        "id": AGENT_RESOURCE_ID,
        "kind": "owasp_agent",
        "name": "OWASP agent",
        "spec": spec,
        "enabled": True,
        "created_at": None,
        "built_in": True,
    }


def _run_agent_sync_job(
    run_id: str,
    *,
    skip_nest: bool,
    skip_github: bool,
    auto_concepts: bool,
) -> Dict[str, Any]:
    from application.utils.owasp_agent.concepts import auto_concepts_from_index
    from application.utils.owasp_agent.index_store import IndexStore
    from application.utils.owasp_agent.sync import sync_all

    store = IndexStore()
    report = sync_all(
        store=store,
        skip_nest=skip_nest,
        skip_github=skip_github,
    )
    concept_actions: List[Dict[str, str]] = []
    if auto_concepts and (report.nest_ok or report.github_ok):
        concept_actions = [
            {"action": a.action, "key": a.concept_key, "detail": a.detail}
            for a in auto_concepts_from_index(store)
        ]
    summary = report.to_dict()
    summary["concepts"] = len(concept_actions)
    summary["skip_nest"] = skip_nest
    summary["skip_github"] = skip_github
    if not (report.nest_ok or report.github_ok):
        status = "error"
    elif report.errors:
        status = "degraded"
    else:
        status = "ok"
    detail = json.dumps(summary)[:2000]
    append_event(run_id, "agent_sync", status, detail)
    if status != "error":
        cs = db.get_staged_change_set(run_id=run_id)
        if cs is not None:
            cs.staging_status = "accepted"
            sqla.session.commit()
    return {"status": status, "sync": summary, "concepts": concept_actions}


def start_agent_sync(
    *,
    skip_nest: Optional[bool] = None,
    skip_github: bool = False,
    auto_concepts: bool = True,
    wait: Optional[bool] = None,
) -> Dict[str, Any]:
    """Sync Nest/GitHub OWASP metadata into the main Postgres agent index.

    Creates an import run so progress shows under Admin → Pipeline. Skips Nest
    by default when ``NEST_API_KEY`` is unset (GitHub-only sync still runs).
    """
    raw_db, _db_env_key = _main_db_url()
    if not raw_db or not is_postgres_url(raw_db):
        raise ValueError(
            "OWASP agent sync needs a Postgres main DB "
            "(set DEV_DATABASE_URL / DATABASE_URL)"
        )
    if skip_nest is None:
        skip_nest = not bool((os.getenv("NEST_API_KEY") or "").strip())

    run = db.create_import_run(source="owasp-agent-sync", version="admin-agent-sync")
    db.persist_staged_change_set(
        run_id=run.id,
        changeset_json=import_diff.change_set_to_json([]),
        staging_status="pending_review",
    )
    append_event(
        run.id,
        "queued",
        "ok",
        json.dumps(
            {
                "skip_nest": skip_nest,
                "skip_github": skip_github,
                "auto_concepts": auto_concepts,
            }
        )[:2000],
    )
    append_event(run.id, "agent_sync", "started", "Nest/GitHub metadata sync")

    testing = (
        bool(has_app_context() and current_app.config.get("TESTING"))
        or (os.getenv("ADMIN_AGENT_SYNC") or "").strip().lower() in TRUE_VALUES
    )
    run_sync = testing if wait is None else bool(wait)
    job_kwargs = dict(
        skip_nest=bool(skip_nest),
        skip_github=bool(skip_github),
        auto_concepts=bool(auto_concepts),
    )
    sync_result: Optional[Dict[str, Any]] = None
    async_job = False
    if run_sync:
        try:
            sync_result = _run_agent_sync_job(run.id, **job_kwargs)
        except Exception as exc:
            logger.exception("agent sync failed")
            append_event(run.id, "agent_sync", "error", str(exc)[:2000])
            raise
    else:
        app = current_app._get_current_object()
        run_id = run.id

        def _worker() -> None:
            with app.app_context():
                try:
                    _run_agent_sync_job(run_id, **job_kwargs)
                except Exception as exc:
                    logger.exception("async agent sync failed")
                    try:
                        append_event(run_id, "agent_sync", "error", str(exc)[:2000])
                    except Exception:
                        logger.exception("failed to record agent sync error event")

        threading.Thread(
            target=_worker, daemon=True, name=f"admin-agent-{run.id}"
        ).start()
        async_job = True
        sync_result = {"async": True, "started": True}

    return {
        "run_id": run.id,
        "source": "owasp-agent-sync",
        "async": async_job,
        "skip_nest": bool(skip_nest),
        "skip_github": bool(skip_github),
        "auto_concepts": bool(auto_concepts),
        "result": sync_result,
    }


def list_targets() -> List[Dict[str, Any]]:
    seed_targets_from_yaml_if_empty()
    rows = (
        sqla.session.query(db.IngestionTarget)
        .order_by(db.IngestionTarget.name.asc())
        .all()
    )
    out = [agent_resource()]
    out.extend(_target_dict(t) for t in rows if t.id != AGENT_RESOURCE_ID)
    return out


def seed_targets_from_yaml_if_empty() -> None:
    try:
        if sqla.session.query(db.IngestionTarget).first() is not None:
            return
        if not REPOS_YAML.is_file():
            return
        data = yaml.safe_load(REPOS_YAML.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            logger.warning("repos.yaml is not a mapping; skip target seed")
            return
        repos = data.get("repositories") or []
        if not isinstance(repos, list):
            logger.warning("repos.yaml repositories is not a list; skip target seed")
            return
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            rid = str(repo.get("id") or "").strip()
            if not rid or rid == AGENT_RESOURCE_ID:
                continue
            t = db.IngestionTarget(
                id=rid,
                kind="oie_repo",
                name=rid,
                spec_json=json.dumps(repo),
                enabled=bool(repo.get("enabled", True)),
                created_at=_now(),
            )
            sqla.session.add(t)
        sqla.session.commit()
    except Exception:
        logger.exception("Failed to seed ingestion targets from yaml")
        sqla.session.rollback()


def add_target(
    *,
    target_id: str,
    kind: str,
    name: str,
    spec: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    if target_id == AGENT_RESOURCE_ID:
        raise ValueError("owasp-agent is a built-in resource")
    if kind not in TARGET_KINDS:
        raise ValueError("kind must be oie_repo or import_source")
    existing = (
        sqla.session.query(db.IngestionTarget)
        .filter(db.IngestionTarget.id == target_id)
        .first()
    )
    if existing:
        raise ValueError("target already exists")
    t = db.IngestionTarget(
        id=target_id,
        kind=kind,
        name=name or target_id,
        spec_json=json.dumps(spec or {}),
        enabled=enabled,
        created_at=_now(),
    )
    sqla.session.add(t)
    sqla.session.commit()
    return _target_dict(t)


def remove_target(target_id: str) -> bool:
    t = (
        sqla.session.query(db.IngestionTarget)
        .filter(db.IngestionTarget.id == target_id)
        .first()
    )
    if t:
        sqla.session.delete(t)
        sqla.session.commit()
        return True
    if target_id == AGENT_RESOURCE_ID:
        raise ValueError("cannot remove built-in resource")
    return False


def _target_dict(t: db.IngestionTarget) -> Dict[str, Any]:
    try:
        spec = json.loads(t.spec_json or "{}")
    except json.JSONDecodeError:
        spec = {}
    return {
        "id": t.id,
        "kind": t.kind,
        "name": t.name,
        "spec": spec,
        "enabled": bool(t.enabled),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "built_in": False,
    }


def append_event(run_id: str, stage: str, status: str, detail: str = "") -> None:
    ev = db.AdminPipelineEvent(
        id=str(uuid.uuid4()),
        run_id=run_id,
        stage=stage,
        status=status,
        detail=detail or None,
        created_at=_now(),
    )
    sqla.session.add(ev)
    sqla.session.commit()


def _subprocess_env() -> Dict[str, str]:
    """Ensure the repo root is on PYTHONPATH for `python /abs/scripts/*.py`."""
    env = os.environ.copy()
    root = str(REPO_ROOT)
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if root not in parts:
        env["PYTHONPATH"] = os.pathsep.join([root, *parts]) if parts else root
    return env


# Cap packaged org expands so admin "New" does not clone the whole of GitHub.
DEFAULT_OIE_MAX_REPOS = 5
ADMIN_OIE_YAML_DIR = REPO_ROOT / "tmp" / "admin_oie"


def _default_skip_bc() -> tuple[bool, bool]:
    """Admin ingest runs Module B and C unless the client opts out.

    Pass ``skip_b=True`` / ``skip_c=True`` to skip the noise filter or librarian.
    Module C.1 (graph filer) is skipped only when ``skip_c1`` is true.
    """
    return False, False


def _write_run_repos_yaml(run_id: str, yaml_text: str) -> Path:
    ADMIN_OIE_YAML_DIR.mkdir(parents=True, exist_ok=True)
    path = ADMIN_OIE_YAML_DIR / f"{run_id}.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


def invoke_oie_cli(
    run_id: str,
    repos_yaml: Optional[str] = None,
    *,
    dry_run: bool = False,
    sync_repos: bool = True,
    max_repos: Optional[int] = DEFAULT_OIE_MAX_REPOS,
    continue_on_error: bool = True,
    skip_b: Optional[bool] = None,
    skip_c: Optional[bool] = None,
    skip_c1: Optional[bool] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Run Module A→B→C→C.1 via the CLI against the app Postgres URL.

    Defaults are live (sync + persist) so admin ingest is end-to-end. Pass
    ``dry_run=True`` / ``sync_repos=False`` only for hermetic probes.
    """
    script = REPO_ROOT / "scripts" / "run_oie_pipeline.py"
    cache_file = _oie_cache_file()
    if skip_b is None or skip_c is None:
        auto_b, auto_c = _default_skip_bc()
        if skip_b is None:
            skip_b = auto_b
        if skip_c is None:
            skip_c = auto_c
    if skip_c1 is None:
        skip_c1 = False
    argv = [
        sys.executable,
        str(script),
        "--run_id",
        run_id,
        "--cache_file",
        cache_file,
    ]
    if dry_run:
        argv.append("--dry-run")
    if not sync_repos:
        argv.append("--no-sync-repos")
    if continue_on_error:
        argv.append("--continue-on-error")
    if skip_b:
        argv.append("--skip-b")
    if skip_c:
        argv.append("--skip-c")
    if skip_c1:
        argv.append("--skip-c1")
    if max_repos is not None and max_repos > 0:
        argv.extend(["--max-repos", str(int(max_repos))])
    if repos_yaml:
        argv.extend(["--repos_yaml", repos_yaml])
    # Clones need headroom; dry/no-sync probes stay short. B/C skipped → shorter.
    if timeout is None:
        if dry_run and not sync_repos:
            timeout = 120
        elif skip_b and skip_c:
            timeout = 600
        else:
            # Clone + LLM for the golden set (and later the org) exceeds 30 minutes.
            timeout = 24 * 60 * 60
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(REPO_ROOT),
        env=_subprocess_env(),
    )
    out = (proc.stdout or "").strip()
    try:
        parsed = json.loads(out)
        if isinstance(parsed, dict) and ("stages" in parsed or "run_id" in parsed):
            parsed["ok"] = bool(parsed.get("ok", proc.returncode == 0))
            parsed["returncode"] = proc.returncode
            parsed["skip_b"] = bool(skip_b)
            parsed["skip_c"] = bool(skip_c)
            parsed["skip_c1"] = bool(skip_c1)
            return parsed
    except json.JSONDecodeError:
        pass
    return {
        "ok": proc.returncode == 0,
        "raw": ((proc.stdout or "") + (proc.stderr or ""))[-2000:],
        "returncode": proc.returncode,
        "skip_b": bool(skip_b),
        "skip_c": bool(skip_c),
        "skip_c1": bool(skip_c1),
    }


def _record_oie_result(run_id: str, oie: Dict[str, Any]) -> None:
    oie_ok = bool(oie.get("ok", oie.get("returncode", 1) == 0))
    append_event(
        run_id,
        "oie",
        "ok" if oie_ok else "error",
        json.dumps(oie)[:2000],
    )
    # Compact trace so Pipeline UI can show flags/path without parsing the blob.
    trace = {
        "engine": oie.get("engine"),
        "flags": oie.get("flags"),
        "graph_path": oie.get("graph_path"),
        "visited": oie.get("visited"),
        "ok": oie_ok,
    }
    if any(trace.values()):
        append_event(
            run_id, "oie_trace", "ok" if oie_ok else "error", json.dumps(trace)[:2000]
        )
    for stage in oie.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        append_event(
            run_id,
            str(stage.get("name") or "oie"),
            str(stage.get("status") or "ok"),
            str(stage.get("detail") or "")[:2000],
        )


def _run_oie_job(
    run_id: str,
    repos_yaml_path: Optional[str],
    *,
    dry_run: bool,
    sync_repos: bool,
    max_repos: Optional[int],
    skip_b: Optional[bool],
    skip_c: Optional[bool],
    cleanup_yaml: bool,
) -> Dict[str, Any]:
    try:
        oie = invoke_oie_cli(
            run_id,
            repos_yaml=repos_yaml_path,
            dry_run=dry_run,
            sync_repos=sync_repos,
            max_repos=max_repos,
            skip_b=skip_b,
            skip_c=skip_c,
        )
        _record_oie_result(run_id, oie)
        return oie
    except Exception as exc:  # noqa: BLE001
        append_event(run_id, "oie", "error", str(exc)[:2000])
        return {"error": str(exc), "ok": False}
    finally:
        if cleanup_yaml and repos_yaml_path:
            try:
                path = Path(repos_yaml_path)
                if path.resolve().is_relative_to(ADMIN_OIE_YAML_DIR.resolve()):
                    path.unlink(missing_ok=True)
            except OSError:
                logger.warning("failed to remove admin oie yaml %s", repos_yaml_path)


def _packaged_harvest_source(custom_name: str) -> tuple[str, Optional[str]]:
    packaged = REPOS_YAML.read_text(encoding="utf-8") if REPOS_YAML.is_file() else ""
    path = str(REPOS_YAML) if REPOS_YAML.is_file() else None
    return repos_yaml_source_name(custom_name, packaged), path


def start_ingestion(
    *,
    source: str = "",
    target_id: Optional[str] = None,
    yaml_text: Optional[str] = None,
    name: Optional[str] = None,
    packaged: bool = False,
    dry_run: bool = False,
    sync_repos: bool = True,
    max_repos: Optional[int] = DEFAULT_OIE_MAX_REPOS,
    skip_b: Optional[bool] = None,
    skip_c: Optional[bool] = None,
    wait: Optional[bool] = None,
) -> Dict[str, Any]:
    custom_name = (name or "").strip()
    do_oie = False
    repos_yaml_path: Optional[str] = None
    cleanup_yaml = False
    one_off_yaml: Optional[str] = None
    stripped_target = str(target_id).strip() if target_id else ""

    if yaml_text is not None:
        data = load_repos_mapping(yaml_text)
        probe_github_sources(data.get("sources") or [])
        source = repos_yaml_source_name(custom_name, yaml_text)
        one_off_yaml = yaml_text
        do_oie = True
    elif packaged:
        do_oie = True
        source, repos_yaml_path = _packaged_harvest_source(custom_name)
    elif stripped_target:
        if stripped_target == AGENT_RESOURCE_ID:
            do_oie = True
            source, repos_yaml_path = _packaged_harvest_source(custom_name)
        else:
            target = (
                sqla.session.query(db.IngestionTarget)
                .filter(db.IngestionTarget.id == stripped_target)
                .first()
            )
            if not target:
                raise KeyError("target not found")
            if not target.enabled:
                raise ValueError("target is disabled")
            if target.kind in HARVEST_KINDS:
                do_oie = True
                source, repos_yaml_path = _packaged_harvest_source(custom_name)
            else:
                source = custom_name or target.name or target.id
    else:
        source = custom_name or (source or "").strip()
        if not source:
            raise ValueError("source is required")

    run = db.create_import_run(source=source, version="admin-start")
    db.persist_staged_change_set(
        run_id=run.id,
        changeset_json=import_diff.change_set_to_json([]),
        staging_status="pending_review",
    )
    append_event(run.id, "queued", "ok", f"source={source}")
    oie: Optional[Dict[str, Any]] = None
    async_job = False
    if do_oie:
        if one_off_yaml is not None:
            repos_yaml_path = str(_write_run_repos_yaml(run.id, one_off_yaml))
            cleanup_yaml = True
        auto_b, auto_c = _default_skip_bc()
        eff_skip_b = auto_b if skip_b is None else skip_b
        eff_skip_c = auto_c if skip_c is None else skip_c
        skip_reason = (
            "admin_default_skip_bc"
            if skip_b is None and skip_c is None and eff_skip_b and eff_skip_c
            else "client_flags" if skip_b is not None or skip_c is not None else "none"
        )
        append_event(
            run.id,
            "oie",
            "started",
            json.dumps(
                {
                    "dry_run": dry_run,
                    "sync_repos": sync_repos,
                    "max_repos": max_repos,
                    "skip_b": eff_skip_b,
                    "skip_c": eff_skip_c,
                    "skip_c1": False,
                    "skip_reason": skip_reason,
                    "repos_yaml": repos_yaml_path,
                    "wait": wait,
                    "graph_path": [
                        "START",
                        "module_a_harvester",
                        "module_b_noise_filter",
                        "module_c_librarian",
                        "module_c1_graph_filer",
                        "END",
                    ],
                    "note": (
                        "Admin default runs Module B, C, and C.1 (graph filer); "
                        "pass skip_b/skip_c/skip_c1 true to opt out. "
                        "Module A may write 0 chunks when checkpoints are already at HEAD."
                    ),
                }
            )[:2000],
        )
        testing = (
            bool(has_app_context() and current_app.config.get("TESTING"))
            or (os.getenv("ADMIN_OIE_SYNC") or "").strip().lower() in TRUE_VALUES
        )
        run_sync = testing if wait is None else bool(wait)
        job_kwargs = dict(
            dry_run=dry_run,
            sync_repos=sync_repos,
            max_repos=max_repos,
            skip_b=eff_skip_b,
            skip_c=eff_skip_c,
            cleanup_yaml=cleanup_yaml,
        )
        if run_sync:
            oie = _run_oie_job(run.id, repos_yaml_path, **job_kwargs)
        else:
            app = current_app._get_current_object()
            run_id = run.id
            yaml_path = repos_yaml_path

            def _worker() -> None:
                with app.app_context():
                    _run_oie_job(run_id, yaml_path, **job_kwargs)

            threading.Thread(
                target=_worker, daemon=True, name=f"admin-oie-{run.id}"
            ).start()
            async_job = True
            oie = {
                "async": True,
                "started": True,
                "skip_b": eff_skip_b,
                "skip_c": eff_skip_c,
            }
    else:
        append_event(
            run.id,
            "recorded",
            "ok",
            "Import run staged; apply via /admin/imports when ready",
        )
    return {
        "run_id": run.id,
        "source": source,
        "oie": oie,
        "dry_run": dry_run,
        "sync_repos": sync_repos,
        "async": async_job,
    }


def import_stage_strip(status: Optional[str]) -> List[Dict[str, str]]:
    if status == "discarded":
        return [
            {"id": "queued", "label": "Queued", "state": "done"},
            {"id": "pending_review", "label": "Discarded", "state": "failed"},
            {"id": "accepted", "label": "Accepted", "state": "idle"},
            {"id": "applied", "label": "Applied", "state": "idle"},
        ]
    if status == "apply_failed":
        return [
            {"id": "queued", "label": "Queued", "state": "done"},
            {"id": "pending_review", "label": "Review", "state": "done"},
            {"id": "accepted", "label": "Accepted", "state": "done"},
            {"id": "applied", "label": "Applied", "state": "failed"},
        ]
    current = status or "queued"
    seen = False
    out: List[Dict[str, str]] = []
    for sid, label in IMPORT_STRIP:
        if sid == current:
            out.append({"id": sid, "label": label, "state": "current"})
            seen = True
        elif not seen:
            out.append({"id": sid, "label": label, "state": "done"})
        else:
            out.append({"id": sid, "label": label, "state": "idle"})
    return out


def pipeline_snapshot() -> Dict[str, Any]:
    runs = db.list_import_runs(limit=50, offset=0)
    run_rows = []
    for r in runs:
        cs = db.get_staged_change_set(run_id=r.id)
        status = cs.staging_status if cs else None
        run_rows.append(
            {
                "id": r.id,
                "source": r.source,
                "version": r.version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "staging_status": status,
                "strip": import_stage_strip(status),
            }
        )
    events = (
        sqla.session.query(db.AdminPipelineEvent)
        .order_by(db.AdminPipelineEvent.created_at.desc())
        .limit(200)
        .all()
    )
    oie_decisions: List[Dict[str, Any]] = []
    unconsumed = 0
    try:
        q = sqla.session.query(db.DecisionQueueItem)
        unconsumed = q.filter(db.DecisionQueueItem.consumed_at.is_(None)).count()
        for item in q.order_by(db.DecisionQueueItem.id.desc()).limit(20):
            oie_decisions.append(
                {
                    "id": item.id,
                    "status": item.status,
                    "source_label": item.source_label,
                    "pipeline_run_id": item.pipeline_run_id,
                    "consumed": item.consumed_at is not None,
                }
            )
    except Exception:  # noqa: BLE001
        unconsumed = 0
    knowledge: List[Dict[str, Any]] = []
    try:
        kq = (
            sqla.session.query(db.KnowledgeQueueItem)
            .order_by(db.KnowledgeQueueItem.created_at.desc())
            .limit(10)
        )
        for item in kq:
            knowledge.append(
                {
                    "id": item.id,
                    "llm_label": item.llm_label,
                    "llm_reasoning": item.llm_reasoning,
                    "pipeline_run_id": item.pipeline_run_id,
                }
            )
    except Exception:  # noqa: BLE001
        knowledge = []
    latest_strip = run_rows[0]["strip"] if run_rows else import_stage_strip(None)
    return {
        "import_runs": run_rows,
        "latest_strip": latest_strip,
        "events": [
            {
                "id": e.id,
                "run_id": e.run_id,
                "stage": e.stage,
                "status": e.status,
                "detail": e.detail,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "oie": {
            "unconsumed": unconsumed,
            "recent": oie_decisions,
            "knowledge": knowledge,
        },
    }


def edit_staged_mapping(
    run_id: str, op_index: int, after: Dict[str, Any]
) -> Dict[str, Any]:
    if not isinstance(after, dict):
        raise ValueError("after must be an object")
    cs = db.get_staged_change_set(run_id=run_id)
    if not cs:
        raise KeyError("no staged change set")
    if cs.staging_status not in ("pending_review", "accepted"):
        raise ValueError("can only edit pending or accepted staged mappings")
    try:
        ops = json.loads(cs.changeset_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid changeset json") from exc
    if not isinstance(ops, list):
        raise ValueError("changeset must be a list")
    if op_index < 0 or op_index >= len(ops):
        raise IndexError("op_index out of range")
    op = ops[op_index]
    if not isinstance(op, dict):
        raise ValueError("invalid op")
    kind = str(op.get("op") or "")
    if kind in ("add_control", "remove_control"):
        op["document"] = after
        field = "document"
    elif kind == "modify_control":
        op["after"] = after
        field = "after"
    else:
        raise ValueError("unsupported op type")
    db.update_staged_change_set(run_id=run_id, changeset_json=json.dumps(ops))
    return {
        "run_id": run_id,
        "op_index": op_index,
        "field": field,
        field: after,
        "changeset": ops,
        "staging_status": cs.staging_status,
    }


def drop_last_ingestion(source: str) -> Dict[str, Any]:
    run = db.get_latest_import_run(source)
    if not run:
        raise KeyError("no import run for source")
    cs = db.get_staged_change_set(run_id=run.id)
    if not cs:
        raise KeyError("no staged change set")
    if cs.staging_status == "applied":
        raise PermissionError(
            "last run is already applied; graph rollback is not implemented"
        )
    db.update_staged_change_set(run_id=run.id, staging_status="discarded")
    append_event(run.id, "dropped", "ok", f"source={source}")
    return {"run_id": run.id, "staging_status": "discarded"}


def _op_document(op: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(op.get("op") or "")
    if kind == "modify_control":
        doc = op.get("after")
    else:
        doc = op.get("document")
    return doc if isinstance(doc, dict) else {}


def _op_added_name(op: Dict[str, Any], doc: Dict[str, Any]) -> str:
    name = doc.get("name")
    if name:
        return str(name)
    key = op.get("key")
    if isinstance(key, list) and key:
        return str(key[0] or "")
    return ""


def review_run_links(run_id: str) -> Dict[str, Any]:
    cs = db.get_staged_change_set(run_id=run_id)
    if not cs:
        raise KeyError("no staged change set")
    try:
        ops = json.loads(cs.changeset_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid changeset json") from exc
    if not isinstance(ops, list):
        raise ValueError("changeset must be a list")
    links: List[Dict[str, Any]] = []
    for op_index, op in enumerate(ops):
        if not isinstance(op, dict):
            continue
        doc = _op_document(op)
        added = {
            "name": _op_added_name(op, doc),
            "section": doc.get("section") or "",
            "sectionID": doc.get("sectionID") or "",
            "op": op.get("op"),
        }
        cres = doc.get("linked_cres")
        if not isinstance(cres, list) or not cres:
            links.append(
                {
                    "op_index": op_index,
                    "link_index": None,
                    "added": added,
                    "linked_to": None,
                    "decision": "pending",
                }
            )
            continue
        for link_index, cre in enumerate(cres):
            if not isinstance(cre, dict):
                continue
            links.append(
                {
                    "op_index": op_index,
                    "link_index": link_index,
                    "added": added,
                    "linked_to": {
                        "id": cre.get("id") or "",
                        "name": cre.get("name") or "",
                    },
                    "decision": cre.get("decision") or "pending",
                }
            )
    return {
        "run_id": run_id,
        "staging_status": cs.staging_status,
        "links": links,
        "changeset": ops,
    }


def review_link(
    run_id: str,
    *,
    op_index: int,
    action: str,
    link_index: Optional[int] = None,
    cre: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    action = (action or "").strip().lower()
    if action not in ("approve", "deny", "relink"):
        raise ValueError("action must be approve, deny, or relink")
    cs = db.get_staged_change_set(run_id=run_id)
    if not cs:
        raise KeyError("no staged change set")
    if cs.staging_status not in ("pending_review", "accepted"):
        raise ValueError("can only edit pending or accepted staged mappings")
    try:
        ops = json.loads(cs.changeset_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid changeset json") from exc
    if not isinstance(ops, list):
        raise ValueError("changeset must be a list")
    if op_index < 0 or op_index >= len(ops):
        raise IndexError("op_index out of range")
    op = ops[op_index]
    if not isinstance(op, dict):
        raise ValueError("invalid op")
    doc = _op_document(op)
    cres = doc.get("linked_cres")
    if not isinstance(cres, list):
        cres = []
        doc["linked_cres"] = cres
    if action == "relink":
        if not isinstance(cre, dict) or not (
            str(cre.get("id") or "").strip() or str(cre.get("name") or "").strip()
        ):
            raise ValueError("relink requires cre.id or cre.name")
        target = {
            "id": str(cre.get("id") or "").strip(),
            "name": str(cre.get("name") or "").strip(),
            "decision": "relinked",
        }
        if link_index is None:
            cres.append(target)
        else:
            if link_index < 0 or link_index >= len(cres):
                raise IndexError("link_index out of range")
            cres[link_index] = target
    elif action == "deny":
        if link_index is None or link_index < 0 or link_index >= len(cres):
            raise IndexError("link_index out of range")
        cres.pop(link_index)
    else:
        if link_index is None or link_index < 0 or link_index >= len(cres):
            raise IndexError("link_index out of range")
        if not isinstance(cres[link_index], dict):
            raise ValueError("invalid link")
        cres[link_index]["decision"] = "approved"
    kind = str(op.get("op") or "")
    if kind == "modify_control":
        op["after"] = doc
    else:
        op["document"] = doc
    db.update_staged_change_set(run_id=run_id, changeset_json=json.dumps(ops))
    return review_run_links(run_id)


def dashboard_payload() -> Dict[str, Any]:
    pipe = pipeline_snapshot()
    events = pipe.get("events") or []
    running = [e for e in events if e.get("status") == "started"]
    failed = [e for e in events if e.get("status") in ("error", "failed")]
    return {
        "running": running[:25],
        "failed": failed[:25],
        "import_runs": (pipe.get("import_runs") or [])[:15],
        "latest_strip": pipe.get("latest_strip"),
        "oie_unconsumed": (pipe.get("oie") or {}).get("unconsumed", 0),
        "agent": agent_status(),
    }


def config_payload() -> Dict[str, Any]:
    return {
        "config": config_catalog.present_config(os.environ),
        "writable": False,
        "restart_instructions": RESTART_INSTRUCTIONS,
    }


def config_put(updates: Dict[str, Optional[str]]) -> Dict[str, Any]:
    applied, rejected = config_catalog.apply_updates(os.environ, updates)
    return {
        "applied": applied,
        "rejected": rejected,
        "config": config_catalog.present_config(os.environ),
        "needs_restart": True,
        "note": RESTART_INSTRUCTIONS,
    }
