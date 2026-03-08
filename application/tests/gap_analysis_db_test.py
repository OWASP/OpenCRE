import unittest
from unittest.mock import MagicMock, patch
from application.database import db
from application.defs import cre_defs as defs


class TestGapAnalysisPruning(unittest.TestCase):
    def setUp(self):
        # Patch the entire Class to avoid descriptor issues with .nodes
        self.mock_NeoStandard = patch("application.database.db.NeoStandard").start()
        self.mock_cypher = patch("application.database.db.db.cypher_query").start()
        self.addCleanup(patch.stopall)

    def test_tiered_execution_optimization(self):
        """
        Verify that if Tier 1 (Strong) returns results, we DO NOT execute Tier 3 (Broad).
        """
        strong_path_mock = [MagicMock()]
        empty_result = []

        # Configure the class mock
        # NeoStandard.nodes.filter(...) should return a list
        self.mock_NeoStandard.nodes.filter.return_value = []

        # We will use a side_effect to return different results based on the query content
        def cypher_side_effect(query, params=None, resolve_objects=True):
            # Crude way to detect query type by checking for unique relationship strings
            if "LINKED_TO|AUTOMATICALLY_LINKED_TO|SAME" in query:  # Tier 1 (Strong)
                return strong_path_mock, None
            if "CONTAINS" in query:  # Tier 2 (Medium)
                return empty_result, None
            if "[*..20]" in query:  # Tier 3 (Broad/Weak)
                return empty_result, None
            return empty_result, None

        self.mock_cypher.side_effect = cypher_side_effect

        # Call the function with tiered pruning enabled
        with patch(
            "application.config.Config.GAP_ANALYSIS_OPTIMIZED", True, create=True
        ):
            db.NEO_DB.gap_analysis("StandardA", "StandardB")

        # ASSERTION:
        # We expect cypher_query to be called.
        # BUT, we expect it to be called ONLY for Tier 1 (and maybe Tier 2 setups),
        # but DEFINITELY NOT for the broad Tier 3 query if Tier 1 found something.

        # Let's inspect all calls to cypher_query
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
            "Tier 3 (Wildcard) query should NOT have been executed because Tier 1 found paths",
        )


if __name__ == "__main__":
    unittest.main()
