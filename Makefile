
.ONESHELL:

.PHONY: dev-run run test covers install-deps dev docker lint frontend clean all

prod-run:
	cp cres/db.sqlite standards_cache.sqlite; gunicorn cre:app --log-file=-

dev-run:
	. ./venv/bin/activate && FLASK_APP=cre.py FLASK_CONFIG=development flask run

test:
	. ./venv/bin/activate &&\
	FLASK_APP=cre.py FLASK_CONFIG=testing flask test &&\
	yarn test --passWithNoTests

cover:
	. ./venv/bin/activate && FLASK_APP=cre.py FLASK_CONFIG=testing flask test --coverage

install-deps:
	. ./venv/bin/activate; pip install -r requirements.txt& yarn install

install:
	virtualenv venv && . ./venv/bin/activate && make install-deps && yarn build

docker:
	docker build -f Dockerfile-dev -t opencre:$(shell git rev-parse HEAD) .

docker-run:
	 docker run -it -p 5000:5000 opencre:$(shell git rev-parse HEAD)

lint:
	black .

frontend:
	yarn build


clean:
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.log' -delete
	find . -type f -name '*.orig' -delete

all: clean lint test dev dev-run
