#!/usr/bin/env python3
"""Standalone import dashboard (outside application/).

Run:
  python scripts/import_dashboard.py --port 8765

Database panels use, in order: ``IMPORT_DASHBOARD_DATABASE_URL``,
``PROD_DATABASE_URL``, ``CRE_CACHE_FILE``, ``SQLALCHEMY_DATABASE_URI``, ``POSTGRES_URL``,
then import-all-style defaults: if ``RUN_COUNT`` > 1 → Postgres
``postgresql://cre:password@127.0.0.1:5432/cre`` (or ``POSTGRES_URL``), else repo
``standards_cache.sqlite``. ``scripts/import-all.sh`` exports ``CRE_CACHE_FILE`` and
``PROD_DATABASE_URL`` before starting the dashboard. Set ``CRE_IMPORT_DASHBOARD_SKIP_DB=1``
to disable SQL queries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Allow `python scripts/import_dashboard.py` without PYTHONPATH (import-all, manual runs).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from flask import Flask, Response, current_app, jsonify, redirect, request
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

from application.utils import redis


REPO_ROOT = _REPO_ROOT
WORKER_LOG_GLOB = "worker-*.log"
_IMPORT_QUEUES = ("high", "default", "low")


def _ga_queue_name() -> str:
    """Must match ``CRE_GA_QUEUE_NAME`` used when enqueueing GA jobs (see cre_main / web_main)."""
    return (os.environ.get("CRE_GA_QUEUE_NAME") or "ga").strip() or "ga"


def _monitored_queue_names() -> tuple[str, ...]:
    return _IMPORT_QUEUES + (_ga_queue_name(),)


def _fetch_rq_job(conn: Any, queue: Queue, job_id: str) -> Any:
    """Load a job by id without RQ 2.x Queue.fetch_job origin filtering (dashboard monitoring)."""
    try:
        return Job.fetch(job_id, connection=conn, serializer=queue.serializer)
    except NoSuchJobError:
        return None
# Only allow terminating IDs that look like Neo4j transaction ids (injection-safe).
_TXN_ID_RE = re.compile(r"^neo4j-transaction-[A-Za-z0-9_-]+$")


def _import_all_default_database_uri() -> str:
    """Match ``scripts/import-all.sh`` when no env is set (manual ``python scripts/import_dashboard.py``)."""
    try:
        run_count = int(os.environ.get("RUN_COUNT", "1") or "1")
    except ValueError:
        run_count = 1
    pg = os.environ.get(
        "POSTGRES_URL", "postgresql://cre:password@127.0.0.1:5432/cre"
    )
    if run_count > 1:
        return pg.strip()
    sqlite_path = REPO_ROOT / "standards_cache.sqlite"
    return str(sqlite_path.resolve())


def _dashboard_db_uri() -> str | None:
    for key in (
        "IMPORT_DASHBOARD_DATABASE_URL",
        "PROD_DATABASE_URL",
        "CRE_CACHE_FILE",
        "SQLALCHEMY_DATABASE_URI",
        "POSTGRES_URL",
    ):
        v = os.environ.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return _import_all_default_database_uri()


def _maybe_init_sqlalchemy(app: Flask) -> None:
    """Bind SQLAlchemy to this Flask app when a DB URL is available (same env as import workers)."""
    if os.environ.get("CRE_IMPORT_DASHBOARD_SKIP_DB", "0") == "1":
        return
    uri = _dashboard_db_uri()
    if not uri:
        return
    from application.config import CMDConfig
    from application import sqla as sqla_ext

    app.config.from_object(CMDConfig(db_uri=uri))
    sqla_ext.init_app(app)


def _dashboard_list_limit() -> int:
    return max(1, min(int(os.environ.get("CRE_IMPORT_DASHBOARD_MAX_LIST_ITEMS", "80")), 500))


def _distinct_node_names_for_ntype(session: Any, ntype: str) -> list[str]:
    from application.database.db import Node

    rows = (
        session.query(Node.name).filter(Node.ntype == ntype).distinct().all()
    )
    return sorted(
        {str(r[0]).strip() for r in rows if r[0] and str(r[0]).strip()}
    )


def _distinct_resource_names_all(session: Any) -> list[str]:
    """Every distinct node.name (matches ``SELECT DISTINCT name FROM node`` with non-empty names)."""
    from application.database.db import Node

    rows = (
        session.query(Node.name)
        .filter(Node.name.isnot(None))
        .filter(Node.name != "")
        .distinct()
        .all()
    )
    return sorted({str(r[0]) for r in rows if r[0]})


def _distinct_names_per_ntype(session: Any) -> dict[str | None, int]:
    """Count of distinct names grouped by ntype (None = NULL ntype rows)."""
    from application.database.db import Node

    from sqlalchemy import func

    rows = (
        session.query(Node.ntype, func.count(func.distinct(Node.name)))
        .group_by(Node.ntype)
        .all()
    )
    return {r[0]: int(r[1]) for r in rows}


def ga_coverage_from_standards_and_keys(
    standard_names: list[str], primary_cache_keys: list[str]
) -> dict[str, Any]:
    """Pure helper: expected directed GA pairs vs rows in gap_analysis_results (primary keys only)."""
    stds = sorted({str(s).strip() for s in standard_names if str(s).strip()})
    n = len(stds)
    expected: set[tuple[str, str]] = set()
    for a in stds:
        for b in stds:
            if a != b:
                expected.add((a, b))

    have: set[tuple[str, str]] = set()
    malformed = 0
    for k in primary_cache_keys:
        if " >> " not in k:
            malformed += 1
            continue
        a, b = k.split(" >> ", 1)
        have.add((a.strip(), b.strip()))

    covered = have & expected
    missing = expected - have
    stale = have - expected
    return {
        "standards_count": n,
        "directed_pairs_expected": n * (n - 1) if n else 0,
        "directed_pairs_with_result": len(have),
        "directed_pairs_covered": len(covered),
        "directed_pairs_missing": len(missing),
        "stale_pairs_in_storage": len(stale),
        "malformed_keys": malformed,
        "sample_missing": [f"{a} → {b}" for a, b in sorted(missing)[: _dashboard_list_limit()]],
        "sample_stale": [f"{a} → {b}" for a, b in sorted(stale)[: _dashboard_list_limit()]],
        "sample_covered": [
            f"{a} → {b}" for a, b in sorted(covered)[: min(20, _dashboard_list_limit())]
        ],
    }


def _db_resources_and_ga_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    """Query Postgres/SQLite for imported resource names and GA pair coverage."""
    err = {
        "ok": False,
        "error": "database not configured (set PROD_DATABASE_URL or CRE_CACHE_FILE for import-all)",
    }
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI"):
        return err, dict(err)

    try:
        from sqlalchemy import not_

        from application import sqla
        from application.database.db import GapAnalysisResults
        from application.defs import cre_defs as defs

        session = sqla.session
        lim = _dashboard_list_limit()

        standards = _distinct_node_names_for_ntype(session, defs.Credoctypes.Standard.value)
        tools = _distinct_node_names_for_ntype(session, defs.Credoctypes.Tool.value)
        codes = _distinct_node_names_for_ntype(session, defs.Credoctypes.Code.value)
        all_names = _distinct_resource_names_all(session)
        per_ntype = _distinct_names_per_ntype(session)

        resources_db: dict[str, Any] = {
            "ok": True,
            # Unfiltered: same as SELECT DISTINCT name FROM node (non-empty).
            "all_resource_names": all_names[:lim],
            "all_resource_names_total": len(all_names),
            "distinct_names_by_ntype": {
                str(k) if k is not None else "(null)": v for k, v in per_ntype.items()
            },
            "standards": standards[:lim],
            "standards_total": len(standards),
            "tools": tools[:lim],
            "tools_total": len(tools),
            "codes": codes[:lim],
            "codes_total": len(codes),
            "truncated": len(all_names) > lim
            or len(standards) > lim
            or len(tools) > lim
            or len(codes) > lim,
        }

        # Primary gap results only. Subresource rows use ``make_subresources_key``:
        # ``"{A} >> {B}->{neo_fragment}"``. Exclude those via `` >> … ->`` so we do
        # not drop legitimate primaries whose *left* standard name contains ``->``.
        rows = (
            session.query(GapAnalysisResults.cache_key)
            .filter(not_(GapAnalysisResults.cache_key.like("% >> %->%")))
            .all()
        )
        keys = [str(r[0]) for r in rows if r[0]]

        gap_analysis_db: dict[str, Any] = {
            "ok": True,
            "primary_cache_rows": len(keys),
        }
        gap_analysis_db.update(
            ga_coverage_from_standards_and_keys(standards, keys)
        )

        return resources_db, gap_analysis_db
    except Exception as exc:
        emsg = str(exc)
        fail = {"ok": False, "error": emsg}
        return fail, fail


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _seconds_since(ts: Any) -> int | None:
    if ts is None:
        return None
    if isinstance(ts, dt.datetime):
        ref = ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
        return int((_now_utc() - ref).total_seconds())
    return None


def _fmt_age(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "-"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _redis_connection_info(conn: Any) -> dict[str, Any]:
    """Best-effort host/port/db for debugging wrong-Redis issues (no passwords)."""
    try:
        pool = conn.connection_pool
        kw = getattr(pool, "connection_kwargs", {}) or {}
        return {
            "host": kw.get("host"),
            "port": kw.get("port"),
            "db": kw.get("db"),
        }
    except Exception:
        return {}


def _rq_meta(conn: Any) -> dict[str, Any]:
    """Which RQ queue / Redis the dashboard is reading (must match workers)."""
    qn = _ga_queue_name()
    try:
        q = Queue(name=qn, connection=conn)
        queued_len = len(q)
        started_n = len(StartedJobRegistry(qn, connection=conn).get_job_ids())
    except Exception as exc:
        return {
            "ga_queue_name": qn,
            "error": str(exc),
            "redis": _redis_connection_info(conn),
        }
    return {
        "ga_queue_name": qn,
        "ga_queue_queued_len": queued_len,
        "ga_started_len": started_n,
        "redis": _redis_connection_info(conn),
    }


def _queue_summary(conn) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for qn in _monitored_queue_names():
        q = Queue(name=qn, connection=conn)
        out[qn] = {
            "queued": len(q),
            "started": len(StartedJobRegistry(qn, connection=conn).get_job_ids()),
            "failed": len(FailedJobRegistry(qn, connection=conn).get_job_ids()),
            "deferred": len(DeferredJobRegistry(qn, connection=conn).get_job_ids()),
            "scheduled": len(ScheduledJobRegistry(qn, connection=conn).get_job_ids()),
            "finished": len(FinishedJobRegistry(qn, connection=conn).get_job_ids()),
        }
    return out


def _import_resources_summary(conn) -> dict[str, Any]:
    imported: set[str] = set()
    pending: set[str] = set()
    failed: set[str] = set()
    for qn in ("high", "default", "low"):
        q = Queue(name=qn, connection=conn)
        finished_ids = FinishedJobRegistry(qn, connection=conn).get_job_ids()
        pending_ids = (
            q.job_ids
            + StartedJobRegistry(qn, connection=conn).get_job_ids()
            + DeferredJobRegistry(qn, connection=conn).get_job_ids()
            + ScheduledJobRegistry(qn, connection=conn).get_job_ids()
        )
        failed_ids = FailedJobRegistry(qn, connection=conn).get_job_ids()

        for jid in finished_ids:
            job = _fetch_rq_job(conn, q, jid)
            if not job:
                continue
            desc = (job.description or "").strip()
            if desc.startswith("import:"):
                imported.add(desc.removeprefix("import:"))

        for jid in pending_ids:
            job = _fetch_rq_job(conn, q, jid)
            if not job:
                continue
            desc = (job.description or "").strip()
            if desc.startswith("import:"):
                pending.add(desc.removeprefix("import:"))

        for jid in failed_ids:
            job = _fetch_rq_job(conn, q, jid)
            if not job:
                continue
            desc = (job.description or "").strip()
            if desc.startswith("import:"):
                failed.add(desc.removeprefix("import:"))

    return {
        "imported_count": len(imported),
        "pending_count": len(pending),
        "failed_count": len(failed),
        "imported": sorted(imported),
        "pending": sorted(pending),
        "failed": sorted(failed),
    }


def _is_ga_gap_query(query: str) -> bool:
    """True if this looks like the gap-analysis allShortestPaths workload."""
    return "allshortestpaths" in (query or "").lower()


def _started_ga_pairs(pending: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Pairs (importing, peer) for GA jobs currently running (RQ started registry)."""
    out: set[tuple[str, str]] = set()
    for p in pending:
        if p.get("state") != "started":
            continue
        desc = (p.get("description") or "").strip()
        if "->" not in desc:
            continue
        a, b = desc.split("->", 1)
        out.add((a.strip(), b.strip()))
    return out


