"""Talk catalogue (title/speaker/date/length per video) as retrievable documents."""

from __future__ import annotations

from typing import Dict, List, Tuple


def parse_catalogue(text: str) -> List[Dict[str, str]]:
    """Lines 'id|YYYYMMDD|seconds|title'; blank or malformed lines are skipped."""
    out: List[Dict[str, str]] = []
    for line in (text or "").splitlines():
        parts = line.rstrip("\n").split("|", 3)
        if len(parts) != 4 or not parts[0].strip() or not parts[3].strip():
            continue
        vid, date, secs, title = (p.strip() for p in parts)
        out.append({"id": vid, "date": date, "seconds": secs, "title": title})
    return out


def _fmt_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else "unknown"


def _fmt_len(s: str) -> str:
    return f"{int(s) // 60} min" if s.isdigit() else "?"


def catalogue_chunks(
    talks: List[Dict[str, str]], per_chunk: int = 30
) -> List[Tuple[str, int, str]]:
    """Newest first; each chunk lists talks as 'date (approx) | length | title | link'."""
    ordered = sorted(talks, key=lambda t: t["date"], reverse=True)
    chunks: List[Tuple[str, int, str]] = []
    for i, start in enumerate(range(0, len(ordered), per_chunk)):
        part = ordered[start : start + per_chunk]
        lines = [
            f"{_fmt_date(t['date'])} (approximate) | {_fmt_len(t['seconds'])} | "
            f"{t['title']} | https://youtu.be/{t['id']}"
            for t in part
        ]
        header = (
            "OWASP Foundation YouTube channel talk catalogue (public talks; speaker names are in the title; "
            "dates are approximate, taken from the channel listing):\n"
        )
        chunks.append(("talks/catalogue.md", i, header + "\n".join(lines)))
    return chunks
