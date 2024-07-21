import tempfile
import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.utils.spreadsheet import (
    prepare_spreadsheet,
    generate_mapping_template_file,
)


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
        self.collection = db.Node_collection()

    def test_prepare_spreadsheet_standards(self) -> None:
        """
        Given:
                * 1 CRE "CREname" that links to
                    ** 2 subsections of Standard "ConflictStandName"
                    ** 2 subsections in  standards "NormalStand1" and "NormalStand2"
                    ** CRE "CREGroup"
                * 1 CRE  "CREGroup" that links to
                    ** CRE "CREname"
                    ** 1 subsection in standard "GroupStand2"
                * 1 Standard  "LoneStand"
        Expect: an array with 5 elements
                    * 1 element contains the mappings of  "CREname" to "NormalStand1", "NormalStand2", "CREGroup"  and 1 subsection of "ConflictStandName"
                    * 1 element contains ONLY the mapping of "CREname" to the remaining subsection of "ConflictStandName"
                    * 1 element contains the mappings of "CREGroup" to "CREname" and "GroupStand2"
                    * 1 element contains the entry of "LoneStand" without any mappings
                    * 1 element contains the entry of "OtherLoneStand" without any mappings
        """

        collection = self.collection

        dbcre = db.CRE(description="CREdesc", name="CREname", external_id="060-060")
        dbgroup = db.CRE(
            description="CREGroupDesc", name="CREGroup", external_id="999-999"
        )
        collection.session.add(dbcre)
        collection.session.add(dbgroup)
        collection.session.commit()
        collection.session.add(db.InternalLinks(cre=dbcre.id, group=dbgroup.id))

        conflict1 = db.Node(
            subsection="4.5.1",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/1",
            ntype="Standard",
        )
        conflict2 = db.Node(
            subsection="4.5.2",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/2",
            ntype="Standard",
        )
        collection.session.add(conflict1)
        collection.session.add(conflict2)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, node=conflict1.id))
        collection.session.add(db.Links(cre=dbcre.id, node=conflict2.id))

        dbs1 = db.Node(
            subsection="4.5.1",
            section="NormalStandSection1",
            name="NormalStand1",
            link="https://example.com/1",
            ntype="Standard",
        )
        dbs2 = db.Node(
            subsection="4.5.2",
            section="NormalStandSection2",
            name="NormalStand2",
            link="https://example.com/2",
            ntype="Standard",
        )
        dbsg = db.Node(
            subsection="4.5.2",
            section="GroupStandSection2",
            name="GroupStand2",
            link="https://example.com/g2",
            ntype="Standard",
        )
        dbls1 = db.Node(
            subsection="4.5.2",
            section="LoneStandSection",
            name="LoneStand",
            link="https://example.com/ls1",
            ntype="Standard",
        )
        dbls2 = db.Node(
            subsection="4.5.2",
            section="OtherLoneStandSection",
            name="OtherLoneStand",
            link="https://example.com/ls2",
            ntype="Standard",
        )
        collection.session.add(dbs1)
        collection.session.add(dbs2)
        collection.session.add(dbsg)
        collection.session.add(dbls1)
        collection.session.add(dbls2)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, node=dbs1.id))
        collection.session.add(db.Links(cre=dbcre.id, node=dbs2.id))
        collection.session.add(db.Links(cre=dbgroup.id, node=dbsg.id))
        collection.session.commit()

        expected = [
            {
                "CRE:description": "CREGroupDesc",
                "CRE:id": "999-999",
                "CRE:name": "CREGroup",
                "Standard:ConflictStandName:hyperlink": None,
                "Standard:ConflictStandName:link_type": None,
                "Standard:ConflictStandName:section": None,
                "Standard:ConflictStandName:subsection": None,
                "Standard:GroupStand2:hyperlink": "https://example.com/g2",
                "Standard:GroupStand2:link_type": "SAME",
                "Standard:GroupStand2:section": "GroupStandSection2",
                "Standard:GroupStand2:subsection": "4.5.2",
                "Linked_CRE_0:id": "060-060",
                "Linked_CRE_0:link_type": "SAME",
                "Linked_CRE_0:name": "CREname",
                "Standard:LoneStand:hyperlink": None,
                "Standard:LoneStand:link_type": None,
                "Standard:LoneStand:section": None,
                "Standard:LoneStand:subsection": None,
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
                "Standard:NormalStand2:hyperlink": None,
                "Standard:NormalStand2:link_type": None,
                "Standard:NormalStand2:section": None,
                "Standard:NormalStand2:subsection": None,
                "Standard:OtherLoneStand:hyperlink": None,
                "Standard:OtherLoneStand:link_type": None,
                "Standard:OtherLoneStand:section": None,
                "Standard:OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "060-060",
                "CRE:name": "CREname",
                "Standard:ConflictStandName:hyperlink": "https://example.com/1",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.1",
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": "999-999",
                "Linked_CRE_0:link_type": "SAME",
                "Linked_CRE_0:name": "CREGroup",
                "Standard:LoneStand:hyperlink": None,
                "Standard:LoneStand:link_type": None,
                "Standard:LoneStand:section": None,
                "Standard:LoneStand:subsection": None,
                "Standard:NormalStand1:hyperlink": "https://example.com/1",
                "Standard:NormalStand1:link_type": "SAME",
                "Standard:NormalStand1:section": "NormalStandSection1",
                "Standard:NormalStand1:subsection": "4.5.1",
                "Standard:NormalStand2:hyperlink": "https://example.com/2",
                "Standard:NormalStand2:link_type": "SAME",
                "Standard:NormalStand2:section": "NormalStandSection2",
                "Standard:NormalStand2:subsection": "4.5.2",
                "Standard:OtherLoneStand:hyperlink": None,
                "Standard:OtherLoneStand:link_type": None,
                "Standard:OtherLoneStand:section": None,
                "Standard:OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "060-060",
                "CRE:name": "CREname",
                "Standard:ConflictStandName:hyperlink": "https://example.com/2",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.2",
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "Standard:LoneStand:hyperlink": None,
                "Standard:LoneStand:link_type": None,
                "Standard:LoneStand:section": None,
                "Standard:LoneStand:subsection": None,
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
                "Standard:NormalStand2:hyperlink": None,
                "Standard:NormalStand2:link_type": None,
                "Standard:NormalStand2:section": None,
                "Standard:NormalStand2:subsection": None,
                "Standard:OtherLoneStand:hyperlink": None,
                "Standard:OtherLoneStand:link_type": None,
                "Standard:OtherLoneStand:section": None,
                "Standard:OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": None,
                "CRE:id": None,
                "CRE:name": None,
                "Standard:ConflictStandName:hyperlink": None,
                "Standard:ConflictStandName:link_type": None,
                "Standard:ConflictStandName:section": None,
                "Standard:ConflictStandName:subsection": None,
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "Standard:LoneStand:hyperlink": "https://example.com/ls1",
                "Standard:LoneStand:link_type": None,
                "Standard:LoneStand:section": "LoneStandSection",
                "Standard:LoneStand:subsection": "4.5.2",
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
                "Standard:NormalStand2:hyperlink": None,
                "Standard:NormalStand2:link_type": None,
                "Standard:NormalStand2:section": None,
                "Standard:NormalStand2:subsection": None,
                "Standard:OtherLoneStand:hyperlink": None,
                "Standard:OtherLoneStand:link_type": None,
                "Standard:OtherLoneStand:section": None,
                "Standard:OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": None,
                "CRE:id": None,
                "CRE:name": None,
                "Standard:ConflictStandName:hyperlink": None,
                "Standard:ConflictStandName:link_type": None,
                "Standard:ConflictStandName:section": None,
                "Standard:ConflictStandName:subsection": None,
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "Standard:LoneStand:hyperlink": None,
                "Standard:LoneStand:link_type": None,
                "Standard:LoneStand:section": None,
                "Standard:LoneStand:subsection": None,
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
                "Standard:NormalStand2:hyperlink": None,
                "Standard:NormalStand2:link_type": None,
                "Standard:NormalStand2:section": None,
                "Standard:NormalStand2:subsection": None,
                "Standard:OtherLoneStand:hyperlink": "https://example.com/ls2",
                "Standard:OtherLoneStand:link_type": None,
                "Standard:OtherLoneStand:section": "OtherLoneStandSection",
                "Standard:OtherLoneStand:subsection": "4.5.2",
            },
        ]

        result = prepare_spreadsheet(
            collection, collection.export(dir=tempfile.mkdtemp())
        )
        self.assertCountEqual(result, expected)

    def test_prepare_spreadsheet_groups(self) -> None:
        """Given:
            * 1 CRE "CREname" that links to
                ** 2 subsections of Standard "ConflictStandName"
                ** 2 subsections in  standards "NormalStand1" and "NormalStand2"
                ** CRE "CREGroup"
            * 1 CRE  "CREGroup" that links to
                ** CRE "CREname"
                ** 1 subsection in standard "GroupStand2"
        Expect: an array with 3 elements
                * 1 element contains the mappings of  "CREname" to "NormalStand1", "NormalStand2", "CREGroup"  and 1 subsection of "ConflictStandName"
                * 1 element contains ONLY the mapping of "CREname" to the remaining subsection of "ConflictStandName"
                * 1 element contains the mappings of "CREGroup" to "CREname" and "GroupStand2"
        """
        collection = self.collection

        dbcre = db.CRE(description="CREdesc", name="CREname", external_id="060-060")
        dbgroup = db.CRE(
            description="CREGroupDesc", name="CREGroup", external_id="999-999"
        )
        collection.session.add(dbcre)
        collection.session.add(dbgroup)
        collection.session.commit()
        collection.session.add(db.InternalLinks(cre=dbcre.id, group=dbgroup.id))

        conflict1 = db.Node(
            subsection="4.5.1",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/1",
            ntype="Standard",
        )
        conflict2 = db.Node(
            subsection="4.5.2",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/2",
            ntype="Standard",
        )
        collection.session.add(conflict1)
        collection.session.add(conflict2)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, node=conflict1.id))
        collection.session.add(db.Links(cre=dbcre.id, node=conflict2.id))

        dbs1 = db.Node(
            subsection="4.5.1",
            section="NormalStandSection1",
            name="NormalStand1",
            link="https://example.com/1",
            ntype="Standard",
        )
        dbs2 = db.Node(
            subsection="4.5.2",
            section="NormalStandSection2",
            name="NormalStand2",
            link="https://example.com/2",
            ntype="Standard",
        )
        dbsg = db.Node(
            subsection="4.5.2",
            section="GroupStandSection2",
            name="GroupStand2",
            link="https://example.com/g2",
            ntype="Standard",
        )
        collection.session.add(dbs1)
        collection.session.add(dbs2)
        collection.session.add(dbsg)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, node=dbs1.id))
        collection.session.add(db.Links(cre=dbcre.id, node=dbs2.id))
        collection.session.add(db.Links(cre=dbgroup.id, node=dbsg.id))
        collection.session.commit()

        expected = [
            {
                "CRE:description": "CREGroupDesc",
                "CRE:id": "999-999",
                "CRE:name": "CREGroup",
                "Standard:ConflictStandName:hyperlink": None,
                "Standard:ConflictStandName:link_type": None,
                "Standard:ConflictStandName:section": None,
                "Standard:ConflictStandName:subsection": None,
                "Standard:GroupStand2:hyperlink": "https://example.com/g2",
                "Standard:GroupStand2:link_type": "SAME",
                "Standard:GroupStand2:section": "GroupStandSection2",
                "Standard:GroupStand2:subsection": "4.5.2",
                "Linked_CRE_0:id": "060-060",
                "Linked_CRE_0:link_type": "SAME",
                "Linked_CRE_0:name": "CREname",
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
                "Standard:NormalStand2:hyperlink": None,
                "Standard:NormalStand2:link_type": None,
                "Standard:NormalStand2:section": None,
                "Standard:NormalStand2:subsection": None,
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "060-060",
                "CRE:name": "CREname",
                "Standard:ConflictStandName:hyperlink": "https://example.com/1",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.1",
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": "999-999",
                "Linked_CRE_0:link_type": "SAME",
                "Linked_CRE_0:name": "CREGroup",
                "Standard:NormalStand1:hyperlink": "https://example.com/1",
                "Standard:NormalStand1:link_type": "SAME",
                "Standard:NormalStand1:section": "NormalStandSection1",
                "Standard:NormalStand1:subsection": "4.5.1",
                "Standard:NormalStand2:hyperlink": "https://example.com/2",
                "Standard:NormalStand2:link_type": "SAME",
                "Standard:NormalStand2:section": "NormalStandSection2",
                "Standard:NormalStand2:subsection": "4.5.2",
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "060-060",
                "CRE:name": "CREname",
                "Standard:ConflictStandName:hyperlink": "https://example.com/2",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.2",
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
                "Standard:NormalStand2:hyperlink": None,
                "Standard:NormalStand2:link_type": None,
                "Standard:NormalStand2:section": None,
                "Standard:NormalStand2:subsection": None,
            },
        ]

        result = prepare_spreadsheet(
            collection, collection.export(dir=tempfile.mkdtemp())
        )
        self.assertDictEqual(result[0], expected[0])

    def test_prepare_spreadsheet_simple(self) -> None:
        """Given:
            * 1 CRE "CREname" that links to
                ** 2 subsections of Standard "ConflictStandName"
                ** 2 subsections in  standards "NormalStand0" and "NormalStand1"
        Expect: an array with 2 elements
                * 1 element contains the mappings of  "CREname" to "NormalStand1", "NormalStand0" and 1 subsection of "ConflictStandName"
                * 1 element contains ONLY the mapping of "CREname" to the remaining subsection of "ConflictStandName"
        """
        # empty string means temporary db
        collection = db.Node_collection()

        # test 0, single CRE, connects to several standards
        # 1 cre maps to the same standard in multiple sections/subsections
        cre = defs.CRE(description="CREdesc", name="CREname", id="123-321-0")
        conflict0 = defs.Standard(
            subsection="4.5.0",
            section="ConflictStandSection",
            name="ConflictStandName",
            hyperlink="https://example.com/0",
        )
        conflict1 = defs.Standard(
            subsection="4.5.1",
            section="ConflictStandSection",
            name="ConflictStandName",
            hyperlink="https://example.com/1",
        )
        s0 = defs.Standard(
            subsection="4.5.0",
            section="NormalStandSection0",
            name="NormalStand0",
            hyperlink="https://example.com/0",
        )
        s1 = defs.Standard(
            subsection="4.5.1",
            section="NormalStandSection1",
            name="NormalStand1",
            hyperlink="https://example.com/1",
        )
        dbcre = collection.add_cre(cre)
        dbc0 = collection.add_node(conflict0)
        dbc1 = collection.add_node(conflict1)
        dbs0 = collection.add_node(s0)
        dbs1 = collection.add_node(s1)
        collection.add_link(dbcre, dbc0)
        collection.add_link(dbcre, dbc1)
        collection.add_link(dbcre, dbs0)
        collection.add_link(dbcre, dbs1)

        expected = [
            {
                "CRE:name": "CREname",
                "CRE:id": "123-321-0",
                "CRE:description": "CREdesc",
                "Standard:ConflictStandName:hyperlink": "https://example.com/0",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.0",
                "Standard:NormalStand0:hyperlink": "https://example.com/0",
                "Standard:NormalStand0:link_type": "SAME",
                "Standard:NormalStand0:section": "NormalStandSection0",
                "Standard:NormalStand0:subsection": "4.5.0",
                "Standard:NormalStand1:hyperlink": "https://example.com/1",
                "Standard:NormalStand1:link_type": "SAME",
                "Standard:NormalStand1:section": "NormalStandSection1",
                "Standard:NormalStand1:subsection": "4.5.1",
            },
            {
                "CRE:name": "CREname",
                "CRE:id": "123-321-0",
                "CRE:description": "CREdesc",
                "Standard:ConflictStandName:hyperlink": "https://example.com/1",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.1",
                "Standard:NormalStand0:hyperlink": None,
                "Standard:NormalStand0:link_type": None,
                "Standard:NormalStand0:section": None,
                "Standard:NormalStand0:subsection": None,
                "Standard:NormalStand1:hyperlink": None,
                "Standard:NormalStand1:link_type": None,
                "Standard:NormalStand1:section": None,
                "Standard:NormalStand1:subsection": None,
            },
        ]
        export = collection.export(dry_run=True)
        result = prepare_spreadsheet(collection, export)
        self.maxDiff = None

        self.assertCountEqual(result, expected)

    def test_generate_mapping_template_file(self) -> None:
        """
        Given: a CRE structure with 4 depth levels and 2 root cres
        prepare a staggered csv accordingly
        """
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
                    description=f"CREdesc{j}-{i}",
                    name=f"CREname{j}-{i}",
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
        csv = generate_mapping_template_file(database=collection, docs=roots)
        self.assertEqual(
            csv,
            [
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
            ],
        )


if __name__ == "__main__":
    unittest.main()
