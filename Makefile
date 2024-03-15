.ONESHELL:

.PHONY: run test covers install-deps dev docker lint frontend clean all

prod-run:
	cp cres/db.sqlite standards_cache.sqlite; gunicorn cre:app --log-file=-

docker-neo4j-rm:
	docker stop cre-neo4j
	docker rm -f cre-neo4j
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

start-containers: docker-neo4j docker-redis

start-worker:
	. ./venv/bin/activate && FLASK_APP=`pwd`/cre.py python cre.py --start_worker

dev-flask:
	. ./venv/bin/activate && INSECURE_REQUESTS=1 FLASK_APP=`pwd`/cre.py  FLASK_CONFIG=development flask run

e2e:
	yarn build
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP=$(CURDIR)/cre.py &&\
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
	export FLASK_APP=$(CURDIR)/cre.py &&\
	flask routes && flask test

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
	virtualenv -p python3 venv
	. ./venv/bin/activate
	make install-deps-python
	playwright install
	
install-typescript:
	yarn add webpack && cd application/frontend && yarn build

install: install-typescript install-python

docker-dev:
	docker build -f Dockerfile-dev -t opencre-dev:$(shell git rev-parse HEAD) .

docker-prod:
	docker build -f Dockerfile -t opencre:$(shell git rev-parse HEAD) .

docker-dev-run:
	 docker run -it -p 5000:5000 opencre-dev:$(shell git rev-parse HEAD)

docker-prod-run:
	 docker run -it -p 5000:5000 opencre:$(shell git rev-parse HEAD)

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

migrate-restore:
	if ! [ -f "standards_cache.sqlite" ]; then cp cres/db.sqlite standards_cache.sqlite; fi
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP=$(CURDIR)/cre.py 
	flask db upgrade  

migrate-upgrade:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP=$(CURDIR)/cre.py 
	flask db upgrade  

migrate-downgrade:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP=$(CURDIR)/cre.py
	flask db downgrade

import-projects:
	[ -d "./venv" ] && . ./venv/bin/activate
	docker stop cre-neo4j cre-redis-stack
	make docker-redis
	make docker-neo4j
	export SERVICE_ACCOUNT_CREDENTIALS=`cat ${HOME}/.config/gcloud/application_default_credentials.json`
	export OpenCRE_gspread_Auth='service_account'
	export GOOGLE_PROJECT_ID='opencre-vertex'
	export NEO4J_URL='neo4j://neo4j:password@127.0.0.1:7687'

	(rm -f worker-1.log && make start-worker&> worker-1.log&)
	(rm -f worker-2.log && make start-worker&> worker-2.log&)
	(rm -f worker-3.log && make start-worker&> worker-3.log&)
	(rm -f worker-4.log && make start-worker&> worker-4.log&)
	(rm -f worker-5.log && make start-worker&> worker-5.log&)
	export FLASK_APP=$(CURDIR)/cre.py &&\
	python cre.py --import_external_projects
	killall python
	killall make


import-all:
	$(shell bash ./scripts/import-all.sh)

import-neo4j:
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP=$(CURDIR)/cre.py && python cre.py --populate_neo4j_db

preload-map-analysis:
	make docker-neo4j&\
	make docker-redis&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make start-worker&\
	make dev-flask&
	sleep 5
	[ -d "./venv" ] && . ./venv/bin/activate &&\
	export FLASK_APP=$(CURDIR)/cre.py 
	python cre.py --preload_map_analysis_target_url 'http://127.0.0.1:5000'	
	killall python flask
all: clean lint test dev dev-run
