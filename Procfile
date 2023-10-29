web: gunicorn cre:app --log-file=-g
worker: FLASK_APP=`pwd`/cre.py python cre.py --start_worker