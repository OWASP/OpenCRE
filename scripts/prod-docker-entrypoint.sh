#! /bin/bash

export INSECURE_REQUESTS=1
export FLASK_CONFIG="production"
export FLASK_APP=`pwd`/cre.py 
flask db upgrade
python /code/cre.py --upstream_sync
gunicorn cre:app -b :5000 --timeout 90
