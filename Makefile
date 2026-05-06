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

docker-postgres:
	docker start cre-postgres 2>/dev/null ||\
	docker run -d --name cre-postgres -e POSTGRES_PASSWORD=password -e POSTGRES_USER=cre -e POSTGRES_DB=cre -p 5432:5432 postgres

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
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP="$(CURDIR)/cre.py" &&\
	export FLASK_CONFIG=development &&\
	export INSECURE_REQUESTS=1 &&\
	flask run &
	sleep 5
	yarn test:e2e
	sleep 20
	killall yarn
	killall flask

test:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP="$(CURDIR)/cre.py" &&\
	flask routes && python -m unittest discover -s application/tests -p "*_test.py"

cover:
	. ./venv/bin/activate && FLASK_APP=cre.py FLASK_CONFIG=testing flask test --cover

install-deps-python:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	pip install --upgrade pip setuptools &&\
	pip install -r requirements.txt

install-deps-typescript:
	(cd application/frontend && yarn install)

install-deps: install-deps-python install-deps-typescript

install-python:
	virtualenv -p python3  venv
	. ./venv/bin/activate &&\
	make install-deps-python &&\
	playwright install
	
install-typescript:
	yarn add webpack && cd application/frontend && yarn build

install: install-typescript install-python

docker-dev:
	docker build -f Dockerfile-dev -t opencre-dev:$(shell git rev-parse HEAD) .

docker-prod:
	docker build -f Dockerfile -t opencre:$(shell git rev-parse HEAD) .

docker-dev-run:
	docker run -it -p 127.0.0.1:$(PORT):$(PORT) opencre-dev:$(shell git rev-parse HEAD)

docker-prod-run:
	 docker run -it -p $(PORT):$(PORT) opencre:$(shell git rev-parse HEAD)

lint:
	[ -d "./venv" ] && . ./venv/bin/activate && black . && yarn lint

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

all: clean lint test dev dev-run
