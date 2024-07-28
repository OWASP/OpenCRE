import io
import csv
import random
import string
import re
import json
import unittest
from unittest.mock import patch
import redis
import rq
import os

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.web import web_main
from application.utils.gap_analysis import GAP_ANALYSIS_TIMEOUT
from application.utils import spreadsheet


class MockJob:
    @property
    def id(self):
        return "ABC"

    def get_status(self):
        return rq.job.JobStatus.STARTED


class TestMain(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        os.environ["INSECURE_REQUESTS"] = "True"
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
            "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
            "cb": defs.CRE(
                id="222-222", description="CB", name="CB", tags=["ta", "td"]
            ),
            "cc": defs.CRE(id="333-333", description="CC", name="CC", tags=["tc"]),
            "cd": defs.CRE(id="444-444", description="CD", name="CD", tags=["", "td"]),
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
            "cd": (
                cres["cd"]
                .add_link(
                    defs.Link(
                        ltype=defs.LinkTypes.PartOf, document=cres["ca"].shallow_copy()
                    )
                )
                .add_link(
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=cres["cb"].shallow_copy(),
                    )
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
        collection = db.Node_collection().with_graph()
        # collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)

        cres = {
            "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
            "cd": defs.CRE(id="222-222", description="CD", name="CD", tags=["td"]),
            "cb": defs.CRE(id="333-333", description="CB", name="CB", tags=["tb"]),
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

        collection.add_internal_link(
            higher=dca, lower=dcd, type=defs.LinkTypes.Contains
        )
        collection.add_internal_link(
            higher=dcb, lower=dcd, type=defs.LinkTypes.Contains
        )
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

            # osib_response = client.get(
            #     f"/rest/v1/id/{cres['cb'].id}?osib=true",
            #     headers={"Content-Type": "application/json"},
            # )
            # osib_expected = {
            #     "data": cres["cb"].todict(),
            #     "osib": osib_defs.cre2osib([cres["cb"]]).todict(),
            # }

            # self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            # self.assertEqual(200, osib_response.status_code)

            md_expected = "<pre>CRE---[222-222CD](https://www.opencre.org/cre/222-222),[111-111CA](https://www.opencre.org/cre/111-111),[333-333CB](https://www.opencre.org/cre/333-333)</pre>"
            md_response = client.get(
                f"/rest/v1/id/{cres['cd'].id}?format=md",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(re.sub("\s", "", md_response.data.decode()), md_expected)

    def test_find_by_name(self) -> None:
        collection = db.Node_collection().with_graph()
        cres = {
            "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
            "cd": defs.CRE(id="222-222", description="CD", name="CD", tags=["td"]),
            "cb": defs.CRE(id="333-333", description="CB", name="CB", tags=["tb"]),
            "cc": defs.CRE(id="444-444", description="CC", name="CC", tags=["tc"]),
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
        collection.add_internal_link(
            higher=dca, lower=dcd, type=defs.LinkTypes.Contains
        )
        collection.add_internal_link(
            higher=dcb, lower=dcd, type=defs.LinkTypes.Contains
        )
        collection.add_internal_link(
            higher=dcc, lower=dcd, type=defs.LinkTypes.Contains
        )

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

            # osib_response = client.get(
            #     f"/rest/v1/name/{cres['cb'].name}?osib=true",
            #     headers={"Content-Type": "application/json"},
            # )
            # osib_expected = {
            #     "data": cres["cb"].todict(),
            #     "osib": osib_defs.cre2osib([cres["cb"]]).todict(),
            # }
            # self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            # self.assertEqual(200, osib_response.status_code)

            md_expected = "<pre>CRE---[222-222CD](https://www.opencre.org/cre/222-222),[111-111CA](https://www.opencre.org/cre/111-111),[333-333CB](https://www.opencre.org/cre/333-333),[444-444CC](https://www.opencre.org/cre/444-444)</pre>"
            md_response = client.get(
                f"/rest/v1/name/{cres['cd'].name}?format=md",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(re.sub("\s", "", md_response.data.decode()), md_expected)

            csv_expected = "CRE:name,CRE:id,CRE:description,Linked_CRE_0:id,Linked_CRE_0:name,Linked_CRE_0:link_type,Linked_CRE_1:id,Linked_CRE_1:name,Linked_CRE_1:link_type,Linked_CRE_2:id,Linked_CRE_2:name,Linked_CRE_2:link_typeCC,4,CC,2,CD,Contains,,,,,,"
            csv_response = client.get(f"/rest/v1/name/{cres['cc'].name}?format=csv")
            expected = []
            actual = []
            [expected.append(dict(row)) for row in csv.DictReader([csv_expected])]
            [
                actual.append(dict(row))
                for row in csv.DictReader(str(csv_response.data).splitlines())
            ]
            self.assertCountEqual(expected, actual)

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

            # osib_expected = {
            #     "total_pages": 1,
            #     "page": 1,
            #     "standards": [nodes["c0"].todict()],
            #     "osib": osib_defs.cre2osib([nodes["c0"]]).todict(),
            # }
            # osib_response = client.get(f"/rest/v1/code/{nodes['c0'].name}?osib=true")
            # self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            # self.assertEqual(200, osib_response.status_code)

            md_expected = "<pre>C0--[C0](https://example.com/c0)</pre>"
            md_response = client.get(f"/rest/v1/code/{nodes['c0'].name}?format=md")
            self.assertEqual(re.sub("\s", "", md_response.data.decode()), md_expected)

            csv_expected = "CRE:name,CRE:id,CRE:description,Code:C0:section,Code:C0:subsection,Code:C0:hyperlink,Code:C0:link_type,Standard:s1:section,Standard:s1:subsection,Standard:s1:hyperlink,Standard:s1:link_type,,,,,,,s11,s111,,,,,,,,,s22,s111,,,,,,,,,s22,s333,,,,,,,,,s22,s333,,,,,,,,,,,https://example.com/foo,"
            csv_response = client.get(
                f"/rest/v1/standard/{nodes['sa'].name}?format=csv"
            )
            expected = []
            actual = []
            [expected.append(dict(row)) for row in csv.DictReader([csv_expected])]
            [
                actual.append(dict(row))
                for row in csv.DictReader(str(csv_response.data).splitlines())
            ]
            self.assertCountEqual(expected, actual)

    def test_find_document_by_tag(self) -> None:
        collection = db.Node_collection()
        cres = {
            "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
            "cb": defs.CRE(
                id="333-333", description="CB", name="CB", tags=["ta", "tb", "tc"]
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

            # osib_response = client.get(
            #     f"/rest/v1/tags?tag=tb&tag=tc&osib=true",
            #     headers={"Content-Type": "application/json"},
            # )
            # osib_expected = {
            #     "data": cres["cb"].todict(),
            #     "osib": osib_defs.cre2osib([cres["cb"]]).todict(),
            # }
            # self.assertCountEqual(osib_response.json, osib_expected)
            # self.assertEqual(200, osib_response.status_code)

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
        collection = db.Node_collection().with_graph()
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/root_cres",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(404, response.status_code)

            cres = {
                "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
                "cd": defs.CRE(id="222-222", description="CD", name="CD", tags=["td"]),
                "cb": defs.CRE(id="333-333", description="CB", name="CB", tags=["tb"]),
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
                higher=dca, lower=dcd, type=defs.LinkTypes.Contains
            )
            collection.add_internal_link(
                higher=dcb, lower=dcd, type=defs.LinkTypes.Contains
            )

            expected = {"data": [cres["ca"].todict(), cres["cb"].todict()]}
            response = client.get(
                "/rest/v1/root_cres",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(json.loads(response.data.decode()), expected)
            self.assertEqual(200, response.status_code)

            # osib_response = client.get(
            #     "/rest/v1/root_cres?osib=true",
            #     headers={"Content-Type": "application/json"},
            # )
            # osib_expected = {
            #     "data": [cres["ca"].todict(), cres["cb"].todict()],
            #     "osib": osib_defs.cre2osib([cres["ca"], cres["cb"]]).todict(),
            # }
            # self.assertEqual(json.loads(osib_response.data.decode()), osib_expected)
            # self.assertEqual(200, osib_response.status_code)

    def test_smartlink(self) -> None:
        self.maxDiff = None
        collection = db.Node_collection().with_graph()
        with self.app.test_client() as client:
            response = client.get(
                "/smartlink/standard/foo/611",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(404, response.status_code)

            cres = {
                "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
                "cd": defs.CRE(id="222-222", description="CD", name="CD", tags=["td"]),
                "cb": defs.CRE(id="333-333", description="CB", name="CB", tags=["tb"]),
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
                higher=dca, lower=dcd, type=defs.LinkTypes.Contains
            )
            collection.add_internal_link(
                higher=dcb, lower=dcd, type=defs.LinkTypes.Contains
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

            # negative test, this cwe does not exist, therefore we redirect to Mitre!
            response = client.get(
                "/smartlink/standard/CWE/999",
                headers={"Content-Type": "application/json"},
            )
            location = ""
            for head in response.headers:
                if head[0] == "Location":
                    location = head[1]
            self.assertEqual(
                location, "https://cwe.mitre.org/data/definitions/999.html"
            )
            self.assertEqual(302, response.status_code)

    @patch.object(redis, "from_url")
    @patch.object(db, "Node_collection")
    def test_gap_analysis_from_cache_full_response(
        self, db_mock, redis_conn_mock
    ) -> None:
        expected = {"result": "hello"}
        redis_conn_mock.return_value.exists.return_value = True
        redis_conn_mock.return_value.get.return_value = json.dumps(expected)
        db_mock.return_value.get_gap_analysis_result.return_value = json.dumps(expected)
        db_mock.return_value.gap_analysis_exists.return_value = True
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/map_analysis?standard=aaa&standard=bbb",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(expected, json.loads(response.data))

    @patch.object(db, "Node_collection")
    @patch.object(rq.job.Job, "fetch")
    @patch.object(rq.Queue, "enqueue_call")
    @patch.object(redis, "from_url")
    def test_gap_analysis_from_cache_job_id(
        self, redis_conn_mock, enqueue_call_mock, fetch_mock, db_mock
    ) -> None:
        expected = {"job_id": "hello"}
        redis_conn_mock.return_value.exists.return_value = True
        redis_conn_mock.return_value.get.return_value = json.dumps(expected)
        fetch_mock.return_value = MockJob()
        db_mock.return_value.gap_analysis_exists.return_value = True
        db_mock.return_value.get_gap_analysis_result.return_value = json.dumps(expected)
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/map_analysis?standard=aaa&standard=bbb",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(expected, json.loads(response.data))
            self.assertFalse(enqueue_call_mock.called)

    @patch.object(db, "Node_collection")
    @patch.object(rq.Queue, "enqueue_call")
    @patch.object(redis, "from_url")
    def test_gap_analysis_create_job_id(
        self, redis_conn_mock, enqueue_call_mock, db_mock
    ) -> None:
        expected = {"job_id": "ABC"}
        redis_conn_mock.return_value.get.return_value = None
        enqueue_call_mock.return_value = MockJob()
        db_mock.return_value.get_gap_analysis_result.return_value = None
        db_mock.return_value.gap_analysis_exists.return_value = False
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/map_analysis?standard=aaa&standard=bbb",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(expected, json.loads(response.data))
            enqueue_call_mock.assert_called_with(
                db.gap_analysis,
                kwargs={
                    "neo_db": db_mock().neo_db,
                    "node_names": ["aaa", "bbb"],
                    "cache_key": "aaa >> bbb",
                },
                timeout=GAP_ANALYSIS_TIMEOUT,
            )
            redis_conn_mock.return_value.set.assert_called_with(
                "aaa >> bbb", '{"job_id": "ABC", "result": ""}'
            )

    @patch.object(redis, "from_url")
    @patch.object(db, "Node_collection")
    def test_standards_from_db(self, node_mock, redis_conn_mock) -> None:
        expected = ["A", "B"]
        redis_conn_mock.return_value.get.return_value = None
        node_mock.return_value.standards.return_value = expected
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/standards",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(expected, json.loads(response.data))

    def test_gap_analysis_weak_links_no_cache(self) -> None:
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/map_analysis_weak_links?standard=aaa&standard=bbb&key=ccc`",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(404, response.status_code)

    @patch.object(db, "Node_collection")
    def test_gap_analysis_weak_links_response(self, db_mock) -> None:
        expected = {"result": "hello"}
        db_mock.return_value.get_gap_analysis_result.return_value = json.dumps(expected)
        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/map_analysis_weak_links?standard=aaa&standard=bbb&key=ccc`",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(expected, json.loads(response.data))

    def test_deeplink(self) -> None:
        self.maxDiff = None
        collection = db.Node_collection().with_graph()
        with self.app.test_client() as client:
            response = client.get(
                f"/rest/v1/deeplink/{''.join(random.choice(string.ascii_letters) for i in range(10))}",
            )
            self.assertEqual(404, response.status_code)

            response = client.get(
                f"/deeplink/{''.join(random.choice(string.ascii_letters) for i in range(10))}",
            )
            self.assertEqual(404, response.status_code)

            response = client.get(
                f"/deeplink/standard/{''.join(random.choice(string.ascii_letters) for i in range(10))}",
            )
            self.assertEqual(404, response.status_code)

            cres = {
                "ca": defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"]),
                "cd": defs.CRE(id="222-222", description="CD", name="CD", tags=["td"]),
                "cb": defs.CRE(id="333-333", description="CB", name="CB", tags=["tb"]),
            }
            standards = {
                "cwe0": defs.Standard(name="CWE", sectionID="456"),
                "ASVS": defs.Standard(
                    name="ASVS",
                    section="sectionASVS",
                    sectionID="v0.1.2",
                    hyperlink="https://github.com/owasp/asvs/blah",
                ),
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
                higher=dca, lower=dcd, type=defs.LinkTypes.Contains
            )
            collection.add_internal_link(
                higher=dcb, lower=dcd, type=defs.LinkTypes.Contains
            )

            collection.add_link(dcb, dasvs)
            collection.add_link(dcd, dcwe)

            response = client.get("/rest/v1/deeplink/CWE?sectionid=456")
            self.assertEqual(404, response.status_code)

            # rest/v1 path works
            response = client.get("/rest/v1/deeplink/ASVS?sectionid=v0.1.2")
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with sectionid
            response = client.get("/deeplink/ASVS?sectionid=v0.1.2")
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with sectionID
            response = client.get("/deeplink/ASVS?sectionID=v0.1.2")
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with section
            response = client.get(f'/deeplink/ASVS?section={standards["ASVS"].section}')
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with section and sectionID/sectionid
            response = client.get(
                f'/deeplink/ASVS?section={standards["ASVS"].section}&sectionID={standards["ASVS"].sectionID}'
            )
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with sectionid in path params
            response = client.get(
                f'/deeplink/ASVS/sectionid/{standards["ASVS"].sectionID}'
            )
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with sectionID in path params
            response = client.get(
                f'/deeplink/ASVS/sectionID/{standards["ASVS"].sectionID}'
            )
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with section in path params
            response = client.get(f'/deeplink/ASVS/section/{standards["ASVS"].section}')
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with section and sectionid in path params
            response = client.get(
                f'/deeplink/ASVS/section/{standards["ASVS"].section}/sectionid/{standards["ASVS"].sectionID}'
            )
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

            # Can retrieve with section and sectionID in path params
            response = client.get(
                f'/deeplink/ASVS/section/{standards["ASVS"].section}/sectionID/{standards["ASVS"].sectionID}'
            )
            for head in response.headers:
                if head[0] == "Location":
                    self.assertEqual(head[1], standards["ASVS"].hyperlink)
            self.assertEqual(302, response.status_code)

    @patch.object(db, "Node_collection")
    def test_all_cres(self, db_mock) -> None:
        cres = []

        for i in range(0, 5):
            c = defs.CRE(name=f"cre{i}", id=f"{i}{i}{i}-{i}{i}{i}")
            if i > 0:
                c.add_link(
                    defs.Link(document=cres[i - 1], ltype=defs.LinkTypes.Contains)
                )
            cres.append(c)

        db_mock.return_value.all_cres_with_pagination.return_value = (cres, 1, 1)

        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/all_cres",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            expected = list([c.todict() for c in cres])
            self.assertEqual(
                {"data": expected, "page": 1, "total_pages": 1},
                json.loads(response.data),
            )

    def test_get_cre_csv(self) -> None:
        # empty string means temporary db
        collection = db.Node_collection().with_graph()
        roots = []
        for j in range(2):
            root = defs.CRE(description=f"root{j}", name=f"root{j}", id=f"123-30{j}")
            db_root = collection.add_cre(root)
            roots.append(root)
            previous_db = db_root
            previous_cre = root

            for i in range(4):
                c = defs.CRE(
                    description=f"CREdesc{i}-{j}",
                    name=f"CREname{i}-{j}",
                    id=f"123-4{j}{i}",
                )
                dbcre = collection.add_cre(c)
                collection.add_internal_link(
                    higher=previous_db, lower=dbcre, type=defs.LinkTypes.Contains
                )
                previous_cre.add_link(
                    defs.Link(document=c, ltype=defs.LinkTypes.Contains)
                )
                previous_cre = c
                previous_db = dbcre

        with self.app.test_client() as client:
            response = client.get(
                "/rest/v1/cre_csv",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, response.status_code)
            expected_out = [
                {
                    "CRE 0": "",
                    "CRE 1": "",
                    "CRE 2": "",
                    "CRE 3": "",
                    "CRE 4": "",
                },
                {"CRE 0": "123-300|root0"},
                {"CRE 1": "123-400|CREname0-0"},
                {"CRE 2": "123-401|CREname0-1"},
                {"CRE 3": "123-402|CREname0-2"},
                {"CRE 4": "123-403|CREname0-3"},
                {"CRE 0": "123-301|root1"},
                {"CRE 1": "123-410|CREname1-0"},
                {"CRE 2": "123-411|CREname1-1"},
                {"CRE 3": "123-412|CREname1-2"},
                {"CRE 4": "123-413|CREname1-3"},
            ]
            data = spreadsheet.write_csv(expected_out)
            self.assertEqual(
                data.getvalue(),
                response.data.decode(),
            )
