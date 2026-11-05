#!/usr/bin/env python3
"""
Verify GA completeness by checking all directed GA standard pairs over HTTP.

A pair is considered complete only when:
  - /rest/v1/map_analysis returns 200, and
  - payload contains a non-empty "result" (empty object ``{}`` or empty list ``[]``
    counts as incomplete — same rule as material GA cache in SQL).

Any non-200 response, malformed JSON, missing "result", "job_id"-only payload,
or an empty structured ``result``, is treated as incomplete.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

import requests


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
        default="https://opencre.org",
        help="OpenCRE base URL (default: https://opencre.org)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=40,
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
        default=100,
        help="Max individual incomplete pairs to print (default: 100)",
    )
    return parser.parse_args()


def _canon_base_url(url: str) -> str:
    return url.rstrip("/")


def main() -> int:
    args = _parse_args()
    base_url = _canon_base_url(args.base_url)
    rest = f"{base_url}/rest/v1"
    timeout = args.timeout_seconds

    standards_resp = requests.get(f"{rest}/ga_standards", timeout=timeout)
    standards_resp.raise_for_status()
    standards = standards_resp.json()
    if not isinstance(standards, list):
        raise RuntimeError("ga_standards response is not a list")

    failures: list[dict[str, Any]] = []
    success_count = 0
    total_pairs = 0
    bucket_counts: Counter[str] = Counter()

    for sa in standards:
        for sb in standards:
            if sa == sb:
                continue
            total_pairs += 1
            try:
                resp = requests.get(
                    f"{rest}/map_analysis",
                    params=[("standard", sa), ("standard", sb)],
                    timeout=timeout,
                )
                body_preview = (resp.text or "").strip().replace("\n", " ")[:200]
                if resp.status_code != 200:
                    bucket = f"http_{resp.status_code}"
                    bucket_counts[bucket] += 1
                    failures.append(
                        {
                            "pair": f"{sa}->{sb}",
                            "status_code": resp.status_code,
                            "bucket": bucket,
                            "body_preview": body_preview,
                        }
                    )
                    continue

                try:
                    payload = resp.json()
                except json.JSONDecodeError:
                    bucket = "invalid_json_200"
                    bucket_counts[bucket] += 1
                    failures.append(
                        {
                            "pair": f"{sa}->{sb}",
                            "status_code": 200,
                            "bucket": bucket,
                            "body_preview": body_preview,
                        }
                    )
                    continue

                result = payload.get("result")
                if _http_gap_result_is_material(result):
                    success_count += 1
                    bucket_counts["ok_result"] += 1
                elif result is not None and not _http_gap_result_is_material(result):
                    bucket = "empty_result_200"
                    bucket_counts[bucket] += 1
                    failures.append(
                        {
                            "pair": f"{sa}->{sb}",
                            "status_code": 200,
                            "bucket": bucket,
                            "body_preview": body_preview,
                        }
                    )
                elif payload.get("job_id"):
                    bucket = "job_id_only"
                    bucket_counts[bucket] += 1
                    failures.append(
                        {
                            "pair": f"{sa}->{sb}",
                            "status_code": 200,
                            "bucket": bucket,
                            "job_id": payload.get("job_id"),
                        }
                    )
                else:
                    bucket = "missing_result"
                    bucket_counts[bucket] += 1
                    failures.append(
                        {
                            "pair": f"{sa}->{sb}",
                            "status_code": 200,
                            "bucket": bucket,
                            "body_preview": body_preview,
                        }
                    )
            except requests.RequestException as exc:
                bucket = "request_exception"
                bucket_counts[bucket] += 1
                failures.append(
                    {
                        "pair": f"{sa}->{sb}",
                        "status_code": None,
                        "bucket": bucket,
                        "error": str(exc),
                    }
                )

    report: dict[str, Any] = {
        "base_url": base_url,
        "ga_standards_count": len(standards),
        "directed_pairs_tested": total_pairs,
        "complete_pairs": success_count,
        "incomplete_pairs": len(failures),
        "buckets": dict(bucket_counts),
        "incomplete_examples": failures[: args.max_failures_print],
    }

    print(
        f"GA completeness check for {base_url}: "
        f"{success_count}/{total_pairs} complete, {len(failures)} incomplete"
    )
    if failures:
        print("Incomplete buckets:")
        for k, v in sorted(bucket_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if k == "ok_result":
                continue
            print(f"  - {k}: {v}")
        print("Incomplete pair samples:")
        for item in failures[: args.max_failures_print]:
            print(f"  - {item['pair']} [{item['bucket']}]")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote report: {args.output_json}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
