import json,re,collections
EV='/Users/sg/Projects/OpenCRE-wt-ingest-comprehension/.private-evals/'
qs=[json.loads(l) for l in open(EV+'questions.jsonl')]
PEOPLE=re.compile(r"\b(who|leader|leaders|lead|author|authors|contributor|contributors|reviewer|reviewers|maintainer|chair|director|translator)\b",re.I)
COUNT=re.compile(r"\bhow many\b|\bnumber of\b|\bcount\b|\btotal\b",re.I)
VER=re.compile(r"\b(version|edition|release[sd]?|20\d\d|19\d\d|previous|latest|newest|current|since|changed?|when)\b",re.I)
def bucket(q):
    f=q['family'];t=q['question']
    if f=='cross_standard' or '+' in q['repo']: return 'cross-standard'
    if f=='multi_doc_combination': return 'multi-doc'
    if f=='count' or COUNT.search(t): return 'count'
    if f=='people_meta' or PEOPLE.search(t): return 'people'
    if f in('compare_versions','adv_temporal') or VER.search(t): return 'version/temporal'
    return 'other'
c=collections.Counter(bucket(q) for q in qs);n=len(qs)
for k,v in c.most_common():print(f"{k:18s}{v:4d} {v/n:5.1%}")
g=c['count']+c['people']+c['version/temporal']
print("graph-shaped (count+people+version/temporal):",g,f"{g/n:.1%}")
lab=collections.Counter(q['family'] for q in qs if q['family'] in('count','people_meta','compare_versions','adv_temporal'))
print("by gold family label only:",sum(lab.values()),f"{sum(lab.values())/n:.1%}")
