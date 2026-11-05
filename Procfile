release: python scripts/check_alembic_revision_guardrail.py
web: gunicorn cre:app
worker: FLASK_APP=`pwd`/cre.py python cre.py --start_worker
