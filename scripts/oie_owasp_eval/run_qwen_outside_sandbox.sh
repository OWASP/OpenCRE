#!/usr/bin/env bash
# Run this in Terminal.app / iTerm (NOT Cursor agent sandbox).
set -euo pipefail
cd "$(dirname "$0")/../.."
source venv/bin/activate
export PYTHONPATH=.
export FLASK_CONFIG=development
export NO_LOAD_GRAPH_DB=1
export CRE_NOISE_FILTER_LLM_MODEL="${CRE_NOISE_FILTER_LLM_MODEL:-ollama/qwen2.5:14b}"
export CRE_NOISE_FILTER_BATCH_SIZE=4
RUN_ID=$(python -c "import json; print(json.load(open('tmp/oie_owasp_eval/state.json'))['sample_run_id'])")
DB=$(python -c "import json; print(json.load(open('tmp/oie_owasp_eval/state.json'))['db_url'])")
# Reset sample to pending
python - <<PY
from application.cmd.cre_main import db_connect
from application import sqla
from application.database.db import HarvestInput
import json
st=json.load(open('tmp/oie_owasp_eval/state.json'))
db_connect(st['db_url'])
sqla.session.query(HarvestInput).filter_by(pipeline_run_id=st['sample_run_id']).update({'status':'pending'}, synchronize_session=False)
sqla.session.commit()
print('reset', st['sample_run_id'])
PY
python cre.py --run_noise_filter --run_id "$RUN_ID" --cache_file "$DB" | tee tmp/oie_owasp_eval/classify_qwen_raw.json
echo "Done. Tell the agent: qwen ready"
