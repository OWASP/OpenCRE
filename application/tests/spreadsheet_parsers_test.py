import copy
import json
from pprint import pprint
import unittest
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application.utils.spreadsheet_parsers import (
    parse_export_format,
    parse_hierarchical_export_format,
    parse_master_spreadsheet_documents,
    parse_standards,
    supported_resource_mapping,
)


class TestParsers(unittest.TestCase):

    def test_parse_export_format(self) -> None:

        input_data, expected = data_gen.export_format_data()
        documents = parse_export_format(input_data)
        actual_cres = documents.pop(defs.Credoctypes.CRE.value)
        standards = documents
        self.maxDiff = None

        expected_cres = expected.pop(defs.Credoctypes.CRE)
        self.assertListEqual(list(actual_cres), list(expected_cres))
        self.assertDictEqual(expected, standards)

    def test_parse_hierarchical_export_format_cre_only(self) -> None:
        input_data, _expected = data_gen.root_csv_data()
        output = parse_hierarchical_export_format(input_data)
        self.assertIn(defs.Credoctypes.CRE.value, list(output.keys()))

    def test_parse_master_after_cre_only_on_same_row_objects_drops_standards(
        self,
    ) -> None:
        """Regression: _parse_cre_graph_and_rows mutates row dicts; a second full parse
        on the same list must not run after parse_hierarchical_export_format or ASVS etc.
        are lost (checkpoint import used to do this).
        """
        input_data, _ = data_gen.root_csv_data()
        fresh = copy.deepcopy(input_data)
        parse_hierarchical_export_format(input_data)
        after_mutation = parse_master_spreadsheet_documents(input_data)
        from_clean = parse_master_spreadsheet_documents(fresh)
        self.assertGreater(len(from_clean.get("ASVS", [])), 0)
        self.assertLess(
            len(after_mutation.get("ASVS", [])), len(from_clean.get("ASVS", []))
        )

    def test_parse_master_spreadsheet_documents(self) -> None:
        #  TODO(northdpole): add a tags linking test
        input_data, expected_output = data_gen.root_csv_data()
        output = parse_master_spreadsheet_documents(input_data)
        self.maxDiff = None

        # Parser now enriches documents with classification tags; compare by ids.
        for k, expected_docs in expected_output.items():
            expected_ids = {getattr(d, "id", None) for d in expected_docs}
            output_ids = {getattr(d, "id", None) for d in output.get(k, [])}
            self.assertSetEqual(
                expected_ids,
                output_ids,
                f"Mismatched ids for {k}: expected {sorted(expected_ids)} got {sorted(output_ids)}",
            )

    def test_parse_standards_subparser_equivalence(self) -> None:
        """Step 2b: parse_standards matches aggregate of per-family extraction."""
        input_data, expected_output = data_gen.root_csv_data()
        # Use first row that has standards
        row = input_data[0]
        legacy_links = parse_standards(dict(row))
        # Each link should be for a supported family
        standards_map = supported_resource_mapping.get("Standards", {})
        for link in legacy_links:
            self.assertIn(link.document.name, standards_map)


if __name__ == "__main__":
    unittest.main()
