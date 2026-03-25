from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
from unittest.mock import patch
import os

from application.utils.external_project_parsers.parsers import pci_dss
from application.prompt_client import prompt_client
from application.utils import spreadsheet as sheet_utils


class TestPciDssParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(sheet_utils, "read_spreadsheet")
    @patch.object(prompt_client.PromptHandler, "get_text_embeddings")
    @patch.object(prompt_client.PromptHandler, "get_id_of_most_similar_cre")
    @patch.object(prompt_client.PromptHandler, "get_id_of_most_similar_node")
    def test_parse_with_embeddings(
        self,
        mock_get_id_of_most_similar_node,
        mock_get_id_of_most_similar_cre,
        mock_get_text_embeddings,
        mock_read_spreadsheet,
    ) -> None:
        cre = defs.CRE(id="123-123", name="CRE-123")
        dbcre = self.collection.add_cre(cre=cre)
        dbnode = self.collection.add_node(defs.Standard(name="fakeNode", sectionID="123"))
        self.collection.add_link(dbcre, dbnode, ltype=defs.LinkTypes.LinkedTo)

        mock_read_spreadsheet.return_value = self.csv
        mock_get_text_embeddings.return_value = [0.1, 0.2]
        mock_get_id_of_most_similar_cre.return_value = dbcre.id
        mock_get_id_of_most_similar_node.return_value = dbnode.id

        entries = pci_dss.PciDss().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )

        self.assertIn(pci_dss.PciDss().name, entries.results)
        self.assertEqual(len(entries.results[pci_dss.PciDss().name]), 2)
        self.assertGreater(mock_get_text_embeddings.call_count, 0)

    @patch.dict(os.environ, {"CRE_NO_GEN_EMBEDDINGS": "1"})
    @patch.object(sheet_utils, "read_spreadsheet")
    @patch.object(prompt_client.PromptHandler, "get_text_embeddings")
    @patch.object(prompt_client.PromptHandler, "get_id_of_most_similar_cre")
    @patch.object(prompt_client.PromptHandler, "get_id_of_most_similar_node")
    def test_parse_no_embeddings_mode(
        self,
        mock_get_id_of_most_similar_node,
        mock_get_id_of_most_similar_cre,
        mock_get_text_embeddings,
        mock_read_spreadsheet,
    ) -> None:
        mock_read_spreadsheet.return_value = self.csv

        entries = pci_dss.PciDss().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )

        self.assertIn(pci_dss.PciDss().name, entries.results)
        self.assertEqual(len(entries.results[pci_dss.PciDss().name]), 2)
        self.assertEqual(mock_get_text_embeddings.call_count, 0)
        self.assertEqual(mock_get_id_of_most_similar_cre.call_count, 0)
        self.assertEqual(mock_get_id_of_most_similar_node.call_count, 0)
        for node in entries.results[pci_dss.PciDss().name]:
            self.assertFalse(node.embeddings)
            self.assertFalse(node.links)

    csv = {
        "Original Content": [
            {
                "Defined Approach Requirements": "Req 1",
                "PCI DSS ID": "1.1.1",
                "Requirement Description": "desc1",
            },
            {
                "Defined Approach Requirements": "Req 2",
                "PCI DSS ID": "1.1.2",
                "Requirement Description": "desc2",
            },
        ]
    }
