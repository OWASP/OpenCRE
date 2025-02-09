import json
from pprint import pprint
import unittest
from application.database import db
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application import create_app, sqla  # type: ignore
from application.utils.spreadsheet_parsers import (
    parse_export_format,
    parse_hierarchical_export_format,
    suggest_from_export_format,
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

    def test_parse_hierarchical_export_format(self) -> None:
        #  TODO(northdpole): add a tags linking test
        input_data, expected_output = data_gen.root_csv_data()
        output = parse_hierarchical_export_format(input_data)
        self.maxDiff = None

        for k, v in expected_output.items():
            for element in v:
                self.assertIn(element, output[k])

        for k, v in output.items():
            for element in v:
                self.assertIn(element, output[k])

    def test_suggest_from_export_format(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        collection = db.Node_collection()

        input_data, expected_output = data_gen.export_format_data()
        for cre in expected_output[defs.Credoctypes.CRE.value]:
            collection.add_cre(cre=cre)

        # clean every other cre
        index = 0
        input_data_no_cres = []
        for line in input_data:
            no_cre_line = line.copy()
            if index % 2 == 0:
                [no_cre_line.pop(key) for key in line.keys() if key.startswith("CRE")]
            index += 1
            input_data_no_cres.append(no_cre_line)
        output = suggest_from_export_format(
            lfile=input_data_no_cres, database=collection
        )
        self.maxDiff = None

        empty_lines = 0
        for line in output:
            cres_in_line = [
                line[c] for c in line.keys() if c.startswith("CRE") and line[c]
            ]
            if len(cres_in_line) == 0:
                empty_lines += 1

        self.assertGreater(
            len(input_data) / 2, empty_lines
        )  # assert that there was at least some suggestions

        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()


if __name__ == "__main__":
    unittest.main()
