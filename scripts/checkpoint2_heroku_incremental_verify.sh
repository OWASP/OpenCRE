#!/usr/bin/env bash

set -euo pipefail

# Tiny helper for Checkpoint 2 incremental verification.
# It exports upstream cache tables from Heroku Postgres, imports them into a local sqlite DB,
# deletes every Nth row through the Python verifier, and confirms only missing cache rows refill.
#
# Required env:
#   HEROKU_APP            e.g. "opencre-prod"
#   LOCAL_SQLITE_DB       e.g. "/home/sg/Projects/OpenCRE/standards_cache.sqlite"
#
# Optional env:
#   EVERY_N               default: 10
#   PYTHON_BIN            default: "python3"
#   EXPORT_DIR            default: "/tmp/opencre_checkpoint2_exports"
#   SKIP_GA_VERIFY        "1" to skip GA cache verification
#   SKIP_VERIFY           "1" to only import caches (no checkpoint verification run)
#   START_GA_SERVICES     default: "1" (start Neo4j + Redis + RQ workers before verify)
#   GA_WORKER_COUNT       default: "2" (number of workers to start if needed)
#   SKIP_DOWNLOAD_IF_CACHED default: "1" (reuse existing CSV exports if present)
#   REFRESH_EMBEDDINGS_EXPORT "1" to force re-download embeddings CSV
#   REFRESH_GA_EXPORT     "1" to force re-download GA CSV
#
# Usage:
#   HEROKU_APP=... LOCAL_SQLITE_DB=... scripts/checkpoint2_heroku_incremental_verify.sh

if ! command -v heroku >/dev/null 2>&1; then
  echo "heroku CLI not found in PATH" >&2
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 not found in PATH" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found in PATH (install postgresql client tools)" >&2
  exit 1
fi

HEROKU_APP="${HEROKU_APP:-}"
LOCAL_SQLITE_DB="${LOCAL_SQLITE_DB:-}"
EVERY_N="${EVERY_N:-10}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXPORT_DIR="${EXPORT_DIR:-/tmp/opencre_checkpoint2_exports}"
SKIP_DOWNLOAD_IF_CACHED="${SKIP_DOWNLOAD_IF_CACHED:-1}"
REFRESH_EMBEDDINGS_EXPORT="${REFRESH_EMBEDDINGS_EXPORT:-0}"
REFRESH_GA_EXPORT="${REFRESH_GA_EXPORT:-0}"
START_GA_SERVICES="${START_GA_SERVICES:-1}"
GA_WORKER_COUNT="${GA_WORKER_COUNT:-2}"

if [[ -z "${PYTHON_BIN:-}" || "${PYTHON_BIN}" == "python3" ]]; then
  if [[ -x "./venv/bin/python" ]]; then
    PYTHON_BIN="./venv/bin/python"
  fi
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "PYTHON_BIN executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ -z "${HEROKU_APP}" ]]; then
  echo "HEROKU_APP is required" >&2
  exit 1
fi

if [[ -z "${LOCAL_SQLITE_DB}" ]]; then
  echo "LOCAL_SQLITE_DB is required" >&2
  exit 1
fi

mkdir -p "${EXPORT_DIR}"
EMBED_CSV="${EXPORT_DIR}/embeddings.csv"
GA_CSV="${EXPORT_DIR}/gap_analysis_results.csv"
DATABASE_URL="$(heroku config:get DATABASE_URL -a "${HEROKU_APP}")"

if [[ -z "${DATABASE_URL}" ]]; then
  echo "Could not fetch DATABASE_URL from Heroku app ${HEROKU_APP}" >&2
  exit 1
fi

EXPECTED_EMBED_HEADER="doc_type,cre_id,node_id,embeddings,embeddings_url,embeddings_content,cre_external_id,cre_name,node_ntype,node_name,node_section_id,node_section,node_subsection,node_version,node_link"
EXPECTED_GA_HEADER="cache_key,ga_object"

ensure_embeddings_export() {
  local use_cache="0"
  if [[ "${SKIP_DOWNLOAD_IF_CACHED}" == "1" && "${REFRESH_EMBEDDINGS_EXPORT}" != "1" && -s "${EMBED_CSV}" ]]; then
    local header
    header="$(sed -n '1p' "${EMBED_CSV}")"
    if [[ "${header}" == "${EXPECTED_EMBED_HEADER}" ]]; then
      use_cache="1"
    else
      echo "Cached embeddings CSV header invalid, re-exporting: ${EMBED_CSV}"
    fi
  fi
  if [[ "${use_cache}" == "1" ]]; then
    echo "Using cached embeddings export: ${EMBED_CSV}"
  else
    echo "Exporting embeddings table from Heroku app: ${HEROKU_APP}"
    psql "${DATABASE_URL}" -c "\copy (
      select
        e.doc_type,
        e.cre_id,
        e.node_id,
        e.embeddings,
        e.embeddings_url,
        e.embeddings_content,
        c.external_id as cre_external_id,
        c.name as cre_name,
        n.ntype as node_ntype,
        n.name as node_name,
        n.section_id as node_section_id,
        n.section as node_section,
        n.subsection as node_subsection,
        n.version as node_version,
        n.link as node_link
      from embeddings e
      left join cre c on e.cre_id = c.id
      left join node n on e.node_id = n.id
    ) to stdout with csv header" > "${EMBED_CSV}"
  fi
}

