from pathlib import Path
from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
from unittest.mock import patch
import os

from application.utils.external_project_parsers.parsers import juiceshop
from application.prompt_client import prompt_client
import requests


class TestJuiceshopParser(unittest.TestCase):
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
            defs.Standard(name="fakeNode", sectionID="123")
        )
        self.collection.add_link(dbcre, dbnode)

        mock_requests.return_value = fakeRequest()
        mock_get_text_embeddings.return_value = [0.1, 0.2]
        mock_get_id_of_most_similar_cre.return_value = dbcre.id
        mock_get_id_of_most_similar_node.return_value = dbnode.id

        entries = juiceshop.JuiceShop().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )

        expected = [
            defs.Tool(
                embeddings=[0.1, 0.2],
                embeddings_text="XSS",
                hyperlink="https://demo.owasp-juice.shop//#/score-board?searchQuery=API-only%20XSS",
                links=[
                    defs.Link(document=defs.CRE(name="CRE-123", id="123-123")),
                ],
                tags=["XSS"],
                name="OWASP Juice Shop",
                section="API-only XSS",
                sectionID="restfulXssChallenge",
                description='Perform a <i>persisted</i> XSS attack with <code>&lt;iframe src="javascript:alert(`xss`)"&gt;</code> without using the frontend application at all.',
                tooltype=defs.ToolTypes.Training,
            ),
            defs.Tool(
                description="Gain access to any access log file of the server.",
                embeddings=[0.1, 0.2],
                embeddings_text="Sensitive Data Exposure",
                hyperlink="https://demo.owasp-juice.shop//#/score-board?searchQuery=Access%20Log",
                links=[
                    defs.Link(document=defs.CRE(name="CRE-123", id="123-123")),
                ],
                name="OWASP Juice Shop",
                section="Access Log",
                sectionID="accessLogDisclosureChallenge",
                tags=["Sensitive Data Exposure"],
                tooltype=defs.ToolTypes.Training,
            ),
        ]
        for name, nodes in entries.results.items():
            self.assertEqual(name, juiceshop.JuiceShop().name)
            self.assertEqual(len(nodes), 2)
            self.assertCountEqual(nodes[0].todict(), expected[0].todict())
            self.assertCountEqual(nodes[1].todict(), expected[1].todict())

    csv = """-
  name: 'API-only XSS'
  category: 'XSS'
  tags:
    - Danger Zone
  description: 'Perform a <i>persisted</i> XSS attack with <code>&lt;iframe src="javascript:alert(`xss`)"&gt;</code> without using the frontend application at all.'
  difficulty: 3
  hint: 'You need to work with the server-side API directly. Try different HTTP verbs on different entities exposed through the API.'
  hintUrl: 'https://pwning.owasp-juice.shop/companion-guide/latest/part2/xss.html#_perform_a_persisted_xss_attack_without_using_the_frontend_application_at_all'
  mitigationUrl: 'https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html'
  key: restfulXssChallenge
  disabledEnv:
    - Docker
    - Heroku
    - Gitpod
-
  name: 'Access Log'
  category: 'Sensitive Data Exposure'
  description: 'Gain access to any access log file of the server.'
  difficulty: 4
  hint: 'Who would want a server access log to be accessible through a web application?'
  hintUrl: 'https://pwning.owasp-juice.shop/companion-guide/latest/part2/sensitive-data-exposure.html#_gain_access_to_any_access_log_file_of_the_server'
  mitigationUrl: 'https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html'
  key: accessLogDisclosureChallenge
"""
