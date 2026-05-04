import unittest
from argparse import Namespace
from unittest.mock import patch

from application.cmd import cre_main
from application.utils import cres_csv_export as export_mod


class TestExportCsvHelpers(unittest.TestCase):
    def test_shortest_paths_single_chain(self) -> None:
        parents = {"T": ["A"], "A": ["R"], "R": []}
        children = {"R": ["A"], "A": ["T"], "T": []}
        roots = {"R"}
        paths = export_mod._shortest_paths_to_target(
            parents=parents, children=children, roots=roots, target="T"
        )
        self.assertEqual(paths, [["R", "A", "T"]])

    def test_shortest_paths_diamond_two_parents(self) -> None:
        parents = {"T": ["A", "B"], "A": ["R"], "B": ["R"], "R": []}
        children = {"R": ["A", "B"], "A": ["T"], "B": ["T"], "T": []}
        roots = {"R"}
        paths = export_mod._shortest_paths_to_target(
            parents=parents, children=children, roots=roots, target="T"
        )
        normalized = sorted(tuple(p) for p in paths)
        self.assertEqual(normalized, [("R", "A", "T"), ("R", "B", "T")])

    def test_shortest_paths_target_is_root(self) -> None:
        parents = {"T": []}
        children = {"T": []}
        roots = {"T"}
        paths = export_mod._shortest_paths_to_target(
            parents=parents, children=children, roots=roots, target="T"
        )
        self.assertEqual(paths, [["T"]])

    def test_shortest_paths_picks_global_shortest_root(self) -> None:
        parents = {"T": ["X"], "X": ["Rnear"], "Rnear": [], "Y": ["Rfar"], "Rfar": []}
        children = {"Rnear": ["X"], "X": ["T"], "T": [], "Rfar": ["Y"], "Y": []}
        roots = {"Rnear", "Rfar"}
        paths = export_mod._shortest_paths_to_target(
            parents=parents, children=children, roots=roots, target="T"
        )
        self.assertEqual(paths, [["Rnear", "X", "T"]])

    def test_roots_and_bfs_dist(self) -> None:
        parents = {"c": ["b"], "b": ["a"], "a": []}
        self.assertEqual(export_mod._roots(parents, ["a", "b", "c"]), {"a"})
        dist = export_mod._bfs_dist_to_target(parents, "c")
        self.assertEqual(dist, {"c": 0, "b": 1, "a": 2})

    def test_gather_standard_links_respects_name_filter(self) -> None:
        cre = {
            "links": [
                {
                    "ltype": "Linked To",
                    "document": {
                        "doctype": "Standard",
                        "name": "ASVS",
                        "sectionID": "1",
                        "section": "V1",
                    },
                },
                {
                    "ltype": "Linked To",
                    "document": {
                        "doctype": "Standard",
                        "name": "NIST",
                        "sectionID": "2",
                        "section": "AC",
                    },
                },
            ]
        }
        only_asvs = export_mod._gather_standard_links(cre, {"ASVS"})
        self.assertEqual(len(only_asvs), 1)
        self.assertEqual(only_asvs[0]["name"], "ASVS")
        all_links = export_mod._gather_standard_links(cre, set())
        self.assertEqual(len(all_links), 2)

    def test_aggregate_standard_columns_pipe_aligned(self) -> None:
        links = [
            {
                "name": "ASVS",
                "sectionID": "1",
                "section": "A",
                "subsection": "",
                "hyperlink": "",
                "description": "",
                "version": "",
                "tooltype": "",
                "ltype": "Linked To",
            },
            {
                "name": "ASVS",
                "sectionID": "2",
                "section": "B",
                "subsection": "",
                "hyperlink": "",
                "description": "",
                "version": "",
                "tooltype": "",
                "ltype": "Linked To",
            },
        ]
        row, keys = export_mod._aggregate_standard_columns(links)
        self.assertEqual(row["ASVS|id"], "1|2")
        self.assertEqual(row["ASVS|name"], "A|B")
        self.assertIn("ASVS|link_type", keys)
        self.assertEqual(row["ASVS|link_type"], "Linked To|Linked To")

    def test_cre_cell_uses_pipe(self) -> None:
        self.assertEqual(
            export_mod._cre_cell({"id": "155-155", "name": "Architecture"}),
            "155-155|Architecture",
        )


class TestExportCliBehavior(unittest.TestCase):
    @patch.object(cre_main.cres_csv_export, "export_cres_and_standards_csv")
    @patch.object(cre_main, "add_from_spreadsheet")
    def test_run_export_short_circuits_other_actions(
        self, add_from_spreadsheet_mock, export_mock
    ) -> None:
        export_mock.return_value = 10
        args = Namespace(
            export=True,
            csv="tmp/out.csv",
            add=True,
            from_ai_exchange_csv=None,
            from_spreadsheet="https://example.invalid/sheet",
            delete_map_analysis_for="",
            delete_resource="",
            zap_in=False,
            cheatsheets_in=False,
            github_tools_in=False,
            capec_in=False,
            cwe_in=False,
            csa_ccm_v4_in=False,
            iso_27001_in=False,
            owasp_secure_headers_in=False,
            pci_dss_4_in=False,
            juiceshop_in=False,
            dsomm_in=False,
            cloud_native_security_controls_in=False,
            import_external_projects=False,
            regenerate_embeddings=False,
            generate_embeddings=False,
            populate_neo4j_db=False,
            start_worker=False,
            preload_map_analysis_target_url="",
            ga_backfill_missing=False,
            ga_backfill_batch_size=200,
            ga_backfill_poll_seconds=5,
            ga_backfill_max_pairs=0,
            ga_backfill_no_queue=False,
            upstream_sync=False,
            cache_file="standards_cache.sqlite",
        )
        cre_main.run(args)
        export_mock.assert_called_once_with(output_path="tmp/out.csv")
        add_from_spreadsheet_mock.assert_not_called()

    def test_run_export_requires_csv(self) -> None:
        args = Namespace(
            export=True,
            csv="",
        )
        with self.assertRaises(ValueError):
            cre_main.run(args)


if __name__ == "__main__":
    unittest.main()
