"""One filer for every source: repos and websites share naming, tags and merging."""

from __future__ import annotations

import unittest

from application import sqla
from application.database import db
from application.defs import cre_defs as defs
from application.tests.oie_review_test import _Fixture, _envelope, _web_envelope
from application.utils.oie_scheduler import graph_filer


class FilerSourcesTest(_Fixture):
    def _linked(self, chunk_id, envelope):
        row = db.DecisionQueueItem(
            chunk_id=chunk_id,
            artifact_id="art",
            pipeline_run_id="run-1",
            schema_version="0.2.0",
            status="linked",
            confidence=0.95,
            envelope=envelope,
        )
        sqla.session.add(row)
        sqla.session.commit()

    def _file(self, **kw):
        return graph_filer.file_linked_decisions(self.collection, floor=0.9, **kw)

    def test_website_decision_is_auto_filed_under_its_host(self) -> None:
        self._linked("w1", _web_envelope("w1", status="linked"))
        res = self._file()
        self.assertEqual((res.filed, res.invalid, res.links_added), (1, 0, 1))
        node = sqla.session.query(db.Node).one()
        self.assertEqual(node.name, "slsa.dev")
        self.assertEqual(node.section, "Build L2")
        self.assertEqual(node.link, "https://www.slsa.dev/spec/v1.0/levels#build-l2")
        link = sqla.session.query(db.Links).one()
        self.assertEqual(link.type, defs.LinkTypes.AutomaticallyLinkedTo.value)

    def test_repo_and_website_nodes_carry_the_same_tags(self) -> None:
        self._linked("r1", _envelope("r1"))
        self._linked("w1", _web_envelope("w1", status="linked"))
        self._file()
        for node in sqla.session.query(db.Node).all():
            tags = node.tags.split(",")
            self.assertIn(graph_filer.AUTO_FILED_TAG, tags)
            self.assertIn(graph_filer.PROVENANCE_TAG, tags)

    def test_existing_tags_are_kept_and_reviewed_nodes_stay_reviewed(self) -> None:
        self._linked("r1", _envelope("r1"))
        self._file()
        node = sqla.session.query(db.Node).one()
        node.tags = "keep-me,oie-reviewed,provenance:myopencre"
        sqla.session.commit()
        self._linked("r2", _envelope("r2", cre_ids=("222-222",)))
        self._file()
        tags = sqla.session.get(db.Node, node.id).tags.split(",")
        self.assertIn("keep-me", tags)
        self.assertIn("oie-reviewed", tags)
        self.assertNotIn(graph_filer.AUTO_FILED_TAG, tags)  # a human already owns it
        self.assertEqual(len(tags), len(set(tags)))

    def test_skip_applies_to_repos_and_websites_alike(self) -> None:
        self._linked("r1", _envelope("r1"))
        self._linked("w1", _web_envelope("w1", status="linked"))
        res = self._file(skip_repos=["OWASP/www-project-foo", "SLSA.dev"])
        self.assertEqual((res.filed, res.skipped_standard_repo), (0, 2))


if __name__ == "__main__":
    unittest.main()
