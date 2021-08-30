#!/bin/bash
export FLASK_APP=/home/credev/cre_sync/cre.py 
export FLASK_CONFIG=development 
/home/credev/.local/bin/flask run --host 0.0.0.0 $@

