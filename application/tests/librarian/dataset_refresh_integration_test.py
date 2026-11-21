"""Integration tests for refreshing golden dataset fixture inputs."""

import importlib.util
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
BUILDER_SCRIPT = REPO_ROOT / "scripts/build_golden_dataset.py"

REFRESH_SPEC = importlib.util.spec_from_file_location(
    "refresh_golden_dataset_inputs", REFRESH_SCRIPT
)
REFRESH_MODULE = importlib.util.module_from_spec(REFRESH_SPEC)
REFRESH_SPEC.loader.exec_module(REFRESH_MODULE)


@unittest.skipUnless(DB_PATH.exists(), "Local standards database is unavailable")
class TestDatasetRefreshIntegration(unittest.TestCase):
    def test_refresh_generates_valid_inputs_without_changing_pins(self):
        """Verify refresh generates valid inputs while preserving historical pins."""

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

            generated_golden = output_dir / "golden_dataset.generated.json"
            subprocess.run(
                [
                    sys.executable,
                    str(BUILDER_SCRIPT),
                    "--inputs",
                    str(output_dir),
                    "--out",
                    str(generated_golden),
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            committed_golden = (
                REPO_ROOT / "application/tests/librarian/fixtures/golden_dataset.json"
            )
            self.assertEqual(
                generated_golden.read_bytes(),
                committed_golden.read_bytes(),
            )

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

    def test_refresh_help_displays_options(self):
        """Verify refresh help documents the available command-line options."""
        result = subprocess.run(
            [sys.executable, str(REFRESH_SCRIPT), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--allow-shrink", result.stdout)
        self.assertIn(
            "90% of the committed ASVS nodes", " ".join(result.stdout.split())
        )

    def load_fixture_data(self):
        """Load fixture data used to construct the test database."""
        source_nodes = json.loads(
            (INPUTS_DIR / "source_nodes.json").read_text(encoding="utf-8")
        )
        curated = json.loads((INPUTS_DIR / "curated.json").read_text(encoding="utf-8"))
        return source_nodes, curated

    def test_shrink_guard_accepts_exactly_90_percent(self):
        """Verify the shrink guard accepts exactly 90 percent of ASVS nodes."""
        old_nodes, _ = self.load_fixture_data()
        asvs_nodes = [{"standard": "ASVS"}] * 250
        REFRESH_MODULE.validate_asvs_count(asvs_nodes, old_nodes)

    def test_shrink_guard_rejects_below_90_percent(self):
        """Verify the shrink guard rejects ASVS counts below 90 percent."""
        old_nodes, _ = self.load_fixture_data()
        asvs_nodes = [{"standard": "ASVS"}] * 249
        with self.assertRaisesRegex(ValueError, "at least 250 required"):
            REFRESH_MODULE.validate_asvs_count(asvs_nodes, old_nodes)

    def test_shrink_guard_allows_explicit_override(self):
        """Verify the explicit override permits an ASVS count reduction."""
        old_nodes, _ = self.load_fixture_data()
        asvs_nodes = [{"standard": "ASVS"}] * 249
        REFRESH_MODULE.validate_asvs_count(asvs_nodes, old_nodes, allow_shrink=True)

    def test_validation_rejects_missing_asvs_nodes(self):
        """Verify validation rejects source data without ASVS nodes."""
        _, curated = self.load_fixture_data()
        with self.assertRaisesRegex(ValueError, "no ASVS source nodes"):
            REFRESH_MODULE.validate_outputs([], curated)

    def test_validation_rejects_unresolved_curated_asvs_section(self):
        """Verify validation rejects curated sections without a CRE mapping."""
        source_nodes, curated = self.load_fixture_data()
        section_id = curated["explicit"][0]["asvs_section_id"]
        source_nodes = [
            node
            for node in source_nodes
            if not (node["standard"] == "ASVS" and node["section_id"] == section_id)
        ]

        with self.assertRaisesRegex(
            ValueError, "must resolve to exactly one ASVS CRE ID"
        ):
            REFRESH_MODULE.validate_outputs(source_nodes, curated)

    def test_validation_rejects_multiple_cre_ids_for_curated_section(self):
        """Verify validation rejects curated sections with multiple CRE mappings."""
        source_nodes, curated = self.load_fixture_data()
        section_id = curated["explicit"][0]["asvs_section_id"]
        node = next(
            node
            for node in source_nodes
            if node["standard"] == "ASVS" and node["section_id"] == section_id
        )
        node["cre_ids"] = sorted(node["cre_ids"] + ["ZZZ-TEST-CRE"])

        with self.assertRaisesRegex(
            ValueError, "must resolve to exactly one ASVS CRE ID"
        ):
            REFRESH_MODULE.validate_outputs(source_nodes, curated)

    def create_database(self, path):
        """Create a temporary SQLite database for refresh tests."""
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

    def seed_asvs_nodes(self, conn):
        """Insert ASVS fixture nodes and their CRE mappings into the test database."""
        nodes = json.loads(
            (INPUTS_DIR / "source_nodes.json").read_text(encoding="utf-8")
        )
        asvs_nodes = [node for node in nodes if node["standard"] == "ASVS"]

        for index, node in enumerate(asvs_nodes):
            node_id = f"asvs-node-{index}"
            conn.execute(
                "INSERT INTO node (id, name, section, section_id) "
                "VALUES (?, ?, ?, ?)",
                (node_id, node["name"], node["section"], node["section_id"]),
            )
            for cre_index, external_id in enumerate(node["cre_ids"]):
                cre_id = f"asvs-cre-{index}-{cre_index}"
                conn.execute(
                    "INSERT INTO cre (id, external_id) VALUES (?, ?)",
                    (cre_id, external_id),
                )
                conn.execute(
                    "INSERT INTO cre_node_links (type, cre, node) " "VALUES (?, ?, ?)",
                    ("test", cre_id, node_id),
                )

    def test_missing_database_is_not_created(self):
        """Verify a missing database path does not create a database file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "does-not-exist.sqlite"
            output_dir = temp_path / "output"

            result = subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(db_path.exists())
            self.assertFalse(output_dir.exists())

    def test_missing_historical_pin_is_reported(self):
        """Verify missing historical pins are reported during refresh."""
        source_nodes, curated = self.load_fixture_data()
        pin = curated["multilink_pins"][0]
        snapshot_node = next(
            node
            for node in source_nodes
            if (node["name"], node["section_id"]) == (pin["name"], pin["section_id"])
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "asvs-only.sqlite"
            output_dir = temp_path / "output"
            self.create_database(db_path)

            import sqlite3

            conn = sqlite3.connect(db_path)
            self.seed_asvs_nodes(conn)
            conn.commit()
            conn.close()

            result = subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                f"{pin['name']}/{pin['section_id']}: "
                f"{snapshot_node['cre_ids']} -> missing in DB",
                result.stdout,
            )

    def test_empty_database_fails_without_writing_outputs(self):
        """Verify an empty database fails without writing fixture outputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "empty.sqlite"
            output_dir = temp_path / "output"
            self.create_database(db_path)

            result = subprocess.run(
                [
                    sys.executable,
                    str(REFRESH_SCRIPT),
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing ASVS shrink", result.stderr)
            self.assertFalse(output_dir.exists())

    def test_changed_cre_mapping_preserves_historical_snapshot(self):
        """Verify changed CRE mappings preserve historical pin snapshots."""
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
            self.seed_asvs_nodes(conn)
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

            result = subprocess.run(
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
        self.assertIn(
            f"{pin['name']}/{pin['section_id']}: "
            f"{original_node['cre_ids']} -> "
            "['CHANGED-CRE-1', 'CHANGED-CRE-2']",
            result.stdout,
        )
        self.assertNotEqual(
            refreshed_by_key[key]["cre_ids"],
            ["CHANGED-CRE-1", "CHANGED-CRE-2"],
        )

    def test_repin_selects_first_fifteen_eligible_nodes(self):
        """Verify repinning selects the first fifteen eligible nodes."""
        import sqlite3

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "repin.sqlite"
            output_dir = temp_path / "output"
            self.create_database(db_path)

            conn = sqlite3.connect(db_path)
            self.seed_asvs_nodes(conn)

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

        self.assertEqual(len(refreshed_nodes), 277 + 15)

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
