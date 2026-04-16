import os
import unittest
from unittest import mock

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers.ai_exchange.csv_source import (
    is_ai_exchange_spreadsheet,
    normalize_rows_for_master_import,
    parse_csv_to_parse_result,
    parse_row_dicts_to_parse_result,
)


class AiExchangeCsvTest(unittest.TestCase):
    def test_detect_and_normalize_new_header_aliases(self) -> None:
        rows = [
            {
                "CRE ID": "999-010",
                "": "",
                "CRE0": "Root",
                "CRE1": "Leaf Alias",
                "CRE2": "",
                "Cross-link CREs": "",
                "MITRE ATLAS|name": "M1",
                "MITRE ATLAS|id": "AML.M0001",
                "MITRE ATLAS|hyperlink": "https://example.com/m1",
                "AI Exchange|name": "Ctl",
                "AI Exchange|id": "ctlid",
                "AI Exchange|hyperlink": "https://example.com/ctl",
                "OWASP Top10 LLM|name": "Prompt Injection",
                "OWASP Top10 LLM|id": "LLM01:2025",
                "OWASP Top10 LLM|hyperlink": "https://example.com/llm",
                "OWASP Top10 LLM|notes": "note",
                "OWASP Top10 ML|name": "Input Manipulation Attack",
                "OWASP Top10 ML|id": "ML01:2023",
                "OWASP Top10 ML|hyperlink": "https://example.com/ml",
                "ETSI SAI 005 MSR|name": "Evasion attacks",
                "ETSI SAI 005 MSR|id": "6.1; 6.2",
                "ETSI SAI 005 MSR|hyperlink": "https://example.com/etsi",
                "ENISA SMLA|name": "Evasion",
                "ENISA SMLA|id": "Table 3:",
                "ENISA SMLA|hyperlink": "https://example.com/enisa",
                "NIST AI 100-2|name": "Evasion Attacks",
                "NIST AI 100-2|id": "Sec. 2.2",
                "NIST AI 100-2|hyperlink": "https://example.com/nist",
            }
        ]

        self.assertTrue(is_ai_exchange_spreadsheet(rows[0]))
        norm = normalize_rows_for_master_import(rows)
        self.assertEqual(norm[0]["CRE hierarchy 1"], "Root")
        self.assertEqual(norm[0]["CRE hierarchy 2"], "Leaf Alias")
        self.assertEqual(norm[0]["Standard OWASP AI Exchange ID"], "ctlid")
        self.assertEqual(norm[0]["Standard OWASP Top10 for LLM ID"], "LLM01:2025")
        self.assertEqual(norm[0]["Standard ETSI ID"], "6.1; 6.2")
        self.assertEqual(norm[0]["Standard ENISA ID"], "Table 3:")

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
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        csv_path = os.path.join(repo_root, "OpenCRE-AI-RelA.csv")
        if not os.path.isfile(csv_path):
            csv_path = os.path.join(repo_root, "OpenCRE-AI-6-WithMitre.csv")
        if not os.path.isfile(csv_path):
            self.skipTest("fixture missing: OpenCRE-AI-RelA.csv or OpenCRE-AI-6-WithMitre.csv")
        pr = parse_csv_to_parse_result(csv_path)
        self.assertIn(defs.Credoctypes.CRE.value, pr.results)
        self.assertGreater(len(pr.results[defs.Credoctypes.CRE.value]), 5)
        self.assertIn("MITRE ATLAS", pr.results)
        self.assertIn("OWASP AI Exchange", pr.results)
        self.assertGreater(len(pr.results["MITRE ATLAS"]), 0)
        self.assertGreater(len(pr.results["OWASP AI Exchange"]), 0)
        if os.path.basename(csv_path) == "OpenCRE-AI-RelA.csv":
            for family in (
                "OWASP Top10 for LLM",
                "OWASP Top10 for ML",
                "BIML",
                "ETSI",
                "ENISA",
                "NIST AI 100-2",
            ):
                self.assertIn(family, pr.results)
                self.assertGreater(len(pr.results[family]), 0)

    def test_parse_row_dicts_pass_through_master_rows(self) -> None:
        from application.tests.utils import data_gen

        input_data, _ = data_gen.root_csv_data()
        pr = parse_row_dicts_to_parse_result(
            [dict(r) for r in input_data]
        )
        self.assertIn(defs.Credoctypes.CRE.value, pr.results)

    def test_normalize_resolves_cross_link_from_existing_db_cre(self) -> None:
        rows = [
            {
                "CRE ID": "999-100",
                "CRE 0": "Root",
                "CRE 1": "Leaf A",
                "Cross-link CREs": "999-200",
                "MITRE ATLAS|name": "",
                "MITRE ATLAS|id": "",
                "MITRE ATLAS|hyperlink": "",
                "AIX|name": "",
                "AIX|id": "",
                "AIX|hyperlink": "",
            }
        ]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.ai_exchange.csv_source._load_existing_cre_names_by_id",
            return_value={"999-200": "Existing DB CRE"},
        ):
            norm = normalize_rows_for_master_import(rows)
        self.assertEqual(norm[0]["Link to other CRE"], "Existing DB CRE")


if __name__ == "__main__":
    unittest.main()
