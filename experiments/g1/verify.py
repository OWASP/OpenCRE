"""Verifier filter: keep a fact only if an independent LLM pass says the quote (+path, repo) states it exactly."""
import json,re,sqlite3,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path.home()/"Projects/OpenCRE-wt-ingest-comprehension/.private-evals"))
from llm import ask_llm
M=int(sys.argv[1])
db=sqlite3.connect("graph.sqlite");db.row_factory=sqlite3.Row
rows=[dict(r) for r in db.execute("select id,repo,path,subj,rel,obj,edition,quote from fact where id>?",(M,))]
P="""Strictly verify each fact against its quote. Fact semantics: leads = the person is project leader/lead/chair/director of obj; contributes = the person authored/reviewed/translated/contributed to obj;
role_of = subj is a person holding a named role/title (obj) or org; released = obj was released/published (version/date); has_count = obj is the number of subj stated as real data (not an example, rating, id, fee, threshold, date).
ok=true ONLY if the quote itself (with path/repo as context for the project) clearly states exactly this fact; candidates/nominees, attendees, speakers, cited paper authors, examples, generic roles, and reversed directions are NOT ok.
Return JSON array [{"id":..,"ok":true|false}] covering every id.
"""
def run(b):
    try:
        _,o=ask_llm(P+json.dumps(b),["claude"],timeout=600)
        return {x["id"]:x["ok"] for x in json.loads(re.search(r"\[.*\]",o,re.S).group(0))}
    except Exception as e:
        print("fail",str(e)[:80]);return {}
bs=[rows[i:i+40] for i in range(0,len(rows),40)]
res={}
with ThreadPoolExecutor(6) as p:
    for r in p.map(run,bs):res.update(r)
bad=[(r["id"],) for r in rows if res.get(r["id"]) is False or r["id"] not in res]
db.executemany("delete from fact where id=?",bad);db.commit()
print("checked",len(rows),"removed",len(bad),"left",len(rows)-len(bad))
