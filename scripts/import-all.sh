#! /bin/bash

set -ex
export SERVICE_ACCOUNT_CREDENTIALS=`cat $SVC_ACC_KEY_PATH`
export OpenCRE_gspread_Auth='service_account'
export GOOGLE_PROJECT_ID='opencre-vertex'
export NEO4J_URL='neo4j://neo4j:password@127.0.0.1:7687'
export FLASK_APP=$(pwd)/cre.py

if [[ -n "$(docker ps | grep cre-neo4)" ]]; then
    docker stop cre-neo4j
    make docker-neo4j-rm || true
fi

if [[ -n "$(docker ps | grep cre-redis-stack)" ]]; then
    docker stop cre-redis-stack
fi

if [[ -n $CRE_DELETE_DB ]]; then
    echo "CRE_DELETE_DB is set, emptying database"
    rm -rf standards_cache.sqlite
fi

make migrate-upgrade
make docker-redis
make docker-neo4j

for i in $(seq 1 $RUN_COUNT); do
 (rm -f "worker-$i.log" && make start-worker &> "worker-$i.log")&
 done

[ -d "./venv" ] && . ./venv/bin/activate

if [[ -z $CRE_SKIP_IMPORT_CORE ]]; then
    echo "CRE_SKIP_IMPORT_CORE is not set, importing core csv"
    python cre.py --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg
fi
if [[ -z $CRE_SKIP_IMPORT_PROJECTS ]]; then
    echo "CRE_SKIP_IMPORT_PROJECTS is not set, importing external projects"
    echo "Importing CWE"
    python cre.py --cwe_in
    echo "Importing CAPEC"
    python cre.py --capec_in
    echo "Importing SECURE HEADERS"
    python cre.py --owasp_secure_headers_in
    echo "Importing PCI DSS 4"
    python cre.py --pci_dss_4_in
    echo "Importing Juiceshop"
    python cre.py --juiceshop_in
    echo "Importing DSOMM"
    python cre.py --dsomm_in
    echo "Importing ZAP"
    python cre.py --zap_in
    echo "Importing CheatSheets"
    python cre.py --cheatsheets_in
    echo "Importing Github Tools"
    python cre.py --github_tools_in
fi

killall python
killall make
    
