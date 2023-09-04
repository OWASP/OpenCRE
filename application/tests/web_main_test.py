import re
import json
import logging
import os
import tempfile
import unittest
from pprint import pprint
from typing import Any, Dict, List

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.defs import osib_defs
from application.web import web_main
from application.utils import mdutils


class TestMain(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

    def test_extend_cre_with_tag_links(self) -> None:
        """
        Given:
        * a CRE CA with tags ta and a "contains" link to CD
        * CRE CB with tags ta,td and a "part of" link to CD
        * CRE CC with tags tc
        * CRE CD with tags tc,td

        extending ca with tag links should return CB as "related" and CD as "contains"
        extending cb with tag links should return CD as "part of" and CA as "related" but not return CD as "related"
        extending cc should return no links
        extending cd should return ca, cb

        """
        collection = db.Node_collection()
        cres = {
            "ca": defs.CRE(id="1", description="CA", name="CA", tags=["ta"]),
            "cb": defs.CRE(id="2", description="CB", name="CB", tags=["ta", "td"]),
            "cc": defs.CRE(id="3", description="CC", name="CC", tags=["tc"]),
            "cd": defs.CRE(id="4", description="CD", name="CD", tags=["", "td"]),
        }
        cres["ca"].add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy())
        )
        cres["cb"].add_link(
            defs.Link(ltype=defs.LinkTypes.PartOf, document=cres["cd"].shallow_copy())
        )
        for _, v in cres.items():
            collection.add_cre(v)

        expected = {
            "ca": cres["ca"].add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Related, document=cres["cb"].shallow_copy()
                )
            ),
            "cb": cres["cb"].add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Related, document=cres["ca"].shallow_copy()
                )
            ),
            "cc": cres["cc"],
            "cd": cres["cd"]
            .add_link(
                defs.Link(
                    ltype=defs.LinkTypes.PartOf, document=cres["ca"].shallow_copy()
                )
            )
            .add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains, document=cres["cb"].shallow_copy()
                )
            ),
        }

        for c, v in cres.items():
            res = web_main.extend_cre_with_tag_links(  # type:ignore # mypy bug
                v, collection=collection
            )
            self.assertCountEqual(res.links, v.links)
            self.assertEqual(res, v)

    def test_find_by_id(self) -> None:
        collection = db.Node_collection()
        collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)

        cres = {
            "ca": defs.CRE(id="1", description="CA", name="CA", tags=["ta"]),
            "cd": defs.CRE(id="2", description="CD", name="CD", tags=["td"]),
            "cb": defs.CRE(id="3", description="CB", name="CB", tags=["tb"]),
        }
        cres["ca"].add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy())
        )
        cres["cb"].add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy())
        )
        dca = collection.add_cre(cres["ca"])
        dcb = collection.add_cre(cres["cb"])
        dcd = collection.add_cre(cres["cd"])

        collection.add_internal_link(group=dca, cre=dcd, type=defs.LinkTypes.Contains)
        collection.add_internal_link(group=dcb, cre=dcd, type=defs.LinkTypes.Contains)
        self.maxDiff = None
        with self.app.test_client() as client:
            response = client.get(f"/rest/v1/id/9999999999")
            self.assertEqual(404, response.status_code)

            expected = {"data": cres["ca"].todict()}
            response = client.get(
                f"/rest/v1/id/{cres['ca'].id}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(json.loads(response.data.decode()), expected)
            self.assertEqual(200, response.status_code)

            osib_response = client.get(
                f"/rest/v1/id/{cres['cb'].id}?osib=true",
                headers={"Content-Type": "application/json"},
            )
            osib_expected = {
                "data": cres["cb"].todict(),
                "osib": osib_defs.cre2osib([cres["cb"]]).todict(),
            }

            self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            self.assertEqual(200, osib_response.status_code)

            md_expected = "<pre>CRE---[2CD](https://www.opencre.org/cre/2),[1CA](https://www.opencre.org/cre/1),[3CB](https://www.opencre.org/cre/3)</pre>"
            md_response = client.get(
                f"/rest/v1/id/{cres['cd'].id}?format=md",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(re.sub("\s", "", md_response.data.decode()), md_expected)

    def test_find_by_name(self) -> None:
        collection = db.Node_collection()
        collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)

        cres = {
            "ca": defs.CRE(id="1", description="CA", name="CA", tags=["ta"]),
            "cd": defs.CRE(id="2", description="CD", name="CD", tags=["td"]),
            "cb": defs.CRE(id="3", description="CB", name="CB", tags=["tb"]),
            "cc": defs.CRE(id="4", description="CC", name="CC", tags=["tc"]),
        }
        cres["ca"].add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy())
        )
        cres["cb"].add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy())
        )
        cres["cc"].add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy())
        )
        dca = collection.add_cre(cres["ca"])
        dcb = collection.add_cre(cres["cb"])
        dcc = collection.add_cre(cres["cc"])
        dcd = collection.add_cre(cres["cd"])
        collection.add_internal_link(group=dca, cre=dcd, type=defs.LinkTypes.Contains)
        collection.add_internal_link(group=dcb, cre=dcd, type=defs.LinkTypes.Contains)
        collection.add_internal_link(group=dcc, cre=dcd, type=defs.LinkTypes.Contains)

        self.maxDiff = None
        with self.app.test_client() as client:
            response = client.get(f"/rest/v1/name/CW")
            self.assertEqual(404, response.status_code)

            expected = {"data": cres["ca"].todict()}
            response = client.get(
                f"/rest/v1/name/{cres['ca'].name}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(json.loads(response.data.decode()), expected)

            osib_response = client.get(
                f"/rest/v1/name/{cres['cb'].name}?osib=true",
                headers={"Content-Type": "application/json"},
            )
            osib_expected = {
                "data": cres["cb"].todict(),
                "osib": osib_defs.cre2osib([cres["cb"]]).todict(),
            }
            self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            self.assertEqual(200, osib_response.status_code)

            md_expected = "<pre>CRE---[2CD](https://www.opencre.org/cre/2),[1CA](https://www.opencre.org/cre/1),[3CB](https://www.opencre.org/cre/3),[4CC](https://www.opencre.org/cre/4)</pre>"
            md_response = client.get(
                f"/rest/v1/name/{cres['cd'].name}?format=md",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(re.sub("\s", "", md_response.data.decode()), md_expected)

            csv_expected = "CRE:name,CRE:id,CRE:description,Linked_CRE_0:id,Linked_CRE_0:name,Linked_CRE_0:link_type,Linked_CRE_1:id,Linked_CRE_1:name,Linked_CRE_1:link_type,Linked_CRE_2:id,Linked_CRE_2:name,Linked_CRE_2:link_typeCC,4,CC,2,CD,Contains,,,,,,"
            csv_response = client.get(f"/rest/v1/name/{cres['cc'].name}?format=csv")
            self.assertEqual(re.sub("\s", "", csv_response.data.decode()), csv_expected)

    def test_find_node_by_name(self) -> None:
        collection = db.Node_collection()
        nodes = {
            "sa": defs.Standard(
                name="s1", section="s11", subsection="s111", version="1.1.1"
            ),
            "sb": defs.Standard(
                name="s1", section="s22", subsection="s111", version="2.2.2"
            ),
            "sc": defs.Standard(
                name="s1", section="s22", subsection="s333", version="3.3.3"
            ),
            "sd": defs.Standard(
                name="s1", section="s22", subsection="s333", version="4.0.0"
            ),
            "se": defs.Standard(
                name="s1", hyperlink="https://example.com/foo", tags=["s1"]
            ),
            "c0": defs.Code(
                name="C0", description="print(0)", hyperlink="https://example.com/c0"
            ),
        }
        for _, v in nodes.items():
            collection.add_node(v)

        self.maxDiff = None

        with self.app.test_client() as client:
            response = client.get(f"/rest/v1/standard/9999999999")
            self.assertEqual(404, response.status_code)
            response = client.get(f"/rest/v1/foobar/9999999999")
            self.assertEqual(404, response.status_code)

            expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [
                    s.todict()
                    for _, s in nodes.items()
                    if s.doctype == defs.Credoctypes.Standard
                ],
            }
            response = client.get(
                f"/rest/v1/standard/{nodes['sa'].name}",
                headers={"Content-Type": "application/json"},
            )

            self.assertEqual(json.loads(response.data.decode()), expected)
            self.assertEqual(200, response.status_code)

            section_expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [
                    s.todict()
                    for _, s in nodes.items()
                    if s.doctype == defs.Credoctypes.Standard
                    and s.section == nodes["sb"].section
                ],
            }
            section_response = client.get(
                f"/rest/v1/standard/{nodes['sb'].name}?section={nodes['sb'].section}",
                headers={"Content-Type": "application/json"},
            )

            self.assertEqual(
                json.loads(section_response.data.decode()), section_expected
            )
            self.assertEqual(200, section_response.status_code)

            subsection_expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [
                    s.todict()
                    for _, s in nodes.items()
                    if s.doctype == defs.Credoctypes.Standard
                    and s.subsection == nodes["sc"].subsection
                ],
            }
            subsection_response = client.get(
                f"/rest/v1/standard/{nodes['sc'].name}?section={nodes['sc'].section}&subsection={nodes['sc'].subsection}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(
                json.loads(subsection_response.data.decode()), subsection_expected
            )
            self.assertEqual(200, subsection_response.status_code)

            version_expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [
                    s.todict()
                    for _, s in nodes.items()
                    if s.doctype == defs.Credoctypes.Standard
                    and s.version == nodes["sd"].version
                ],
            }
            version_response = client.get(
                f"/rest/v1/standard/{nodes['sd'].name}?version={nodes['sd'].version}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(
                json.loads(version_response.data.decode()), version_expected
            )
            self.assertEqual(200, version_response.status_code)

            hyperlink_expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [
                    s.todict()
                    for _, s in nodes.items()
                    if s.doctype == defs.Credoctypes.Standard
                    and s.hyperlink == nodes["se"].hyperlink
                ],
            }
            hyperlink_response = client.get(
                f"/rest/v1/standard/{nodes['se'].name}?hyperlink={nodes['se'].hyperlink}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(
                json.loads(hyperlink_response.data.decode()), hyperlink_expected
            )
            self.assertEqual(200, response.status_code)

            non_standards_expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [nodes["c0"].todict()],
            }
            non_standards_response = client.get(
                f"/rest/v1/code/{nodes['c0'].name}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(
                json.loads(non_standards_response.data.decode()), non_standards_expected
            )
            self.assertEqual(200, non_standards_response.status_code)

            osib_expected = {
                "total_pages": 1,
                "page": 1,
                "standards": [nodes["c0"].todict()],
                "osib": osib_defs.cre2osib([nodes["c0"]]).todict(),
            }
            osib_response = client.get(f"/rest/v1/code/{nodes['c0'].name}?osib=true")
            self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            self.assertEqual(200, osib_response.status_code)

            md_expected = "<pre>C0--[C0](https://example.com/c0)</pre>"
            md_response = client.get(f"/rest/v1/code/{nodes['c0'].name}?format=md")
            self.assertEqual(re.sub("\s", "", md_response.data.decode()), md_expected)

            csv_expected = "CRE:name,CRE:id,CRE:description,Code:C0:section,Code:C0:subsection,Code:C0:hyperlink,Code:C0:link_type,Standard:s1:section,Standard:s1:subsection,Standard:s1:hyperlink,Standard:s1:link_type,,,,,,,s11,s111,,,,,,,,,s22,s111,,,,,,,,,s22,s333,,,,,,,,,s22,s333,,,,,,,,,,,https://example.com/foo,"
            csv_response = client.get(
                f"/rest/v1/standard/{nodes['sa'].name}?format=csv"
            )
            self.assertEqual(re.sub("\s", "", csv_response.data.decode()), csv_expected)

    def test_find_document_by_tag(self) -> None:
        collection = db.Node_collection()
        cres = {
            "ca": defs.CRE(id="1", description="CA", name="CA", tags=["ta"]),
            "cb": defs.CRE(
                id="3", description="CB", name="CB", tags=["ta", "tb", "tc"]
            ),
        }

        collection.add_cre(cres["ca"])
        collection.add_cre(cres["cb"])

        with self.app.test_client() as client:
            response = client.get(f"/rest/v1/tags?tag=CW")
            self.assertEqual(404, response.status_code)

            expected = {"data": [cres["ca"].todict(), cres["cb"].todict()]}

            response = client.get(f"/rest/v1/tags?tag=ta")
            self.assertEqual(200, response.status_code)
            self.assertCountEqual(json.loads(response.data.decode()), expected)

            osib_response = client.get(
                f"/rest/v1/tags?tag=tb&tag=tc&osib=true",
                headers={"Content-Type": "application/json"},
            )
            osib_expected = {
                "data": cres["cb"].todict(),
                "osib": osib_defs.cre2osib([cres["cb"]]).todict(),
            }
            self.assertCountEqual(osib_response.json, osib_expected)
            self.assertEqual(200, osib_response.status_code)

    def test_test_search(self) -> None:
        collection = db.Node_collection()
        docs = {
            "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
            "sa": defs.Standard(section="sa", subsection="sbb", name="SB"),
        }

        collection.add_cre(docs["ca"])
        collection.add_node(docs["sa"])

        with self.app.test_client() as client:
            response = client.get(f"/rest/v1/text_search?text='CRE:2'")
            self.assertEqual(404, response.status_code)

            expected = [docs["ca"].todict()]
            requests = [
                "/rest/v1/text_search?text='CRE:111-111'",
                "/rest/v1/text_search?text='CRE:CA'" "/rest/v1/text_search?text='CA'",
            ]
            for r in requests:
                response = client.get(r)
                self.assertEqual(200, response.status_code)
                self.assertCountEqual(response.json, expected)

            expected = [docs["sa"].todict()]
            srequests = [
                "/rest/v1/text_search?text=Standard:SB",
                "/rest/v1/text_search?text=Standard:SB:sa",
                "/rest/v1/text_search?text=Standard:SB:sa:sbb",
                "/rest/v1/text_search?text=SB",
            ]
            for r in srequests:
                resp = client.get(r)
                self.assertEqual(200, resp.status_code)
                self.assertDictEqual(resp.json[0], expected[0])

    def test_find_root_cres(self) -> None:
        self.maxDiff = None
        collection = db.Node_collection()
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/root_cres",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(404, response.status_code)

            cres = {
                "ca": defs.CRE(id="1", description="CA", name="CA", tags=["ta"]),
                "cd": defs.CRE(id="2", description="CD", name="CD", tags=["td"]),
                "cb": defs.CRE(id="3", description="CB", name="CB", tags=["tb"]),
            }
            cres["ca"].add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy()
                )
            )
            cres["cb"].add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy()
                )
            )
            dca = collection.add_cre(cres["ca"])
            dcb = collection.add_cre(cres["cb"])
            dcd = collection.add_cre(cres["cd"])
            collection.add_internal_link(
                group=dca, cre=dcd, type=defs.LinkTypes.Contains
            )
            collection.add_internal_link(
                group=dcb, cre=dcd, type=defs.LinkTypes.Contains
            )

            expected = {"data": [cres["ca"].todict(), cres["cb"].todict()]}
            response = client.get(
                "/rest/v1/root_cres",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(json.loads(response.data.decode()), expected)
            self.assertEqual(200, response.status_code)

            osib_response = client.get(
                "/rest/v1/root_cres?osib=true",
                headers={"Content-Type": "application/json"},
            )
            osib_expected = {
                "data": [cres["ca"].todict(), cres["cb"].todict()],
                "osib": osib_defs.cre2osib([cres["ca"], cres["cb"]]).todict(),
            }
            self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            self.assertEqual(200, osib_response.status_code)

    def test_smartlink(self) -> None:
        self.maxDiff = None
        collection = db.Node_collection()
        with self.app.test_client() as client:
            response = client.get(
                "/smartlink/standard/foo/611",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(404, response.status_code)

            cres = {
                "ca": defs.CRE(id="1", description="CA", name="CA", tags=["ta"]),
                "cd": defs.CRE(id="2", description="CD", name="CD", tags=["td"]),
                "cb": defs.CRE(id="3", description="CB", name="CB", tags=["tb"]),
            }
            standards = {
                "cwe0": defs.Standard(name="CWE", sectionID="456"),
                "ASVS": defs.Standard(name="ASVS", section="v0.1.2"),
            }
            cres["ca"].add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy()
                )
            )
            cres["cb"].add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains, document=cres["cd"].shallow_copy()
                )
            )
            cres["cd"].add_link(defs.Link(document=standards["cwe0"]))
            cres["cb"].add_link(defs.Link(document=standards["ASVS"]))

            dca = collection.add_cre(cres["ca"])
            dcb = collection.add_cre(cres["cb"])
            dcd = collection.add_cre(cres["cd"])
            dasvs = collection.add_node(standards["ASVS"])
            dcwe = collection.add_node(standards["cwe0"])
            collection.add_internal_link(
                group=dca, cre=dcd, type=defs.LinkTypes.Contains
            )
            collection.add_internal_link(
                group=dcb, cre=dcd, type=defs.LinkTypes.Contains
            )

            collection.add_link(dcb, dasvs)
            collection.add_link(dcd, dcwe)

            response = client.get(
                "/smartlink/standard/CWE/456",
                headers={"Content-Type": "application/json"},
            )
            location = ""
            for head in response.headers:
                if head[0] == "Location":
                    location = head[1]
            self.assertEqual(location, "/node/standard/CWE/sectionid/456")
            self.assertEqual(302, response.status_code)

            response = client.get(
                "/smartlink/standard/ASVS/v0.1.2",
                headers={"Content-Type": "application/json"},
            )
            location = ""
            for head in response.headers:
                if head[0] == "Location":
                    location = head[1]
            self.assertEqual(location, "/node/standard/ASVS/section/v0.1.2")
            self.assertEqual(302, response.status_code)

            # negative test, this cwe does not exist, therefore there is nowhere to redirect to
            response = client.get(
                "/smartlink/standard/CWE/999",
                headers={"Content-Type": "application/json"},
            )
            location = ""
            for head in response.headers:
                if head[0] == "Location":
                    location = head[1]
            self.assertEqual(location, "")
            self.assertEqual(404, response.status_code)
