"""Integration tests for refreshing golden dataset fixture inputs."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = REPO_ROOT / "standards_cache.sqlite"
INPUTS_DIR = REPO_ROOT / "application/tests/librarian/fixtures/dataset_inputs"
REFRESH_SCRIPT = REPO_ROOT / "scripts/refresh_golden_dataset_inputs.py"


@unittest.skipUnless(DB_PATH.exists(), "Local standards database is unavailable")
class TestDatasetRefreshIntegration(unittest.TestCase):
    def test_refresh_generates_valid_inputs_without_changing_pins(self):
        original_nodes = json.loads(
            (INPUTS_DIR / "source_nodes.json").read_text(encoding="utf-8")
        )
        original_curated = json.loads(
            (INPUTS_DIR / "curated.json").read_text(encoding="utf-8")
        )

        original_pins = {
            (node["name"], node["section_id"]): node for node in original_nodes
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(DB_PATH),
                    "--out-dir",
                    temp_dir,
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            output_dir = Path(temp_dir)
            refreshed_nodes = json.loads(
                (output_dir / "source_nodes.json").read_text(encoding="utf-8")
            )
            refreshed_curated = json.loads(
                (output_dir / "curated.json").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )

            for filename in (
                "source_nodes.json",
                "curated.json",
                "manifest.json",
            ):
                self.assertTrue((output_dir / filename).is_file())

        refreshed_by_key = {
            (node["name"], node["section_id"]): node for node in refreshed_nodes
        }

        self.assertEqual(len(refreshed_nodes), len(refreshed_by_key))
        self.assertEqual(
            refreshed_curated["multilink_pins"],
            original_curated["multilink_pins"],
        )

        for pin in refreshed_curated["multilink_pins"]:
            key = (pin["name"], pin["section_id"])
            self.assertIn(key, refreshed_by_key)
            self.assertEqual(refreshed_by_key[key], original_pins[key])

            cre_ids = refreshed_by_key[key]["cre_ids"]
            self.assertGreaterEqual(len(cre_ids), 2)
            self.assertLessEqual(len(cre_ids), 4)
            self.assertEqual(cre_ids, sorted(set(cre_ids)))

        self.assertEqual(
            manifest["record_counts"]["source_nodes"],
            len(refreshed_nodes),
        )
        self.assertEqual(
            manifest["record_counts"]["asvs"],
            sum(node["standard"] == "ASVS" for node in refreshed_nodes),
        )
        self.assertEqual(
            manifest["record_counts"]["multilink_pins"],
            len(refreshed_curated["multilink_pins"]),
        )


class TestDatasetRefreshWithSyntheticDatabase(unittest.TestCase):
    def create_database(self, path):
        import sqlite3

        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE node (id VARCHAR PRIMARY KEY, name VARCHAR, "
            "section VARCHAR, section_id VARCHAR);"
            "CREATE TABLE cre (id VARCHAR PRIMARY KEY, external_id VARCHAR);"
            "CREATE TABLE cre_node_links (type VARCHAR, cre VARCHAR, node VARCHAR, "
            "PRIMARY KEY (cre, node));"
        )
        conn.close()

    def test_empty_database_preserves_all_historical_pins(self):
        original_nodes = json.loads(
            (INPUTS_DIR / "source_nodes.json").read_text(encoding="utf-8")
        )
        original_curated = json.loads(
            (INPUTS_DIR / "curated.json").read_text(encoding="utf-8")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "empty.sqlite"
            output_dir = temp_path / "output"
            self.create_database(db_path)

            subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            refreshed_nodes = json.loads(
                (output_dir / "source_nodes.json").read_text(encoding="utf-8")
            )
            refreshed_curated = json.loads(
                (output_dir / "curated.json").read_text(encoding="utf-8")
            )

        original_by_key = {
            (node["name"], node["section_id"]): node for node in original_nodes
        }
        refreshed_by_key = {
            (node["name"], node["section_id"]): node for node in refreshed_nodes
        }

        self.assertEqual(
            refreshed_curated["multilink_pins"],
            original_curated["multilink_pins"],
        )

        for pin in original_curated["multilink_pins"]:
            key = (pin["name"], pin["section_id"])
            self.assertEqual(refreshed_by_key[key], original_by_key[key])

        self.assertEqual(len(refreshed_curated["multilink_pins"]), 15)

    def test_changed_cre_mapping_preserves_historical_snapshot(self):
        original_nodes = json.loads(
            (INPUTS_DIR / "source_nodes.json").read_text(encoding="utf-8")
        )
        original_curated = json.loads(
            (INPUTS_DIR / "curated.json").read_text(encoding="utf-8")
        )

        pin = original_curated["multilink_pins"][0]
        key = (pin["name"], pin["section_id"])
        original_node = next(
            node for node in original_nodes if (node["name"], node["section_id"]) == key
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "changed.sqlite"
            output_dir = temp_path / "output"
            self.create_database(db_path)

            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO node (id, name, section, section_id) "
                "VALUES (?, ?, ?, ?)",
                ("node-1", pin["name"], original_node["section"], pin["section_id"]),
            )

            for index, cre_id in enumerate(("CHANGED-CRE-1", "CHANGED-CRE-2")):
                conn.execute(
                    "INSERT INTO cre (id, external_id) VALUES (?, ?)",
                    (f"cre-{index}", cre_id),
                )
                conn.execute(
                    "INSERT INTO cre_node_links (type, cre, node) VALUES (?, ?, ?)",
                    ("test", f"cre-{index}", "node-1"),
                )
            conn.commit()
            conn.close()

            subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            refreshed_nodes = json.loads(
                (output_dir / "source_nodes.json").read_text(encoding="utf-8")
            )

        refreshed_by_key = {
            (node["name"], node["section_id"]): node for node in refreshed_nodes
        }

        self.assertEqual(refreshed_by_key[key], original_node)
        self.assertNotEqual(
            refreshed_by_key[key]["cre_ids"],
            ["CHANGED-CRE-1", "CHANGED-CRE-2"],
        )

    def test_repin_selects_first_fifteen_eligible_nodes(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "repin.sqlite"
            output_dir = temp_path / "output"
            self.create_database(db_path)

            conn = sqlite3.connect(db_path)

            for index in range(16):
                name = f"CWE synthetic {index:02d}"
                section_id = f"synthetic-{index:02d}"
                section = f"This is a sufficiently long synthetic section {index}."

                conn.execute(
                    "INSERT INTO node (id, name, section, section_id) "
                    "VALUES (?, ?, ?, ?)",
                    (f"node-{index}", name, section, section_id),
                )

                for cre_index in range(2):
                    cre_id = f"CRE-{index:02d}-{cre_index}"
                    conn.execute(
                        "INSERT INTO cre (id, external_id) VALUES (?, ?)",
                        (f"cre-{index}-{cre_index}", cre_id),
                    )
                    conn.execute(
                        "INSERT INTO cre_node_links (type, cre, node) "
                        "VALUES (?, ?, ?)",
                        ("test", f"cre-{index}-{cre_index}", f"node-{index}"),
                    )

            conn.commit()
            conn.close()

            subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(output_dir),
                    "--repin",
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            refreshed_nodes = json.loads(
                (output_dir / "source_nodes.json").read_text(encoding="utf-8")
            )
            refreshed_curated = json.loads(
                (output_dir / "curated.json").read_text(encoding="utf-8")
            )

        expected_pins = [
            {
                "name": f"CWE synthetic {index:02d}",
                "section_id": f"synthetic-{index:02d}",
            }
            for index in range(15)
        ]

        self.assertEqual(
            refreshed_curated["multilink_pins"],
            expected_pins,
        )

        nodes_by_key = {
            (node["name"], node["section_id"]): node for node in refreshed_nodes
        }

        self.assertEqual(len(refreshed_nodes), 15)

        for pin in expected_pins:
            key = (pin["name"], pin["section_id"])
            self.assertIn(key, nodes_by_key)
            self.assertEqual(len(nodes_by_key[key]["cre_ids"]), 2)
            self.assertEqual(
                nodes_by_key[key]["cre_ids"],
                sorted(nodes_by_key[key]["cre_ids"]),
            )

        self.assertNotIn(
            ("CWE synthetic 15", "synthetic-15"),
            nodes_by_key,
        )


if __name__ == "__main__":
    unittest.main()
