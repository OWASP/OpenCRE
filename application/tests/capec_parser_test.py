from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
import tempfile
import os

from application.utils.external_project_parsers import capec_parser


class TestCapecParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        sqla.create_all(app=self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.collection = db.Node_collection()

    def test_register_capec(self) -> None:
        fd, fname = tempfile.mkstemp()
        with os.fdopen(fd=fd, mode="w") as xml:
            xml.write(self.capec_xml)
        cres = []
        for cwe in [276, 285, 434]:
            dbnode = self.collection.add_node(defs.Standard(name="CWE", section=cwe))
            cre = defs.CRE(id=f"{cwe}-{cwe}", name=f"CRE-{cwe}")
            cres.append(cre)
            dbcre = self.collection.add_cre(cre=cre)
            self.collection.add_link(cre=dbcre, node=dbnode)
        capec_parser.register_capec(cache=self.collection, xml_file=fname)

        expected = defs.Standard(
            name="CAPEC",
            doctype=defs.Credoctypes.Standard,
            links=[
                defs.Link(document=defs.CRE(name="CRE-276", id="276-276")),
                defs.Link(document=defs.CRE(name="CRE-285", id="285-285")),
                defs.Link(document=defs.CRE(name="CRE-434", id="434-434")),
            ],
            hyperlink="https://capec.mitre.org/data/definitions/1.html",
            section="1",
            subsection="Accessing Functionality Not Properly Constrained by ACLs",
            version="3.7",
        )

        node = self.collection.get_nodes(
            name="CAPEC",
            section="1",
            subsection="Accessing Functionality Not Properly Constrained by ACLs",
        )[0]
        self.assertEquals(node, expected)

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
         <Attack_Pattern ID="10" Name="Accessing Functionality Not Properly Constrained by ACLs"
                      Abstraction="Standard"
                      Status="Stable"> 
         <Related_Weaknesses>
         </Related_Weaknesses>
      </Attack_Pattern>
   </Attack_Patterns>
</Attack_Pattern_Catalog>"""
