#! /bin/bash

set -ex
export SERVICE_ACCOUNT_CREDENTIALS=`cat $SVC_ACC_KEY_PATH`
export OpenCRE_gspread_Auth='service_account'
export GOOGLE_PROJECT_ID='opencre-vertex'
export NEO4J_URL='neo4j://neo4j:password@127.0.0.1:7687'
export FLASK_APP=$(pwd)/cre.py


docker stop cre-neo4j cre-redis-stack
make docker-neo4j-rm
docker rm -f cre-neo4j cre-redis-stack
rm -rf standards_cache.sqlite
make migrate-upgrade
make docker-redis
make docker-neo4j

for i in $(shell seq 1 $(RUN_COUNT)); do
 (rm -f "worker-$$i.log" && make start-worker&> "worker-$$i.log")&
 done

[ -d "./venv" ] && . ./venv/bin/activate
python cre.py --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg
python cre.py --import_external_projects

killall python
killall make
    
