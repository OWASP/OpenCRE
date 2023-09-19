import unittest
from application.defs import cre_defs

from application.utils.gap_analysis import (
    get_path_score,
    get_relation_direction,
    get_next_id,
    PENALTIES,
)


class TestGapAnalysis(unittest.TestCase):
    def tearDown(self) -> None:
        return None

    def setUp(self) -> None:
        return None

    def test_get_relation_direction_UP(self):
        step = {
            "start": cre_defs.CRE(name="bob", id="123"),
            "end": cre_defs.CRE(name="bob", id="234"),
        }
        self.assertEqual(get_relation_direction(step, "123"), "UP")

    def test_get_relation_direction_DOWN(self):
        step = {
            "start": cre_defs.CRE(name="bob", id="123"),
            "end": cre_defs.CRE(name="bob", id="234"),
        }
        self.assertEqual(get_relation_direction(step, "234"), "DOWN")

    def test_get_next_id_start(self):
        step = {
            "start": cre_defs.CRE(name="bob", id="123"),
            "end": cre_defs.CRE(name="bob", id="234"),
        }
        self.assertEqual(get_next_id(step, "234"), "123")

    def test_get_next_id_end(self):
        step = {
            "start": cre_defs.CRE(name="bob", id="123"),
            "end": cre_defs.CRE(name="bob", id="234"),
        }
        self.assertEqual(get_next_id(step, "123"), "234")

    def test_get_path_score_direct_siblings_returns_zero(self):
        path = {
            "start": cre_defs.CRE(
                name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
            ),
            "end": cre_defs.CRE(name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"),
            "path": [
                {
                    "end": cre_defs.CRE(
                        name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(
                        name="bob", id="e2ac59b2-c1d8-4525-a6b3-155d480aecc9"
                    ),
                },
            ],
        }
        self.assertEqual(get_path_score(path), 0)

    def test_get_path_score_one_up_returns_one_up_penaltiy(self):
        path = {
            "start": cre_defs.CRE(
                name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
            ),
            "end": cre_defs.CRE(name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"),
            "path": [
                {
                    "end": cre_defs.CRE(
                        name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                },
                {
                    "end": cre_defs.CRE(name="bob", id="123"),
                    "relationship": "CONTAINS",
                    "start": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
            ],
        }
        self.assertEqual(get_path_score(path), PENALTIES["CONTAINS_UP"])
        self.assertEqual(path["path"][1]["score"], PENALTIES["CONTAINS_UP"])

    def test_get_path_score_one_down_one_returns_one_down_penaltiy(self):
        path = {
            "start": cre_defs.CRE(
                name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
            ),
            "end": cre_defs.CRE(name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"),
            "path": [
                {
                    "end": cre_defs.CRE(
                        name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                    "relationship": "CONTAINS",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
            ],
        }
        self.assertEqual(get_path_score(path), PENALTIES["CONTAINS_DOWN"])
        self.assertEqual(path["path"][1]["score"], PENALTIES["CONTAINS_DOWN"])

    def test_get_path_score_related_returns_related_penalty(self):
        path = {
            "start": cre_defs.CRE(
                name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
            ),
            "end": cre_defs.CRE(name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"),
            "path": [
                {
                    "end": cre_defs.CRE(
                        name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                    "relationship": "RELATED",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
            ],
        }
        self.assertEqual(get_path_score(path), PENALTIES["RELATED"])
        self.assertEqual(path["path"][1]["score"], PENALTIES["RELATED"])

    def test_get_path_score_one_of_each_returns_penalty(self):
        path = {
            "start": cre_defs.CRE(
                name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
            ),
            "end": cre_defs.CRE(name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"),
            "path": [
                {
                    "end": cre_defs.CRE(
                        name="bob", id="029f7cd7-ef2f-4f25-b0d2-3227cde4b34b"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="07bc9f6f-5387-4dc6-b277-0022ed76049f"
                    ),
                    "relationship": "CONTAINS",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
                {
                    "end": cre_defs.CRE(name="bob", id="456"),
                    "relationship": "RELATED",
                    "start": cre_defs.CRE(name="bob", id="123"),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"
                    ),
                    "relationship": "CONTAINS",
                    "start": cre_defs.CRE(name="bob", id="456"),
                },
                {
                    "end": cre_defs.CRE(
                        name="bob", id="7d030730-14cc-4c43-8927-f2d0f5fbcf5d"
                    ),
                    "relationship": "LINKED_TO",
                    "start": cre_defs.CRE(name="bob", id="456"),
                },
            ],
        }
        self.assertEqual(
            get_path_score(path),
            PENALTIES["RELATED"]
            + PENALTIES["CONTAINS_UP"]
            + PENALTIES["CONTAINS_DOWN"],
        )
        self.assertEqual(path["path"][1]["score"], PENALTIES["CONTAINS_DOWN"])
        self.assertEqual(path["path"][2]["score"], PENALTIES["RELATED"])
        self.assertEqual(path["path"][3]["score"], PENALTIES["CONTAINS_UP"])
