.ONESHELL:

.PHONY: run test covers install-deps dev docker lint frontend clean all

prod-run:
	gunicorn cre:app --log-file=-

docker-neo4j-rm:
	docker stop cre-neo4j
	docker rm -f cre-neo4j
	docker volume inspect cre_neo4j_data >/dev/null 2>&1 || docker volume create cre_neo4j_data
	docker volume inspect cre_neo4j_logs >/dev/null 2>&1 || docker volume create cre_neo4j_logs
	docker volume rm cre_neo4j_data
	docker volume rm cre_neo4j_logs
	# rm -rf .neo4j

docker-neo4j:
	docker start cre-neo4j 2>/dev/null   || docker run -d --name cre-neo4j --env NEO4J_PLUGINS='["apoc"]'  --env NEO4J_AUTH=neo4j/password --volume=`pwd`/.neo4j/data:/data --volume=`pwd`/.neo4j/logs:/logs --workdir=/var/lib/neo4j -p 7474:7474 -p 7687:7687 neo4j

docker-redis-rm:
	docker stop cre-redis-stack
	docker rm -f cre-redis-stack

docker-redis:
	docker start cre-redis-stack 2>/dev/null ||\
	docker run -d --name cre-redis-stack -p 6379:6379 -p 8001:8001 redis/redis-stack:latest

# Local app DB — always pgvector (embedding_vec / Librarian / chat similarity).
POSTGRES_IMAGE ?= pgvector/pgvector:pg16

docker-postgres-rm:
	-docker stop cre-postgres
	-docker rm -f cre-postgres

docker-postgres:
	@wanted="$(POSTGRES_IMAGE)"; \
	if docker inspect cre-postgres >/dev/null 2>&1; then \
		have=$$(docker inspect -f '{{.Config.Image}}' cre-postgres); \
		if [ "$$have" = "$$wanted" ]; then \
			docker start cre-postgres >/dev/null; \
		else \
			echo "Recreating cre-postgres (was $$have → $$wanted)"; \
			docker stop cre-postgres >/dev/null 2>&1 || true; \
			docker rm -f cre-postgres >/dev/null 2>&1 || true; \
			docker run -d --name cre-postgres \
				-e POSTGRES_PASSWORD=password \
				-e POSTGRES_USER=cre \
				-e POSTGRES_DB=cre \
				-p 5432:5432 \
				"$$wanted"; \
		fi; \
	else \
		docker run -d --name cre-postgres \
			-e POSTGRES_PASSWORD=password \
			-e POSTGRES_USER=cre \
			-e POSTGRES_DB=cre \
			-p 5432:5432 \
			"$$wanted"; \
	fi; \
	ready=0; \
	for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
		if docker exec cre-postgres pg_isready -U cre -d cre >/dev/null 2>&1; then ready=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ready" != "1" ]; then \
		echo "error: cre-postgres did not become ready within 30s" >&2; \
		exit 1; \
	fi; \
	docker exec cre-postgres psql -U cre -d cre -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null

start-containers: docker-neo4j docker-redis

start-worker:
	. ./venv/bin/activate && FLASK_APP=`pwd`/cre.py python cre.py --start_worker

upstream-sync:
	. ./venv/bin/activate && python cre.py --upstream_sync

PORT?=5000

dev-flask:
	. ./venv/bin/activate && INSECURE_REQUESTS=1 FLASK_APP=`pwd`/cre.py  FLASK_CONFIG=development flask run --port $(PORT)

dev-flask-docker:
	. ./venv/bin/activate && INSECURE_REQUESTS=1 FLASK_APP=`pwd`/cre.py  FLASK_CONFIG=development flask run --host=0.0.0.0 --port $(PORT)

e2e:
	yarn build
	if [ -d "./venv" ]; then . ./venv/bin/activate; fi
	export FLASK_APP="$(CURDIR)/cre.py"
	export FLASK_CONFIG=development
	export INSECURE_REQUESTS=1
	flask run --host=127.0.0.1 --port=5000 > /tmp/opencre-e2e-flask.log 2>&1 &
	FLASK_PID=$$!
	trap 'kill $$FLASK_PID 2>/dev/null || true' EXIT INT TERM
	for i in `seq 1 30`; do \
		curl -fsS http://127.0.0.1:5000 >/dev/null && break; \
		sleep 1; \
	done
	curl -fsS http://127.0.0.1:5000 >/dev/null || { echo "ERROR: Flask did not become ready on http://127.0.0.1:5000 after 30s; see /tmp/opencre-e2e-flask.log"; exit 1; }
	env -u ELECTRON_RUN_AS_NODE yarn test:e2e

# Build the e2e SQLite schema from the ORM models (create_all), then load CRE
# data from upstream. Local/CI e2e uses create_all, NOT migrate-upgrade:
# migrations are the Postgres path and omit columns the models added without a
# migration (e.g. cre.document_metadata, see application/database/db.py), so a
# migrate-built SQLite cache is incomplete. create_all always matches the models.
e2e-db:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	rm -f "$(CURDIR)/standards_cache.sqlite" &&\
	NO_LOAD_GRAPH_DB=1 FLASK_CONFIG=development python -c "from application import create_app, sqla; app=create_app(mode='development'); app.app_context().push(); sqla.create_all()" &&\
	python cre.py --upstream_sync

test:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP="$(CURDIR)/cre.py" &&\
	flask routes && python -m unittest discover -s application/tests -p "*_test.py"

cover:
	. ./venv/bin/activate && FLASK_APP=cre.py FLASK_CONFIG=testing flask test --cover

install-deps-python:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	pip install --upgrade pip setuptools &&\
	pip install -r requirements-dev.txt

install-deps-typescript:
	(cd application/frontend && yarn install)

install-deps: install-deps-python install-deps-typescript

install-python:
	virtualenv -p python3 venv
	. ./venv/bin/activate &&\
	make install-deps-python &&\
	playwright install  # Python embeddings/scraping (prompt_client); NOT frontend e2e — keep when migrating to Cypress

install-typescript:
	yarn add webpack && cd application/frontend && yarn build

install: install-typescript install-python migrate-upgrade

docker-dev:
	docker build -f Dockerfile-dev -t opencre-dev:$(shell git rev-parse HEAD) .

docker-prod:
	docker build -f Dockerfile -t opencre:$(shell git rev-parse HEAD) .

docker-dev-run:
	docker run -it -p 127.0.0.1:$(PORT):$(PORT) opencre-dev:$(shell git rev-parse HEAD)

docker-prod-run:
	 docker run -it -p $(PORT):$(PORT) opencre:$(shell git rev-parse HEAD)

lint:
	[ -d "./venv" ] && . ./venv/bin/activate && black . && yarn lint && make openapi-guardrail

mypy:
	[ -d "./venv" ] && . ./venv/bin/activate &&  mypy --ignore-missing-imports --implicit-reexport --no-strict-optional --strict application

frontend:
	yarn build

clean:
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.log' -delete
	find . -type f -name '*.orig' -delete

migrate-upgrade:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP="$(CURDIR)/cre.py" 
	flask db upgrade  

alembic-guardrail:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	python scripts/check_alembic_revision_guardrail.py

openapi-generate:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	python scripts/generate_openapi.py

openapi-guardrail:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	python scripts/check_openapi_guardrail.py

migrate-downgrade:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP="$(CURDIR)/cre.py"
	flask db downgrade

import-projects:
	$(shell CRE_SKIP_IMPORT_CORE=1 bash  ./scripts/import-all.sh)

import-all:
	$(shell bash ./scripts/import-all.sh)

import-neo4j:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP="$(CURDIR)/cre.py" && python cre.py --populate_neo4j_db

backfill-gap-analysis:
	RUN_COUNT=8 bash ./scripts/backfill_gap_analysis.sh

sync-gap-analysis-table-local:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	python scripts/sync_gap_analysis_table.py \
		--from-sqlite "$(CURDIR)/standards_cache.sqlite" \
		--to-postgres "postgresql://cre:password@127.0.0.1:5432/cre" \
		--require-local-destination

verify-ga-complete-prod:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	python scripts/verify_ga_completeness.py \
		--base-url "https://opencre.org" \
		--output-json "$(CURDIR)/tmp/prod-ga-completeness.json"

monitor-ga-health-prod:
	@[ -d "./.venv" ] && . ./.venv/bin/activate || ([ -d "./venv" ] && . ./venv/bin/activate); \
	python scripts/monitor_ga_health.py \
		--base-url "https://opencre.org" \
		--output-json "$(CURDIR)/tmp/prod-ga-health.json"

verify-ga-parity-local:
	@[ -d "./.venv" ] && . ./.venv/bin/activate || ([ -d "./venv" ] && . ./venv/bin/activate); \
	export CRE_CACHE_FILE="$${CRE_CACHE_FILE:-postgresql://cre:password@127.0.0.1:5432/cre}"; \
	export NEO4J_URL="$${NEO4J_URL:-bolt://neo4j:password@127.0.0.1:7687}"; \
	export PYTHONPATH="$(CURDIR)"; \
	python scripts/verify_ga_postgres_neo_parity.py --output-json "$(CURDIR)/tmp/local-ga-parity.json"

backfill-gap-analysis-sync:
	@[ -d "./.venv" ] && . ./.venv/bin/activate || ([ -d "./venv" ] && . ./venv/bin/activate); \
	export FLASK_APP="$(CURDIR)/cre.py"; \
	export CRE_CACHE_FILE="$${CRE_CACHE_FILE:-postgresql://cre:password@127.0.0.1:5432/cre}"; \
	export NEO4J_URL="$${NEO4J_URL:-bolt://neo4j:password@127.0.0.1:7687}"; \
	python cre.py --cache_file "$$CRE_CACHE_FILE" --populate_neo4j_db && \
	python cre.py --cache_file "$$CRE_CACHE_FILE" --ga_backfill_missing --ga_backfill_no_queue

backfill-opencre-ga:
	@[ -d "./.venv" ] && . ./.venv/bin/activate || ([ -d "./venv" ] && . ./venv/bin/activate); \
	export FLASK_APP="$(CURDIR)/cre.py"; \
	python cre.py --cache_file "$${CRE_CACHE_FILE:-$(CURDIR)/standards_cache.sqlite}" --ga_backfill_opencre_direct

all: clean lint test dev dev-run
