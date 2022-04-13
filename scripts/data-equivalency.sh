#!/bin/bash
curr_dir=$(pwd)

rm -rf import.dump latest.backup latest.dump latest.dump.1

docker run -d -e POSTGRES_HOST_AUTH_METHOD=trust --rm --network host postgres:13.6
sleep 10

export PROD_DATABASE_URL=postgres://postgres@0.0.0.0:5432
make migrate-upgrade
make import-all

rm -rf /tmp/diff_data
mkdir -p /tmp/diff_data
cd /tmp/diff_data

heroku login && heroku pg:backups:download -a opencreorg

source $curr_dir/venv/bin/activate
python $curr_dir/cre.py --compare_datasets --dataset1=$PROD_DATABASE_URL --dataset2=sqlite://cres/db.sqlite
exit $?