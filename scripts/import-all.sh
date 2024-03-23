#! /bin/bash

set -ex
export SERVICE_ACCOUNT_CREDENTIALS=`cat $SVC_ACC_KEY_PATH`
export OpenCRE_gspread_Auth='service_account'
export GOOGLE_PROJECT_ID='opencre-vertex'
export NEO4J_URL='neo4j://neo4j:password@127.0.0.1:7687'
export FLASK_APP=$(pwd)/cre.py

if [ -n $(docker ps | grep cre-neo4) ]; then
    docker stop cre-neo4j
    make docker-neo4j-rm || true
fi

if [ -n $(docker ps | grep cre-redis-stack) ]; then
    docker stop cre-redis-stack
fi

if [ -n $CRE_DELETE_DB ]; then
    echo "CRE_DELETE_DB is set, emptying database"
    rm -rf standards_cache.sqlite
fi

make migrate-upgrade
make docker-redis
make docker-neo4j

for i in seq 1 $RUN_COUNT; do
 (rm -f "worker-$$i.log" && make start-worker&> "worker-$$i.log")&
 done

[ -d "./venv" ] && . ./venv/bin/activate

if [ -z $CRE_SKIP_IMPORT_CORE ]; then
    echo "CRE_SKIP_IMPORT_CORE is not set, importing core csv"
    python cre.py --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg
fi
if [ -z $CRE_SKIP_IMPORT_PROJECTS ]; then
    echo "CRE_SKIP_IMPORT_PROJECTS is not set, importing external projects"
    python cre.py --import_external_projects
fi

killall python
killall make
    