ensure_ga_export() {
  local use_cache="0"
  if [[ "${SKIP_DOWNLOAD_IF_CACHED}" == "1" && "${REFRESH_GA_EXPORT}" != "1" && -s "${GA_CSV}" ]]; then
    local header
    header="$(sed -n '1p' "${GA_CSV}")"
    if [[ "${header}" == "${EXPECTED_GA_HEADER}" ]]; then
      use_cache="1"
    else
      echo "Cached GA CSV header invalid, re-exporting: ${GA_CSV}"
    fi
  fi
  if [[ "${use_cache}" == "1" ]]; then
    echo "Using cached gap-analysis export: ${GA_CSV}"
  else
    echo "Exporting gap_analysis_results table from Heroku app: ${HEROKU_APP}"
    psql "${DATABASE_URL}" -c "\copy (select cache_key, ga_object from gap_analysis_results) to stdout with csv header" > "${GA_CSV}"
  fi
}

ensure_embeddings_export
ensure_ga_export

echo "Ensuring local sqlite schema exists: ${LOCAL_SQLITE_DB}"
OPENCRE_IMPORT_CORE=0 "${PYTHON_BIN}" - <<PY
from application.cmd import cre_main
from application import sqla
import sqlite3
db_path = "${LOCAL_SQLITE_DB}"
cre_main.db_connect(path=db_path)
# Repair potentially malformed tables from previous failed sqlite import runs.
conn = sqlite3.connect(db_path)
conn.execute("DROP TABLE IF EXISTS embeddings")
conn.execute("DROP TABLE IF EXISTS gap_analysis_results")
conn.commit()
conn.close()
sqla.create_all()
print(f"Schema ready at {db_path}")
PY

echo "Importing exported cache tables into local sqlite DB: ${LOCAL_SQLITE_DB}"
"${PYTHON_BIN}" - <<PY
import csv
import sqlite3
import sys

db_path = "${LOCAL_SQLITE_DB}"
embed_csv = "${EMBED_CSV}"
ga_csv = "${GA_CSV}"

expected_embed_header = [
    "doc_type",
    "cre_id",
    "node_id",
    "embeddings",
    "embeddings_url",
    "embeddings_content",
    "cre_external_id",
    "cre_name",
    "node_ntype",
    "node_name",
    "node_section_id",
    "node_section",
    "node_subsection",
    "node_version",
    "node_link",
]
expected_ga_header = ["cache_key", "ga_object"]

