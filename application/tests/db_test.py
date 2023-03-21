import os
import tempfile
import unittest
import uuid
from copy import copy, deepcopy
from pprint import pprint
from pydoc import doc
from typing import Any, Dict, List, Union

import yaml
from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs


class TestDB(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        sqla.create_all(app=self.app)

        self.app_context = self.app.app_context()
        self.app_context.push()
        self.collection = db.Node_collection()
        collection = self.collection
        collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)

        dbcre = collection.add_cre(
            defs.CRE(id="111-000", description="CREdesc", name="CREname")
        )
        self.dbcre = dbcre
        dbgroup = collection.add_cre(
            defs.CRE(id="111-001", description="Groupdesc", name="GroupName")
        )
        dbstandard = collection.add_node(
            defs.Standard(
                subsection="4.5.6",
                section="FooStand",
                name="BarStand",
                hyperlink="https://example.com",
                tags=["a", "b", "c"],
            )
        )

        collection.add_node(
            defs.Standard(
                subsection="4.5.6",
                section="Unlinked",
                name="Unlinked",
                hyperlink="https://example.com",
            )
        )

        collection.session.add(dbcre)
        collection.add_link(cre=dbcre, node=dbstandard)
        collection.add_internal_link(cre=dbcre, group=dbgroup)

        self.collection = collection

    def test_get_by_tags(self) -> None:
        """
        Given: A CRE with no links and a combination of possible tags:
                    "tag1,dash-2,underscore_3,space 4,co_mb-ination%5"
               A Standard with no links and a combination of possible tags
                    "tag1, dots.5.5, space 6 , several spaces and newline          7        \n"
               some limited overlap between the tag-sets
        Expect:
               The CRE to be returned when searching for "tag-2" and for ["tag1","underscore_3"]
               The Standard to be returned when searching for "space 6" and ["dots.5.5", "space 6"]
               Both to be returned when searching for "space" and "tag1"
        """

        dbcre = db.CRE(
            description="tagCREdesc1",
            name="tagCREname1",
            tags="tag1,dash-2,underscore_3,space 4,co_mb-ination%5",
        )
        cre = db.CREfromDB(dbcre)
        cre.id = ""
        dbstandard = db.Node(
            subsection="4.5.6.7",
            section="tagsstand",
            name="tagsstand",
            link="https://example.com",
            version="",
            tags="tag1, dots.5.5, space 6 , several spaces and newline          7        \n",
            ntype=defs.Standard.__name__,
        )
        standard = db.nodeFromDB(dbstandard)
        self.collection.session.add(dbcre)
        self.collection.session.add(dbstandard)
        self.collection.session.commit()

        self.maxDiff = None
        self.assertEqual(self.collection.get_by_tags(["dash-2"]), [cre])
        self.assertEqual(self.collection.get_by_tags(["tag1", "underscore_3"]), [cre])
        self.assertEqual(self.collection.get_by_tags(["space 6"]), [standard])
        self.assertEqual(
            self.collection.get_by_tags(["dots.5.5", "space 6"]), [standard]
        )

        self.assertCountEqual([cre, standard], self.collection.get_by_tags(["space"]))
        self.assertCountEqual(
            [cre, standard], self.collection.get_by_tags(["space", "tag1"])
        )
        self.assertCountEqual(self.collection.get_by_tags(["tag1"]), [cre, standard])

        self.assertEqual(self.collection.get_by_tags([]), [])
        self.assertEqual(self.collection.get_by_tags(["this should not be a tag"]), [])

    def test_get_standards_names(self) -> None:
        result = self.collection.get_node_names()
        expected = [("Standard", "BarStand"), ("Standard", "Unlinked")]
        self.assertEqual(expected, result)

    def test_get_max_internal_connections(self) -> None:
        self.assertEqual(self.collection.get_max_internal_connections(), 1)

        dbcrelo = db.CRE(name="internal connections test lo", description="ictlo")
        dbcrehi = db.CRE(name="internal connections test hi", description="icthi")
        self.collection.session.add(dbcrelo)
        self.collection.session.add(dbcrehi)
        self.collection.session.commit()
        for i in range(0, 100):
            dbcre = db.CRE(name=str(i) + " name", description=str(i) + " desc")
            self.collection.session.add(dbcre)
            self.collection.session.commit()

            # 1 low level cre to multiple groups
            self.collection.session.add(
                db.InternalLinks(group=dbcre.id, cre=dbcrelo.id)
            )

            # 1 hi level cre to multiple low level
            self.collection.session.add(
                db.InternalLinks(group=dbcrehi.id, cre=dbcre.id)
            )

            self.collection.session.commit()

        result = self.collection.get_max_internal_connections()
        self.assertEqual(result, 100)

    def test_export(self) -> None:
        """
        Given:
            A CRE "CREname" that links to a CRE "GroupName" and a Standard "BarStand"
        Expect:
            2 documents on disk, one for "CREname"
            with a link to "BarStand" and "GroupName" and one for "GroupName" with a link to "CREName"
        """
        loc = tempfile.mkdtemp()
        collection = db.Node_collection()
        collection = self.collection
        collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)
        code0 = defs.Code(name="co0")
        code1 = defs.Code(name="co1")
        tool0 = defs.Tool(name="t0", tooltype=defs.ToolTypes.Unknown)
        dbstandard = collection.add_node(
            defs.Standard(
                subsection="4.5.6",
                section="FooStand",
                sectionID="123",
                name="BarStand",
                hyperlink="https://example.com",
                tags=["a", "b", "c"],
            )
        )

        collection.add_node(
            defs.Standard(
                subsection="4.5.6",
                section="Unlinked",
                sectionID="Unlinked",
                name="Unlinked",
                hyperlink="https://example.com",
            )
        )
        self.collection.add_link(self.dbcre, self.collection.add_node(code0))
        self.collection.add_node(code1)
        self.collection.add_node(tool0)

        expected = [
            defs.CRE(
                id="111-001",
                description="Groupdesc",
                name="GroupName",
                links=[
                    defs.Link(
                        document=defs.CRE(
                            id="111-000", description="CREdesc", name="CREname"
                        )
                    )
                ],
            ),
            defs.CRE(
                id="111-000",
                description="CREdesc",
                name="CREname",
                links=[
                    defs.Link(
                        document=defs.CRE(
                            id="112-001", description="Groupdesc", name="GroupName"
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            name="BarStand",
                            section="FooStand",
                            sectionID="456",
                            subsection="4.5.6",
                            hyperlink="https://example.com",
                            tags=["a", "b", "c"],
                        )
                    ),
                    defs.Link(document=defs.Code(name="co0")),
                ],
            ),
            defs.Standard(
                subsection="4.5.6",
                section="Unlinked",
                name="Unlinked",
                sectionID="Unlinked",
                hyperlink="https://example.com",
            ),
            defs.Tool(name="t0", tooltype=defs.ToolTypes.Unknown),
            defs.Code(name="co1"),
        ]
        self.collection.export(loc)

        # load yamls from loc, parse,
        #  ensure yaml1 is result[0].todict and
        #  yaml2 is expected[1].todict
        group = expected[0].todict()
        cre = expected[1].todict()
        groupname = (
            expected[0]
            .name.replace("/", "-")
            .replace(" ", "_")
            .replace('"', "")
            .replace("'", "")
            + ".yaml"
        )
        with open(os.path.join(loc, groupname), "r") as f:
            doc = yaml.safe_load(f)
            self.assertDictEqual(group, doc)

        crename = (
            expected[1]
            .name.replace("/", "-")
            .replace(" ", "_")
            .replace('"', "")
            .replace("'", "")
            + ".yaml"
        )
        self.maxDiff = None
        with open(os.path.join(loc, crename), "r") as f:
            doc = yaml.safe_load(f)
            self.assertCountEqual(cre, doc)

    def test_StandardFromDB(self) -> None:
        expected = defs.Standard(
            name="foo",
            section="bar",
            sectionID="213",
            subsection="foobar",
            hyperlink="https://example.com/foo/bar",
            version="1.1.1",
        )
        self.assertEqual(
            expected,
            db.nodeFromDB(
                db.Node(
                    name="foo",
                    section="bar",
                    subsection="foobar",
                    link="https://example.com/foo/bar",
                    version="1.1.1",
                    section_id="213",
                    ntype=defs.Standard.__name__,
                )
            ),
        )

    def test_CREfromDB(self) -> None:
        c = defs.CRE(
            id="cid",
            doctype=defs.Credoctypes.CRE,
            description="CREdesc",
            name="CREname",
        )
        self.assertEqual(
            c,
            db.CREfromDB(
                db.CRE(external_id="cid", description="CREdesc", name="CREname")
            ),
        )

    def test_add_cre(self) -> None:
        original_desc = str(uuid.uuid4())
        name = str(uuid.uuid4())

        c = defs.CRE(
            id="cid", doctype=defs.Credoctypes.CRE, description=original_desc, name=name
        )
        self.assertIsNone(
            self.collection.session.query(db.CRE).filter(db.CRE.name == c.name).first()
        )

        # happy path, add new cre
        newCRE = self.collection.add_cre(c)
        dbcre = (
            self.collection.session.query(db.CRE).filter(db.CRE.name == c.name).first()
        )  # ensure transaction happened (commit() called)
        self.assertIsNotNone(dbcre.id)
        self.assertEqual(dbcre.name, c.name)
        self.assertEqual(dbcre.description, c.description)
        self.assertEqual(dbcre.external_id, c.id)

        # ensure the right thing got returned
        self.assertEqual(newCRE.name, c.name)

        # ensure no accidental update (add only adds)
        c.description = "description2"
        newCRE = self.collection.add_cre(c)
        dbcre = (
            self.collection.session.query(db.CRE).filter(db.CRE.name == c.name).first()
        )
        # ensure original description
        self.assertEqual(dbcre.description, original_desc)
        # ensure original description
        self.assertEqual(newCRE.description, original_desc)

    def test_add_node(self) -> None:
        original_section = str(uuid.uuid4())
        name = str(uuid.uuid4())

        s = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            section=original_section,
            subsection=original_section,
            name=name,
            tags=["a", "b", "c"],
        )

        self.assertIsNone(
            self.collection.session.query(db.Node)
            .filter(db.Node.name == s.name)
            .first()
        )

        # happy path, add new standard
        newStandard = self.collection.add_node(s)
        self.assertIsNotNone(newStandard)

        dbstandard = (
            self.collection.session.query(db.Node)
            .filter(db.Node.name == s.name)
            .first()
        )  # ensure transaction happened (commit() called)
        self.assertIsNotNone(dbstandard.id)
        self.assertEqual(dbstandard.name, s.name)
        self.assertEqual(dbstandard.section, s.section)
        self.assertEqual(dbstandard.subsection, s.subsection)
        self.assertEqual(
            newStandard.name, s.name
        )  # ensure the right thing got returned
        self.assertEqual(dbstandard.ntype, s.doctype.value)
        self.assertEqual(dbstandard.tags, ",".join(s.tags))
        # standards match on all of name,section, subsection <-- if you change even one of them it's a new entry

    def find_cres_of_cre(self) -> None:
        dbcre = db.CRE(description="CREdesc1", name="CREname1")
        groupless_cre = db.CRE(description="CREdesc2", name="CREname2")
        dbgroup = db.CRE(description="Groupdesc1", name="GroupName1")
        dbgroup2 = db.CRE(description="Groupdesc2", name="GroupName2")

        only_one_group = db.CRE(description="CREdesc3", name="CREname3")

        self.collection.session.add(dbcre)
        self.collection.session.add(groupless_cre)
        self.collection.session.add(dbgroup)
        self.collection.session.add(dbgroup2)
        self.collection.session.add(only_one_group)
        self.collection.session.commit()

        internalLink = db.InternalLinks(cre=dbcre.id, group=dbgroup.id, type="Contains")
        internalLink2 = db.InternalLinks(
            cre=dbcre.id, group=dbgroup2.id, type="Contains"
        )
        internalLink3 = db.InternalLinks(
            cre=only_one_group.id, group=dbgroup.id, type="Contains"
        )
        self.collection.session.add(internalLink)
        self.collection.session.add(internalLink2)
        self.collection.session.add(internalLink3)
        self.collection.session.commit()

        # happy path, find cre with 2 groups

        groups = self.collection.find_cres_of_cre(dbcre)
        if not groups:
            self.fail("Expected exactly 2 cres")
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups, [dbgroup, dbgroup2])

        # find cre with 1 group
        group = self.collection.find_cres_of_cre(only_one_group)

        if not group:
            self.fail("Expected exactly 1 cre")
        self.assertEqual(len(group), 1)
        self.assertEqual(group, [dbgroup])

        # ensure that None is return if there are no groups
        groups = self.collection.find_cres_of_cre(groupless_cre)
        self.assertIsNone(groups)

    def test_find_cres_of_standard(self) -> None:
        dbcre = db.CRE(description="CREdesc1", name="CREname1")
        dbgroup = db.CRE(description="CREdesc2", name="CREname2")
        dbstandard1 = db.Node(
            section="section1",
            name="standard1",
            ntype=defs.Standard.__name__,
        )
        group_standard = db.Node(
            section="section2",
            name="standard2",
            ntype=defs.Standard.__name__,
        )
        lone_standard = db.Node(
            section="section3",
            name="standard3",
            ntype=defs.Standard.__name__,
        )

        self.collection.session.add(dbcre)
        self.collection.session.add(dbgroup)
        self.collection.session.add(dbstandard1)
        self.collection.session.add(group_standard)
        self.collection.session.add(lone_standard)
        self.collection.session.commit()

        self.collection.session.add(db.Links(cre=dbcre.id, node=dbstandard1.id))
        self.collection.session.add(db.Links(cre=dbgroup.id, node=dbstandard1.id))
        self.collection.session.add(db.Links(cre=dbgroup.id, node=group_standard.id))
        self.collection.session.commit()

        # happy path, 1 group and 1 cre link to 1 standard
        cres = self.collection.find_cres_of_node(dbstandard1)

        if not cres:
            self.fail("Expected 2 cres")
        self.assertEqual(len(cres), 2)
        self.assertEqual(cres, [dbcre, dbgroup])

        # group links to standard
        cres = self.collection.find_cres_of_node(group_standard)

        if not cres:
            self.fail("Expected 1 cre")
        self.assertEqual(len(cres), 1)
        self.assertEqual(cres, [dbgroup])

        # no links = None
        cres = self.collection.find_cres_of_node(lone_standard)
        self.assertIsNone(cres)

    def test_get_CREs(self) -> None:
        """Given: a cre 'C1' that links to cres both as a group and a cre and other standards
        return the CRE in Document format"""
        collection = db.Node_collection()
        dbc1 = db.CRE(external_id="123", description="gcCD1", name="gcC1")
        dbc2 = db.CRE(description="gcCD2", name="gcC2")
        dbc3 = db.CRE(description="gcCD3", name="gcC3")
        db_id_only = db.CRE(description="c_get_by_internal_id_only", name="cgbiio")
        dbs1 = db.Node(
            ntype=defs.Standard.__name__,
            name="gcS2",
            section="gc1",
            subsection="gc2",
            link="gc3",
            version="gc1.1.1",
        )

        dbs2 = db.Node(
            ntype=defs.Standard.__name__,
            name="gcS3",
            section="gc1",
            subsection="gc2",
            link="gc3",
            version="gc3.1.2",
        )

        collection.session.add(dbc1)
        collection.session.add(dbc2)
        collection.session.add(dbc3)
        collection.session.add(dbs1)
        collection.session.add(dbs2)
        collection.session.add(db_id_only)
        collection.session.commit()

        collection.session.add(
            db.InternalLinks(type="Contains", group=dbc1.id, cre=dbc2.id)
        )
        collection.session.add(
            db.InternalLinks(type="Contains", group=dbc1.id, cre=dbc3.id)
        )
        collection.session.add(db.Links(type="Linked To", cre=dbc1.id, node=dbs1.id))

        collection.session.commit()

        cd1 = defs.CRE(id="123", description="gcCD1", name="gcC1", links=[])
        cd2 = defs.CRE(description="gcCD2", name="gcC2")
        cd3 = defs.CRE(description="gcCD3", name="gcC3")
        c_id_only = defs.CRE(description="c_get_by_internal_id_only", name="cgbiio")

        expected = [
            copy(cd1)
            .add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="gcS2",
                        section="gc1",
                        subsection="gc2",
                        hyperlink="gc3",
                        version="gc1.1.1",
                    ),
                )
            )
            .add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains,
                    document=copy(cd2),
                )
            )
            .add_link(defs.Link(ltype=defs.LinkTypes.Contains, document=copy(cd3)))
        ]
        self.maxDiff = None
        shallow_cd1 = copy(cd1)
        shallow_cd1.links = []
        cd2.add_link(defs.Link(ltype=defs.LinkTypes.PartOf, document=shallow_cd1))
        cd3.add_link(defs.Link(ltype=defs.LinkTypes.PartOf, document=shallow_cd1))
        self.assertEqual([], collection.get_CREs())

        res = collection.get_CREs(name="gcC1")
        self.assertEqual(len(expected), len(res))
        self.assertDictEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(external_id="123")
        self.assertEqual(len(expected), len(res))
        self.assertDictEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(external_id="12%", partial=True)
        self.assertEqual(len(expected), len(res))
        self.assertDictEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(name="gcC%", partial=True)

        res = collection.get_CREs(external_id="1%", name="gcC%", partial=True)
        self.assertEqual(len(expected), len(res))
        self.assertDictEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(description="gcCD1")
        self.assertEqual(len(expected), len(res))
        self.assertDictEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(external_id="1%", description="gcC%", partial=True)
        self.assertEqual(len(expected), len(res))
        self.assertDictEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(description="gcC%", name="gcC%", partial=True)
        want = [expected[0], cd2, cd3]
        for el in res:
            found = False
            for wel in want:
                if el.todict() == wel.todict():
                    found = True
            self.assertTrue(found)

        self.assertEqual([], collection.get_CREs(external_id="123", name="gcC5"))
        self.assertEqual([], collection.get_CREs(external_id="1234"))
        self.assertEqual([], collection.get_CREs(name="gcC5"))

        collection.session.add(db.Links(type="Linked To", cre=dbc1.id, node=dbs2.id))

        only_gcS2 = deepcopy(expected)
        expected[0].add_link(
            defs.Link(
                ltype=defs.LinkTypes.LinkedTo,
                document=defs.Standard(
                    name="gcS3",
                    section="gc1",
                    subsection="gc2",
                    hyperlink="gc3",
                    version="gc3.1.2",
                ),
            )
        )
        res = collection.get_CREs(name="gcC1")
        self.assertCountEqual(expected[0].todict(), res[0].todict())

        res = collection.get_CREs(name="gcC1", include_only=["gcS2"])
        self.assertDictEqual(only_gcS2[0].todict(), res[0].todict())

        ccd2 = copy(cd2)
        ccd2.links = []
        ccd3 = copy(cd3)
        ccd3.links = []
        no_standards = [
            copy(cd1)
            .add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Contains,
                    document=ccd2,
                )
            )
            .add_link(defs.Link(ltype=defs.LinkTypes.Contains, document=ccd3))
        ]
        res = collection.get_CREs(name="gcC1", include_only=["gcS0"])
        self.assertEqual(no_standards, res)

        self.assertEqual([c_id_only], collection.get_CREs(internal_id=db_id_only.id))

    def test_get_standards(self) -> None:
        """Given: a Standard 'S1' that links to cres
        return the Standard in Document format"""
        collection = db.Node_collection()
        docs: Dict[str, Union[db.CRE, db.Node]] = {
            "dbc1": db.CRE(external_id="123", description="CD1", name="C1"),
            "dbc2": db.CRE(description="CD2", name="C2"),
            "dbc3": db.CRE(description="CD3", name="C3"),
            "dbs1": db.Node(
                ntype=defs.Standard.__name__,
                name="S1",
                section="1",
                section_id="123",
                subsection="2",
                link="3",
                version="4",
            ),
        }
        links = [("dbc1", "dbs1"), ("dbc2", "dbs1"), ("dbc3", "dbs1")]
        for k, v in docs.items():
            collection.session.add(v)
        collection.session.commit()

        for cre, standard in links:
            collection.session.add(
                db.Links(type="Linked To", cre=docs[cre].id, node=docs[standard].id)
            )
        collection.session.commit()

        expected = [
            defs.Standard(
                name="S1",
                section="1",
                sectionID="123",
                subsection="2",
                hyperlink="3",
                version="4",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(name="C1", description="CD1", id="123"),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(name="C2", description="CD2"),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(name="C3", description="CD3"),
                    ),
                ],
            )
        ]

        res = collection.get_nodes(name="S1")
        self.assertEqual(expected, res)

    def test_get_nodes_with_pagination(self) -> None:
        """Given: a Standard 'S1' that links to cres
        return the Standard in Document format and the total pages and the page we are in
        """
        collection = db.Node_collection()
        docs: Dict[str, Union[db.Node, db.CRE]] = {
            "dbc1": db.CRE(external_id="123", description="CD1", name="C1"),
            "dbc2": db.CRE(description="CD2", name="C2"),
            "dbc3": db.CRE(description="CD3", name="C3"),
            "dbs1": db.Node(
                name="S1",
                section="1",
                section_id="123",
                subsection="2",
                link="3",
                version="4",
                ntype=defs.Standard.__name__,
            ),
        }
        links = [("dbc1", "dbs1"), ("dbc2", "dbs1"), ("dbc3", "dbs1")]
        for k, v in docs.items():
            collection.session.add(v)
        collection.session.commit()

        for cre, standard in links:
            collection.session.add(db.Links(cre=docs[cre].id, node=docs[standard].id))
        collection.session.commit()

        expected = [
            defs.Standard(
                name="S1",
                section="1",
                sectionID="123",
                subsection="2",
                hyperlink="3",
                version="4",
                links=[
                    defs.Link(
                        document=defs.CRE(name="C1", description="CD1", id="123")
                    ),
                    defs.Link(document=defs.CRE(name="C2", description="CD2")),
                    defs.Link(document=defs.CRE(name="C3", description="CD3")),
                ],
            )
        ]
        total_pages, res, pagination_object = collection.get_nodes_with_pagination(
            name="S1"
        )
        self.assertEqual(total_pages, 1)
        self.assertEqual(expected, res)

        only_c1 = [
            defs.Standard(
                name="S1",
                section="1",
                sectionID="123",
                subsection="2",
                hyperlink="3",
                version="4",
                links=[
                    defs.Link(document=defs.CRE(name="C1", description="CD1", id="123"))
                ],
            )
        ]
        _, res, _ = collection.get_nodes_with_pagination(name="S1", include_only=["C1"])
        self.assertEqual(only_c1, res)
        _, res, _ = collection.get_nodes_with_pagination(
            name="S1", include_only=["123"]
        )
        self.assertEqual(only_c1, res)

        self.assertEqual(
            collection.get_nodes_with_pagination(name="this should not exit"),
            (None, None, None),
        )

    def test_gap_analysis(self) -> None:
        """Given
        the following standards SA1, SA2, SA3 SAA1 , SB1, SD1, SDD1, SW1, SX1
        the following CREs CA, CB, CC, CD, CDD , CW, CX
        the following links
        CC -> CA, CB,CD
        CD -> CDD
        CA-> SA1, SAA1
        CB -> SB1
        CD -> SD1
        CDD -> SDD1
        CW -> SW1
        CX -> SA3, SX1
        NoCRE -> SA2

        Then:
        gap_analysis(SA) returns SA1, SA2, SA3
        gap_analysis(SA,SAA) returns SA1 <-> SAA1, SA2, SA3
        gap_analysis(SA,SDD) returns SA1 <-> SDD1, SA2, SA3
        gap_analysis(SA, SW) returns SA1,SA2,SA3, SW1 # no connection
        gap_analysis(SA, SB, SD, SW) returns SA1 <->(SB1,SD1), SA2 , SW1, SA3
        gap_analysis(SA, SX) returns SA1, SA2, SA3->SX1

            give me a single standard
            give me two standards connected by same cre
            give me two standards connected by cres who are children of the same cre
            give me two standards connected by completely different cres
            give me two standards with sections on different trees.

            give me two standards without  connections
            give me 3 or more standards

        """

        collection = db.Node_collection()
        collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)

        cres = {
            "dbca": collection.add_cre(defs.CRE(id="1", description="CA", name="CA")),
            "dbcb": collection.add_cre(defs.CRE(id="2", description="CB", name="CB")),
            "dbcc": collection.add_cre(defs.CRE(id="3", description="CC", name="CC")),
            "dbcd": collection.add_cre(defs.CRE(id="4", description="CD", name="CD")),
            "dbcdd": collection.add_cre(
                defs.CRE(id="5", description="CDD", name="CDD")
            ),
            "dbcw": collection.add_cre(defs.CRE(id="6", description="CW", name="CW")),
            "dbcx": collection.add_cre(defs.CRE(id="7", description="CX", name="CX")),
        }
        def_standards = {
            "sa1": defs.Standard(name="SA", section="SA1"),
            "sa2": defs.Standard(name="SA", section="SA2"),
            "sa3": defs.Standard(name="SA", section="SA3"),
            "saa1": defs.Standard(name="SAA", section="SAA1"),
            "sb1": defs.Standard(name="SB", section="SB1"),
            "sd1": defs.Standard(name="SD", section="SD1"),
            "sdd1": defs.Standard(name="SDD", section="SDD1"),
            "sw1": defs.Standard(name="SW", section="SW1"),
            "sx1": defs.Standard(name="SX", section="SX1"),
        }
        standards = {}
        for k, s in def_standards.items():
            standards["db" + k] = collection.add_node(s)
        ltype = defs.LinkTypes.LinkedTo
        collection.add_link(cre=cres["dbca"], node=standards["dbsa1"])
        collection.add_link(cre=cres["dbca"], node=standards["dbsaa1"])
        collection.add_link(cre=cres["dbcb"], node=standards["dbsb1"])
        collection.add_link(cre=cres["dbcd"], node=standards["dbsd1"])
        collection.add_link(cre=cres["dbcdd"], node=standards["dbsdd1"])
        collection.add_link(cre=cres["dbcw"], node=standards["dbsw1"])
        collection.add_link(cre=cres["dbcx"], node=standards["dbsa3"])
        collection.add_link(cre=cres["dbcx"], node=standards["dbsx1"])

        collection.add_internal_link(group=cres["dbcc"], cre=cres["dbca"])
        collection.add_internal_link(group=cres["dbcc"], cre=cres["dbcb"])
        collection.add_internal_link(group=cres["dbcc"], cre=cres["dbcd"])
        collection.add_internal_link(group=cres["dbcd"], cre=cres["dbcdd"])

        expected = {
            "SA": [def_standards["sa1"], def_standards["sa2"], def_standards["sa3"]],
            "SA,SAA": [
                copy(def_standards["sa1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["saa1"])
                ),
                copy(def_standards["saa1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["sa1"])
                ),
                def_standards["sa2"],
                def_standards["sa3"],
            ],
            "SAA,SA": [
                copy(def_standards["sa1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["saa1"])
                ),
                copy(def_standards["saa1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["sa1"])
                ),
                def_standards["sa2"],
                def_standards["sa3"],
            ],
            "SA,SDD": [
                copy(def_standards["sa1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["sdd1"])
                ),
                copy(def_standards["sdd1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["sa1"])
                ),
                def_standards["sa2"],
                def_standards["sa3"],
            ],
            "SA,SW": [
                def_standards["sa1"],
                def_standards["sa2"],
                def_standards["sa3"],
                def_standards["sw1"],
            ],
            "SA,SB,SD,SW": [
                copy(def_standards["sa1"])
                .add_link(defs.Link(ltype=ltype, document=def_standards["sb1"]))
                .add_link(defs.Link(ltype=ltype, document=def_standards["sd1"])),
                copy(def_standards["sb1"])
                .add_link(defs.Link(ltype=ltype, document=def_standards["sa1"]))
                .add_link(defs.Link(ltype=ltype, document=def_standards["sd1"])),
                copy(def_standards["sd1"])
                .add_link(defs.Link(ltype=ltype, document=def_standards["sa1"]))
                .add_link(defs.Link(ltype=ltype, document=def_standards["sb1"])),
                def_standards["sa2"],
                def_standards["sa3"],
                def_standards["sw1"],
            ],
            "SA,SX": [
                def_standards["sa1"],
                def_standards["sa2"],
                copy(def_standards["sa3"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["sx1"])
                ),
                copy(def_standards["sx1"]).add_link(
                    defs.Link(ltype=ltype, document=def_standards["sa3"])
                ),
            ],
        }

        self.maxDiff = None
        for args, expected_vals in expected.items():
            stands = args.split(",")
            res = collection.gap_analysis(stands)
            self.assertCountEqual(res, expected_vals)

    def test_add_internal_link(self) -> None:
        """test that internal links are added successfully,
        edge cases:
            cre or group don't exist
            called on a cycle scenario"""

        cres = {
            "dbca": self.collection.add_cre(
                defs.CRE(id="1", description="CA", name="CA")
            ),
            "dbcb": self.collection.add_cre(
                defs.CRE(id="2", description="CB", name="CB")
            ),
            "dbcc": self.collection.add_cre(
                defs.CRE(id="3", description="CC", name="CC")
            ),
        }

        # happy path
        self.collection.add_internal_link(
            cres["dbca"], cres["dbcb"], defs.LinkTypes.Same
        )

        # no cycle, free to insert
        self.collection.add_internal_link(
            group=cres["dbcb"], cre=cres["dbcc"], type=defs.LinkTypes.Same
        )

        # introdcues a cycle, should not be inserted
        self.collection.add_internal_link(
            group=cres["dbcc"], cre=cres["dbca"], type=defs.LinkTypes.Same
        )

        #   "happy path, internal link exists"
        res = (
            self.collection.session.query(db.InternalLinks)
            .filter(
                db.InternalLinks.group == cres["dbca"].id,
                db.InternalLinks.cre == cres["dbcb"].id,
            )
            .first()
        )
        self.assertEqual((res.group, res.cre), (cres["dbca"].id, cres["dbcb"].id))

        res = (
            self.collection.session.query(db.InternalLinks)
            .filter(
                db.InternalLinks.group == cres["dbcb"].id,
                db.InternalLinks.cre == cres["dbcc"].id,
            )
            .first()
        )
        self.assertEqual((res.group, res.cre), (cres["dbcb"].id, cres["dbcc"].id))

        # cycles are not inserted branch
        none_res = (
            self.collection.session.query(db.InternalLinks)
            .filter(
                db.InternalLinks.group == cres["dbcc"].id,
                db.InternalLinks.cre == cres["dbca"].id,
            )
            .one_or_none()
        )
        self.assertIsNone(none_res)

    def test_text_search(self) -> None:
        """Given:
         a cre(id=123-456,name=foo,description='lorem ipsum foo+bar')
         a standard(name=Bar,section=blah,subsection=foo, hyperlink='https://example.com/blah/foo')
         a standard(name=Bar,section=blah,subsection=foo1, hyperlink='https://example.com/blah/foo1')
         a standard(name=Bar,section=blah1,subsection=foo, hyperlink='https://example.com/blah1/foo')

        full_text_search('123-456') returns cre:foo
        full_text_search('CRE:foo') and full_text_search('CRE foo') returns cre:foo
        full_text_search('CRE:123-456') and full_text_search('CRE 123-456') returns cre:foo

        full_text_search('Standard:Bar') and full_text_search('Standard Bar') returns: [standard:Bar:blah:foo,
                                                   standard:Bar:blah:foo1,
                                                   standard:Bar:blah1:foo]

        full_text_search('Standard:blah') and full_text_search('Standard blah')  returns [standard:Bar::blah:foo,
                                                                                          standard:Bar:blah:foo1]
        full_text_search('Standard:blah:foo') returns [standard:Bar:blah:foo]
        full_text_search('Standard:foo') returns [standard:Bar:blah:foo,
                                                  standard:Bar:blah1:foo]
        <Same for searching with hyperlink>

        full_text_search('ipsum') returns cre:foo
        full_text_search('foo') returns [cre:foo,standard:Bar:blah:foo, standard:Bar:blah:foo1,standard:Bar:blah1:foo]
        """
        collection = db.Node_collection()
        cre = defs.CRE(
            id="123-456", name="textSearchCRE", description="lorem ipsum tsSection+tsC"
        )
        collection.add_cre(cre)

        s1 = defs.Standard(
            name="textSearchStandard",
            section="tsSection",
            subsection="tsSubSection",
            hyperlink="https://example.com/tsSection/tsSubSection",
        )
        collection.add_node(s1)
        s2 = defs.Standard(
            name="textSearchStandard",
            section="tsSection",
            subsection="tsSubSection1",
            hyperlink="https://example.com/tsSection/tsSubSection1",
        )
        collection.add_node(s2)
        s3 = defs.Standard(
            name="textSearchStandard",
            section="tsSection1",
            subsection="tsSubSection1",
            hyperlink="https://example.com/tsSection1/tsSubSection1",
        )
        collection.add_node(s3)
        t1 = defs.Tool(
            name="textSearchTool",
            tooltype=defs.ToolTypes.Offensive,
            hyperlink="https://example.com/textSearchTool",
            description="test text search with tool",
            sectionID="15",
            section="rule 15",
        )
        collection.add_node(t1)
        collection.session.commit()
        expected: Dict[str, List[Any]] = {
            "123-456": [cre],
            "CRE:textSearchCRE": [cre],
            "CRE textSearchCRE": [cre],
            "CRE:123-456": [cre],
            "CRE 123-456": [cre],
            "Standard:textSearchStandard": [s1, s2, s3],
            "Standard textSearchStandard": [s1, s2, s3],
            "Standard:tsSection": [s1, s2],
            "Standard tsSection": [s1, s2],
            "Standard:tsSection:tsSubSection1": [s2],
            "Standard tsSection tsSubSection1": [s2],
            "Standard:tsSubSection1": [s2, s3],
            "Standard tsSubSection1": [s2, s3],
            "Standard:https://example.com/tsSection/tsSubSection1": [s2],
            "Standard https://example.com/tsSection1/tsSubSection1": [s3],
            "https://example.com/tsSection": [s1, s2, s3],
            "ipsum": [cre],
            "tsSection": [cre, s1, s2, s3],
            "https://example.com/textSearchTool": [t1],
            "text search": [t1],
        }
        self.maxDiff = None
        for k, val in expected.items():
            res = self.collection.text_search(k)
            try:
                self.assertCountEqual(res, val)
            except Exception as e:
                pprint(k)
                pprint("|" * 99)
                pprint(res)
                pprint("|" * 99)
                pprint(val)
                pprint("|" * 99)
                input()
                raise e

    def test_dbNodeFromNode(self) -> None:
        data = {
            "tool": defs.Tool(
                name="fooTool",
                description="lorem ipsum tsSection+tsC",
                tooltype=defs.ToolTypes.Defensive,
                tags=["1", "2", "3"],
            ),
            "standard": defs.Standard(
                name="stand", section="s1", subsection="s2", version="s3"
            ),
            "code": defs.Code(
                name="c",
                description="c2",
                hyperlink="https://example.com/code/hyperlink",
                tags=["1", "2"],
            ),
        }
        expected = {
            "tool": db.Node(
                name="fooTool",
                description="lorem ipsum tsSection+tsC",
                tags=",".join([defs.ToolTypes.Defensive.value, "1", "2", "3"]),
                ntype=defs.Credoctypes.Tool.value,
            ),
            "standard": db.Node(
                name="stand",
                section="s1",
                subsection="s2",
                version="s3",
                ntype=defs.Credoctypes.Standard.value,
            ),
            "code": db.Node(
                name="c",
                description="c2",
                link="https://example.com/code/hyperlink",
                tags="1,2",
                ntype=defs.Credoctypes.Code.value,
            ),
        }
        for k, v in data.items():
            nd = db.dbNodeFromNode(v)
            for vname, var in vars(nd).items():
                if var and not vname.startswith("_"):
                    self.assertEqual(var, vars(expected[k]).get(vname))

    def test_nodeFromDB(self) -> None:
        expected = {
            "tool": defs.Tool(
                name="fooTool",
                description="lorem ipsum tsSection+tsC",
                tooltype=defs.ToolTypes.Defensive,
                tags=["1", "2", "3"],
            ),
            "standard": defs.Standard(
                name="stand", section="s1", subsection="s2", version="s3"
            ),
            "code": defs.Code(
                name="c",
                description="c2",
                hyperlink="https://example.com/code/hyperlink",
                tags=["1", "2"],
            ),
        }
        data = {
            "tool": db.Node(
                name="fooTool",
                description="lorem ipsum tsSection+tsC",
                tags=",".join([defs.ToolTypes.Defensive.value, "1", "2", "3"]),
                ntype=defs.Credoctypes.Tool.value,
            ),
            "standard": db.Node(
                name="stand",
                section="s1",
                subsection="s2",
                version="s3",
                ntype=defs.Credoctypes.Standard.value,
            ),
            "code": db.Node(
                name="c",
                description="c2",
                link="https://example.com/code/hyperlink",
                tags="1,2",
                ntype=defs.Credoctypes.Code.value,
            ),
        }
        for k, v in data.items():
            nd = db.nodeFromDB(v)
            for vname, var in vars(nd).items():
                if var and not vname.startswith("_"):
                    self.assertCountEqual(var, vars(expected[k]).get(vname))

    def test_object_select(self) -> None:
        dbnode1 = db.Node(
            name="fooTool",
            description="lorem ipsum tsSection+tsC",
            tags=f"{defs.ToolTypes.Defensive.value},1",
        )
        dbnode2 = db.Node(
            name="fooTool",
            description="lorem2",
            link="https://example.com/foo/bar",
            tags=f"{defs.ToolTypes.Defensive.value},1",
        )

        self.collection = db.Node_collection()
        collection = db.Node_collection()
        collection.session.add(dbnode1)
        collection.session.add(dbnode2)
        self.assertEqual(collection.object_select(dbnode1), [dbnode1])
        self.assertEqual(collection.object_select(dbnode2), [dbnode2])
        self.assertCountEqual(
            collection.object_select(db.Node(name="fooTool")), [dbnode1, dbnode2]
        )

        self.assertEqual(collection.object_select(None), [])

    def test_get_root_cres(self):
        """Given:
        6 CRES:
            * C0 <-- Root
            * C1 <-- Root
            * C2 Part Of C0
            * C3 Part Of C1
            * C4 Part Of C2
            * C5 Related to C0
        3 Nodes:
            * N0  Unlinked
            * N1 Linked To C1
            * N2 Linked to C2
            * N3 Linked to C3
            * N4 Linked to C4
        Get_root_cres should return C0, C1
        """
        cres = []
        nodes = []
        dbcres = []
        dbnodes = []
        sqla.session.remove()
        sqla.drop_all()
        sqla.create_all(app=self.app)
        collection = db.Node_collection()
        collection.graph.graph = db.CRE_Graph.load_cre_graph(sqla.session)

        for i in range(0, 6):
            if i == 0 or i == 1:
                cres.append(defs.CRE(name=f">> C{i}", id=f"{i}"))
            else:
                cres.append(defs.CRE(name=f"C{i}", id=f"{i}"))

            dbcres.append(collection.add_cre(cres[i]))
            nodes.append(defs.Standard(section=f"S{i}", name=f"N{i}"))
            dbnodes.append(collection.add_node(nodes[i]))
            cres[i].add_link(
                defs.Link(document=copy(nodes[i]), ltype=defs.LinkTypes.LinkedTo)
            )
            collection.add_link(
                cre=dbcres[i], node=dbnodes[i], type=defs.LinkTypes.LinkedTo
            )

        cres[0].add_link(
            defs.Link(document=cres[2].shallow_copy(), ltype=defs.LinkTypes.Contains)
        )
        cres[0].add_link(
            defs.Link(document=cres[5].shallow_copy(), ltype=defs.LinkTypes.Related)
        )
        cres[1].add_link(
            defs.Link(document=cres[3].shallow_copy(), ltype=defs.LinkTypes.Contains)
        )
        cres[2].add_link(
            defs.Link(document=cres[4].shallow_copy(), ltype=defs.LinkTypes.Contains)
        )

        cres[3].add_link(
            defs.Link(document=cres[5].shallow_copy(), ltype=defs.LinkTypes.Contains)
        )
        collection.add_internal_link(
            group=dbcres[0], cre=dbcres[2], type=defs.LinkTypes.Contains
        )
        collection.add_internal_link(
            group=dbcres[1], cre=dbcres[3], type=defs.LinkTypes.Contains
        )
        collection.add_internal_link(
            group=dbcres[2], cre=dbcres[4], type=defs.LinkTypes.Contains
        )
        collection.add_internal_link(
            group=dbcres[5], cre=dbcres[0], type=defs.LinkTypes.Related
        )
        collection.add_internal_link(
            group=dbcres[3], cre=dbcres[5], type=defs.LinkTypes.Contains
        )
        collection.session.commit()

        root_cres = collection.get_root_cres()
        self.maxDiff = None
        self.assertEqual(root_cres, [cres[0], cres[1]])


if __name__ == "__main__":
    unittest.main()
