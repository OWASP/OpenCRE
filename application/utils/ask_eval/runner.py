"""Run the #1078 gold set against ``/rest/v1/completion`` and score it.

Two steps kept apart so scoring stays hermetic:

- ``fetch_live`` asks a running OpenCRE each gold question and returns one record
  per row. Records are written to JSONL, so a live run becomes a fixture.
- ``score_records`` scores recorded responses with ``gold.score_case``. No network.

A record is ``{"id": <gold id>, "status": <http status>, "body": <json body>}``.
Rows with no record are reported as ``missing``; non-200 records as ``errors``.
Both stay out of the metrics so one flaky request does not read as a wrong answer.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from application.utils.ask_eval.gold import (
    GoldRow,
    normalize_completion,
    score_case,
    summarize,
)

Record = Dict[str, Any]
# Cloudflare in front of opencre.org rejects urllib's default agent (error 1010).
USER_AGENT = "opencre-chat-eval/1078"
PostFn = Callable[[str, Mapping[str, Any], Mapping[str, str], int], Tuple[int, Any]]


def _urllib_post(
    url: str, body: Mapping[str, Any], headers: Mapping[str, str], timeout: int
) -> Tuple[int, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, {"error": raw[:500]}


def fetch_live(
    rows: Sequence[GoldRow],
    base_url: str,
    *,
    token: Optional[str] = None,
    timeout: int = 120,
    post: Optional[PostFn] = None,
) -> List[Record]:
    """POST each gold question to ``/rest/v1/completion``, one record per row."""
    send = post or _urllib_post
    url = base_url.rstrip("/") + "/rest/v1/completion"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    records: List[Record] = []
    for row in rows:
        try:
            status, body = send(url, {"prompt": row.question}, headers, timeout)
        except (OSError, ValueError) as exc:
            status, body = 0, {"error": f"{type(exc).__name__}: {exc}"}
        records.append({"id": row.id, "status": status, "body": body})
    return records


def write_records(path: Path, records: Sequence[Record]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")


def load_records(path: Path) -> List[Record]:
    out: List[Record] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def score_records(rows: Sequence[GoldRow], records: Sequence[Record]) -> Dict[str, Any]:
    """Score recorded responses against the gold rows they answer."""
    by_id = {str(r.get("id")): r for r in records}
    scores = []
    missing: List[str] = []
    errors: Dict[str, int] = {}
    for row in rows:
        rec = by_id.get(row.id)
        if rec is None:
            missing.append(row.id)
            continue
        body = rec.get("body")
        if rec.get("status") != 200 or not isinstance(body, Mapping):
            errors[row.id] = int(rec.get("status") or 0)
            continue
        scores.append(score_case(row, normalize_completion(body)))
    report = summarize(scores)
    report["missing"] = missing
    report["errors"] = errors
    report["cases"] = [dict(asdict(s), passed=s.passed) for s in scores]
    return report


def compare_reports(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Dict[str, Any]:
    """Which cases flipped between two scored runs (e.g. current chat vs #1161)."""
    before = {c["id"]: c["passed"] for c in baseline.get("cases", [])}
    after = {c["id"]: c["passed"] for c in candidate.get("cases", [])}
    both = sorted(set(before) & set(after))
    metrics = (
        "passed",
        "cre_recall",
        "cre_precision",
        "cite_group_recall",
        "abstain_correct",
    )
    return {
        "fixed": [i for i in both if after[i] and not before[i]],
        "broken": [i for i in both if before[i] and not after[i]],
        "metrics": {m: [baseline.get(m), candidate.get(m)] for m in metrics},
    }
