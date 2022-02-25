
.ONESHELL:

.PHONY: dev-run run test covers install-deps dev docker lint frontend clean all

prod-run:
	cp cres/db.sqlite standards_cache.sqlite; gunicorn cre:app --log-file=-

dev-run:
	. ./venv/bin/activate && FLASK_APP=cre.py FLASK_CONFIG=development flask run
e2e:
	yarn build
	[ -d "./venv" ] && . ./venv/bin/activate
	export FLASK_APP=cre
	export FLASK_CONFIG=development
	fFLASK_CONFIG=development flask run&
	
	yarn test:e2e
	killall yarn
	killall flask
test:
	[ -d "./venv" ] && . ./venv/bin/activate
	export FLASK_APP=cre
	flask routes
	flask test

cover:
	. ./venv/bin/activate && FLASK_APP=cre.py FLASK_CONFIG=testing flask test --cover

install-deps:
	[ -d "./venv" ] && . ./venv/bin/activate 
	pip install -r requirements.txt& yarn install

install:
	virtualenv -p python3 venv && . ./venv/bin/activate && make install-deps && yarn build

docker:
	docker build -f Dockerfile-dev -t opencre:$(shell git rev-parse HEAD) .

docker-run:
	 docker run -it -p 5000:5000 opencre:$(shell git rev-parse HEAD)

lint:
	[ -d "./venv" ] && . ./venv/bin/activate && black .

mypy:
	[ -d "./venv" ] && . ./venv/bin/activate &&  mypy --ignore-missing-imports --implicit-reexport --no-strict-optional --strict application

frontend:
	yarn build

clean:
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.log' -delete
	find . -type f -name '*.orig' -delete

migrate-upgrade:
	[ -d "./venv" ] && . ./venv/bin/activate
	export FLASK_APP=cre
	flask db upgrade  
migrate-downgrade:
	[ -d "./venv" ] && . ./venv/bin/activate
	export FLASK_APP=cre
	flask db downgrade
all: clean lint test dev dev-run