# Heroku exports can contain very large JSON/vector payloads.
csv.field_size_limit(sys.maxsize)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS embeddings (
        embeddings VARCHAR NOT NULL,
        doc_type VARCHAR NOT NULL,
        cre_id VARCHAR NOT NULL,
        node_id VARCHAR NOT NULL,
        embeddings_url VARCHAR DEFAULT '',
        embeddings_content VARCHAR DEFAULT '',
        PRIMARY KEY (embeddings, doc_type, cre_id, node_id)
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS gap_analysis_results (
        cache_key VARCHAR PRIMARY KEY,
        ga_object VARCHAR
    )
    """
)

cur.execute("DELETE FROM embeddings")
cur.execute("DELETE FROM gap_analysis_results")

def norm(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None

def resolve_local_cre_id(external_id):
    ext = norm(external_id)
    if not ext:
        return None
    row = cur.execute(
        "SELECT id FROM cre WHERE external_id = ? LIMIT 1",
        (ext,),
    ).fetchone()
    return row[0] if row else None

def resolve_local_node_id(row):
    ntype = norm(row.get("node_ntype"))
    name = norm(row.get("node_name"))
    section_id = norm(row.get("node_section_id"))
    section = norm(row.get("node_section"))
    subsection = norm(row.get("node_subsection"))
    version = norm(row.get("node_version"))
    link = norm(row.get("node_link"))
    if not ntype or not name:
        return None, "missing_node_identity_fields"
    hit = cur.execute(
        """
        SELECT id
        FROM node
        WHERE ntype = ?
          AND name = ?
          AND ((section_id IS NULL AND ? IS NULL) OR section_id = ?)
          AND ((section IS NULL AND ? IS NULL) OR section = ?)
          AND ((subsection IS NULL AND ? IS NULL) OR subsection = ?)
          AND ((version IS NULL AND ? IS NULL) OR version = ?)
          AND ((link IS NULL AND ? IS NULL) OR link = ?)
        LIMIT 1
        """,
        (
            ntype,
            name,
            section_id,
            section_id,
            section,
            section,
            subsection,
            subsection,
            version,
            version,
            link,
            link,
        ),
    ).fetchone()
    if hit:
        return hit[0], "strict"

    # Fallback 1: ntype + name + section_id (most stable for standards)
    if section_id:
        rows = cur.execute(
            """
            SELECT id FROM node
            WHERE ntype = ? AND name = ? AND section_id = ?
            """,
            (ntype, name, section_id),
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0], "fallback_section_id"
        if len(rows) > 1:
            return None, "ambiguous_section_id"

    # Fallback 2: ntype + name + section
    if section:
        rows = cur.execute(
            """
            SELECT id FROM node
            WHERE ntype = ? AND name = ? AND section = ?
            """,
            (ntype, name, section),
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0], "fallback_section"
        if len(rows) > 1:
            return None, "ambiguous_section"

    # Fallback 3: unique ntype + name only.
    rows = cur.execute(
        """
        SELECT id FROM node
        WHERE ntype = ? AND name = ?
        """,
        (ntype, name),
    ).fetchall()
    if len(rows) == 1:
        return rows[0][0], "fallback_name_only"
    if len(rows) > 1:
        return None, "ambiguous_name_only"
    return None, "no_node_match"

with open(embed_csv, "r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    if reader.fieldnames != expected_embed_header:
        raise RuntimeError(
            f"Embeddings CSV header mismatch. Expected {expected_embed_header}, got {reader.fieldnames}"
        )
    batch = []
    mapped = 0
    skipped = 0
    mapped_by_strategy = {}
    skipped_by_reason = {}
    skipped_examples = []
    for row in reader:
        doc_type = row.get("doc_type", "") or ""
        local_cre_id = None
        local_node_id = None
        reason = ""
        if doc_type == "CRE":
            local_cre_id = resolve_local_cre_id(row.get("cre_external_id"))
            if local_cre_id:
                reason = "cre_external_id"
            else:
                reason = "no_cre_external_id_match"
        else:
            local_node_id, reason = resolve_local_node_id(row)
        if not local_cre_id and not local_node_id:
            skipped += 1
            skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
            if len(skipped_examples) < 30:
                skipped_examples.append(
                    {
                        "doc_type": doc_type,
                        "reason": reason,
                        "cre_external_id": row.get("cre_external_id", ""),
                        "node_ntype": row.get("node_ntype", ""),
                        "node_name": row.get("node_name", ""),
                        "node_section_id": row.get("node_section_id", ""),
                        "node_section": row.get("node_section", ""),
                        "embeddings_url": row.get("embeddings_url", ""),
                    }
                )
            continue
        batch.append(
            (
                row.get("embeddings", "") or "",
                doc_type,
                local_cre_id or "",
                local_node_id or "",
                row.get("embeddings_url", "") or "",
                row.get("embeddings_content", "") or "",
            )
        )
        mapped += 1
        mapped_by_strategy[reason] = mapped_by_strategy.get(reason, 0) + 1
        if len(batch) >= 1000:
            cur.executemany(
                """
                INSERT INTO embeddings
                (embeddings, doc_type, cre_id, node_id, embeddings_url, embeddings_content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            batch = []
    if batch:
        cur.executemany(
            """
            INSERT INTO embeddings
            (embeddings, doc_type, cre_id, node_id, embeddings_url, embeddings_content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
    print(f"Embeddings remap: mapped={mapped}, skipped_unmapped={skipped}")
    print(f"Embeddings remap strategies: {mapped_by_strategy}")
    print(f"Embeddings skipped reasons: {skipped_by_reason}")
    if skipped_examples:
        print("Embeddings skipped examples (up to 30):")
        for ex in skipped_examples:
            print(ex)

with open(ga_csv, "r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    if reader.fieldnames != expected_ga_header:
        raise RuntimeError(
            f"GA CSV header mismatch. Expected {expected_ga_header}, got {reader.fieldnames}"
        )
    batch = []
    for row in reader:
        batch.append((row.get("cache_key", "") or "", row.get("ga_object", "") or ""))
        if len(batch) >= 1000:
            cur.executemany(
                "INSERT INTO gap_analysis_results (cache_key, ga_object) VALUES (?, ?)",
                batch,
            )
            batch = []
    if batch:
        cur.executemany(
            "INSERT INTO gap_analysis_results (cache_key, ga_object) VALUES (?, ?)",
            batch,
        )

conn.commit()
conn.close()
print("CSV import complete.")
PY

echo "Imported row counts:"
sqlite3 "${LOCAL_SQLITE_DB}" "SELECT COUNT(*) AS embeddings_count FROM embeddings;"
sqlite3 "${LOCAL_SQLITE_DB}" "SELECT COUNT(*) AS gap_analysis_count FROM gap_analysis_results;"

if [[ "${SKIP_VERIFY:-0}" == "1" ]]; then
  echo "SKIP_VERIFY=1 set; skipping checkpoint verification run."
  exit 0
fi

WORKER_PIDS=""
cleanup_workers() {
  if [[ -n "${WORKER_PIDS}" ]]; then
    echo "Stopping temporary RQ workers: ${WORKER_PIDS}"
    kill ${WORKER_PIDS} 2>/dev/null || true
  fi
}
trap cleanup_workers EXIT

if [[ "${START_GA_SERVICES}" == "1" ]]; then
  if ! command -v make >/dev/null 2>&1; then
    echo "make not found; cannot auto-start Neo4j/Redis/workers" >&2
    exit 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found; cannot auto-start Neo4j/Redis/workers" >&2
    exit 1
  fi

  echo "Starting GA infra containers (Neo4j + Redis)..."
  make docker-neo4j
  make docker-redis

  existing_workers="$(pgrep -f "cre.py --start_worker" || true)"
  if [[ -n "${existing_workers}" ]]; then
    echo "Detected existing RQ worker(s), not starting duplicates: ${existing_workers}"
  else
    echo "Starting ${GA_WORKER_COUNT} temporary RQ worker(s)..."
    for _i in $(seq 1 "${GA_WORKER_COUNT}"); do
      ( make start-worker >/tmp/opencre-checkpoint2-worker-"${_i}".log 2>&1 ) &
      WORKER_PIDS="${WORKER_PIDS} $!"
    done
    # Give workers time to boot and connect.
    sleep 3
  fi

  # Health checks: Redis + Neo4j + at least one worker.
  echo "Waiting for Redis and Neo4j readiness..."
  REDIS_READY=0
  NEO4J_READY=0
  WORKER_READY=0
  for _attempt in $(seq 1 30); do
    if docker exec cre-redis-stack redis-cli ping >/dev/null 2>&1; then
      REDIS_READY=1
    fi
    # Prefer actual DB handshake over process/port checks.
    if docker exec cre-neo4j cypher-shell -u neo4j -p password "RETURN 1;" >/dev/null 2>&1; then
      NEO4J_READY=1
    else
      # Fallback: host bolt port open check.
      if command -v python3 >/dev/null 2>&1; then
        if python3 - <<'PY' >/dev/null 2>&1
import socket
s = socket.socket()
s.settimeout(1.0)
try:
    s.connect(("127.0.0.1", 7687))
    print("ok")
finally:
    s.close()
PY
        then
          NEO4J_READY=1
        fi
      fi
    fi
    if pgrep -f "cre.py --start_worker" >/dev/null 2>&1; then
      WORKER_READY=1
    fi
    if [[ "${REDIS_READY}" == "1" && "${NEO4J_READY}" == "1" && "${WORKER_READY}" == "1" ]]; then
      break
    fi
    sleep 2
  done

  if [[ "${REDIS_READY}" != "1" ]]; then
    echo "Redis did not become ready in time." >&2
    exit 1
  fi
  if [[ "${NEO4J_READY}" != "1" ]]; then
    echo "Neo4j logs (last 80 lines):"
    docker logs --tail 80 cre-neo4j 2>/dev/null || true
    echo "Neo4j did not become ready in time." >&2
    exit 1
  fi
  if [[ "${WORKER_READY}" != "1" ]]; then
    echo "RQ worker did not become ready in time." >&2
    exit 1
  fi
  echo "GA infra readiness checks passed."
fi

echo "Running Checkpoint 2 incremental verification (every ${EVERY_N}th row delete/refill)"
GA_FLAG=""
if [[ "${SKIP_GA_VERIFY:-0}" == "1" ]]; then
  GA_FLAG="--skip-gap-analysis-verification"
fi

"${PYTHON_BIN}" scripts/tmp_upstream_structural_content_diff.py \
  --db "${LOCAL_SQLITE_DB}" \
  --verify-checkpoint-2-incremental \
  --delete-every-n "${EVERY_N}" \
  ${GA_FLAG}

echo "Checkpoint 2 verification completed."
