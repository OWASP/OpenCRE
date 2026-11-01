#!/usr/bin/env python3
"""Audit provisional ASVS 5.0 gold quality for chapters V1 / V5 / V15.

Flags rows that are hard to score fairly under leaf-grain exact match:

- empty ``cre_ids``
- multi-CRE soup (2+ gold CREs)
- SPLIT / DELETED / COVERED tags from the v4→v5 YAML
- multi-source v4 remaps
- hub-ish section ids (fewer than 3 dotted parts, e.g. V1 / V1.1)

Writes JSON + Markdown under ``tmp/oie_owasp_eval/experiments/``.

Usage::

    PYTHONPATH=. python scripts/oie_owasp_eval/audit_asvs5_gold_chapters.py
    PYTHONPATH=. python scripts/oie_owasp_eval/audit_asvs5_gold_chapters.py \\
        --chapters V1,V5,V15
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = (
    ROOT
    / "application"
    / "tests"
    / "fixtures"
    / "owasp_mappings"
    / "owasp_asvs_5_0_provisional.json"
)
DEFAULT_OUT_DIR = ROOT / "tmp" / "oie_owasp_eval" / "experiments"

SECTION_ID_RE = re.compile(r"^V(\d+)(?:\.(\d+))?(?:\.(\d+))?$", re.IGNORECASE)


def _chapter(section_id: str) -> Optional[str]:
    m = SECTION_ID_RE.match(section_id.strip())
    if not m:
        return None
    return f"V{m.group(1)}"


def _grain(section_id: str) -> str:
    """requirement | subcategory | category | unknown."""
    m = SECTION_ID_RE.match(section_id.strip())
    if not m:
        return "unknown"
    if m.group(3) is not None:
        return "requirement"
    if m.group(2) is not None:
        return "subcategory"
    return "category"


def _flag_row(row: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    cre_ids = [c for c in (row.get("cre_ids") or []) if c]
    if not cre_ids:
        flags.append("empty_cre_ids")
    elif len(cre_ids) >= 2:
        flags.append("multi_cre_soup")
    sid = str(row.get("section_id") or "")
    grain = _grain(sid)
    if grain in ("category", "subcategory"):
        flags.append(f"hub_grain_{grain}")
    prov = row.get("gold_provenance") or {}
    tags = " | ".join(str(t) for t in (prov.get("mapping_tags") or []))
    upper = tags.upper()
    if "SPLIT" in upper:
        flags.append("tag_split")
    if "DELETED" in upper or "COVERED BY" in upper:
        flags.append("tag_deleted_or_covered")
    sources = prov.get("source_v4_section_ids") or []
    if len(sources) >= 2:
        flags.append("multi_v4_source")
    if not prov:
        flags.append("missing_provenance")
    return flags


def audit(rows: Sequence[Dict[str, Any]], chapters: Set[str]) -> Dict[str, Any]:
    by_chapter: Dict[str, List[Dict[str, Any]]] = {c: [] for c in sorted(chapters)}
    flag_counts: Counter[str] = Counter()
    flagged_rows: List[Dict[str, Any]] = []

    for row in rows:
        sid = str(row.get("section_id") or "")
        ch = _chapter(sid)
        if ch is None or ch not in chapters:
            continue
        flags = _flag_row(row)
        entry = {
            "section_id": sid,
            "cre_ids": list(row.get("cre_ids") or []),
            "grain": _grain(sid),
            "flags": flags,
            "source_v4_section_ids": list(
                (row.get("gold_provenance") or {}).get("source_v4_section_ids") or []
            ),
            "mapping_tags": list(
                (row.get("gold_provenance") or {}).get("mapping_tags") or []
            ),
            "section_preview": (row.get("section") or "")[:160],
        }
        by_chapter[ch].append(entry)
        for f in flags:
            flag_counts[f] += 1
        if flags:
            flagged_rows.append(entry)

    chapter_summary = {}
    for ch, items in by_chapter.items():
        n = len(items)
        flagged = sum(1 for i in items if i["flags"])
        multi = sum(1 for i in items if "multi_cre_soup" in i["flags"])
        empty = sum(1 for i in items if "empty_cre_ids" in i["flags"])
        split = sum(1 for i in items if "tag_split" in i["flags"])
        chapter_summary[ch] = {
            "rows": n,
            "flagged": flagged,
            "clean": n - flagged,
            "multi_cre_soup": multi,
            "empty_cre_ids": empty,
            "tag_split": split,
            "pct_flagged": round(100.0 * flagged / n, 1) if n else 0.0,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapters": sorted(chapters),
        "total_rows": sum(s["rows"] for s in chapter_summary.values()),
        "total_flagged": len(flagged_rows),
        "flag_counts": dict(flag_counts.most_common()),
        "chapter_summary": chapter_summary,
        "flagged_rows": flagged_rows,
        "by_chapter": by_chapter,
    }


def _markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# ASVS 5 provisional gold audit (V1 / V5 / V15)",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        f"Total rows: **{report['total_rows']}** · "
        f"Flagged: **{report['total_flagged']}**",
        "",
        "## Chapter summary",
        "",
        "| Chapter | Rows | Clean | Flagged | % flagged | Multi-CRE | Empty | SPLIT |",
        "|---------|------|-------|---------|-----------|-----------|-------|-------|",
    ]
    for ch, s in report["chapter_summary"].items():
        lines.append(
            f"| {ch} | {s['rows']} | {s['clean']} | {s['flagged']} | "
            f"{s['pct_flagged']} | {s['multi_cre_soup']} | "
            f"{s['empty_cre_ids']} | {s['tag_split']} |"
        )
    lines.extend(["", "## Flag counts", ""])
    for flag, n in (report.get("flag_counts") or {}).items():
        lines.append(f"- `{flag}`: {n}")
    lines.extend(["", "## Flagged rows (sample ≤40)", ""])
    for row in (report.get("flagged_rows") or [])[:40]:
        lines.append(
            f"- **{row['section_id']}** flags=`{','.join(row['flags'])}` "
            f"cres=`{','.join(row['cre_ids']) or '∅'}` "
            f"v4=`{','.join(row['source_v4_section_ids'])}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--chapters",
        default="V1,V5,V15",
        help="Comma-separated ASVS chapter prefixes (default V1,V5,V15)",
    )
    args = parser.parse_args()
    chapters = {c.strip().upper() for c in args.chapters.split(",") if c.strip()}
    rows = json.loads(args.gold.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"expected list gold fixture, got {type(rows)}")
    report = audit(rows, chapters)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out_dir / f"asvs5_gold_audit_v1_v5_v15_{stamp}.json"
    md_path = args.out_dir / f"asvs5_gold_audit_v1_v5_v15_{stamp}.md"
    latest_json = args.out_dir / "asvs5_gold_audit_v1_v5_v15_latest.json"
    latest_md = args.out_dir / "asvs5_gold_audit_v1_v5_v15_latest.md"
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    md = _markdown(report)
    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
