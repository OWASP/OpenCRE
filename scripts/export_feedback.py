#!/usr/bin/env python3
"""Turn thumbs-down answers into candidate evaluation questions for human review.

    python scripts/export_feedback.py --since-days 7 --out feedback-candidates.jsonl

Each line has the question, what the system answered, the rater's comment and empty ``reference`` /
``family`` fields for a reviewer to fill in. Nothing is added to the evaluation set automatically: a
person writes the correct reference (or marks the question as flawed) first. Question text is shared
only after e-mail addresses are removed. Prints a short summary (thumbs up/down counts) to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def build_candidates(
    rows: List[Dict[str, Any]], since: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Newest first, one per distinct question, e-mail addresses removed."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        rated = row.get("rated_at")
        if since and rated and datetime.fromisoformat(rated) < since:
            continue
        key = _norm(row.get("question", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "answer_id": row["id"],
                "rated_at": rated,
                "source": row.get("source"),
                "question": _EMAIL.sub("[email]", row.get("question") or ""),
                "system_answer": _EMAIL.sub("[email]", row.get("answer") or ""),
                "citations": row.get("citations") or [],
                "rater_comment": _EMAIL.sub("[email]", row.get("comment") or ""),
                "flags": row.get("flags"),
                "reference": "",  # reviewer: the correct short answer, or leave empty and set flawed=true
                "family": "",  # reviewer: eval family (definition, count, people_meta, ...)
                "flawed": False,
            }
        )
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--out", default="feedback-candidates.jsonl")
    a = ap.parse_args(argv)

    from application import create_app

    app = create_app(mode="production")
    with app.app_context():
        from application.utils.answer_feedback import list_feedback

        down = list_feedback(rating="down", limit=500)
        up = list_feedback(rating="up", limit=500)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=a.since_days
    )
    recent_up = [
        r
        for r in up
        if r.get("rated_at") and datetime.fromisoformat(r["rated_at"]) >= since
    ]
    candidates = build_candidates(down, since)
    with open(a.out, "w", encoding="utf-8") as fh:
        for c in candidates:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    total = len(candidates) + len(recent_up)
    print(
        f"last {a.since_days} days: {len(recent_up)} thumbs up, {len(candidates)} distinct thumbs-down questions"
        + (f" ({len(candidates) / total:.0%} down)" if total else "")
        + f" -> {a.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
