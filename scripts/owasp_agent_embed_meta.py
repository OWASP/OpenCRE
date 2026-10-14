#!/usr/bin/env python3
"""Embed OWASP agent meta (+ evidence notes) into shared ``embeddings``.

Requires Postgres with ``embeddings.source_channel`` (Alembic c9d0e1f2a3b4)
and a working embedding model (``CRE_EMBED_MODEL`` / LiteLLM).

Usage:
  PYTHONPATH=. python scripts/owasp_agent_embed_meta.py
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-evidence",
        action="store_true",
        help="Do not embed curated evidence notes (e.g. trifecta prose)",
    )
    args = parser.parse_args()
    os.environ.setdefault("OWASP_AGENT_ENABLED", "1")

    from application import create_app
    from application.database import db as db_mod
    from application.prompt_client import prompt_client
    from application.utils.owasp_agent.index_store import IndexStore
    from application.utils.owasp_agent.meta_embeddings import sync_meta_embeddings

    app = create_app(mode="production")
    with app.app_context():
        database = db_mod.Node_collection()
        store = IndexStore()
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)

        def embed(text: str):
            return handler.get_text_embeddings(text)

        stats = sync_meta_embeddings(
            store,
            database,
            embed,
            include_evidence=not args.skip_evidence,
        )
        print("owasp_agent_embed_meta", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
