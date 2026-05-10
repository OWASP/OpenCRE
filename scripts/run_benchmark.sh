#!/bin/bash
set -ex

echo "=== Setting up Benchmark ==="

if [ -f .env ]; then
    echo "Loading and exporting variables from .env..."
    set -a
    source .env
    set +a
fi

# Work in a temporary directory or specific benchmark dir
BENCHMARK_DIR=$(mktemp -d -t opencre-benchmark-XXXXXX)
echo "Benchmark directory: $BENCHMARK_DIR"

# Clean up ANY previous benchmark containers before we start
echo "Stopping any existing benchmark containers..."
docker stop cre-postgres cre-postgres-upstream 2>/dev/null || true
docker rm -v cre-postgres cre-postgres-upstream 2>/dev/null || true

cleanup_dir() {
    echo "Cleaning up $BENCHMARK_DIR"
    rm -rf "$BENCHMARK_DIR"
    # We DO NOT stop containers here so they can be inspected after failure
}
trap cleanup_dir EXIT

# Database URIs
export IMPORTED_DB="postgresql://cre:password@localhost:5432/cre"
export UPSTREAM_DB="postgresql://cre:password@localhost:5433/cre"

# Function to start a PostgreSQL container and run migrations
setup_db() {
    local container=$1
    local port=$2
    local uri=$3

    echo "Setting up DB in container $container on port $port"
    docker stop "$container" 2>/dev/null || true
    docker rm -v "$container" 2>/dev/null || true
    docker run -d --name "$container" -e POSTGRES_PASSWORD=password -e POSTGRES_USER=cre -e POSTGRES_DB=cre -p "$port:5432" postgres
    
    echo "Waiting for $container to be ready..."
    until docker exec "$container" pg_isready -U cre -d cre; do
      sleep 1
    done

    echo "Running migrations for $container..."
    [ -d "./venv" ] && . ./venv/bin/activate
    export FLASK_APP=cre.py
    export SQLALCHEMY_DATABASE_URI="$uri"
    flask db upgrade
}

# 0) Setup PostgreSQL containers and run migrations
setup_db "cre-postgres" 5432 "$IMPORTED_DB"
setup_db "cre-postgres-upstream" 5433 "$UPSTREAM_DB"

# Use PostgreSQL for imported database to avoid SQLite locking issues
export CRE_USE_POSTGRES=1
export BENCHMARK_MODE=1
export CRE_DB_URI="$IMPORTED_DB"

export CRE_NO_NEO4J=0
export NO_LOAD_GRAPH_DB=0
export CRE_NO_GEN_EMBEDDINGS=1

echo "1) Running import-all with 6 workers"
export RUN_COUNT=6
export CRE_SKIP_IMPORT_CORE=""
export CRE_SKIP_IMPORT_PROJECTS=""

# Let's clean the local DB just to be safe.
export CRE_DELETE_DB=1
make import-all

echo "2) Syncing upstream DB to $UPSTREAM_DB"
# The Makefile's upstream-sync doesn't take parameters, so we use python directly
[ -d "./venv" ] && . ./venv/bin/activate
python3 cre.py --upstream_sync --cache_file "$UPSTREAM_DB"
python3 -c "from application.cmd.cre_main import download_gap_analysis_from_upstream; download_gap_analysis_from_upstream('$UPSTREAM_DB')"

echo "3) Diffing the DBs..."
python3 scripts/benchmark_import_parity.py --upstream-db "$UPSTREAM_DB" --imported-db "$IMPORTED_DB" --log-file content-diffs.log

echo "4) Running Gap Analysis benchmark"
# Backfill missing GA pairs directly from DB truth (no HTTP preload loop)
export RUN_COUNT=6
# Ensure workers and flask use the same DB
export SQLALCHEMY_DATABASE_URI="$IMPORTED_DB"
POSTGRES_URL="$IMPORTED_DB" make backfill-gap-analysis

echo "Benchmark completed successfully!"
