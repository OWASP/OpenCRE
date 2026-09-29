#!/usr/bin/env python3
"""Generate hidden CRE summaries for Librarian C.1/C.2.

Writes JSON files under ``CRE_LIBRARIAN_CRE_SUMMARY_CACHE`` (default
``tmp/oie_cre_summaries``). Never writes ``CRE.description`` or public Node
fields. REST/UI keep serving the public CRE document.

Usage (local clone only — refuses the ``cre`` database and Heroku URLs):

  source /Users/sg/Projects/OpenCRE/venv/bin/activate
  set -a; source /Users/sg/Projects/OpenCRE/.env; set +a
  PYTHONPATH=. python scripts/oie_generate_cre_summaries.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre_prodclone
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _assert_local_clone_url(url: str) -> None:
    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/").split("/")[0]
    host = (parsed.hostname or "").lower()
    if "heroku" in url.lower() or "opencreorg" in url.lower():
        raise SystemExit(
            f"refusing production/Heroku URL {url!r}; use cre_prodclone locally"
        )
    if db_name == "cre":
        raise SystemExit(
            "refusing database 'cre'; pass cre_prodclone "
            "(postgresql://cre:password@127.0.0.1:5432/cre_prodclone)"
        )
    if host not in ("127.0.0.1", "localhost", ""):
        raise SystemExit(f"refusing non-local host {host!r}; summaries are local-only")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("DEV_DATABASE_URL", ""),
        help="SQLAlchemy URL (must be local cre_prodclone, never 'cre')",
    )
    parser.add_argument(
        "--summary-cache",
        default=os.environ.get("CRE_LIBRARIAN_CRE_SUMMARY_CACHE", ""),
        help="Directory for hidden JSON blurbs (default tmp/oie_cre_summaries)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Only load/write from the JSON cache; do not call the LLM",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip in-memory C.1 vectors (C.2 text / cache only)",
    )
    args = parser.parse_args()
    if not args.cache_file:
        print("DEV_DATABASE_URL / --cache-file required", file=sys.stderr)
        return 2
    _assert_local_clone_url(args.cache_file)

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    if args.summary_cache:
        os.environ["CRE_LIBRARIAN_CRE_SUMMARY_CACHE"] = args.summary_cache

    from application.cmd.cre_main import db_connect
    from application.defs import cre_defs as defs
    from application.utils.librarian.cre_summary import (
        default_cache_dir,
        default_llm_fn,
        inject_cre_summaries,
        load_cre_records,
    )
    from application.utils.librarian.cre_text import load_linked_standard_refs

    database = db_connect(args.cache_file)
    records = load_cre_records(database)
    cre_texts = database.get_embedding_contents_by_doc_type(defs.Credoctypes.CRE.value)
    if not cre_texts:
        # Fall back to CRE table ids so a hub-less clone still gets cache files.
        cre_texts = {rec.cre_id: rec.name for rec in records.values() if rec.cre_id}
    cache_dir = Path(args.summary_cache) if args.summary_cache else default_cache_dir()
    llm_fn = None if args.no_llm else default_llm_fn()
    embed_fn = None
    if not args.no_embed:
        from application.prompt_client import prompt_client

        embed_fn = prompt_client.PromptHandler(
            database=database, load_all_embeddings=False
        ).get_text_embeddings

    out_texts, vectors = inject_cre_summaries(
        cre_texts=cre_texts,
        records=records,
        linked=load_linked_standard_refs(database),
        llm_fn=llm_fn,
        cache_dir=cache_dir,
        embed_fn=embed_fn,
    )
    n_cache = len(list(cache_dir.glob("*.json")))
    print(
        f"hidden CRE summaries: injected={len(out_texts)} "
        f"cache_files={n_cache} dir={cache_dir} "
        f"in_memory_vectors={0 if not vectors else len(vectors)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
