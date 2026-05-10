import os
import unittest

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers.ai_exchange.csv_source import (
    is_ai_exchange_spreadsheet,
    normalize_rows_for_master_import,
    parse_csv_to_parse_result,
    parse_row_dicts_to_parse_result,
)


class AiExchangeCsvTest(unittest.TestCase):
    def test_detect_and_normalize_shape(self) -> None:
        rows = [
            {
                "OLD CRE 2": "",
                "OLD CRE 3": "",
                "CRE ID": "999-001",
                "CRE 0": "Root",
                "CRE 1": "Leaf A",
                "CRE 2": "",
                "CRE 3": "",
                "CRE 4": "",
                "Cross-link CREs": "999-002",
                "MITRE ATLAS|name": "M1",
                "MITRE ATLAS|id": "AML.M0001",
                "MITRE ATLAS|hyperlink": "https://example.com/m1",
                "AIX|name": "Ctl",
                "AIX|id": "ctlid",
                "AIX|hyperlink": "https://example.com/ctl",
            },
            {
                "CRE ID": "999-002",
                "CRE 0": "Root",
                "CRE 1": "Leaf B",
                "CRE 2": "",
                "CRE 3": "",
                "CRE 4": "",
                "Cross-link CREs": "",
                "MITRE ATLAS|name": "",
                "MITRE ATLAS|id": "",
                "MITRE ATLAS|hyperlink": "",
                "AIX|name": "",
                "AIX|id": "",
                "AIX|hyperlink": "",
            },
        ]
        self.assertTrue(is_ai_exchange_spreadsheet(rows[0]))
        norm = normalize_rows_for_master_import(rows)
        self.assertIn("CRE hierarchy 1", norm[0])
        self.assertEqual(norm[0]["CRE hierarchy 1"], "Root")
        self.assertEqual(norm[0]["CRE hierarchy 2"], "Leaf A")
        self.assertEqual(norm[0]["Link to other CRE"], "Leaf B")
        self.assertEqual(norm[0]["Standard OWASP AI Exchange ID"], "ctlid")

    def test_parse_row_dicts_produces_cres_and_new_standards(self) -> None:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        csv_path = os.path.join(repo_root, "OpenCRE-AI-6-WithMitre.csv")
        if not os.path.isfile(csv_path):
            self.skipTest(f"fixture missing: {csv_path}")
        pr = parse_csv_to_parse_result(csv_path)
        self.assertIn(defs.Credoctypes.CRE.value, pr.results)
        self.assertGreater(len(pr.results[defs.Credoctypes.CRE.value]), 5)
        self.assertIn("MITRE ATLAS", pr.results)
        self.assertIn("OWASP AI Exchange", pr.results)
        self.assertGreater(len(pr.results["MITRE ATLAS"]), 0)
        self.assertGreater(len(pr.results["OWASP AI Exchange"]), 0)

    def test_parse_row_dicts_pass_through_master_rows(self) -> None:
        from application.tests.utils import data_gen

        input_data, _ = data_gen.root_csv_data()
        pr = parse_row_dicts_to_parse_result([dict(r) for r in input_data])
        self.assertIn(defs.Credoctypes.CRE.value, pr.results)


if __name__ == "__main__":
    unittest.main()
