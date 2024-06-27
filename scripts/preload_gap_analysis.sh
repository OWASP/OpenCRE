#! /bin/bash

set -ex
export NEO4J_URL='neo4j://neo4j:password@127.0.0.1:7687'
export FLASK_APP=$(pwd)/cre.py

make docker-redis
make docker-neo4j

for i in $(seq 1 $RUN_COUNT); do
 (rm -f "worker-$i.log" && make start-worker &> "worker-$i.log")&
 done

[ -d "./venv" ] && . ./venv/bin/activate
rm -f gap_analysis_flask.log && make dev-flask&>gap_analysis_flask.log&

sleep 5

python cre.py --preload_map_analysis_target_url 'http://127.0.0.1:5000'
echo "Map Analysis Loaded"	

killall python flask
    
