"""Tests for Module C diff scaffolding (Step 6) and change-set (Step 7)."""

import unittest
from application.defs import cre_defs as defs
from application.utils.import_diff import (
    StandardDiff,
    diff_standards,
    diff_to_change_set,
    change_set_to_json,
    change_set_from_json,
    detect_manual_edit_keys,
    detect_conflicts,
    has_conflicts,
    AddControl,
    ModifyControl,
    RemoveControl,
)


class TestImportDiff(unittest.TestCase):
    def test_diff_standards_empty(self) -> None:
        result = diff_standards([], [])
        self.assertEqual(len(result.added), 0)
        self.assertEqual(len(result.removed), 0)
        self.assertEqual(len(result.modified), 0)

    def test_diff_standards_added(self) -> None:
        prev: list = []
        new = [
            defs.Standard(name="ASVS", section="1.1", sectionID="1.1", description=""),
        ]
        result = diff_standards(prev, new)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(result.added[0].name, "ASVS")
        self.assertEqual(len(result.removed), 0)
        self.assertEqual(len(result.modified), 0)

    def test_diff_standards_removed(self) -> None:
        prev = [
            defs.Standard(name="ASVS", section="1.1", sectionID="1.1", description=""),
        ]
        new: list = []
        result = diff_standards(prev, new)
        self.assertEqual(len(result.removed), 1)
        self.assertEqual(result.removed[0].name, "ASVS")
        self.assertEqual(len(result.added), 0)
        self.assertEqual(len(result.modified), 0)

    def test_diff_standards_modified(self) -> None:
        prev = [
            defs.Standard(
                name="ASVS", section="1.1", sectionID="1.1", description="old"
            ),
        ]
        new = [
            defs.Standard(
                name="ASVS", section="1.1", sectionID="1.1", description="new"
            ),
        ]
        result = diff_standards(prev, new)
        self.assertEqual(len(result.modified), 1)
        self.assertEqual(result.modified[0][0].description, "old")
        self.assertEqual(result.modified[0][1].description, "new")
        self.assertEqual(len(result.added), 0)
        self.assertEqual(len(result.removed), 0)

    def test_diff_standards_unchanged(self) -> None:
        std = defs.Standard(name="ASVS", section="1.1", sectionID="1.1", description="")
        result = diff_standards([std], [std])
        self.assertEqual(len(result.added), 0)
        self.assertEqual(len(result.removed), 0)
        self.assertEqual(len(result.modified), 0)

    def test_diff_to_change_set_roundtrip(self) -> None:
        prev = [
            defs.Standard(
                name="ASVS", section="1.1", sectionID="1.1", description="old"
            ),
        ]
        new = [
            defs.Standard(
                name="ASVS", section="1.1", sectionID="1.1", description="new"
            ),
        ]
        diff = diff_standards(prev, new)
        ops = diff_to_change_set(diff)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op, "modify_control")

        json_str = change_set_to_json(ops)
        loaded = change_set_from_json(json_str)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].op, "modify_control")
        self.assertEqual(loaded[0].before["description"], "old")
        self.assertEqual(loaded[0].after["description"], "new")

    def test_conflict_detection(self) -> None:
        """Step 8: synthetic manual edits produce conflicts."""
        edited = {("ASVS", "1.1", "1.1")}
        ops = [
            ModifyControl(key=("ASVS", "1.1", "1.1"), before={"a": 1}, after={"a": 2}),
            ModifyControl(key=("ASVS", "1.2", "1.2"), before={"a": 1}, after={"a": 2}),
        ]
        self.assertTrue(has_conflicts(ops, edited))
        conflicts = detect_conflicts(ops, edited)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].key, ("ASVS", "1.1", "1.1"))

    def test_conflict_detection_remove_conflict(self) -> None:
        edited = {("ASVS", "2.1", "2.1")}
        ops = [
            RemoveControl(
                key=("ASVS", "2.1", "2.1"),
                document={"name": "ASVS", "section": "2.1", "sectionID": "2.1"},
            )
        ]
        self.assertTrue(has_conflicts(ops, edited))
        conflicts = detect_conflicts(ops, edited)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].op, "remove_control")

    def test_conflict_detection_ignores_adds(self) -> None:
        edited = {("ASVS", "3.1", "3.1")}
        ops = [
            AddControl(
                key=("ASVS", "3.1", "3.1"),
                document={"name": "ASVS", "section": "3.1", "sectionID": "3.1"},
            )
        ]
        self.assertFalse(has_conflicts(ops, edited))
        self.assertEqual(detect_conflicts(ops, edited), [])

    def test_change_set_from_json_ignores_unknown_ops(self) -> None:
        payload = """
        [
          {"op": "future_op", "key": ["A", "B", "C"]},
          {"op": "add_control", "key": ["ASVS", "1.1", "1.1"], "document": {"name":"ASVS"}}
        ]
        """
        loaded = change_set_from_json(payload)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].op, "add_control")

    def test_detect_manual_edit_keys(self) -> None:
        baseline = [
            defs.Standard(
                name="ASVS", section="1.1", sectionID="1.1", description="old"
            ),
            defs.Standard(
                name="ASVS", section="1.2", sectionID="1.2", description="same"
            ),
        ]
        current = [
            defs.Standard(
                name="ASVS", section="1.1", sectionID="1.1", description="new"
            ),
            defs.Standard(
                name="ASVS", section="1.2", sectionID="1.2", description="same"
            ),
            defs.Standard(
                name="ASVS", section="1.3", sectionID="1.3", description="added"
            ),
        ]
        edited = detect_manual_edit_keys(baseline, current)
        self.assertEqual(edited, {("ASVS", "1.1", "1.1")})
