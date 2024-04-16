web: gunicorn cre:app --log-file=-g
worker:  FLASK_RUN_PORT="5002" FLASK_APP=`pwd`/cre.py python cre.py --start_worker