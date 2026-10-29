#!/usr/bin/env python3
"""Crawl approved external sites and store them as raw, embedded chunks (like a repository).

    python scripts/ingest_external.py                      # dry run of every approved site (default)
    python scripts/ingest_external.py --id owasp-benelux --apply --skip-unchanged
    python scripts/ingest_external.py --spec-json '{"id":"x-site","name":"X","start_urls":["https://x.org/"]}' --max-pages 5

Default is a dry run: it crawls (politely, see web_source.py) and prints pages, chunks and an
estimated embedding cost, and writes nothing (not even the conditional-request cache).
Env: OWASP_CRAWL_DELAY (seconds between requests, default 1), OWASP_CRAWL_CACHE_DIR.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from application.utils.comprehension import external  # noqa: E402
from application.utils.comprehension.external_ingest import ingest_spec  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", nargs="*", default=[], help="only these approved site ids")
    ap.add_argument(
        "--spec-json", help="ad-hoc ExternalSpec JSON instead of the targets table"
    )
    ap.add_argument(
        "--apply", action="store_true", help="write chunks (default: dry run)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="crawl and report only (default)"
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="override the spec's page cap (lower only)",
    )
    ap.add_argument(
        "--skip-unchanged", action="store_true", help="only write new or changed chunks"
    )
    ap.add_argument(
        "--enrich",
        action="store_true",
        help="LLM context sentence and likely questions per chunk",
    )
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--debug", action="store_true", help="log every request and queue step"
    )
    a = ap.parse_args()
    import logging

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s crawler %(message)s", "%H:%M:%S")
    )
    crawl_log = logging.getLogger("opencrebot")
    crawl_log.addHandler(handler)
    crawl_log.setLevel(logging.DEBUG if a.debug else logging.INFO)
    crawl_log.propagate = False
    if a.apply and a.dry_run:
        ap.error("--apply and --dry-run are exclusive")

    if a.spec_json:
        spec = external.validate_spec(json.loads(a.spec_json))
        if spec.kind != external.KIND_SITE:
            ap.error("--spec-json must be an external_site")
        if not a.apply:  # ad-hoc dry run needs no app or database
            ingest_spec(spec, apply=False, max_pages=a.max_pages)
            return 0
        specs = [spec]
    else:
        specs = []

    from application import create_app
    from application.database import db as db_mod
    from application.prompt_client import litellm_router, prompt_client

    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        database = db_mod.Node_collection()
        if not a.spec_json:
            specs = external.load_specs(database.session, kinds=(external.KIND_SITE,))
            if a.id:
                specs = [s for s in specs if s.id in set(a.id)]
        if not specs:
            print("no approved external sites to ingest", flush=True)
            return 0
        embed = enrich_fn = None
        if a.apply:
            handler = prompt_client.PromptHandler(database, load_all_embeddings=False)
            embed = handler.get_text_embeddings
            if a.enrich:
                enrich_fn = litellm_router.system_user_fn(
                    os.environ.get(
                        "CRE_COMPREHENSION_ENRICH_MODEL", "gemini/gemini-2.5-flash-lite"
                    ),
                    extra_try_kwargs={"reasoning_effort": "disable"},
                )
        for spec in specs:
            try:
                ingest_spec(
                    spec,
                    apply=a.apply,
                    max_pages=a.max_pages,
                    skip_unchanged=a.skip_unchanged,
                    enrich=a.enrich,
                    workers=a.workers,
                    database=database,
                    embed=embed,
                    enrich_fn=enrich_fn,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{spec.id}: FAILED {str(exc)[:200]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
