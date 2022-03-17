import tempfile
import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.utils.spreadsheet import prepare_spreadsheet


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

        dbcre = db.CRE(description="CREdesc", name="CREname", external_id="06-06-06")
        dbgroup = db.CRE(
            description="CREGroupDesc", name="CREGroup", external_id="09-09-09"
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
                "CRE:id": "09-09-09",
                "CRE:name": "CREGroup",
                "Standard:ConflictStandName:hyperlink": None,
                "Standard:ConflictStandName:link_type": None,
                "Standard:ConflictStandName:section": None,
                "Standard:ConflictStandName:subsection": None,
                "Standard:GroupStand2:hyperlink": "https://example.com/g2",
                "Standard:GroupStand2:link_type": "SAME",
                "Standard:GroupStand2:section": "GroupStandSection2",
                "Standard:GroupStand2:subsection": "4.5.2",
                "Linked_CRE_0:id": "06-06-06",
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
                "CRE:id": "06-06-06",
                "CRE:name": "CREname",
                "Standard:ConflictStandName:hyperlink": "https://example.com/1",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.1",
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": "09-09-09",
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
                "CRE:id": "06-06-06",
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

        dbcre = db.CRE(description="CREdesc", name="CREname", external_id="06-06-06")
        dbgroup = db.CRE(
            description="CREGroupDesc", name="CREGroup", external_id="09-09-09"
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
                "CRE:id": "09-09-09",
                "CRE:name": "CREGroup",
                "Standard:ConflictStandName:hyperlink": None,
                "Standard:ConflictStandName:link_type": None,
                "Standard:ConflictStandName:section": None,
                "Standard:ConflictStandName:subsection": None,
                "Standard:GroupStand2:hyperlink": "https://example.com/g2",
                "Standard:GroupStand2:link_type": "SAME",
                "Standard:GroupStand2:section": "GroupStandSection2",
                "Standard:GroupStand2:subsection": "4.5.2",
                "Linked_CRE_0:id": "06-06-06",
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
                "CRE:id": "06-06-06",
                "CRE:name": "CREname",
                "Standard:ConflictStandName:hyperlink": "https://example.com/1",
                "Standard:ConflictStandName:link_type": "SAME",
                "Standard:ConflictStandName:section": "ConflictStandSection",
                "Standard:ConflictStandName:subsection": "4.5.1",
                "Standard:GroupStand2:hyperlink": None,
                "Standard:GroupStand2:link_type": None,
                "Standard:GroupStand2:section": None,
                "Standard:GroupStand2:subsection": None,
                "Linked_CRE_0:id": "09-09-09",
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
                "CRE:id": "06-06-06",
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


if __name__ == "__main__":
    unittest.main()
