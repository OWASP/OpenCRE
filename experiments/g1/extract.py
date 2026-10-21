#!/usr/bin/env python3
"""G1 extraction: project docs -> dated fact graph (SQLite). Laptop only.

    python extract.py OWASP/www-board ...   # cached per chunk; safe to rerun
Facts are kept only if the quote occurs verbatim in the source chunk (provenance check).
"""
from __future__ import annotations
import hashlib, json, os, re, sqlite3, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EVAL = Path.home() / "Projects/OpenCRE-wt-ingest-comprehension/.private-evals"
sys.path.insert(0, str(EVAL))
import corpus  # noqa: E402
from llm import ask_llm  # noqa: E402

HERE = Path(__file__).parent
DB = HERE / "graph.sqlite"
RAW = HERE / "raw"
ORDER = ["gemini"]
os.environ.setdefault("EVAL_GEMINI_MODEL", "gemini-2.5-flash-lite")
ETYPES = {"project", "person", "event", "version", "control", "organization", "document"}
RELS = {"leads", "contributes", "released", "part_of", "maps_to", "has_count", "role_of", "held_at", "reviewed", "translated", "has_title"}
CHUNK = 9000

PROMPT = """Extract dated facts from this OWASP project document for a knowledge graph.
Source path: {path}
Emit JSON only: an array of objects
{{"subj":"..","subj_type":"project|person|event|version|control|organization|document","rel":"leads|contributes|released|part_of|maps_to|has_count|role_of|held_at|reviewed|translated|has_title","obj":"..","obj_type":"..","valid_from":"YYYY[-MM[-DD]]|null","valid_to":"YYYY[-MM[-DD]]|null","edition":"version/edition label this fact belongs to, e.g. 2017, 4.0, or null","quote":"<verbatim excerpt <=200 chars from the text that states the fact>"}}
Rules: only facts stated in the text (no inference); one fact per object; quote MUST be copied exactly.
Priority: project leaders/authors/reviewers/contributors (with edition/year), releases and dates, counts stated in text
(use rel has_count, obj = the number as written, subj = what is counted), list membership (items part_of a list/edition),
roles/titles of people, events and dates. Skip generic prose. Return [] if nothing qualifies.
TEXT:
{text}"""


def chunks(docs: dict[str, str]):
    for path, text in docs.items():
        for i in range(0, len(text), CHUNK):
            yield path, text[i : i + CHUNK + 300]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def grounded(x: dict, path: str) -> bool:
    """Both ends and every date/edition must be visible in the quote (or source path); relation words must fit."""
    q = norm(str(x["quote"]))
    p = norm(path)
    if len(q) < 12:
        return False
    for end in (x["subj"], x["obj"]):
        e = norm(str(end))
        if e not in q and not (len(e) > 3 and e in p):
            return False
    for k in ("valid_from", "valid_to", "edition"):
        v = x.get(k)
        if v and str(v).lower() != "null":
            if not all(y in q or y in p for y in re.findall(r"\d{4}|\d+(?:\.\d+)+", str(v))):
                return False
    return True


def one(args):
    repo, path, text = args
    key = hashlib.sha1((repo + path + text).encode()).hexdigest()
    f = RAW / f"{key}.json"
    if f.exists():
        return repo, path, text, json.loads(f.read_text())
    try:
        _, raw = ask_llm(PROMPT.format(path=path, text=text), ORDER, timeout=300)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        facts = json.loads(m.group(0)) if m else []
    except Exception as e:  # noqa: BLE001
        print("fail", path, str(e)[:80], flush=True)
        return repo, path, text, None
    f.write_text(json.dumps(facts))
    return repo, path, text, facts


def main(repos: list[str]) -> None:
    RAW.mkdir(exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("""create table if not exists fact(id integer primary key, repo, path, subj, subj_type, rel, obj, obj_type,
        valid_from, valid_to, edition, quote, unique(repo,path,subj,rel,obj,edition))""")
    for repo in repos:
        docs = corpus.fetch(repo)
        jobs = [(repo, p, t) for p, t in chunks(docs)]
        print(repo, len(jobs), "chunks", flush=True)
        kept = dropped = 0
        with ThreadPoolExecutor(max_workers=12) as pool:
            for r, path, text, facts in pool.map(one, jobs):
                if not isinstance(facts, list):
                    continue
                nt = norm(text)
                for x in facts:
                    if not isinstance(x, dict):
                        continue
                    try:
                        ok = (x["rel"] in RELS and x["subj_type"] in ETYPES and x.get("obj_type", "document") in ETYPES
                              and x["subj"] and x["obj"] and norm(str(x["quote"])) in nt and grounded(x, path))
                    except Exception:  # noqa: BLE001
                        ok = False
                    if not ok:
                        dropped += 1
                        continue
                    db.execute("insert or ignore into fact(repo,path,subj,subj_type,rel,obj,obj_type,valid_from,valid_to,edition,quote) values(?,?,?,?,?,?,?,?,?,?,?)",
                        (r, path, str(x["subj"]), x["subj_type"], x["rel"], str(x["obj"]), x.get("obj_type", "document"), x.get("valid_from"), x.get("valid_to"), x.get("edition"), str(x["quote"])))
                    kept += 1
        db.commit()
        print(repo, "kept", kept, "dropped", dropped, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
