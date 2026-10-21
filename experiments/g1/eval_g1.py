#!/usr/bin/env python3
"""Run the 252-question sample through the router; unrouted/INSUFFICIENT questions reuse the baseline (L4+2M, 62.7%) answers, routed ones are re-judged."""
import collections, json, sys, os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
EVAL = Path.home() / "Projects/OpenCRE-wt-ingest-comprehension/.private-evals"
sys.path.insert(0, str(EVAL))
import judge as J  # noqa
import router  # noqa

qs = [json.loads(l) for l in (EVAL / "questions_abl.jsonl").read_text().splitlines()]
base_ans = [json.loads(l) for l in (EVAL / "answers_abl_combo_longctx_lc2m.jsonl").read_text().splitlines()]
base_res = [json.loads(l) for l in (EVAL / "results_abl_combo_longctx_lc2m.jsonl").read_text().splitlines()]
assert len(qs) == len(base_ans) == len(base_res) == 252
tag = sys.argv[1] if len(sys.argv) > 1 else "g1"
with ThreadPoolExecutor(max_workers=6) as p:
    ga = list(p.map(lambda q: router.graph_answer(q["question"]), qs))
routed = [i for i, g in enumerate(ga) if g]
print("routed", len(routed), flush=True)
batch = [(i, qs[i], ga[i][0], ga[i][1]) for i in routed]
verd = {}
for s in range(0, len(batch), 25):
    verd.update(J.judge_batch(batch[s:s + 25]))
final = []
for i, b in enumerate(base_res):
    if i in verd:
        final.append({**b, "answer": ga[i][0][:1500], "verdict": verd[i]["verdict"], "reason": verd[i]["reason"], "routed": True, "base_verdict": b["verdict"]})
    else:
        final.append({**b, "routed": False})
Path(__file__).with_name(f"results_{tag}.jsonl").write_text("\n".join(json.dumps(r) for r in final) + "\n")
def acc(rs): return sum(r["verdict"] == "correct" for r in rs) / max(1, len(rs))
print(f"baseline {acc(base_res):.1%}  G1 {acc(final):.1%}  delta {100*(acc(final)-acc(base_res)):+.1f} pts")
print(f"routed subset: baseline {acc([base_res[i] for i in routed]):.0%} -> G1 {acc([final[i] for i in routed]):.0%} (n={len(routed)})")
g = collections.defaultdict(lambda: [0, 0, 0])
for b, f in zip(base_res, final):
    x = g[b["family"]]; x[0] += 1; x[1] += b["verdict"] == "correct"; x[2] += f["verdict"] == "correct"
for k, (n, a, c) in sorted(g.items()): print(f"  {k:26s} n={n} base={a} g1={c}")
