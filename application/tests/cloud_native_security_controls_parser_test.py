from pathlib import Path
from tempfile import mkdtemp, mkstemp
import zipfile
from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
from unittest.mock import patch
import os

from application.utils.external_project_parsers.parsers import (
    cloud_native_security_controls,
)
from application.prompt_client import prompt_client
import requests


class TestCloudNativeSecurityControlsParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(prompt_client.PromptHandler, "get_text_embeddings")
    @patch.object(prompt_client.PromptHandler, "get_id_of_most_similar_cre")
    @patch.object(prompt_client.PromptHandler, "get_id_of_most_similar_node")
    @patch.object(requests, "get")
    def test_parse(
        self,
        mock_requests,
        mock_get_id_of_most_similar_node,
        mock_get_id_of_most_similar_cre,
        mock_get_text_embeddings,
    ) -> None:
        class fakeRequest:
            status_code = 200
            text = self.csv

        cre = defs.CRE(id="123-123", name=f"CRE-123")
        dbcre = self.collection.add_cre(cre=cre)
        dbnode = self.collection.add_node(
            defs.Standard(name="fakeNode", sectionID="123-123")
        )
        self.collection.add_link(dbcre, dbnode, ltype=defs.LinkTypes.LinkedTo)

        mock_requests.return_value = fakeRequest()
        mock_get_text_embeddings.return_value = [0.1, 0.2]
        mock_get_id_of_most_similar_cre.return_value = dbcre.id
        mock_get_id_of_most_similar_node.return_value = dbnode.id

        entries = cloud_native_security_controls.CloudNativeSecurityControls().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )
        expected = [
            defs.Standard(
                embeddings=[0.1, 0.2],
                embeddings_text="Secrets are injected at runtime, such as environment "
                "variables or as a file",
                hyperlink="https://github.com/cloud-native-security-controls/controls-catalog/blob/main/controls/controls_catalog.csv#L2",
                links=[
                    defs.Link(
                        document=defs.CRE(name="CRE-123", id="123-123"),
                        ltype=defs.LinkTypes.LinkedTo,
                    ),
                ],
                name="Cloud Native Security Controls",
                section="Access",
                sectionID=1,
                subsection="Secrets are injected at runtime, such as environment variables "
                "or as a file",
                version="CNSWP v1.0",
            ),
            defs.Standard(
                embeddings=[0.1, 0.2],
                embeddings_text="Secrets are injected at runtime, such as environment variables or as a file",
                hyperlink="https://github.com/cloud-native-security-controls/controls-catalog/blob/main/controls/controls_catalog.csv#L2",
                links=[
                    defs.Link(
                        document=defs.CRE(name="CRE-123", id="123-123"),
                        ltype=defs.LinkTypes.LinkedTo,
                    ),
                ],
                name="Cloud Native Security Controls",
                section="Access",
                sectionID=2,
                subsection="Applications and workloads are explicitly authorized to communicate with each other using mutual authentication",
                version="CNSWP v1.0",
            ),
        ]
        for name, nodes in entries.results.items():
            self.assertEqual(
                name, cloud_native_security_controls.CloudNativeSecurityControls().name
            )
            self.assertEqual(len(nodes), 2)
            self.assertCountEqual(nodes[0].todict(), expected[0].todict())
            self.assertCountEqual(nodes[1].todict(), expected[1].todict())

    csv = """ID,Originating Document,Section,Control Title,Control Implementation,NIST SP800-53r5 references,Assurance Level,Risk Categories
1,CNSWP v1.0,Access,"Secrets are injected at runtime, such as environment variables or as a file",,IA-5(7) Authenticator Management | No Embedded Unencrypted Static Authenticators,N/A,N/A
2,CNSWP v1.0,Access,Applications and workloads are explicitly authorized to communicate with each other using mutual authentication,,IA-9 Service Identification and Authentication,N/A,N/A
"""
