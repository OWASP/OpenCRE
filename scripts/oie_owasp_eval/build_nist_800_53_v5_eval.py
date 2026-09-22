#!/usr/bin/env python3
"""Build NIST 800-53 v5 eval gold (opencre.org Links) + OSCAL Module A sources.

Gold (CRE answer key)::

  application/tests/fixtures/owasp_mappings/nist_800_53_v5.json

Sources (control statement + guidance from usnistgov OSCAL catalog)::

  scripts/oie_owasp_eval/fixtures/b2_sources/nist_800_53_v5/<SECTION_ID>.txt

Usage::

  PYTHONPATH=. python scripts/oie_owasp_eval/build_nist_800_53_v5_eval.py
  PYTHONPATH=. python scripts/oie_owasp_eval/build_nist_800_53_v5_eval.py --sample 48
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_GOLD = (
    ROOT
    / "application"
    / "tests"
    / "fixtures"
    / "owasp_mappings"
    / "nist_800_53_v5.json"
)
DEFAULT_SOURCES = (
    ROOT / "scripts" / "oie_owasp_eval" / "fixtures" / "b2_sources" / "nist_800_53_v5"
)
OSCAL_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/"
    "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
)
OSCAL_CACHE = ROOT / "tmp" / "oie_owasp_eval" / "nist_sp80053_rev5_catalog.json"
BASE_URL = "https://opencre.org"
USER_AGENT = "OpenCRE-NIST80053-EvalGold/1.0"
STANDARD_NAME = "NIST 800-53 v5"

# Hub uses AC-2 / IA-2(1); OSCAL labels are AC-02 / IA-02(01).
_LABEL_RE = re.compile(
    r"^([A-Z]{1,4})-0*(\d+)(?:\((0*)(\d+)\))?$",
    re.IGNORECASE,
)


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def normalize_control_id(raw: str) -> str:
    """Map ``AC-02`` / ``IA-02(01)`` / ``ac-2.1`` → hub-style ``AC-2`` / ``IA-2(1)``."""
    s = (raw or "").strip().upper().replace("_", "-")
    # OSCAL dotted enhancement id: ia-2.1 / IA-02.01
    dotted = re.match(r"^([A-Z]{1,4})-0*(\d+)\.0*(\d+)$", s)
    if dotted:
        return f"{dotted.group(1)}-{int(dotted.group(2))}({int(dotted.group(3))})"
    m = _LABEL_RE.match(s)
    if m:
        fam = m.group(1).upper()
        num = int(m.group(2))
        if m.group(4) is not None:
            return f"{fam}-{num}({int(m.group(4))})"
        return f"{fam}-{num}"
    # Already hub-ish: AC-2(1)
    m2 = re.match(r"^([A-Z]{1,4})-(\d+)(?:\((\d+)\))?$", s, re.IGNORECASE)
    if not m2:
        return s
    fam, num, enh = m2.group(1).upper(), m2.group(2), m2.group(3)
    return f"{fam}-{int(num)}" + (f"({int(enh)})" if enh else "")


def sid_from_node(node: Mapping[str, Any]) -> Optional[str]:
    for key in ("sectionID", "section_id"):
        val = node.get(key)
        if val:
            return normalize_control_id(str(val))
    section = str(node.get("section") or "")
    m = re.match(r"^([A-Z]{1,4}-\d+(?:\([0-9]+\))?)\b", section, re.I)
    if m:
        return normalize_control_id(m.group(1))
    return None


def cre_ids_from_node(node: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for link in node.get("links") or []:
        if not isinstance(link, dict):
            continue
        doc = link.get("document") or {}
        if str(doc.get("doctype") or "").upper() != "CRE":
            continue
        cid = str(doc.get("id") or "").strip()
        if cid and cid not in out:
            out.append(cid)
    return out


def fetch_hub_nodes(*, base_url: str = BASE_URL) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"{base_url.rstrip('/')}/rest/v1/Standard/"
            f"{urllib.parse.quote(STANDARD_NAME)}?page={page}"
        )
        data = _get_json(url)
        batch = data.get("standards") or []
        if not batch:
            break
        rows.extend(batch)
        total_pages = int(data.get("total_pages") or page)
        if page >= total_pages:
            break
        page += 1
    return rows


def build_gold_rows(nodes: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for node in nodes:
        sid = sid_from_node(node)
        cres = cre_ids_from_node(node)
        if not sid or not cres:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        rows.append(
            {
                "section_id": sid,
                "section": str(node.get("section") or sid),
                "hyperlink": str(node.get("hyperlink") or ""),
                "cre_ids": cres,
                "gold_provenance": {
                    "kind": "hub_links",
                    "method": "opencre_org_standard_api",
                    "standard": STANDARD_NAME,
                },
            }
        )
    rows.sort(key=lambda r: r["section_id"])
    return rows


def stratified_sample(
    rows: Sequence[Dict[str, Any]], n: int
) -> List[Dict[str, Any]]:
    """Take up to ``n`` rows, round-robin across control families."""
    if n <= 0 or n >= len(rows):
        return list(rows)
    by_fam: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        fam = str(row["section_id"]).split("-", 1)[0]
        by_fam[fam].append(row)
    families = sorted(by_fam.keys(), key=lambda f: (-len(by_fam[f]), f))
    out: List[Dict[str, Any]] = []
    idx = {f: 0 for f in families}
    while len(out) < n:
        progressed = False
        for fam in families:
            i = idx[fam]
            bucket = by_fam[fam]
            if i >= len(bucket):
                continue
            out.append(bucket[i])
            idx[fam] = i + 1
            progressed = True
            if len(out) >= n:
                break
        if not progressed:
            break
    out.sort(key=lambda r: r["section_id"])
    for row in out:
        prov = dict(row.get("gold_provenance") or {})
        prov["sample"] = True
        prov["sample_size"] = n
        row["gold_provenance"] = prov
    return out


def _walk_prose(parts: Sequence[Mapping[str, Any]], chunks: List[str]) -> None:
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        prose = part.get("prose")
        if isinstance(prose, str) and prose.strip():
            chunks.append(prose.strip())
        nested = part.get("parts")
        if isinstance(nested, list):
            _walk_prose(nested, chunks)


def load_oscal_index(path: Path) -> Dict[str, Tuple[str, str]]:
    """Map hub-style section id → (title, statement+guidance prose)."""
    catalog = json.loads(path.read_text(encoding="utf-8"))["catalog"]
    index: Dict[str, Tuple[str, str]] = {}

    def add(control: Mapping[str, Any]) -> None:
        label = None
        for prop in control.get("props") or []:
            if isinstance(prop, dict) and prop.get("name") == "label":
                label = str(prop.get("value") or "")
                break
        raw_id = label or str(control.get("id") or "")
        sid = normalize_control_id(raw_id)
        title = str(control.get("title") or sid)
        chunks: List[str] = []
        # Prefer statement + guidance only (skip assessment noise).
        for part in control.get("parts") or []:
            if not isinstance(part, dict):
                continue
            name = str(part.get("name") or "")
            if name not in {"statement", "guidance"}:
                continue
            prose = part.get("prose")
            if isinstance(prose, str) and prose.strip():
                chunks.append(prose.strip())
            _walk_prose(part.get("parts") or [], chunks)
        text = "\n".join(chunks).strip()
        # Strip OSCAL parameter placeholders for cleaner retrieval.
        text = re.sub(r"\{\{\s*insert:[^}]+\}\}", "…", text)
        if sid and text:
            index[sid] = (title, text)
        for sub in control.get("controls") or []:
            if isinstance(sub, dict):
                add(sub)

    for group in catalog.get("groups") or []:
        for control in group.get("controls") or []:
            if isinstance(control, dict):
                add(control)
    return index


def ensure_oscal(cache: Path = OSCAL_CACHE) -> Path:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file() and cache.stat().st_size > 1_000_000:
        return cache
    print(f"GET {OSCAL_URL}", flush=True)
    urllib.request.urlretrieve(OSCAL_URL, cache)
    return cache


def write_sources(
    rows: Sequence[Mapping[str, Any]],
    oscal: Mapping[str, Tuple[str, str]],
    dest: Path,
) -> Dict[str, int]:
    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    missing = 0
    for row in rows:
        sid = str(row["section_id"])
        title, body = oscal.get(sid, ("", ""))
        if not body:
            missing += 1
            continue
        section = str(row.get("section") or title or sid)
        text = (
            f"Source: {sid}\n"
            f"Section-ID: {sid}\n"
            f"Section: {section}\n"
            f"Standard: {STANDARD_NAME}\n\n"
            f"{title}\n\n{body}\n"
        )
        # Match B2 loader: b2_sources/<stem>/<section_id>.txt
        (dest / f"{sid}.txt").write_text(text, encoding="utf-8")
        written += 1
    return {"written": written, "missing_oscal": missing}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-gold", type=Path, default=DEFAULT_OUT_GOLD)
    parser.add_argument("--out-sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="If >0, stratified sample of N controls (default: all hub-linked).",
    )
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--skip-sources", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    print(f"fetching {STANDARD_NAME} from {args.base_url} …", flush=True)
    nodes = fetch_hub_nodes(base_url=args.base_url)
    gold = build_gold_rows(nodes)
    print(f"hub nodes={len(nodes)} gold_rows={len(gold)}", flush=True)
    if args.sample > 0:
        gold = stratified_sample(gold, args.sample)
        print(f"sampled to {len(gold)}", flush=True)

    args.out_gold.parent.mkdir(parents=True, exist_ok=True)
    args.out_gold.write_text(json.dumps(gold, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out_gold}", flush=True)

    if not args.skip_sources:
        oscal_path = ensure_oscal()
        index = load_oscal_index(oscal_path)
        print(f"oscal controls indexed={len(index)}", flush=True)
        stats = write_sources(gold, index, args.out_sources)
        print(json.dumps({"sources_dir": str(args.out_sources), **stats}, indent=2))
        if stats["missing_oscal"]:
            print(
                f"warning: {stats['missing_oscal']} gold ids missing from OSCAL",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
