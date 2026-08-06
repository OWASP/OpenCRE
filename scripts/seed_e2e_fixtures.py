#!/usr/bin/env python3
"""
Seed a minimal, checked-in fixture graph into the e2e SQLite cache.

Replaces the live `--upstream_sync` network call (which pulls the full graph
from opencre.org) for local/CI Cypress runs: no network I/O, and the ids/terms
below are the explicit contract the cypress/e2e/*.cy.js specs assert against.
Run after `make e2e-db`'s create_all schema step, never instead of it.

Fixture contract:
- CRE 558-807 "Mutually authenticate": root CRE, linked to ASVS/V13.2.5 and
  NIST/AC-1 (cre.cy.js, search.cy.js, smoke.cy.js root_cres, smartlink).
- Standard ASVS/V13.2.5 (has a hyperlink): the only fixture standard linked
  to a CRE, so filters=asvs must keep it while dropping NIST/AC-1, and the
  smartlink for it redirects straight to /cre/558-807.
- Standard NIST/AC-1: exists only to prove a filter actually excludes
  something.
- CRE 170-772 "Cryptography": unlinked, matches the free-text "crypto" query.
- Standard ASVS/V2.1.1..24: unlinked filler pushing /node/standard/ASVS past
  the 20-item page size so pagination has more than one page. Named "V2.*"
  (rather than "V1.*") so ASVS/V13.2.5 always sorts first alphabetically and
  lands on page 1, regardless of locale string-compare edge cases.
- No CWE node is created: the smartlink Mitre-fallback test relies on no
  match existing for an arbitrary CWE id.
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from application import create_app
from application.database import db
from application.defs import cre_defs as defs


def main() -> None:
    app = create_app(mode="development")
    with app.app_context():
        collection = db.Node_collection().with_graph()

        cre = defs.CRE(
            id="558-807",
            name="Mutually authenticate",
            description="e2e fixture CRE, owned by scripts/seed_e2e_fixtures.py",
        )
        crypto_cre = defs.CRE(
            id="170-772",
            name="Cryptography",
            description="e2e fixture CRE for the free-text 'crypto' search",
        )
        asvs = defs.Standard(
            name="ASVS",
            section="V13.2.5",
            hyperlink="https://example.com/asvs/v13.2.5",
        )
        nist = defs.Standard(name="NIST", section="AC-1")

        dcre = collection.add_cre(cre)
        collection.add_cre(crypto_cre)
        dasvs = collection.add_node(asvs)
        dnist = collection.add_node(nist)
        collection.add_link(dcre, dasvs, ltype=defs.LinkTypes.LinkedTo)
        collection.add_link(dcre, dnist, ltype=defs.LinkTypes.LinkedTo)

        for i in range(1, 25):
            collection.add_node(defs.Standard(name="ASVS", section=f"V2.1.{i}"))

    print("Seeded e2e fixture graph.")


if __name__ == "__main__":
    main()
