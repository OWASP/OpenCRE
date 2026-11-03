#!/usr/bin/env python3
"""Phase 2: optional LI/Docling ingest into existing embeddings tables.

Does not create a VectorStoreIndex as SoT. Local DB only.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from application.utils.db_url import assert_local_db_url  # noqa: E402
from application.utils.rag_parity.flags import load_flags  # noqa: E402
from application.utils.rag_parity.phase2_ingest import (
    ingest_path_to_writer,
)  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="File to ingest")
    parser.add_argument("--node-id", required=True, help="Existing Node.id")
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("CRE_CACHE_FILE")
        or os.environ.get("DEV_DATABASE_URL", ""),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Quality-filter only; do not write",
    )
    args = parser.parse_args()
    if not args.cache_file:
        print("--cache-file required", file=sys.stderr)
        return 2
    assert_local_db_url(args.cache_file)
    os.environ.setdefault("CRE_RAG_PARITY_INGEST", "1")

    class DryWriter:
        def upsert_prose(self, *, node_id: str, text: str, source: str) -> None:
            print(f"dry-run would write {len(text)} chars → node {node_id}")

    writer: object
    if args.dry_run:
        writer = DryWriter()
    else:
        os.environ.setdefault("FLASK_CONFIG", "development")
        os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
        from application.cmd.cre_main import db_connect
        from application.database.db import Embeddings

        database = db_connect(args.cache_file)

        class DbWriter:
            def upsert_prose(self, *, node_id: str, text: str, source: str) -> None:
                row = (
                    database.session.query(Embeddings)
                    .filter(Embeddings.node_id == node_id)
                    .first()
                )
                if row is None:
                    raise SystemExit(f"no embeddings row for node_id={node_id}")
                row.embeddings_content = text
                database.session.commit()

        writer = DbWriter()

    result = ingest_path_to_writer(
        args.path,
        node_id=args.node_id,
        writer=writer,  # type: ignore[arg-type]
        flags=load_flags(),
    )
    print(
        f"ingest written={result.written} rejected={result.rejected} "
        f"backend={result.backend}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
