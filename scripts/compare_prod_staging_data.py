#!/usr/bin/env python3
"""
Compare OpenCRE **production** vs **staging** SQL snapshots using the same engine as
``scripts/benchmark_import_parity.py`` (structural graph parity + content samples).

- **Imported** side (first DB) = staging — pass ``--staging-db``.
- **Upstream** side (second DB) = production — pass ``--prod-db``.

Connection strings may be ``sqlite:///...`` or ``postgresql://...`` (SQLAlchemy URLs).

Environment defaults (after loading ``<repo>/.env`` if present):
  ``STAGING_DATABASE_URL``, ``PROD_DATABASE_URL`` (Heroku: ``heroku config:get DATABASE_URL -a <app>``).
  Existing shell variables override ``.env`` (``override=False``).

Relationship noise: internal CRE–CRE edges classify *reversed-only* flips separately from
true add/remove (see ``internal_edge_remodeling`` in the report).

Optional: Vertex AI Gemini summary (needs ADC or service account; project from
``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_PROJECT_ID``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv_at_startup() -> None:
    """Populate os.environ from repo ``.env`` before argparse reads defaults."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    path = _REPO_ROOT / ".env"
    if path.is_file():
        load_dotenv(path, override=False)


def _load_parity_module():
    path = _REPO_ROOT / "scripts" / "benchmark_import_parity.py"
    spec = importlib.util.spec_from_file_location("benchmark_import_parity", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gemini_summary(report: Dict[str, Any], model_name: str) -> str:
    try:
        import vertexai  # type: ignore
        from vertexai.generative_models import GenerativeModel  # type: ignore
    except ImportError as e:
        return f"(Gemini skipped: {e})"

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
        "GOOGLE_PROJECT_ID"
    )
    if not project:
        return "(Gemini skipped: set GOOGLE_CLOUD_PROJECT or GOOGLE_PROJECT_ID)"

    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)
    model = GenerativeModel(model_name)

    payload = json.dumps(report, indent=2, default=str)
    if len(payload) > 120_000:
        payload = payload[:120_000] + "\n…(truncated for model context)…"

    prompt = f"""You are helping engineers compare OpenCRE database snapshots.

Context:
- "imported" / staging data is the first database (typically staging.opencre.org).
- "upstream" / production data is the second database (typically opencre.org).

The JSON uses the parity engine from benchmark_import_parity:
- internal_edge_remodeling.reversed_only = CRE–CRE edges that exist in both DBs but with opposite direction (usually NOT meaningful for product decisions).
- internal_edge_remodeling.type_changed = same ordered pair but link type set differs (meaningful).
- internal_edge_remodeling.true_add_remove = connectivity that only exists on one side (meaningful).
- cre_node_edges = links between CREs and standards/tools/code nodes (meaningful if counts non-zero).

Write:
1) A short executive summary (2–6 sentences).
2) Bullet list: **Meaningful differences** (structural / missing nodes / GA payload drift / property diffs).
3) Bullet list: **Likely benign / noise** (e.g. reversed-only internal edges, cosmetic fields if obvious).
4) **Risk level**: Low / Medium / High and one-line rationale.

JSON report:
{payload}
"""
    resp = model.generate_content(prompt)
    text = getattr(resp, "text", None)
    if text:
        return text
    try:
        return resp.candidates[0].content.parts[0].text  # type: ignore[index]
    except Exception:
        return str(resp)


def main() -> None:
    _load_dotenv_at_startup()
    parser = argparse.ArgumentParser(
        description="Compare prod vs staging OpenCRE DBs (parity engine + optional Gemini summary)."
    )
    parser.add_argument(
        "--staging-db",
        default=os.environ.get("STAGING_DATABASE_URL", ""),
        help="Staging DB URL (default: env STAGING_DATABASE_URL)",
    )
    parser.add_argument(
        "--prod-db",
        default=os.environ.get("PROD_DATABASE_URL", ""),
        help="Production DB URL (default: env PROD_DATABASE_URL)",
    )
    parser.add_argument(
        "--log-file",
        default="prod-staging-parity.log",
        help="Full parity log (same format as benchmark_import_parity)",
    )
    parser.add_argument(
        "--json-out",
        default="prod-staging-summary.json",
        help="Write structured summary JSON for CI or review",
    )
    parser.add_argument(
        "--skip-gemini",
        action="store_true",
        help="Do not call Vertex Gemini",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("GEMINI_SUMMARY_MODEL", "gemini-2.0-flash-001"),
        help="Vertex model id (default: gemini-2.0-flash-001)",
    )
    args = parser.parse_args()

    if not args.staging_db.strip():
        print(
            "ERROR: --staging-db or STAGING_DATABASE_URL is required.\n"
            "Example: export STAGING_DATABASE_URL=$(heroku config:get DATABASE_URL -a opencre-staging)",
            file=sys.stderr,
        )
        sys.exit(2)
    if not args.prod_db.strip():
        print(
            "ERROR: --prod-db or PROD_DATABASE_URL is required.\n"
            "Example: export PROD_DATABASE_URL=$(heroku config:get DATABASE_URL -a opencreorg)",
            file=sys.stderr,
        )
        sys.exit(2)

    parity = _load_parity_module()
    summary: Dict[str, Any] = {}
    ok = parity.diff_databases(
        args.staging_db,
        args.prod_db,
        args.log_file,
        summary_out=summary,
    )

    envelope: Dict[str, Any] = {
        "legend": {
            "imported_side": "staging (first DB argument)",
            "upstream_side": "production (second DB argument)",
            "staging_db": args.staging_db,
            "prod_db": args.prod_db,
        },
        "parity_engine": summary,
        "fundamental_structural_match": ok,
    }

    Path(args.json_out).write_text(
        json.dumps(envelope, indent=2, default=str), encoding="utf-8"
    )
    print(f"Wrote structured summary: {args.json_out}")
    print(f"Wrote full parity log: {args.log_file}")

    gemini_text: Optional[str] = None
    if not args.skip_gemini:
        print("Calling Gemini for executive summary…")
        gemini_text = _gemini_summary(envelope, args.gemini_model)
        out_md = Path(args.json_out).with_suffix(".gemini.md")
        out_md.write_text(gemini_text or "", encoding="utf-8")
        print(f"Wrote Gemini summary: {out_md}")
        print("\n--- Gemini summary ---\n")
        print(gemini_text or "")
    else:
        print(
            "(Gemini skipped; use compare_prod_staging_data.py without --skip-gemini)"
        )

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
