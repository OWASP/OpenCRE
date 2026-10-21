import json,random,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path.home()/"Projects/OpenCRE-wt-ingest-comprehension/.private-evals"))
from llm import ask_llm
db=sqlite3.connect("graph.sqlite");db.row_factory=sqlite3.Row
random.seed(88)
rows=[dict(r) for r in db.execute("select id,path,subj,rel,obj,edition,valid_from,valid_to,quote from fact where id>2418")]
s=random.sample(rows,min(150,len(rows)))
P="For each fact, does the quote (plus its source path as context) support it (subject, relation, object, edition/date)? Relations: leads/contributes=person works on project; released=version released; part_of=item belongs to list; has_count=obj is a number of subj; has_title=role/title. Be strict.\nReturn JSON array [{\"id\":..,\"ok\":true|false,\"why\":\"..\"}].\n"+json.dumps(s)
_,out=ask_llm(P,["claude"],timeout=600)
a=json.loads(re.search(r"\[.*\]",out,re.S).group(0))
ok=sum(x["ok"] for x in a);print(ok,"/",len(a))
for x in a:
    if not x["ok"]:print(x)
