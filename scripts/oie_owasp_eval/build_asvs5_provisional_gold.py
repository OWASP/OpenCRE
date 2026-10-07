#!/usr/bin/env python3
"""Build provisional ASVS 5.0 gold from opencre.org ASVS 4 Links + official YAML.

Transfers CRE links from production ASVS 4.x nodes onto ASVS 5.0 section ids
using OWASP's ``mapping_v4.0.3_to_v5.0.0.yml``. Pure DELETED rows with no v5
target are skipped. Emit path:

  application/tests/fixtures/owasp_mappings/owasp_asvs_5_0_provisional.json

Each row carries ``gold_provenance`` marking the remapped answer key as
provisional (not mentor-verified ASVS 5 Links).

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/build_asvs5_provisional_gold.py
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    ROOT
    / "application"
    / "tests"
    / "fixtures"
    / "owasp_mappings"
    / "owasp_asvs_5_0_provisional.json"
)
DEFAULT_BASE_URL = "https://opencre.org"
DEFAULT_MAPPING_URL = (
    "https://raw.githubusercontent.com/OWASP/ASVS/master/5.0/mappings/"
    "mapping_v4.0.3_to_v5.0.0.yml"
)
DEFAULT_CSV_URL = (
    "https://raw.githubusercontent.com/OWASP/ASVS/master/5.0/docs_en/"
    "OWASP_Application_Security_Verification_Standard_5.0.0_en.csv"
)

USER_AGENT = "OpenCRE-ASVS5-ProvisionalGold/1.0"
MAPPING_YAML_LABEL = "OWASP/ASVS mapping_v4.0.3_to_v5.0.0.yml"
GOLD_KIND = "provisional"
GOLD_METHOD = "asvs4_opencre_links_via_official_v4_to_v5_yaml"

# Official ASVS 5.0 English chapter markdown (for stable hyperlinks).
ASVS5_CHAPTER_MD: Mapping[str, str] = {
    "V1": "0x10-V1-Encoding-and-Sanitization.md",
    "V2": "0x11-V2-Validation-and-Business-Logic.md",
    "V3": "0x12-V3-Web-Frontend-Security.md",
    "V4": "0x13-V4-API-and-Web-Service.md",
    "V5": "0x14-V5-File-Handling.md",
    "V6": "0x15-V6-Authentication.md",
    "V7": "0x16-V7-Session-Management.md",
    "V8": "0x17-V8-Authorization.md",
    "V9": "0x18-V9-Self-contained-Tokens.md",
    "V10": "0x19-V10-OAuth-and-OIDC.md",
    "V11": "0x20-V11-Cryptography.md",
    "V12": "0x21-V12-Secure-Communication.md",
    "V13": "0x22-V13-Configuration.md",
    "V14": "0x23-V14-Data-Protection.md",
    "V15": "0x24-V15-Secure-Coding-and-Architecture.md",
    "V16": "0x25-V16-Security-Logging-and-Error-Handling.md",
    "V17": "0x26-V17-WebRTC.md",
}

V4_KEY_RE = re.compile(r"^v4\.0\.3-(.+)$", re.IGNORECASE)
V5_ID_RE = re.compile(r"v5\.0\.0-(\d+(?:\.\d+)*)", re.IGNORECASE)
SECTION_ID_RE = re.compile(r"^V?\d+(?:\.\d+)*$", re.IGNORECASE)


def _http_get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def normalize_section_id(raw: str) -> str:
    """Normalize ``1.1.1`` / ``v1.1.1`` / ``V1.1.1`` → ``V1.1.1``."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError(f"unrecognized ASVS section id: {raw!r}")
    if text[0] in "Vv" and SECTION_ID_RE.match(text):
        return "V" + text[1:]
    if SECTION_ID_RE.match(text):
        return "V" + text if not text.upper().startswith("V") else "V" + text[1:]
    raise ValueError(f"unrecognized ASVS section id: {raw!r}")


def chapter_id_for(section_id: str) -> str:
    """``V13.1.1`` → ``V13``."""
    sid = normalize_section_id(section_id)
    return "V" + sid[1:].split(".", 1)[0]


def hyperlink_for(section_id: str) -> str:
    sid = normalize_section_id(section_id)
    chapter = chapter_id_for(sid)
    md = ASVS5_CHAPTER_MD.get(chapter)
    if not md:
        return f"https://github.com/OWASP/ASVS/tree/master/5.0/en#{sid}"
    return f"https://github.com/OWASP/ASVS/blob/master/5.0/en/{md}#{sid.lower()}"


