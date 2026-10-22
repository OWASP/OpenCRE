"""G1 router + graph answerer. Rules pick {graph, text}; graph answers cite sources; empty/low confidence -> None (caller falls back)."""
from __future__ import annotations
import json, os, re, sqlite3, sys
from pathlib import Path

EVAL = Path.home() / "Projects/OpenCRE-wt-ingest-comprehension/.private-evals"
sys.path.insert(0, str(EVAL))
from llm import ask_llm  # noqa: E402

DB = Path(__file__).parent / "graph.sqlite"
ALIASES = {
    "OWASP/www-project-top-ten": ["top 10 project", "owasp top 10", "top ten", "top 10-20", "top 10 20", "top 10 release", "top 10 for"],
    "OWASP/www-project-security-culture": ["security culture"],
    "OWASP/www-project-mobile-top-10": ["mobile top 10", "mobile top ten", "mobile risk", "ios apps", "android apps", "binary protections"],
    "OWASP/www-project-ai-security-and-privacy-guide": ["ai security", "ai exchange", "ultimate ai security", "ai guide", "testimonial", "hero section"],
    "OWASP/www-board": ["board", "owasp foundation", "board of directors", "owasp members", "members did owasp", "owasp have", "election", "seats"],
    "OWASP/owasp-scs": ["smart contract security", "scs ", "owasp scs"],
    "OWASP/www-project-threat-dragon": ["threat dragon"],
    "OWASP/ASVS": ["asvs", "application security verification"],
    "OWASP/masvs": ["masvs", "mobile application security verification"],
    "OWASP/SAMM": ["samm", "software assurance maturity"],
    "OWASP/API-Security": ["api security", "api top 10", "api1:", "api-security"],
    "OWASP/wstg": ["wstg", "web security testing guide"],
    "OWASP/www-project-developer-guide": ["developer guide"],
    "OWASP/www-project-machine-learning-security-top-10": ["machine learning security", "ml security", "ml top 10", "ml01", "ml02"],
    "OWASP/www-project-kubernetes-top-ten": ["kubernetes"],
    "OWASP/www-project-smart-contract-top-10": ["smart contract top", "sc01", "sc02"],
}
GRAPH_Q = re.compile(r"\b(who|leader|leaders|led|lead|author|authors|contributor|contributors|reviewer|reviewers|how many|number of|count|total|when|what year|which year|date|released|release|edition|version|since|until|chair|member|members|title|role|recent|previous|change|differ|current|survey|individuals|resources)\b", re.I)
STOP = set("the a an of in is are was were what who how many which for to and or on by with as at from this that does did do project owasp".split())


def detect_repo(q: str) -> str | None:
    ql = q.lower() + " "
    hits = [r for r, al in ALIASES.items() if any(a in ql for a in al)]
    if "top 10" in ql and "mobile" in ql:
        hits = ["OWASP/www-project-mobile-top-10"]
    if len(hits) > 1:
        hits = [h for h in hits if h not in ("OWASP/www-project-top-ten", "OWASP/owasp-scs", "OWASP/www-board")] or hits
    if "OWASP/www-project-smart-contract-top-10" in hits and "OWASP/owasp-scs" in hits:
        hits = ["OWASP/www-project-smart-contract-top-10"]
    return hits[0] if len(hits) == 1 else None


def infer_repo(q: str) -> str | None:
    """No project named: pick the repo whose facts overlap the question most (clear winner only)."""
    if not DB.exists():
        return None
    db = sqlite3.connect(DB)
    repos = [r[0] for r in db.execute("select distinct repo from fact")]
    tot = {}
    for r in repos:
        fs = _scored(r, q)
        tot[r] = sum(sc for sc, _ in fs[:5])
    best = sorted(tot.items(), key=lambda kv: kv[1], reverse=True)
    if len(best) >= 2 and best[0][1] >= 10 and best[0][1] >= 1.6 * best[1][1]:
        return best[0][0]
    return None


def _scored(repo: str, q: str):
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute("select * from fact where repo=?", (repo,))]
    qt = {t for t in re.findall(r"[a-z0-9]+", q.lower()) if t not in STOP and len(t) > 2}
    ys = set(re.findall(r"\b(?:19|20)\d\d\b", q))

    def score(r):
        txt = " ".join(str(r[x]) for x in ("subj", "obj", "edition", "quote", "rel", "path")).lower()
        tt = set(re.findall(r"[a-z0-9]+", txt))
        s = len(qt & tt) + 3 * sum(y in txt for y in ys)
        if re.search(r"\b(who|lead|leader|led)\b", q, re.I) and r["rel"] == "leads":
            s += 2
        if re.search(r"how many|number|count|total", q, re.I) and r["rel"] in ("has_count", "part_of"):
            s += 2
        return s

    out = [(score(r), r) for r in rows]
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def facts_for(repo: str, q: str, k: int = 45) -> list[dict]:
    return [r for sc, r in _scored(repo, q)[:k] if sc > 0]


PROMPT = """Answer the question using ONLY the dated facts below (each has a verbatim source quote). Be precise: respect editions/years named in the question,
never mix names from different editions, count only what the facts list. If the facts do not contain what is needed, reply exactly: INSUFFICIENT
Otherwise reply "Answer: ..." in 1-3 sentences and cite facts as [n].
Question: {q}
Facts:
{facts}"""


def graph_answer(q: str) -> tuple[str, list[str]] | None:
    if not GRAPH_Q.search(q):
        return None
    repo = detect_repo(q) or infer_repo(q)
    if not repo or not DB.exists():
        return None
    fs = facts_for(repo, q)
    if len(fs) < 2:
        return None
    lines = "\n".join(f'[{i+1}] {f["subj"]} --{f["rel"]}--> {f["obj"]} (edition {f["edition"]}, {f["valid_from"]}..{f["valid_to"]}) src={f["path"]} quote="{f["quote"][:200]}"' for i, f in enumerate(fs))
    os.environ.setdefault("EVAL_GEMINI_MODEL", "gemini-2.5-pro")
    try:
        _, out = ask_llm(PROMPT.format(q=q, facts=lines), ["gemini", "claude"], timeout=300)
    except Exception:  # noqa: BLE001
        return None
    if "INSUFFICIENT" in out[:40].upper() or not out.strip().startswith("Answer"):
        return None
    used = sorted({int(n) for grp in re.findall(r"\[([\d,\s]+)\]", out) for n in re.findall(r"\d+", grp) if 0 < int(n) <= len(fs)})
    cites = [f"https://github.com/{repo}/blob/HEAD/{fs[n-1]['path']}" for n in used]
    return out.strip(), cites
