#!/usr/bin/env python3
"""B1: score Module C suggestions vs opencre.org human CRE links.

Resources: ASVS + OWASP Cheat Sheets (public REST).

Hit rules:
  - ASVS: chunk grain — ≥1 of top-2 suggested CRE external_ids ∈ human-linked
    set for the matched section id.
  - CheatSheetSeries: **sheet grain** — for each cheat sheet file, union
    suggested CREs across that sheet's chunks; hit if ≥1 intersects the
    human-linked set for that sheet (API node keyed by filename / hyperlink).

Usage:
  OPENCRE_BASE_URL=https://opencre.org \\
  PYTHONPATH=. python scripts/oie_owasp_eval/score_b1_opencre_api.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre \\
    --run-id <pipeline_run_id>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, unquote, urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"

RESOURCE_SPECS = (
    {
        "api_name": "ASVS",
        "repo_substr": "ASVS",
        "label": "ASVS",
        "grain": "chunk",
    },
    {
        "api_name": "OWASP Cheat Sheets",
        "repo_substr": "CheatSheetSeries",
        "label": "CheatSheetSeries",
        "grain": "sheet",
    },
)

_SECTION_ID_RE = re.compile(
    r"\b(?:V)?(\d+\.\d+(?:\.\d+)?)\b|\*\*(\d+\.\d+(?:\.\d+)?)\*\*",
    re.IGNORECASE,
)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "OpenCRE-OIE-B1/1.0"
    s.trust_env = False
    return s


def fetch_standard_nodes(base_url: str, api_name: str) -> List[Dict[str, Any]]:
    base = base_url.rstrip("/")
    url = f"{base}/rest/v1/Standard/{quote(api_name)}"
    sess = _session()
    r = sess.get(url, timeout=60)
    r.raise_for_status()
    payload = r.json()
    nodes = list(payload.get("standards") or [])
    total = int(payload.get("total_pages") or 1)
    for page in range(2, total + 1):
        rr = sess.get(url, params={"page": page}, timeout=60)
        rr.raise_for_status()
        nodes.extend(rr.json().get("standards") or [])
    return nodes


def human_cre_ids(node: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for link in node.get("links") or []:
        doc = link.get("document") or {}
        if str(doc.get("doctype") or "").upper() == "CRE":
            cid = str(doc.get("id") or "").strip()
            if cid:
                out.add(cid)
    return out


def section_keys_for_node(node: Dict[str, Any]) -> Set[str]:
    """Keys used to align a harvest chunk to this API node."""
    keys: Set[str] = set()
    nid = str(node.get("id") or "")
    parts = nid.split(":")
    if len(parts) >= 2 and parts[0].upper() in ("ASVS", "OWASP CHEAT SHEETS"):
        keys.add(parts[1].strip().lower())
    section = str(node.get("section") or "").strip().lower()
    if section:
        keys.add(section[:120])
        for m in _SECTION_ID_RE.finditer(section):
            keys.add((m.group(1) or m.group(2) or "").lower())
    href = str(node.get("hyperlink") or "")
    if href:
        keys.add(href.lower())
        path = urlparse(href).path.lower()
        keys.add(path)
        frag = urlparse(href).fragment.lower()
        if frag:
            keys.add(frag)
        base = Path(unquote(path)).name.lower()
        if base:
            keys.add(base)
            keys.add(base.replace(".html", "").replace(".md", "").replace("_", " "))
            keys.add(base.replace(".html", "").replace(".md", ""))
    keys.discard("")
    return keys


def build_gold_index(nodes: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    key_to_cres: Dict[str, Set[str]] = defaultdict(set)
    for node in nodes:
        cres = human_cre_ids(node)
        if not cres:
            continue
        for key in section_keys_for_node(node):
            key_to_cres[key].update(cres)
    return key_to_cres


def sheet_stem(locator_path: str) -> str:
    name = Path(locator_path or "").name.lower()
    return name.replace(".md", "").replace(".html", "")


def chunk_keys(text: str, locator_path: str, heading_path: List[str]) -> Set[str]:
    keys: Set[str] = set()
    path = (locator_path or "").lower()
    if path:
        keys.add(path)
        keys.add(Path(path).name.lower())
        stem = sheet_stem(path)
        keys.add(stem)
        keys.add(stem.replace("_", " ").replace("-", " "))
        keys.add(stem.replace("_", "-"))
    for h in heading_path or []:
        keys.add(str(h).strip().lower())
    for m in _SECTION_ID_RE.finditer(text or ""):
        sid = (m.group(1) or m.group(2) or "").lower()
        keys.add(sid)
        keys.add(f"v{sid}")
    for m in re.finditer(r"\b(\d+\.\d+\.\d+)\b", text or ""):
        keys.add(m.group(1).lower())
    keys.discard("")
    return keys


def top2_cre_external_ids(
    envelope: Dict[str, Any], uuid_to_ext: Dict[str, str]
) -> List[str]:
    """Prefer retrieval.reranked order; fall back to suggested/links."""
    ordered: List[str] = []

    def add(cre_id: Optional[str]) -> None:
        if not cre_id:
            return
        ext = uuid_to_ext.get(cre_id, cre_id)
        if ext not in ordered:
            ordered.append(ext)

    retrieval = envelope.get("retrieval") or {}
    for key in ("reranked", "candidates"):
        for cand in retrieval.get(key) or []:
            if isinstance(cand, dict):
                add(cand.get("cre_id"))
            if len(ordered) >= 2:
                return ordered[:2]
    for field in ("links", "suggested_links"):
        for link in envelope.get(field) or []:
            if isinstance(link, dict):
                add(link.get("cre_id"))
            if len(ordered) >= 2:
                return ordered[:2]
    return ordered[:2]


def match_gold(keys: Set[str], key_to_cres: Dict[str, Set[str]]) -> Set[str]:
    gold: Set[str] = set()
    for k in keys:
        if k in key_to_cres:
            gold |= key_to_cres[k]
        for gk, cres in key_to_cres.items():
            if len(k) >= 8 and (k in gk or gk in k):
                gold |= cres
    return gold


def _resource_for(repo: str, path: str, chunk_id: str) -> Optional[Dict[str, Any]]:
    for spec in RESOURCE_SPECS:
        if spec["repo_substr"] in (repo or path or chunk_id):
            return spec
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENCRE_BASE_URL", "https://opencre.org"),
    )
    parser.add_argument(
        "--cache-file",
        default=os.environ.get(
            "DEV_DATABASE_URL", "postgresql://cre:password@127.0.0.1:5432/cre"
        ),
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=ART / "b1_accuracy_report.json",
    )
    args = parser.parse_args()

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    gold_by_resource: Dict[str, Dict[str, Set[str]]] = {}
    for spec in RESOURCE_SPECS:
        nodes = fetch_standard_nodes(args.base_url, spec["api_name"])
        gold_by_resource[spec["label"]] = build_gold_index(nodes)
        print(
            f"gold {spec['label']}: nodes={len(nodes)} "
            f"index_keys={len(gold_by_resource[spec['label']])}",
            flush=True,
        )

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import CRE, DecisionQueueItem

    db_connect(args.cache_file)
    uuid_to_ext = {
        row.id: (row.external_id or row.id)
        for row in sqla.session.query(CRE.id, CRE.external_id).all()
    }

    decisions = (
        sqla.session.query(DecisionQueueItem)
        .filter_by(pipeline_run_id=args.run_id)
        .all()
    )

    # Sheet-level aggregation for Cheat Sheets
    sheet_pred: Dict[str, Set[str]] = defaultdict(set)
    sheet_gold: Dict[str, Set[str]] = {}
    sheet_meta: Dict[str, Dict[str, Any]] = {}

    chunk_scorable = 0
    chunk_hits = 0
    details: List[Dict[str, Any]] = []
    unaligned = 0

    for row in decisions:
        env = row.envelope if isinstance(row.envelope, dict) else {}
        knowledge = env.get("knowledge") or {}
        text = knowledge.get("text") or ""
        loc = knowledge.get("locator") or {}
        path = loc.get("path") or loc.get("id") or ""
        src = knowledge.get("source") or {}
        repo = str(src.get("repository") or "")
        chunk_id = row.chunk_id or ""
        if not repo and chunk_id.startswith("chk:art:"):
            body = chunk_id[len("chk:art:") :]
            art = body.rsplit(":", 1)[0]
            if art.startswith("OWASP/"):
                bits = art.split(":", 1)
                repo = bits[0]
                if len(bits) > 1 and not path:
                    path = bits[1]

        spec = _resource_for(repo, path, chunk_id)
        if not spec:
            continue

        keys = chunk_keys(text, path, [])
        gold = match_gold(keys, gold_by_resource[spec["label"]])
        top2 = top2_cre_external_ids(env, uuid_to_ext)
        top2_ext = [t for t in top2 if t]

        if spec["grain"] == "sheet":
            stem = sheet_stem(path) or sheet_stem(chunk_id)
            if not stem:
                unaligned += 1
                continue
            sheet_pred[stem].update(top2_ext)
            if stem not in sheet_gold:
                sheet_keys = {
                    stem,
                    stem.replace("_", " "),
                    stem.replace("_", "-"),
                    f"{stem}.md",
                    f"{stem}.html",
                    path.lower() if path else "",
                }
                sheet_keys.discard("")
                sheet_gold[stem] = match_gold(
                    sheet_keys, gold_by_resource[spec["label"]]
                )
            sheet_meta[stem] = {
                "resource": spec["label"],
                "path": path,
                "grain": "sheet",
            }
            continue

        # ASVS chunk grain
        if not gold:
            unaligned += 1
            details.append(
                {
                    "chunk_id": chunk_id,
                    "resource": spec["label"],
                    "grain": "chunk",
                    "aligned": False,
                    "top2": top2_ext,
                    "gold_size": 0,
                    "hit": False,
                }
            )
            continue

        chunk_scorable += 1
        hit = any(t in gold for t in top2_ext)
        if hit:
            chunk_hits += 1
        details.append(
            {
                "chunk_id": chunk_id,
                "resource": spec["label"],
                "grain": "chunk",
                "aligned": True,
                "top2": top2_ext,
                "gold_sample": sorted(gold)[:8],
                "hit": hit,
                "keys_sample": sorted(keys)[:8],
            }
        )

    sheet_scorable = 0
    sheet_hits = 0
    for stem, pred in sorted(sheet_pred.items()):
        gold = sheet_gold.get(stem) or set()
        meta = sheet_meta.get(stem) or {}
        if not gold:
            unaligned += 1
            details.append(
                {
                    "sheet": stem,
                    "resource": meta.get("resource", "CheatSheetSeries"),
                    "grain": "sheet",
                    "aligned": False,
                    "predicted": sorted(pred)[:12],
                    "gold_size": 0,
                    "hit": False,
                }
            )
            continue
        sheet_scorable += 1
        hit = bool(pred & gold)
        if hit:
            sheet_hits += 1
        details.append(
            {
                "sheet": stem,
                "resource": meta.get("resource", "CheatSheetSeries"),
                "grain": "sheet",
                "aligned": True,
                "predicted": sorted(pred)[:12],
                "gold_sample": sorted(gold)[:12],
                "hit": hit,
                "path": meta.get("path"),
            }
        )

    scorable = chunk_scorable + sheet_scorable
    hits = chunk_hits + sheet_hits
    rate = (hits / scorable) if scorable else 0.0
    report = {
        "run_id": args.run_id,
        "base_url": args.base_url,
        "rule": {
            "ASVS": "chunk: ≥1 of top-2 suggested CRE external_ids ∈ section gold",
            "CheatSheetSeries": (
                "sheet: union of top-2 across chunks; hit if ∩ sheet gold nonempty"
            ),
        },
        "resources": [s["label"] for s in RESOURCE_SPECS],
        "decisions_total": len(decisions),
        "scorable": scorable,
        "unaligned": unaligned,
        "hits": hits,
        "accuracy": round(rate, 4),
        "pass_gt_60": rate > 0.60,
        "by_grain": {
            "ASVS_chunk": {
                "scorable": chunk_scorable,
                "hits": chunk_hits,
                "accuracy": round(
                    (chunk_hits / chunk_scorable) if chunk_scorable else 0.0, 4
                ),
            },
            "CheatSheetSeries_sheet": {
                "scorable": sheet_scorable,
                "hits": sheet_hits,
                "accuracy": round(
                    (sheet_hits / sheet_scorable) if sheet_scorable else 0.0, 4
                ),
            },
        },
        "details": details[:200],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in report if k != "details"}, indent=2))
    print(f"wrote {args.out}", flush=True)
    return 0 if scorable else 2


if __name__ == "__main__":
    sys.exit(main())
