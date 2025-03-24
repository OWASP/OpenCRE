import unittest
import io
import csv
from pprint import pprint

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.utils.spreadsheet import *
from application.tests.utils.data_gen import export_format_data


class TestDB(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection().with_graph()

    def test_prepare_spreadsheet_one_cre(self) -> None:
        collection = self.collection
        expected = [
            {
                "CRE 0": "444-444|CC",
            },
            {
                "CRE 1": "222-222|CD",
            },
        ]
        cd = defs.CRE(name="CD", description="CD", tags=["td"], id="222-222")
        cc = defs.CRE(
            name="CC",
            description="CC",
            links=[
                defs.Link(
                    document=cd,
                    ltype=defs.LinkTypes.Contains,
                )
            ],
            tags=["tc"],
            metadata={},
            id="444-444",
        )

        collection.add_internal_link(
            collection.add_cre(cc),
            collection.add_cre(cd),
            ltype=defs.LinkTypes.Contains,
        )
        result = ExportSheet().prepare_spreadsheet(storage=collection, docs=[cc, cd])

        self.assertCountEqual(result, expected)

    def test_prepare_spreadsheet_empty(self) -> None:
        collection = self.collection
        expected = []
        result = ExportSheet().prepare_spreadsheet(storage=collection, docs=[])
        self.assertCountEqual(result, expected)

    def test_prepare_spreadsheet(self) -> None:
        collection = self.collection
        expected, inputDocs = export_format_data()
        importItems = []
        for name, items in inputDocs.items():
            for item in items:
                importItems.append(item)
                if name == defs.Credoctypes.CRE:
                    dbitem = collection.add_cre(item)
                else:
                    dbitem = collection.add_node(item)
                for link in item.links:
                    if link.document.doctype == defs.Credoctypes.CRE:
                        linked_item = collection.add_cre(link.document)
                        if item.doctype == defs.Credoctypes.CRE:
                            collection.add_internal_link(
                                dbitem, linked_item, ltype=link.ltype
                            )
                        else:
                            collection.add_link(
                                node=dbitem, cre=linked_item, ltype=link.ltype
                            )
                    else:
                        linked_item = collection.add_node(link.document)
                        if item.doctype == defs.Credoctypes.CRE:
                            collection.add_link(
                                cre=dbitem, node=linked_item, ltype=link.ltype
                            )
                        else:
                            collection.add_internal_link(
                                cre=linked_item, node=dbitem, type=link.ltype
                            )
        result = ExportSheet().prepare_spreadsheet(docs=importItems, storage=collection)

        output = io.StringIO()
        header = expected[0].keys()
        writer = csv.DictWriter(output, fieldnames=header)
        writer.writeheader()
        for row in result:
            writer.writerow(row)
        out = output.getvalue().splitlines()
        result = list(csv.DictReader(out))

        self.assertCountEqual(result, expected)

    # def get_spreadsheet_url(self) -> str:
    #     """Helper function to retrieve the spreadsheet URL from an environment variable."""
    #     return os.environ.get("TEST_SPREADSHEET_URL", "https://docs.google.com/spreadsheets/d/1IgfpPw5TCKSJ4eDlzfI9oNwVOZgtXQvWxSbC7SHE7Zg")

    # def test_read_spreadsheet_iso_numbers(self) -> None:
    #     url = self.get_spreadsheet_url()
    #     alias = "Test Spreadsheet"
    #     result = read_spreadsheet(url, alias, validate=False, parse_numbered_only=False)

    #     # Assuming the spreadsheet has a column "ISO Number" with values "7.10" and "8.20"
    #     expected = [
    #         {"ISO Number": "7.10", "Name": "Example 1", "Value": 10},
    #         {"ISO Number": "8.20", "Name": "Example 2", "Value": 20}
    #     ]

    #     self.assertEqual(result["Sheet1"], expected)