def _neo4j_params_map(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return dict(raw)  # type: ignore[arg-type]
    except Exception:
        return None


def neo4j_orphan_gap_transactions(
    neo_tx: list[dict[str, Any]], pending: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Mark GA-shaped Neo4j txs as orphans when no matching started RQ job owns them.

    A healthy long GA query runs under an RQ job in the *started* state with
    description ``importing->peer`` matching Neo4j parameters ``name1``/``name2``.
    If the worker crashed, the transaction may still run while the queue no longer
    has that job — or another pair may be running while this tx is a zombie.
    """
    started_pairs = _started_ga_pairs(pending)
    orphans: list[dict[str, Any]] = []
    for tx in neo_tx:
        if not _is_ga_gap_query(str(tx.get("query") or "")):
            continue
        params = _neo4j_params_map(tx.get("parameters"))
        n1 = n2 = None
        if params:
            n1 = params.get("name1")
            n2 = params.get("name2")
        if n1 is not None and n2 is not None:
            pair = (str(n1), str(n2))
            if pair not in started_pairs:
                row = dict(tx)
                row["orphan_reason"] = "no matching started GA job for name1/name2"
                orphans.append(row)
            continue
        # No parameters (or not yet bound): only flag orphan if nothing is started.
        # If a GA job is started, assume this tx belongs to it (avoid false orphans).
        if not started_pairs:
            row = dict(tx)
            row["orphan_reason"] = "GA-shaped query but no started GA jobs (likely crashed worker)"
            orphans.append(row)
    return orphans


def _neo4j_driver():
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None
    url = os.environ.get("NEO4J_URL", "bolt://neo4j:password@127.0.0.1:7687")
    m = re.match(r"^bolt://([^:]+):([^@]+)@(.+)$", url)
    if not m:
        return None
    user, password, hostport = m.group(1), m.group(2), m.group(3)
    uri = f"bolt://{hostport}"
    try:
        return GraphDatabase.driver(uri, auth=(user, password))
    except Exception:
        return None


def _neo4j_transactions() -> list[dict[str, str]]:
    """Best-effort current Neo4j query snapshot."""
    rows: list[dict[str, str]] = []
    driver = _neo4j_driver()
    if driver is None:
        return []
    limit = int(os.environ.get("CRE_IMPORT_DASHBOARD_NEO_TX_LIMIT", "25"))
    limit = max(1, min(limit, 100))
    try:
        with driver.session() as session:
            try:
                result = session.run(
                    "SHOW TRANSACTIONS "
                    "YIELD transactionId, elapsedTime, status, currentQuery, parameters "
                    "RETURN transactionId, elapsedTime, status, currentQuery, parameters "
                    "ORDER BY elapsedTime DESC LIMIT $lim",
                    {"lim": limit},
                )
                use_params = True
            except Exception:
                result = session.run(
                    "SHOW TRANSACTIONS "
                    "YIELD transactionId, elapsedTime, status, currentQuery "
                    "RETURN transactionId, elapsedTime, status, currentQuery "
                    "ORDER BY elapsedTime DESC LIMIT $lim",
                    {"lim": limit},
                )
                use_params = False
            for rec in result:
                pm = None
                if use_params:
                    try:
                        pm = _neo4j_params_map(rec["parameters"])
                    except (KeyError, TypeError):
                        pm = None
                rows.append(
                    {
                        "transaction_id": str(rec["transactionId"]),
                        "elapsed": str(rec["elapsedTime"]),
                        "status": str(rec["status"]),
                        "query": str(rec["currentQuery"]).strip().replace("\n", " "),
                        **(
                            {"parameters": pm}
                            if pm is not None
                            else {}
                        ),
                    }
                )
        driver.close()
    except Exception:
        try:
            driver.close()
        except Exception:
            pass
        return []
    return rows


def terminate_neo4j_transactions(transaction_ids: list[str]) -> dict[str, Any]:
    """Run TERMINATE TRANSACTIONS for validated ids. Returns ok/message."""
    safe: list[str] = []
    for raw in transaction_ids:
        tid = str(raw).strip()
        if _TXN_ID_RE.match(tid):
            safe.append(tid)
    if not safe:
        return {"ok": False, "error": "no valid transaction ids", "terminated": []}
    driver = _neo4j_driver()
    if driver is None:
        return {"ok": False, "error": "neo4j driver unavailable", "terminated": []}
    # Cypher TERMINATE TRANSACTIONS requires literal string list; ids are regex-validated.
    quoted = ", ".join(f"'{s}'" for s in safe)
    cypher = f"TERMINATE TRANSACTIONS {quoted}"
    try:
        with driver.session() as session:
            result = session.run(cypher)
            summary = result.consume()
        driver.close()
        return {
            "ok": True,
            "terminated": safe,
            "summary": str(getattr(summary, "counters", "") or summary),
        }
    except Exception as exc:
        try:
            driver.close()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "terminated": []}


def _owner_processes_present() -> dict[str, Any]:
    patterns = (
        "python cre.py --start_worker",
        "python cre.py --cache_file",
        "python cre.py --add --from_spreadsheet",
    )
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid,cmd"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return {"count": 0, "samples": []}
    lines = [ln.strip() for ln in output.splitlines() if "python cre.py" in ln]
    matches = [
        ln
        for ln in lines
        if any(p in ln for p in patterns)
    ]
    return {"count": len(matches), "samples": matches[:20]}


def _ga_pending_details(conn) -> list[dict[str, Any]]:
    qn = _ga_queue_name()
    q = Queue(name=qn, connection=conn)
    bucket_to_ids = {
        "queued": q.job_ids,
        "started": StartedJobRegistry(qn, connection=conn).get_job_ids(),
        "deferred": DeferredJobRegistry(qn, connection=conn).get_job_ids(),
        "scheduled": ScheduledJobRegistry(qn, connection=conn).get_job_ids(),
    }
    rows: list[dict[str, Any]] = []
    for bucket, ids in bucket_to_ids.items():
        for jid in ids:
            job = _fetch_rq_job(conn, q, jid)
            if not job:
                continue
            created_s = _seconds_since(getattr(job, "created_at", None))
            enqueued_s = _seconds_since(getattr(job, "enqueued_at", None))
            started_s = _seconds_since(getattr(job, "started_at", None))
            age_s = started_s if started_s is not None else enqueued_s
            if age_s is None:
                age_s = created_s
            rows.append(
                {
                    "job_id": jid,
                    "description": (job.description or "").strip(),
                    "state": bucket,
                    "state_backend": (
                        "rq:worker-running"
                        if bucket == "started"
                        else f"rq:{bucket}"
                    ),
                    "age_seconds": age_s,
                    "age_hms": _fmt_age(age_s),
                }
            )
    rows.sort(key=lambda r: (r.get("age_seconds") or 0), reverse=True)
    return rows


def _ga_finished_pairs_summary(conn) -> dict[str, Any]:
    """RQ finished registry for the GA queue (same jobs that log ``pair->pair finished``)."""
    qn = _ga_queue_name()
    q = Queue(name=qn, connection=conn)
    reg = FinishedJobRegistry(qn, connection=conn)
    ids = reg.get_job_ids()
    lim = max(
        1,
        min(
            int(os.environ.get("CRE_IMPORT_DASHBOARD_GA_FINISHED_SAMPLE", "40")),
            200,
        ),
    )
    tail = ids[-lim:] if len(ids) > lim else ids
    sample: list[dict[str, str]] = []
    for jid in reversed(tail):
        job = _fetch_rq_job(conn, q, jid)
        if not job:
            continue
        desc = (job.description or "").strip()
        if desc:
            sample.append(
                {
                    "job_id": jid,
                    "description": desc,
                    "log_line": f"{desc} finished",
                }
            )
    return {"finished_count": len(ids), "finished_sample": sample}


def _ga_failures_and_retries(conn) -> dict[str, Any]:
    qn = _ga_queue_name()
    q = Queue(name=qn, connection=conn)
    fr = FailedJobRegistry(qn, connection=conn).get_job_ids()
    failures: list[dict[str, str]] = []
    for jid in fr[:100]:
        job = _fetch_rq_job(conn, q, jid)
        if not job:
            continue
        retries = getattr(job, "meta", {}).get("retry_count")
        failures.append(
            {
                "job_id": jid,
                "description": (job.description or "").strip(),
                "status": str(job.get_status(refresh=False)),
                "retries_seen": str(retries) if retries is not None else "-",
            }
        )
    return {"failed_count": len(fr), "failed_jobs": failures}


def _tail_worker_logs(lines_per_file: int = 25) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in sorted(REPO_ROOT.glob(WORKER_LOG_GLOB)):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            out[path.name] = lines[-lines_per_file:]
        except Exception:
            out[path.name] = ["<unable to read log>"]
    return out


def _terminate_auth_ok() -> tuple[bool, str | None]:
    """Return (allowed, error_message)."""
    if os.environ.get("CRE_IMPORT_DASHBOARD_ALLOW_TERMINATE", "1") != "1":
        return False, "terminate disabled (set CRE_IMPORT_DASHBOARD_ALLOW_TERMINATE=1)"
    expected = os.environ.get("CRE_IMPORT_DASHBOARD_TERMINATE_TOKEN", "").strip()
    if not expected:
        return True, None
    got = (request.headers.get("X-Dashboard-Token") or "").strip()
    if not got and request.headers.get("Authorization", "").startswith("Bearer "):
        got = request.headers.get("Authorization", "")[7:].strip()
    if got != expected:
        return False, "missing or invalid X-Dashboard-Token"
    return True, None


def create_app() -> Flask:
    app = Flask(__name__)
    _maybe_init_sqlalchemy(app)

    @app.get("/health")
    def health():
        """Liveness check for scripts and curl (import-all verifies this returns 200)."""
        return jsonify({"ok": True})

    @app.get("/favicon.ico")
    def favicon():
        # Avoid noisy 404 in browser devtools; no icon bundled for this helper app.
        return Response(status=204)

    @app.get("/dashboard")
    @app.get("/import-dashboard")
    def dashboard_alias():
        # Common mistaken URLs — the UI lives at / only.
        return redirect("/", code=302)

    @app.get("/")
    def index():
        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>OpenCRE Import Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 16px; background: #101218; color: #e6e6e6; }
    h1, h2 { margin: 8px 0; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .card { background: #171a22; padding: 12px; border-radius: 8px; border: 1px solid #2b3140; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th, td { border-bottom: 1px solid #2b3140; text-align: left; padding: 6px; vertical-align: top; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; }
    .logs { max-height: 220px; overflow-y: auto; background: #0e1118; padding: 8px; border-radius: 6px; }
    .small { font-size: 12px; color: #b8c0d9; }
    button.btn-stop { background: #8b2e2e; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
    button.btn-stop:hover { background: #a83838; }
    #term_msg { color: #f0a0a0; min-height: 1.2em; }
  </style>
  <script>
    function esc(s) {
      if (s == null || s === undefined) return '';
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    function termHeaders() {
      const h = {'Content-Type': 'application/json'};
      const inp = document.getElementById('dash_token');
      const tok = (inp && inp.value.trim()) || localStorage.getItem('import_dashboard_terminate_token') || '';
      if (tok) {
        h['X-Dashboard-Token'] = tok;
        localStorage.setItem('import_dashboard_terminate_token', tok);
      }
      return h;
    }
    async function terminateNeo4jTxn(id, label) {
      const ok = confirm('Terminate Neo4j transaction ' + id + '? ' + (label || ''));
      if (!ok) return;
      const res = await fetch('/api/neo4j/terminate', {
        method: 'POST',
        headers: termHeaders(),
        body: JSON.stringify({ transaction_ids: [id] }),
      });
      const j = await res.json();
      const el = document.getElementById('term_msg');
      if (j.ok) {
        el.innerText = 'Terminated: ' + (j.terminated || []).join(', ');
      } else {
        el.innerText = 'Terminate failed: ' + (j.error || res.status);
      }
      await refresh();
    }
    async function refresh() {
      const status = await (await fetch('/api/status')).json();
      const logs = await (await fetch('/api/logs?lines=40')).json();

      document.getElementById('ts').innerText = new Date().toLocaleTimeString();
      const tokRow = document.getElementById('token_row');
      if (status.terminate_token_required) {
        tokRow.style.display = 'block';
        const inp = document.getElementById('dash_token');
        if (!inp.value && localStorage.getItem('import_dashboard_terminate_token')) {
          inp.value = localStorage.getItem('import_dashboard_terminate_token');
        }
        inp.onchange = () => localStorage.setItem('import_dashboard_terminate_token', inp.value);
      } else {
        tokRow.style.display = 'none';
      }
      document.getElementById('terminate_hint').innerText =
        status.allow_terminate ? '' : ' (termination disabled)';

      document.getElementById('queues').innerHTML = Object.entries(status.queues).map(([q, v]) =>
        `<tr><td>${q}</td><td>${v.queued}</td><td>${v.started}</td><td>${v.failed}</td><td>${v.deferred}</td><td>${v.scheduled}</td><td>${v.finished}</td></tr>`
      ).join('');

      const rdb = status.resources_db || {};
      let dbHtml = '';
      if (rdb.ok) {
        const byNt = rdb.distinct_names_by_ntype || {};
        const byNtStr = Object.entries(byNt).map(([k, v]) => `${esc(k)}:${v}`).join(' · ') || '—';
        dbHtml =
          `<div><b>Distinct node.name (any ntype)</b>: ${rdb.all_resource_names_total} — like <code>SELECT DISTINCT name FROM node</code></div>` +
          `<div class="small" style="margin-top:6px;">Sample: ${esc((rdb.all_resource_names || []).join(', ') || '—')}${rdb.truncated ? ' …' : ''}</div>` +
          `<div class="small" style="margin-top:6px;"><b>Distinct names per ntype</b>: ${byNtStr}</div>` +
          `<div style="margin-top:10px;"><b>By type (Standard / Tool / Code only)</b></div>` +
          `<div><b>Standards</b> ${rdb.standards_total} | <b>Tools</b> ${rdb.tools_total} | <b>Code</b> ${rdb.codes_total}</div>` +
          `<div class="small" style="margin-top:6px;"><b>Standard names</b> (sample): ${esc((rdb.standards || []).join(', ') || '—')}</div>` +
          `<div class="small"><b>Tool names</b> (sample): ${esc((rdb.tools || []).join(', ') || '—')}</div>` +
          `<div class="small"><b>Code names</b> (sample): ${esc((rdb.codes || []).join(', ') || '—')}</div>`;
      } else {
        dbHtml = `<div class="small">${esc(rdb.error || 'unavailable')}</div>`;
      }
      document.getElementById('resources_db').innerHTML = dbHtml;

      const imp = status.resources_rq || status.resources || {};
      document.getElementById('resources_rq').innerHTML =
        `<div class="small" style="margin-bottom:6px;">Only jobs whose description starts with <code>import:</code> on queues <code>high</code>/<code>default</code>/<code>low</code> (spreadsheet / register batches). <b>Gap-analysis pair jobs</b> (<code>A-&gt;B</code>) are on the <code>ga</code> queue — see below.</div>` +
        `<div>Finished import jobs: <b>${imp.imported_count}</b> | Pending: <b>${imp.pending_count}</b> | Failed: <b>${imp.failed_count}</b></div>` +
        `<div class="small">Imported (labels): ${esc((imp.imported || []).join(', ') || '-')}</div>` +
        `<div class="small">Pending: ${esc((imp.pending || []).join(', ') || '-')}</div>` +
        `<div class="small">Failed: ${esc((imp.failed || []).join(', ') || '-')}</div>`;

      const gdb = status.gap_analysis_db || {};
      let gaDbHtml = '';
      if (gdb.ok) {
        gaDbHtml =
          `<div>Standards in DB: <b>${gdb.standards_count}</b> · Directed pairs (all ordered A≠B): <b>${gdb.directed_pairs_expected}</b></div>` +
          `<div style="margin-top:6px;">With GA row in DB: <b>${gdb.directed_pairs_with_result}</b> · Covered vs expected: <b>${gdb.directed_pairs_covered}</b> · <span style="color:#f0c674">Missing: <b>${gdb.directed_pairs_missing}</b></span> · Stale (not in current standard set): <b>${gdb.stale_pairs_in_storage}</b></div>` +
          `<div class="small">Primary cache keys scanned: ${gdb.primary_cache_rows} · Malformed keys: ${gdb.malformed_keys || 0}</div>` +
          `<div class="small" style="margin-top:8px;"><b>Sample missing pairs</b> (estimate remaining work)</div>` +
          `<div class="logs mono" style="max-height:120px;">${esc((gdb.sample_missing || []).join('\\n') || '—')}</div>` +
          `<div class="small" style="margin-top:8px;"><b>Sample covered</b></div>` +
          `<div class="logs mono" style="max-height:80px;">${esc((gdb.sample_covered || []).join('\\n') || '—')}</div>`;
      } else {
        gaDbHtml = `<div class="small">${esc(gdb.error || 'unavailable')}</div>`;
      }
      document.getElementById('ga_db').innerHTML = gaDbHtml;

      const ga = status.ga;
      const rqm = status.rq_meta || {};
      const rparts = [];
      if (rqm.ga_queue_name) rparts.push(`RQ queue <code>${esc(rqm.ga_queue_name)}</code>`);
      if (rqm.redis && rqm.redis.host != null) {
        rparts.push(`Redis ${esc(String(rqm.redis.host))}:${esc(String(rqm.redis.port ?? ''))} db=${esc(String(rqm.redis.db ?? ''))}`);
      }
      if (rqm.ga_queue_queued_len != null) rparts.push(`queued depth <b>${rqm.ga_queue_queued_len}</b>`);
      if (rqm.ga_started_len != null) rparts.push(`started <b>${rqm.ga_started_len}</b>`);
      if (rqm.error) rparts.push(`<span style="color:#f0a0a0">${esc(rqm.error)}</span>`);
      const fin = ga.finished_pairs || {};
      const finSample = (fin.finished_sample || []).map((x) => esc(x.log_line || x.description || '')).join('<br/>');
      document.getElementById('ga_counts').innerHTML =
        `<div class="small" style="margin-bottom:6px;">${rparts.join(' · ') || '—'}</div>` +
        `<div class="small">The <b>RQ Queues</b> table row for <code>${esc(rqm.ga_queue_name || 'ga')}</code> shows <b>finished</b> = GA pairs completed (kept in Redis). Below: active jobs + recent finished samples (same text as <code>application.utils.redis</code> worker logs).</div>` +
        `<div style="margin-top:8px;">In-flight GA jobs (queued+started+deferred+scheduled): <b>${ga.pending_count}</b> | Failed GA jobs: <b>${ga.failures.failed_count}</b> | Finished GA jobs in registry: <b>${fin.finished_count != null ? fin.finished_count : '?'}</b></div>` +
        `<div class="small" style="margin-top:8px;"><b>Recent finished GA pairs</b> (newest first)</div>` +
        `<div class="logs mono" style="max-height:160px;margin-top:4px;">${finSample || '—'}</div>`;
      document.getElementById('ga_pending').innerHTML = ga.pending.map(r =>
        `<tr><td>${r.description}</td><td>${r.state}</td><td>${r.state_backend}</td><td>${r.age_hms}</td><td class="mono">${r.job_id}</td></tr>`
      ).join('');
      document.getElementById('ga_failed').innerHTML = ga.failures.failed_jobs.map(r =>
        `<tr><td>${r.description}</td><td>${r.retries_seen}</td><td class="mono">${r.job_id}</td></tr>`
      ).join('');

      const stopBtn = (t, kind) => {
        if (!status.allow_terminate) return '';
        const id = (t.transaction_id || '').replace(/'/g, "\\\\'");
        return `<button type="button" class="btn-stop" onclick="terminateNeo4jTxn('${id}', '${kind}')">Stop</button>`;
      };
      document.getElementById('neo').innerHTML = (status.neo4j_transactions || []).map(t =>
        `<tr><td class="mono">${t.transaction_id}</td><td>${t.elapsed}</td><td>${t.status}</td><td class="mono">${t.query}</td><td>${stopBtn(t, 'active')}</td></tr>`
      ).join('') || '<tr><td colspan="5">No active transactions (or unavailable)</td></tr>';
      document.getElementById('neo_orphans').innerHTML = (status.neo4j_orphans || []).map(t =>
        `<tr><td class="mono">${t.transaction_id}</td><td>${t.elapsed}</td><td>${t.status}</td><td class="mono">${t.query}</td><td class="small">${t.orphan_reason || ''}</td><td>${stopBtn(t, 'orphan')}</td></tr>`
      ).join('') || '<tr><td colspan="6">No orphan transactions detected</td></tr>';
      document.getElementById('owners').innerText =
        `Owner processes: ${status.owner_processes.count}`;

      const logsRoot = document.getElementById('logs');
      logsRoot.innerHTML = '';
      Object.entries(logs.worker_logs).forEach(([name, lines]) => {
        const div = document.createElement('div');
        div.className = 'card';
        div.style.flex = '1 1 45%';
        div.innerHTML = `<h3>${name}</h3><div class="logs mono">${(lines || []).join('\\n')}</div>`;
        logsRoot.appendChild(div);
      });
    }

    window.addEventListener('DOMContentLoaded', async () => {
      await refresh();
      setInterval(refresh, 5000);
    });
  </script>
</head>
<body>
  <h1>OpenCRE Import Dashboard</h1>
  <div class="small">Updated: <span id="ts">-</span> (auto refresh 5s)<span id="terminate_hint"></span></div>
  <div id="token_row" class="small" style="display:none;margin:8px 0;">
    <label>Termination token (matches CRE_IMPORT_DASHBOARD_TERMINATE_TOKEN):
      <input id="dash_token" type="password" size="40" placeholder="paste once; stored in localStorage" />
    </label>
  </div>
  <div id="term_msg" class="small"></div>

  <div class="row">
    <div class="card" style="flex: 1 1 420px;">
      <h2>Resources (database)</h2>
      <div class="small">Top section = all distinct <code>node.name</code> values (any <code>ntype</code>). Rows below filter <code>ntype</code> to Standard / Tool / Code only (CWE, PCI DSS, etc. are Standards).</div>
      <div id="resources_db" style="margin-top:8px;"></div>
      <h3 class="small" style="margin:12px 0 4px;">RQ <code>import:…</code> jobs only (not GA pairs)</h3>
      <div id="resources_rq" class="small"></div>
    </div>
    <div class="card" style="flex: 2 1 520px;">
      <h2>RQ Queues</h2>
      <div class="small">The <code>ga</code> row’s <b>finished</b> column counts completed gap-analysis pair jobs (same queue as <code>CWE-&gt;PCI DSS</code>).</div>
      <table>
        <thead><tr><th>queue</th><th>queued</th><th>started</th><th>failed</th><th>deferred</th><th>scheduled</th><th>finished</th></tr></thead>
        <tbody id="queues"></tbody>
      </table>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex: 1 1 100%; min-width: 280px;">
      <h2>Gap analysis pair coverage (database)</h2>
      <div class="small">Directed pairs use the same cache key as workers: <code>make_resources_key([A,B])</code> → <code>A &gt;&gt; B</code>. &quot;Missing&quot; = expected ordered pairs among current standards minus rows in <code>gap_analysis_results</code> (primary keys only).</div>
      <div id="ga_db" style="margin-top:8px;"></div>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex: 1 1 420px;">
      <h2>Gap analysis (RQ)</h2>
      <div class="small">Uses <code>CRE_GA_QUEUE_NAME</code> (default <code>ga</code>) and <code>REDIS_URL</code>. <b>In-flight count</b> is only non-finished jobs; when pairs complete, they move to the <b>finished</b> registry — use the sample below or the RQ table. <b>“2 imported”</b> in the box above refers to <code>import:</code> spreadsheet jobs, not GA.</div>
      <div id="ga_counts"></div>
      <table>
        <thead><tr><th>pair</th><th>state</th><th>backend</th><th>age</th><th>job id</th></tr></thead>
        <tbody id="ga_pending"></tbody>
      </table>
    </div>
    <div class="card" style="flex: 1 1 360px;">
      <h2>Failures / Retries</h2>
      <table>
        <thead><tr><th>pair</th><th>retries seen</th><th>job id</th></tr></thead>
        <tbody id="ga_failed"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>Neo4j Active Transactions</h2>
    <div id="owners" class="small"></div>
    <table>
      <thead><tr><th>transaction id</th><th>elapsed</th><th>status</th><th>query</th><th>action</th></tr></thead>
      <tbody id="neo"></tbody>
    </table>
  </div>

  <div class="card">
    <h2>Orphan GA Neo4j Transactions</h2>
    <div class="small">Gap-analysis (allShortestPaths) queries with no matching <b>started</b> GA job, or no started GA jobs at all when parameters are unavailable — typical after a worker crash. Safe to terminate if the DB is stuck.</div>
    <table>
      <thead><tr><th>transaction id</th><th>elapsed</th><th>status</th><th>query</th><th>reason</th><th>action</th></tr></thead>
      <tbody id="neo_orphans"></tbody>
    </table>
  </div>

  <h2>Worker Logs (local)</h2>
  <div class="row" id="logs"></div>
</body>
</html>
"""

    @app.get("/api/status")
    def api_status():
        conn = redis.connect()
        queues = _queue_summary(conn)
        resources_rq = _import_resources_summary(conn)
        resources_db, gap_analysis_db = _db_resources_and_ga_snapshot()
        pending = _ga_pending_details(conn)
        failures = _ga_failures_and_retries(conn)
        ga_finished = _ga_finished_pairs_summary(conn)
        neo_tx = _neo4j_transactions()
        owner_processes = _owner_processes_present()
        orphans = neo4j_orphan_gap_transactions(neo_tx, pending)
        return jsonify(
            {
                "timestamp": _now_utc().isoformat(),
                "queues": queues,
                "rq_meta": _rq_meta(conn),
                "resources": resources_rq,
                "resources_rq": resources_rq,
                "resources_db": resources_db,
                "gap_analysis_db": gap_analysis_db,
                "ga": {
                    "pending_count": len(pending),
                    "pending": pending,
                    "failures": failures,
                    "finished_pairs": ga_finished,
                },
                "neo4j_transactions": neo_tx,
                "neo4j_orphans": orphans,
                "owner_processes": owner_processes,
                "allow_terminate": os.environ.get(
                    "CRE_IMPORT_DASHBOARD_ALLOW_TERMINATE", "1"
                )
                == "1",
                "terminate_token_required": bool(
                    os.environ.get("CRE_IMPORT_DASHBOARD_TERMINATE_TOKEN", "").strip()
                ),
            }
        )

    @app.post("/api/neo4j/terminate")
    def api_neo4j_terminate():
        allowed, err = _terminate_auth_ok()
        if not allowed:
            return jsonify({"ok": False, "error": err}), 403
        payload = request.get_json(force=True, silent=True) or {}
        ids = payload.get("transaction_ids")
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list):
            return jsonify({"ok": False, "error": "transaction_ids must be a list"}), 400
        out = terminate_neo4j_transactions(ids)
        code = 200 if out.get("ok") else 400
        return jsonify(out), code

    @app.get("/api/logs")
    def api_logs():
        lines = int(request.args.get("lines", "25"))
        lines = max(1, min(lines, 500))
        return jsonify(
            {
                "timestamp": _now_utc().isoformat(),
                "worker_logs": _tail_worker_logs(lines_per_file=lines),
            }
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    app = create_app()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