def human_cre_ids(node: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for link in node.get("links") or []:
        doc = link.get("document") or {}
        if str(doc.get("doctype") or "").upper() != "CRE":
            continue
        cid = str(doc.get("id") or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def fetch_asvs_nodes(base_url: str) -> List[Dict[str, Any]]:
    base = base_url.rstrip("/")
    url = f"{base}/rest/v1/Standard/{quote('ASVS')}"
    payload = json.loads(_http_get(url).decode("utf-8"))
    nodes = list(payload.get("standards") or [])
    total = int(payload.get("total_pages") or 1)
    for page in range(2, total + 1):
        page_url = f"{url}?page={page}"
        page_payload = json.loads(_http_get(page_url).decode("utf-8"))
        nodes.extend(page_payload.get("standards") or [])
    return nodes


def index_v4_cre_links(
    nodes: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Map normalized v4 section id → {cre_ids, section, hyperlink}."""
    index: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        raw_sid = str(node.get("sectionID") or "").strip()
        if not raw_sid:
            nid = str(node.get("id") or "")
            m = re.match(r"^ASVS:(V?[\d.]+):", nid, re.IGNORECASE)
            if not m:
                continue
            raw_sid = m.group(1)
        try:
            sid = normalize_section_id(raw_sid)
        except ValueError:
            continue
        cres = human_cre_ids(node)
        if not cres:
            continue
        existing = index.get(sid)
        if existing is None:
            index[sid] = {
                "cre_ids": list(cres),
                "section": str(node.get("section") or "").strip(),
                "hyperlink": str(node.get("hyperlink") or "").strip(),
            }
            continue
        seen = set(existing["cre_ids"])
        for cid in cres:
            if cid not in seen:
                existing["cre_ids"].append(cid)
                seen.add(cid)
    return index


def load_mapping_yaml(url: str) -> Mapping[str, Any]:
    raw = _http_get(url)
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"mapping YAML root must be a mapping, got {type(data)}")
    return data


def load_asvs5_csv(url: str) -> Dict[str, Dict[str, str]]:
    """Map ``V1.1.1`` → {section, chapter_id, req_id} from the official CSV."""
    text = _http_get(url).decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    out: Dict[str, Dict[str, str]] = {}
    for row in reader:
        req_id = str(row.get("req_id") or "").strip()
        if not req_id:
            continue
        try:
            sid = normalize_section_id(req_id)
        except ValueError:
            continue
        out[sid] = {
            "section": str(row.get("req_description") or "").strip(),
            "chapter_id": str(row.get("chapter_id") or "").strip(),
            "req_id": req_id,
        }
    return out


def parse_v5_targets(tag: str) -> List[str]:
    """Extract normalized v5 section ids from a mapping tag string."""
    targets: List[str] = []
    seen: Set[str] = set()
    for match in V5_ID_RE.finditer(tag or ""):
        sid = normalize_section_id(match.group(1))
        if sid not in seen:
            seen.add(sid)
            targets.append(sid)
    return targets


def transfer_cres(
    mapping: Mapping[str, Any],
    v4_index: Mapping[str, Mapping[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
    """Union v4 CRE ids onto v5 section ids."""
    acc: Dict[str, Dict[str, Any]] = {}
    stats = {
        "mapping_entries": 0,
        "deleted_v4_only": 0,
        "mapped_with_targets": 0,
        "v4_missing_on_opencre": 0,
        "v4_with_cres_transferred": 0,
    }

    for key, value in mapping.items():
        stats["mapping_entries"] += 1
        key_m = V4_KEY_RE.match(str(key))
        if not key_m:
            continue
        try:
            v4_sid = normalize_section_id(key_m.group(1))
        except ValueError:
            continue
        if isinstance(value, dict):
            tag = str(value.get("tag-v5.0.0") or value.get("tag") or "")
        else:
            tag = str(value or "")
        targets = parse_v5_targets(tag)
        if not targets:
            stats["deleted_v4_only"] += 1
            continue
        stats["mapped_with_targets"] += 1
        v4_row = v4_index.get(v4_sid)
        if not v4_row:
            stats["v4_missing_on_opencre"] += 1
            continue
        cres = list(v4_row.get("cre_ids") or [])
        if not cres:
            stats["v4_missing_on_opencre"] += 1
            continue
        stats["v4_with_cres_transferred"] += 1
        for v5_sid in targets:
            bucket = acc.get(v5_sid)
            if bucket is None:
                bucket = {
                    "cre_ids": [],
                    "source_v4_section_ids": [],
                    "mapping_tags": [],
                }
                acc[v5_sid] = bucket
            cre_seen: Set[str] = set(bucket["cre_ids"])
            for cid in cres:
                if cid not in cre_seen:
                    bucket["cre_ids"].append(cid)
                    cre_seen.add(cid)
            if v4_sid not in bucket["source_v4_section_ids"]:
                bucket["source_v4_section_ids"].append(v4_sid)
            if tag and tag not in bucket["mapping_tags"]:
                bucket["mapping_tags"].append(tag)

    return acc, stats


def _section_sort_key(sid: str) -> Tuple[Any, ...]:
    parts = normalize_section_id(sid)[1:].split(".")
    out: List[Any] = []
    for part in parts:
        out.append(int(part) if part.isdigit() else part)
    return tuple(out)


def build_fixture_rows(
    transferred: Mapping[str, Mapping[str, Any]],
    asvs5_csv: Mapping[str, Mapping[str, str]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    rows: List[Dict[str, Any]] = []
    stats = {
        "mapped_v5_with_cres": 0,
        "unmapped_new_v5": 0,
        "transferred_missing_csv_text": 0,
    }
    mapped_ids = set(transferred.keys())
    for sid in asvs5_csv.keys():
        if sid not in mapped_ids:
            stats["unmapped_new_v5"] += 1

    for sid in sorted(transferred.keys(), key=_section_sort_key):
        bucket = transferred[sid]
        cre_ids = list(bucket.get("cre_ids") or [])
        if not cre_ids:
            continue
        csv_row = asvs5_csv.get(sid) or {}
        section = str(csv_row.get("section") or "").strip()
        if not section:
            stats["transferred_missing_csv_text"] += 1
            section = f"ASVS 5.0 requirement {sid} (provisional; text unavailable)"
        tags = list(bucket.get("mapping_tags") or [])
        rows.append(
            {
                "section_id": sid,
                "section": section,
                "hyperlink": hyperlink_for(sid),
                "cre_ids": cre_ids,
                "gold_provenance": {
                    "kind": GOLD_KIND,
                    "method": GOLD_METHOD,
                    "mapping_yaml": MAPPING_YAML_LABEL,
                    "source_v4_section_ids": list(
                        bucket.get("source_v4_section_ids") or []
                    ),
                    "mapping_tags": tags,
                },
            }
        )
        stats["mapped_v5_with_cres"] += 1
    return rows, stats


def build(
    *,
    base_url: str,
    mapping_url: str,
    csv_url: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    nodes = fetch_asvs_nodes(base_url)
    v4_index = index_v4_cre_links(nodes)
    mapping = load_mapping_yaml(mapping_url)
    asvs5_csv = load_asvs5_csv(csv_url)
    transferred, xfer_stats = transfer_cres(mapping, v4_index)
    rows, row_stats = build_fixture_rows(transferred, asvs5_csv)
    summary: Dict[str, Any] = {
        "opencre_asvs_nodes": len(nodes),
        "opencre_v4_sections_with_cres": len(v4_index),
        "asvs5_csv_requirements": len(asvs5_csv),
        "fixture_rows": len(rows),
        **xfer_stats,
        **row_stats,
        "sources": {
            "opencre_base_url": base_url,
            "mapping_url": mapping_url,
            "csv_url": csv_url,
        },
    }
    return rows, summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--mapping-url", default=DEFAULT_MAPPING_URL)
    parser.add_argument("--csv-url", default=DEFAULT_CSV_URL)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="optional path for denominator / provenance summary JSON",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    rows, summary = build(
        base_url=args.base_url,
        mapping_url=args.mapping_url,
        csv_url=args.csv_url,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(f"wrote {len(rows)} rows to {args.out}")
    print(
        "denominators: "
        f"mapped_v5_with_cres={summary['mapped_v5_with_cres']} "
        f"unmapped_new_v5={summary['unmapped_new_v5']} "
        f"deleted_v4_only={summary['deleted_v4_only']} "
        f"v4_missing_on_opencre={summary['v4_missing_on_opencre']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
