#!/usr/bin/env python3
"""G1 part 3: L7-style text-pipeline router, flag G1_TEXT_ROUTER (off unless set). Emulated on the laptop:
the 'text pipeline' = whole-project reading (L4) from the local repo cache, with a stricter prompt for people/count questions
(and a per-standard prompt for cross-standard/multi-doc). Unrouted or project-less questions keep the baseline (62.7%) answer.

    python text_router.py strict|perstd [tag]
"""
import collections, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
EVAL = Path.home() / "Projects/OpenCRE-wt-ingest-comprehension/.private-evals"
sys.path.insert(0, str(EVAL)); sys.path.insert(0, str(Path(__file__).parent))
import corpus, judge as J, router  # noqa
from llm import ask_llm  # noqa

if os.environ.get("G1_TEXT_ROUTER", "1") == "0":
    raise SystemExit("flag off")
PEOPLE = re.compile(r"\b(who|leaders?|lead|authors?|contributors?|reviewers?|maintainers?|chair|directors?|translators?)\b", re.I)
COUNT = re.compile(r"\bhow many\b|\bnumber of\b|\btotal\b", re.I)
STRICT = """Answer from the project documents below ONLY. This is a {kind} question, so be exact:
- people: name exactly the people the documents list for the edition/section/role the question asks about. Do not add names from other editions, sections or roles; do not drop any; if the question gives a number ("four leaders") make the list match it or say what the documents say.
- counts: if the documents state the number, give it exactly as written (keep qualifiers such as "over", "more than", "+"); otherwise count the items explicitly listed in the named section, one by one, and state the list. Do not merge or split items.
- if the documents do not contain it, say so. Cite the file path(s). Reply "Answer: ..." in 1-4 sentences.
Question: {q}

DOCUMENTS:
{docs}"""
NEUTRAL = """Answer the question using only the project documents below. Cite file paths. Reply "Answer: ..." concisely.
Question: {q}

DOCUMENTS:
{docs}"""
PERSTD = """The question involves several standards/projects. Answer for EACH standard separately first (one short paragraph per standard, using only its documents, naming the relevant sections/ids), then give the combined answer. Cite file paths. If a standard's documents do not cover the point, say so for that standard.
Question: {q}

DOCUMENTS:
{docs}"""


def repos_in(q):
    ql = q.lower() + " "
    return [r for r, al in router.ALIASES.items() if any(a in ql for a in al)]


def route(q, mode, fam):
    if mode in ("strict", "neutral"):
        kind = "people" if PEOPLE.search(q) else "count" if COUNT.search(q) else None
        r = router.detect_repo(q)
        return (kind, [r]) if kind and r else None
    hits = repos_in(q)
    if fam in ("cross_standard", "multi_doc_combination") and len(hits) >= 2:
        return "perstd", hits[:2]
    return None


def answer(q, kind, repos):
    cap = 1_500_000 // len(repos)
    docs = "".join(f"\n\n##### PROJECT {r}\n" + corpus.bundle(corpus.fetch(r), cap) for r in repos)
    p = (PERSTD if kind == "perstd" else NEUTRAL if os.environ.get("G1_NEUTRAL") else STRICT).format(kind=kind, q=q, docs=docs)
    os.environ["EVAL_GEMINI_MODEL"] = "gemini-2.5-pro"
    _, out = ask_llm(p, ["gemini", "claude"], timeout=900)
    cites = [f"https://github.com/{r}" for r in repos]
    return out.strip(), cites


if __name__ == "__main__":
    mode = sys.argv[1]; tag = sys.argv[2] if len(sys.argv) > 2 else "tr_" + mode
    qs = [json.loads(l) for l in (EVAL / "questions_abl.jsonl").read_text().splitlines()]
    base = [json.loads(l) for l in (EVAL / "results_abl_combo_longctx_lc2m.jsonl").read_text().splitlines()]
    routes = [route(q["question"], mode, q["family"]) for q in qs]
    idx = [i for i, r in enumerate(routes) if r]
    print("routed", len(idx), flush=True)

    def go(i):
        try:
            return i, answer(qs[i]["question"], *routes[i])
        except Exception as e:  # noqa: BLE001
            return i, None
    with ThreadPoolExecutor(max_workers=4) as p:
        ans = dict(p.map(go, idx))
    batch = [(i, qs[i], ans[i][0], ans[i][1]) for i in idx if ans[i]]
    verd = {}
    for s in range(0, len(batch), 25):
        verd.update(J.judge_batch(batch[s:s + 25]))
    final = [{**b, "routed": False} for b in base]
    for i, v in verd.items():
        final[i] = {**base[i], "answer": ans[i][0][:1500], "verdict": v["verdict"], "reason": v["reason"], "routed": True, "base_verdict": base[i]["verdict"]}
    Path(__file__).with_name(f"results_{tag}.jsonl").write_text("\n".join(json.dumps(r) for r in final) + "\n")
    acc = lambda rs: sum(r["verdict"] == "correct" for r in rs) / max(1, len(rs))
    ids = list(verd)
    print(f"baseline {acc(base):.1%} {tag} {acc(final):.1%} delta {100*(acc(final)-acc(base)):+.1f} pts; routed n={len(ids)}: base {acc([base[i] for i in ids]):.0%} -> {acc([final[i] for i in ids]):.0%}")
    g = collections.defaultdict(lambda: [0, 0, 0])
    for b, f in zip(base, final):
        x = g[b["family"]]; x[0] += 1; x[1] += b["verdict"] == "correct"; x[2] += f["verdict"] == "correct"
    for k, (n, a, c) in sorted(g.items()):
        if a != c: print(f"  {k:26s} n={n} base={a} {tag}={c}")
