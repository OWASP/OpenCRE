#!/usr/bin/env python3
"""
Monitor production (or staging) gap-analysis health over HTTP.

Alerts when map_analysis responses are incomplete, especially HTTP 503 which
indicates the Heroku Neo4j/Redis fallback regression path.

Exit codes:
  0 — all directed GA pairs return 200 with material ``result``
  1 — incomplete pairs and/or 503 responses detected
  2 — configuration or request failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any


def _http_gap_result_is_material(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, dict):
        return len(result) > 0
    if isinstance(result, list):
        return len(result) > 0
    return bool(result)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENCRE_GA_MONITOR_BASE_URL", "https://opencre.org"),
        help="OpenCRE base URL (default: https://opencre.org)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("OPENCRE_GA_MONITOR_TIMEOUT", "40")),
        help="HTTP timeout in seconds (default: 40)",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional output JSON report path",
    )
    parser.add_argument(
        "--max-failures-print",
        type=int,
        default=50,
        help="Max individual incomplete pairs to print (default: 50)",
    )
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("OPENCRE_GA_MONITOR_WEBHOOK_URL", ""),
        help="Optional webhook URL for alert payload (JSON POST)",
    )
    return parser.parse_args()


def _get_json(url: str, timeout: int) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_pair(
    base_rest: str, sa: str, sb: str, timeout: int
) -> dict[str, Any] | None:
    if sa == sb:
        return None
    query = urllib.parse.urlencode([("standard", sa), ("standard", sb)])
    url = f"{base_rest}/map_analysis?{query}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        code = exc.code
        body = (exc.read() or b"").decode("utf-8", errors="replace")
    except Exception as exc:
        return {
            "pair": f"{sa}->{sb}",
            "status_code": None,
            "bucket": "request_exception",
            "error": str(exc),
        }

    body_preview = body.strip().replace("\n", " ")[:200]
    if code != 200:
        bucket = f"http_{code}"
        if code == 503:
            bucket = "http_503_regression"
        return {
            "pair": f"{sa}->{sb}",
            "status_code": code,
            "bucket": bucket,
            "body_preview": body_preview,
        }

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {
            "pair": f"{sa}->{sb}",
            "status_code": 200,
            "bucket": "invalid_json_200",
            "body_preview": body_preview,
        }

    result = payload.get("result")
    if _http_gap_result_is_material(result):
        return None
    if result is not None and not _http_gap_result_is_material(result):
        return {
            "pair": f"{sa}->{sb}",
            "status_code": 200,
            "bucket": "empty_result_200",
            "body_preview": body_preview,
        }
    if payload.get("job_id"):
        return {
            "pair": f"{sa}->{sb}",
            "status_code": 200,
            "bucket": "job_id_only",
            "job_id": payload.get("job_id"),
        }
    return {
        "pair": f"{sa}->{sb}",
        "status_code": 200,
        "bucket": "missing_result",
        "body_preview": body_preview,
    }


def _post_webhook(webhook_url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"webhook returned HTTP {resp.status}")


def main() -> int:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")
    rest = f"{base_url}/rest/v1"
    timeout = args.timeout_seconds

    try:
        standards = _get_json(f"{rest}/ga_standards", timeout)
    except Exception as exc:
        print(f"Failed to fetch ga_standards from {base_url}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(standards, list):
        print("ga_standards response is not a list", file=sys.stderr)
        return 2

    failures: list[dict[str, Any]] = []
    success_count = 0
    total_pairs = 0
    bucket_counts: Counter[str] = Counter()

    for sa in standards:
        for sb in standards:
            if sa == sb:
                continue
            total_pairs += 1
            item = _check_pair(rest, sa, sb, timeout)
            if item is None:
                success_count += 1
                bucket_counts["ok_result"] += 1
            else:
                failures.append(item)
                bucket_counts[item["bucket"]] += 1

    report: dict[str, Any] = {
        "base_url": base_url,
        "ga_standards_count": len(standards),
        "directed_pairs_tested": total_pairs,
        "complete_pairs": success_count,
        "incomplete_pairs": len(failures),
        "buckets": dict(bucket_counts),
        "incomplete_examples": failures[: args.max_failures_print],
        "alert": len(failures) > 0,
        "regression_503_count": bucket_counts.get("http_503_regression", 0),
    }

    print(
        f"GA health check for {base_url}: "
        f"{success_count}/{total_pairs} complete, {len(failures)} incomplete"
    )
    if bucket_counts.get("http_503_regression"):
        print(
            f"ALERT: {bucket_counts['http_503_regression']} pair(s) returned HTTP 503 "
            "(Heroku Neo4j/Redis fallback regression)"
        )
    if failures:
        print("Incomplete buckets:")
        for key, count in sorted(bucket_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if key == "ok_result":
                continue
            print(f"  - {key}: {count}")
        print("Incomplete pair samples:")
        for item in failures[: args.max_failures_print]:
            print(f"  - {item['pair']} [{item['bucket']}]")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(f"Wrote report: {args.output_json}")

    if args.webhook_url and failures:
        try:
            _post_webhook(args.webhook_url, report)
            print(f"Posted alert to webhook ({len(failures)} incomplete pairs)")
        except Exception as exc:
            print(f"Webhook alert failed: {exc}", file=sys.stderr)
            return 2

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
