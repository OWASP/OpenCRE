# Tests disabled as importer disabled

# from pathlib import Path
# from tempfile import mkdtemp, mkstemp
# import zipfile
# from application.utils import spreadsheet as sheet_utils
# from application.defs import cre_defs as defs
# import unittest
# from application import create_app, sqla  # type: ignore
# from application.database import db
# from unittest.mock import patch

# from application.utils.external_project_parsers.parsers import ccmv4
# from application.prompt_client import prompt_client


# class TestCloudControlsMappingParser(unittest.TestCase):
#     def tearDown(self) -> None:
#         self.app_context.pop()

#     def setUp(self) -> None:
#         self.app = create_app(mode="test")
#         self.app_context = self.app.app_context()
#         self.app_context.push()
#         sqla.create_all()
#         self.collection = db.Node_collection()

#     @patch.object(sheet_utils, "read_spreadsheet")
#     def test_parse(
#         self,
#         mock_read_spreadsheet,
#     ) -> None:
#         for i in range(1, 4):
#             dbcre = self.collection.add_cre(
#                 cre=defs.CRE(id=f"123-{i}{i}{i}", name=f"CRE-123-{i}{i}{i}")
#             )
#             dbnode = self.collection.add_node(
#                 defs.Standard(
#                     name="NIST 800-53 v5",
#                     section=f"nist80053-{i}{i}",
#                     sectionID=f"nist80053-{i}{i}",
#                 )
#             )
#             self.collection.add_link(dbcre, dbnode)
#         mock_read_spreadsheet.return_value = self.csv

#         entries = ccmv4.CloudControlsMatrix().parse(
#             cache=self.collection,
#             ph=prompt_client.PromptHandler(database=self.collection),
#         )

#         expected = [
#             defs.Standard(
#                 links=[
#                     defs.Link(document=defs.CRE(name="CRE-123-111", id="123-111")),
#                     defs.Link(document=defs.CRE(name="CRE-123-222", id="123-222")),
#                 ],
#                 name="Cloud Native Security Controls",
#                 section="asdf:123",
#                 sectionID=123,
#                 version="v4.0",
#             ),
#             defs.Standard(
#                 links=[
#                     defs.Link(document=defs.CRE(name="CRE-123-333", id="123-444")),
#                     defs.Link(document=defs.CRE(name="CRE-123-444", id="123-333")),
#                 ],
#                 name="Cloud Native Security Controls",
#                 section="asdf:124",
#                 sectionID=124,
#                 version="v4.0",
#             ),
#         ]
#         for name, nodes in entries.results.items():
#             self.assertEqual(name, ccmv4.CloudControlsMatrix().name)
#             self.assertEqual(len(nodes), 2)
#             self.assertCountEqual(nodes[0].todict(), expected[0].todict())
#             self.assertCountEqual(nodes[1].todict(), expected[1].todict())

#     csv = {
#         "0.ccmv4": [
#             {
#                 "Control ID": 123,
#                 "Control Title": "",
#                 "NIST 800-53 rev 5": "nist80053-11\nnist80053-22",
#             },
#             {
#                 "Control ID": 124,
#                 "Control Title": "asdf2",
#                 "NIST 800-53 rev 5": "nist80053-33\nnist80053-44",
#             },
#         ]
#     }
