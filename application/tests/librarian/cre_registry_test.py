"""Unit tests for emit-time CRE membership grounding."""

import unittest

from application.utils.librarian.cre_registry import CreRegistry, ground_decision
from application.utils.librarian.decision_engine import DecisionResult
from application.utils.librarian.schemas import Decision, ReasonCode


class CreRegistryResolveTest(unittest.TestCase):
    def test_unknown_id_resolves_to_none(self) -> None:
        reg = CreRegistry(frozenset({"uuid-real", "616-305"}))
        self.assertIsNone(reg.resolve("ghost-id"))

    def test_member_id_resolves_to_itself(self) -> None:
        reg = CreRegistry(frozenset({"uuid-real"}))
        self.assertEqual(reg.resolve("uuid-real"), "uuid-real")

    def test_external_id_maps_to_canonical(self) -> None:
        reg = CreRegistry(
            frozenset({"uuid-real", "616-305"}),
            canonical_map={"616-305": "uuid-real"},
        )
        self.assertEqual(reg.resolve("616-305"), "uuid-real")

    def test_disabled_registry_passthrough(self) -> None:
        reg = CreRegistry.disabled()
        self.assertEqual(reg.resolve("anything"), "anything")

    def test_ground_ids_drops_ghosts_and_dedupes(self) -> None:
        reg = CreRegistry(
            frozenset({"uuid-a", "616-305"}),
            canonical_map={"616-305": "uuid-a"},
        )
        self.assertEqual(
            reg.ground_ids(["ghost", "616-305", "uuid-a", "ghost-2"]),
            ("uuid-a",),
        )


class GroundDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = CreRegistry(frozenset({"uuid-real", "616-305"}))

    def test_linked_with_only_ghosts_becomes_review_no_candidates(self) -> None:
        result = DecisionResult(Decision.linked, 0.99, ("ghost-id",), None)
        grounded = ground_decision(result, self.reg)
        self.assertEqual(grounded.decision, Decision.review)
        self.assertEqual(grounded.cre_ids, ())
        self.assertEqual(grounded.reason_code, ReasonCode.no_candidates)

    def test_linked_keeps_valid_ids(self) -> None:
        result = DecisionResult(Decision.linked, 0.99, ("616-305",), None)
        grounded = ground_decision(result, self.reg)
        self.assertEqual(grounded.decision, Decision.linked)
        self.assertEqual(grounded.cre_ids, ("616-305",))
        self.assertIsNone(grounded.reason_code)

    def test_review_drops_invalid_suggested_ids(self) -> None:
        result = DecisionResult(
            Decision.review,
            0.4,
            ("ghost-id", "616-305"),
            ReasonCode.below_threshold,
        )
        grounded = ground_decision(result, self.reg)
        self.assertEqual(grounded.decision, Decision.review)
        self.assertEqual(grounded.cre_ids, ("616-305",))
        self.assertEqual(grounded.reason_code, ReasonCode.below_threshold)

    def test_disabled_registry_leaves_decision_unchanged(self) -> None:
        result = DecisionResult(Decision.linked, 0.99, ("ghost-id",), None)
        grounded = ground_decision(result, CreRegistry.disabled())
        self.assertEqual(grounded, result)


if __name__ == "__main__":
    unittest.main()
