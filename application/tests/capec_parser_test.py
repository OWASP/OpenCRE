from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
import tempfile
from unittest.mock import Mock, patch
import os

from application.utils.external_project_parsers.parsers import capec_parser
from application.prompt_client import prompt_client
import requests


class TestCapecParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(requests, "get")
    def test_register_capec(self, mock_requests) -> None:
        class fakeRequest:
            status_code = 200
            text = self.capec_xml

        mock_requests.return_value = fakeRequest()
        for cwe in [276, 285, 434]:
            dbnode = self.collection.add_node(defs.Standard(name="CWE", sectionID=cwe))
            cre = defs.CRE(id=f"{cwe}-{cwe}", name=f"CRE-{cwe}")
            dbcre = self.collection.add_cre(cre=cre)
            self.collection.add_link(
                cre=dbcre, node=dbnode, ltype=defs.LinkTypes.LinkedTo
            )
        entries = capec_parser.Capec().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )
        expected = [
            defs.Standard(
                name="CAPEC",
                doctype=defs.Credoctypes.Standard,
                links=[
                    defs.Link(
                        document=defs.CRE(name="CRE-276", id="276-276"),
                        ltype=defs.LinkTypes.LinkedTo,
                    ),
                    defs.Link(
                        document=defs.CRE(name="CRE-285", id="285-285"),
                        ltype=defs.LinkTypes.LinkedTo,
                    ),
                    defs.Link(
                        document=defs.CRE(name="CRE-434", id="434-434"),
                        ltype=defs.LinkTypes.LinkedTo,
                    ),
                ],
                hyperlink="https://capec.mitre.org/data/definitions/1.html",
                sectionID="1",
                section="Accessing Functionality Not Properly Constrained by ACLs",
                version="3.7",
            ),
            defs.Standard(
                name="CAPEC",
                doctype=defs.Credoctypes.Standard,
                hyperlink="https://capec.mitre.org/data/definitions/10.html",
                sectionID="10",
                section="Another CAPEC",
                version="3.7",
            ),
        ]
        for name, nodes in entries.results.items():
            self.assertEqual(name, capec_parser.Capec().name)
            self.assertEqual(len(nodes), 2)
            self.assertCountEqual(nodes[0].todict(), expected[0].todict())
            self.assertCountEqual(nodes[1].todict(), expected[1].todict())

    capec_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Attack_Pattern_Catalog xmlns="http://capec.mitre.org/capec-3"
                        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                        xmlns:capec="http://capec.mitre.org/capec-3"
                        xmlns:xhtml="http://www.w3.org/1999/xhtml"
                        Name="CAPEC"
                        Version="3.7"
                        Date="2022-02-22"
                        xsi:schemaLocation="http://capec.mitre.org/capec-3 http://capec.mitre.org/data/xsd/ap_schema_v3.5.xsd">
   <Attack_Patterns>
      <Attack_Pattern ID="1" Name="Accessing Functionality Not Properly Constrained by ACLs"
                      Abstraction="Standard"
                      Status="Stable"> 
         <Related_Weaknesses>
            <Related_Weakness CWE_ID="276"/>
            <Related_Weakness CWE_ID="285"/>
            <Related_Weakness CWE_ID="434"/>
            <Related_Weakness CWE_ID="693"/>
            <Related_Weakness CWE_ID="732"/>
            <Related_Weakness CWE_ID="1193"/>
            <Related_Weakness CWE_ID="1220"/>
            <Related_Weakness CWE_ID="1297"/>
            <Related_Weakness CWE_ID="1311"/>
            <Related_Weakness CWE_ID="1314"/>
            <Related_Weakness CWE_ID="1315"/>
            <Related_Weakness CWE_ID="1318"/>
            <Related_Weakness CWE_ID="1320"/>
            <Related_Weakness CWE_ID="1321"/>
            <Related_Weakness CWE_ID="1327"/>
         </Related_Weaknesses>
      </Attack_Pattern>
         <Attack_Pattern ID="10" Name="Another CAPEC"
                      Abstraction="Standard"
                      Status="Stable"> 
         <Related_Weaknesses>
         </Related_Weaknesses>
      </Attack_Pattern>
   </Attack_Patterns>
</Attack_Pattern_Catalog>"""
