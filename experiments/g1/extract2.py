#!/usr/bin/env python3
"""G1 pass 2: people / counts / editions with project+edition taken from file context (path, title, repo). Subject must be in the quote."""
from __future__ import annotations
import hashlib, json, os, re, sqlite3, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import extract as E  # noqa: E402

PROMPT = """Extract facts about PEOPLE, COUNTS and EDITIONS from this OWASP project document.
Repo: {repo}   File: {path}   Document title: {title}
Emit JSON only: array of
{{"subj":"person or counted thing","rel":"leads|contributes|role_of|released|has_count","obj":"the project/edition/list it concerns (use the project name from the repo/title)","edition":"year/version the fact is about or null","valid_from":null,"valid_to":null,"quote":"<verbatim excerpt <=200 chars containing the subj>"}}
Rules: leads = project leader/lead/chair; contributes = author/contributor/reviewer/translator (put the edition in 'edition' if the section states one, e.g. 2017);
role_of = named title/role/organization of a person; released = version/edition published with its date; has_count = a number stated for something (subj = what is counted, obj = the number as written).
Only facts stated in the text. Copy quotes exactly. [] if none.
TEXT:
{text}"""
KEY = re.compile(r"leader|lead\b|contributor|author|reviewer|translat|survey|released|published|members|elected|seats|ballot|edition|version|team|chair|credits|acknowledg", re.I)


def title_of(text: str) -> str:
    m = re.search(r"^(?:title:\s*(.+)|#\s+(.+))$", text, re.M)
    return (m.group(1) or m.group(2)).strip() if m else ""


def job(a):
    repo, path, text, title = a
    key = hashlib.sha1(("p2" + repo + path + text).encode()).hexdigest()
    f = E.RAW / f"{key}.json"
    if f.exists():
        return a, json.loads(f.read_text())
    try:
        _, raw = E.ask_llm(PROMPT.format(repo=repo, path=path, title=title, text=text), E.ORDER, timeout=300)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        facts = json.loads(m.group(0)) if m else []
    except Exception as e:  # noqa: BLE001
        print("fail", path, str(e)[:60], flush=True)
        return a, None
    f.write_text(json.dumps(facts))
    return a, facts


def ok(x: dict, path: str, title: str, repo: str) -> bool:
    try:
        q = E.norm(str(x["quote"])); s = E.norm(str(x["subj"]))
        if x["rel"] not in ("leads", "contributes", "role_of", "released", "has_count") or len(q) < 8 or len(s) < 3 or s not in q:
            return False
        if E.norm(str(x["obj"])) == s:
            return False
        ctx = E.norm(path + " " + title + " " + repo)
        ed = x.get("edition")
        if ed and str(ed).lower() != "null" and not all(y in q or y in ctx for y in re.findall(r"\d{4}|\d+(?:\.\d+)+", str(ed))):
            return False
        if x["rel"] == "has_count" and not re.search(r"\d", q):
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def main(repos):
    db = sqlite3.connect(E.DB)
    for repo in repos:
        docs = E.corpus.fetch(repo)
        jobs = []
        for p, t in docs.items():
            if not KEY.search(t):
                continue
            title = title_of(t)
            for i in range(0, len(t), E.CHUNK):
                jobs.append((repo, p, t[i:i + E.CHUNK + 300], title))
        print(repo, len(jobs), "chunks", flush=True)
        kept = dropped = 0
        with ThreadPoolExecutor(max_workers=12) as pool:
            for (r, path, text, title), facts in pool.map(job, jobs):
                if not isinstance(facts, list):
                    continue
                nt = E.norm(text)
                for x in facts:
                    if isinstance(x, dict) and E.norm(str(x.get("quote", ""))) in nt and ok(x, path, title, r):
                        db.execute("insert or ignore into fact(repo,path,subj,subj_type,rel,obj,obj_type,valid_from,valid_to,edition,quote) values(?,?,?,?,?,?,?,?,?,?,?)",
                            (r, path, str(x["subj"]), "person", x["rel"], str(x["obj"]), "project", None, None, x.get("edition"), str(x["quote"])))
                        kept += 1
                    else:
                        dropped += 1
        db.commit()
        print(repo, "kept", kept, "dropped", dropped, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
