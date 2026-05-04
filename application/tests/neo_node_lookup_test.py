"""Tests for NeoNode-by-document_id lookup (avoids Neo4j 5 unknown-label warnings)."""

import unittest
from unittest.mock import MagicMock, patch

from application.database import db


class TestNeoNodeFirstOrNoneByDocumentId(unittest.TestCase):
    def test_returns_none_when_no_rows(self) -> None:
        with patch.object(db.db, "cypher_query", return_value=([], None)):
            out = db._neo_node_first_or_none_by_document_id("doc-1")
        self.assertIsNone(out)

    def test_returns_first_inflated_node(self) -> None:
        node = MagicMock()
        with patch.object(db.db, "cypher_query", return_value=([(node,)], None)):
            out = db._neo_node_first_or_none_by_document_id("doc-2")
        self.assertIs(out, node)

    def test_query_does_not_use_neonode_pattern_label(self) -> None:
        """Catalog-safe: no ``:NeoNode`` in the MATCH pattern (Neo4j 5+ notifications)."""
        with patch.object(db.db, "cypher_query", return_value=([], None)) as cq:
            db._neo_node_first_or_none_by_document_id("x")
        self.assertEqual(cq.call_count, 1)
        query = cq.call_args[0][0]
        self.assertIn("MATCH (n)", query)
        self.assertIn("'NeoNode' IN labels(n)", query)
        self.assertNotIn(":NeoNode", query)


if __name__ == "__main__":
    unittest.main()
