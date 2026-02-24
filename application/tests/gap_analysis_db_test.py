import unittest
from unittest.mock import MagicMock, patch
from application.database import db


class TestGapAnalysisPruning(unittest.TestCase):
    def setUp(self):
        self.mock_NeoStandard = patch("application.database.db.NeoStandard").start()
        self.mock_cypher = patch("application.database.db.db.cypher_query").start()
        # NEO_DB is a singleton — get the instance directly
        self.neo_db = db.NEO_DB.instance()
        self.addCleanup(patch.stopall)

    def test_tiered_execution_optimization(self):
        """
        Verify that if Tier 1 (Strong) returns results, we DO NOT execute Tier 3 (Broad).
        """
        strong_path_mock = [MagicMock()]
        empty_result = []

        self.mock_NeoStandard.nodes.filter.return_value = []

        def cypher_side_effect(query, params=None, resolve_objects=True):
            if "LINKED_TO|AUTOMATICALLY_LINKED_TO|SAME" in query:
                return strong_path_mock, None
            if "CONTAINS" in query:
                return empty_result, None
            if "[*..20]" in query:
                return empty_result, None
            return empty_result, None

        self.mock_cypher.side_effect = cypher_side_effect

        self.neo_db.gap_analysis("StandardA", "StandardB")

        calls = self.mock_cypher.call_args_list
        tier_1_called = False
        tier_3_called = False
        for call in calls:
            query_str = call[0][0]
            if "LINKED_TO|AUTOMATICALLY_LINKED_TO" in query_str:
                tier_1_called = True
            if "[*..20]" in query_str:
                tier_3_called = True

        self.assertTrue(tier_1_called, "Tier 1 query should have been executed")
        self.assertFalse(
            tier_3_called,
            "Tier 3 query should NOT run when Tier 1 found paths",
        )


if __name__ == "__main__":
    unittest.main()