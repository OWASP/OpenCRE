import base64
import os
import tempfile
import unittest
import uuid
from pprint import pprint

import yaml

from application.database import db
from application.defs import cre_defs as defs
from application.utils.spreadsheet import *
from application import create_app, sqla


class TestDB(unittest.TestCase):

    def tearDown(self):
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self):
        self.app = create_app(mode='test')
        sqla.create_all(app=self.app)

        self.app_context = self.app.app_context()
        self.app_context.push()
        self.collection = db.Standard_collection()

    def test_prepare_spreadsheet_standards(self):
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

        dbcre = db.CRE(description="CREdesc", name="CREname",
                       external_id="06-06-06")
        dbgroup = db.CRE(
            description="CREGroupDesc", name="CREGroup", external_id="09-09-09"
        )
        collection.session.add(dbcre)
        collection.session.add(dbgroup)
        collection.session.commit()
        collection.session.add(db.InternalLinks(
            cre=dbcre.id, group=dbgroup.id))

        conflict1 = db.Standard(
            subsection="4.5.1",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/1",
        )
        conflict2 = db.Standard(
            subsection="4.5.2",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/2",
        )
        collection.session.add(conflict1)
        collection.session.add(conflict2)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, standard=conflict1.id))
        collection.session.add(db.Links(cre=dbcre.id, standard=conflict2.id))

        dbs1 = db.Standard(
            subsection="4.5.1",
            section="NormalStandSection1",
            name="NormalStand1",
            link="https://example.com/1",
        )
        dbs2 = db.Standard(
            subsection="4.5.2",
            section="NormalStandSection2",
            name="NormalStand2",
            link="https://example.com/2",
        )
        dbsg = db.Standard(
            subsection="4.5.2",
            section="GroupStandSection2",
            name="GroupStand2",
            link="https://example.com/g2",
        )
        dbls1 = db.Standard(
            subsection="4.5.2",
            section="LoneStandSection",
            name="LoneStand",
            link="https://example.com/ls1",
        )
        dbls2 = db.Standard(
            subsection="4.5.2",
            section="OtherLoneStandSection",
            name="OtherLoneStand",
            link="https://example.com/ls2",
        )
        collection.session.add(dbs1)
        collection.session.add(dbs2)
        collection.session.add(dbsg)
        collection.session.add(dbls1)
        collection.session.add(dbls2)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, standard=dbs1.id))
        collection.session.add(db.Links(cre=dbcre.id, standard=dbs2.id))
        collection.session.add(db.Links(cre=dbgroup.id, standard=dbsg.id))
        collection.session.commit()

        expected = [
            {
                "CRE:description": "CREGroupDesc",
                "CRE:id": "09-09-09",
                "CRE:name": "CREGroup",
                "ConflictStandName:hyperlink": None,
                "ConflictStandName:link_type": None,
                "ConflictStandName:section": None,
                "ConflictStandName:subsection": None,
                "GroupStand2:hyperlink": "https://example.com/g2",
                "GroupStand2:link_type": "SAM",
                "GroupStand2:section": "GroupStandSection2",
                "GroupStand2:subsection": "4.5.2",
                "Linked_CRE_0:id": "06-06-06",
                "Linked_CRE_0:link_type": "SAM",
                "Linked_CRE_0:name": "CREname",
                "LoneStand:hyperlink": None,
                "LoneStand:link_type": None,
                "LoneStand:section": None,
                "LoneStand:subsection": None,
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
                "NormalStand2:hyperlink": None,
                "NormalStand2:link_type": None,
                "NormalStand2:section": None,
                "NormalStand2:subsection": None,
                "OtherLoneStand:hyperlink": None,
                "OtherLoneStand:link_type": None,
                "OtherLoneStand:section": None,
                "OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "06-06-06",
                "CRE:name": "CREname",
                "ConflictStandName:hyperlink": "https://example.com/1",
                "ConflictStandName:link_type": "SAM",
                "ConflictStandName:section": "ConflictStandSection",
                "ConflictStandName:subsection": "4.5.1",
                "GroupStand2:hyperlink": None,
                "GroupStand2:link_type": None,
                "GroupStand2:section": None,
                "GroupStand2:subsection": None,
                "Linked_CRE_0:id": "09-09-09",
                "Linked_CRE_0:link_type": "SAM",
                "Linked_CRE_0:name": "CREGroup",
                "LoneStand:hyperlink": None,
                "LoneStand:link_type": None,
                "LoneStand:section": None,
                "LoneStand:subsection": None,
                "NormalStand1:hyperlink": "https://example.com/1",
                "NormalStand1:link_type": "SAM",
                "NormalStand1:section": "NormalStandSection1",
                "NormalStand1:subsection": "4.5.1",
                "NormalStand2:hyperlink": "https://example.com/2",
                "NormalStand2:link_type": "SAM",
                "NormalStand2:section": "NormalStandSection2",
                "NormalStand2:subsection": "4.5.2",
                "OtherLoneStand:hyperlink": None,
                "OtherLoneStand:link_type": None,
                "OtherLoneStand:section": None,
                "OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "06-06-06",
                "CRE:name": "CREname",
                "ConflictStandName:hyperlink": "https://example.com/2",
                "ConflictStandName:link_type": "SAM",
                "ConflictStandName:section": "ConflictStandSection",
                "ConflictStandName:subsection": "4.5.2",
                "GroupStand2:hyperlink": None,
                "GroupStand2:link_type": None,
                "GroupStand2:section": None,
                "GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "LoneStand:hyperlink": None,
                "LoneStand:link_type": None,
                "LoneStand:section": None,
                "LoneStand:subsection": None,
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
                "NormalStand2:hyperlink": None,
                "NormalStand2:link_type": None,
                "NormalStand2:section": None,
                "NormalStand2:subsection": None,
                "OtherLoneStand:hyperlink": None,
                "OtherLoneStand:link_type": None,
                "OtherLoneStand:section": None,
                "OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": None,
                "CRE:id": None,
                "CRE:name": None,
                "ConflictStandName:hyperlink": None,
                "ConflictStandName:link_type": None,
                "ConflictStandName:section": None,
                "ConflictStandName:subsection": None,
                "GroupStand2:hyperlink": None,
                "GroupStand2:link_type": None,
                "GroupStand2:section": None,
                "GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "LoneStand:hyperlink": "https://example.com/ls1",
                "LoneStand:link_type": None,
                "LoneStand:section": "LoneStandSection",
                "LoneStand:subsection": "4.5.2",
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
                "NormalStand2:hyperlink": None,
                "NormalStand2:link_type": None,
                "NormalStand2:section": None,
                "NormalStand2:subsection": None,
                "OtherLoneStand:hyperlink": None,
                "OtherLoneStand:link_type": None,
                "OtherLoneStand:section": None,
                "OtherLoneStand:subsection": None,
            },
            {
                "CRE:description": None,
                "CRE:id": None,
                "CRE:name": None,
                "ConflictStandName:hyperlink": None,
                "ConflictStandName:link_type": None,
                "ConflictStandName:section": None,
                "ConflictStandName:subsection": None,
                "GroupStand2:hyperlink": None,
                "GroupStand2:link_type": None,
                "GroupStand2:section": None,
                "GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "LoneStand:hyperlink": None,
                "LoneStand:link_type": None,
                "LoneStand:section": None,
                "LoneStand:subsection": None,
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
                "NormalStand2:hyperlink": None,
                "NormalStand2:link_type": None,
                "NormalStand2:section": None,
                "NormalStand2:subsection": None,
                "OtherLoneStand:hyperlink": "https://example.com/ls2",
                "OtherLoneStand:link_type": None,
                "OtherLoneStand:section": "OtherLoneStandSection",
                "OtherLoneStand:subsection": "4.5.2",
            },
        ]

        result = prepare_spreadsheet(
            collection, collection.export(dir=tempfile.mkdtemp())
        )
        self.assertCountEqual(result, expected)

    def test_prepare_spreadsheet_groups(self):
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

        dbcre = db.CRE(description="CREdesc", name="CREname",
                       external_id="06-06-06")
        dbgroup = db.CRE(
            description="CREGroupDesc", name="CREGroup", external_id="09-09-09"
        )
        collection.session.add(dbcre)
        collection.session.add(dbgroup)
        collection.session.commit()
        collection.session.add(db.InternalLinks(
            cre=dbcre.id, group=dbgroup.id))

        conflict1 = db.Standard(
            subsection="4.5.1",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/1",
        )
        conflict2 = db.Standard(
            subsection="4.5.2",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/2",
        )
        collection.session.add(conflict1)
        collection.session.add(conflict2)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, standard=conflict1.id))
        collection.session.add(db.Links(cre=dbcre.id, standard=conflict2.id))

        dbs1 = db.Standard(
            subsection="4.5.1",
            section="NormalStandSection1",
            name="NormalStand1",
            link="https://example.com/1",
        )
        dbs2 = db.Standard(
            subsection="4.5.2",
            section="NormalStandSection2",
            name="NormalStand2",
            link="https://example.com/2",
        )
        dbsg = db.Standard(
            subsection="4.5.2",
            section="GroupStandSection2",
            name="GroupStand2",
            link="https://example.com/g2",
        )
        collection.session.add(dbs1)
        collection.session.add(dbs2)
        collection.session.add(dbsg)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, standard=dbs1.id))
        collection.session.add(db.Links(cre=dbcre.id, standard=dbs2.id))
        collection.session.add(db.Links(cre=dbgroup.id, standard=dbsg.id))
        collection.session.commit()

        expected = [
            {
                "CRE:description": "CREGroupDesc",
                "CRE:id": "09-09-09",
                "CRE:name": "CREGroup",
                "ConflictStandName:hyperlink": None,
                "ConflictStandName:link_type": None,
                "ConflictStandName:section": None,
                "ConflictStandName:subsection": None,
                "GroupStand2:hyperlink": "https://example.com/g2",
                "GroupStand2:link_type": "SAM",
                "GroupStand2:section": "GroupStandSection2",
                "GroupStand2:subsection": "4.5.2",
                "Linked_CRE_0:id": "06-06-06",
                "Linked_CRE_0:link_type": "SAM",
                "Linked_CRE_0:name": "CREname",
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
                "NormalStand2:hyperlink": None,
                "NormalStand2:link_type": None,
                "NormalStand2:section": None,
                "NormalStand2:subsection": None,
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "06-06-06",
                "CRE:name": "CREname",
                "ConflictStandName:hyperlink": "https://example.com/1",
                "ConflictStandName:link_type": "SAM",
                "ConflictStandName:section": "ConflictStandSection",
                "ConflictStandName:subsection": "4.5.1",
                "GroupStand2:hyperlink": None,
                "GroupStand2:link_type": None,
                "GroupStand2:section": None,
                "GroupStand2:subsection": None,
                "Linked_CRE_0:id": "09-09-09",
                "Linked_CRE_0:link_type": "SAM",
                "Linked_CRE_0:name": "CREGroup",
                "NormalStand1:hyperlink": "https://example.com/1",
                "NormalStand1:link_type": "SAM",
                "NormalStand1:section": "NormalStandSection1",
                "NormalStand1:subsection": "4.5.1",
                "NormalStand2:hyperlink": "https://example.com/2",
                "NormalStand2:link_type": "SAM",
                "NormalStand2:section": "NormalStandSection2",
                "NormalStand2:subsection": "4.5.2",
            },
            {
                "CRE:description": "CREdesc",
                "CRE:id": "06-06-06",
                "CRE:name": "CREname",
                "ConflictStandName:hyperlink": "https://example.com/2",
                "ConflictStandName:link_type": "SAM",
                "ConflictStandName:section": "ConflictStandSection",
                "ConflictStandName:subsection": "4.5.2",
                "GroupStand2:hyperlink": None,
                "GroupStand2:link_type": None,
                "GroupStand2:section": None,
                "GroupStand2:subsection": None,
                "Linked_CRE_0:id": None,
                "Linked_CRE_0:link_type": None,
                "Linked_CRE_0:name": None,
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
                "NormalStand2:hyperlink": None,
                "NormalStand2:link_type": None,
                "NormalStand2:section": None,
                "NormalStand2:subsection": None,
            },
        ]

        result = prepare_spreadsheet(
            collection, collection.export(dir=tempfile.mkdtemp())
        )

        self.assertCountEqual(result, expected)

    def test_prepare_spreadsheet_simple(self):
        """Given:
            * 1 CRE "CREname" that links to
                ** 2 subsections of Standard "ConflictStandName"
                ** 2 subsections in  standards "NormalStand0" and "NormalStand1"
        Expect: an array with 2 elements
                * 1 element contains the mappings of  "CREname" to "NormalStand1", "NormalStand0" and 1 subsection of "ConflictStandName"
                * 1 element contains ONLY the mapping of "CREname" to the remaining subsection of "ConflictStandName"
        """
        # empty string means temporary db
        collection = self.collection

        # test 0, single CRE, connects to several standards, 1 cre maps to the same standard in multiple sections/subsections
        dbcre = db.CRE(description="CREdesc", name="CREname",
                       external_id="123-321-0")
        collection.session.add(dbcre)

        conflict0 = db.Standard(
            subsection="4.5.0",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/0",
        )
        conflict1 = db.Standard(
            subsection="4.5.1",
            section="ConflictStandSection",
            name="ConflictStandName",
            link="https://example.com/1",
        )
        collection.session.add(conflict0)
        collection.session.add(conflict1)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, standard=conflict0.id))
        collection.session.add(db.Links(cre=dbcre.id, standard=conflict1.id))

        dbs0 = db.Standard(
            subsection="4.5.0",
            section="NormalStandSection0",
            name="NormalStand0",
            link="https://example.com/0",
        )
        dbs1 = db.Standard(
            subsection="4.5.1",
            section="NormalStandSection1",
            name="NormalStand1",
            link="https://example.com/1",
        )
        collection.session.add(dbs0)
        collection.session.add(dbs1)
        collection.session.commit()
        collection.session.add(db.Links(cre=dbcre.id, standard=dbs0.id))
        collection.session.add(db.Links(cre=dbcre.id, standard=dbs1.id))

        expected = [
            {
                "CRE:name": "CREname",
                "CRE:id": "123-321-0",
                "CRE:description": "CREdesc",
                "ConflictStandName:hyperlink": "https://example.com/0",
                "ConflictStandName:link_type": "SAM",
                "ConflictStandName:section": "ConflictStandSection",
                "ConflictStandName:subsection": "4.5.0",
                "NormalStand0:hyperlink": "https://example.com/0",
                "NormalStand0:link_type": "SAM",
                "NormalStand0:section": "NormalStandSection0",
                "NormalStand0:subsection": "4.5.0",
                "NormalStand1:hyperlink": "https://example.com/1",
                "NormalStand1:link_type": "SAM",
                "NormalStand1:section": "NormalStandSection1",
                "NormalStand1:subsection": "4.5.1",
            },
            {
                "CRE:name": "CREname",
                "CRE:id": "123-321-0",
                "CRE:description": "CREdesc",
                "ConflictStandName:hyperlink": "https://example.com/1",
                "ConflictStandName:link_type": "SAM",
                "ConflictStandName:section": "ConflictStandSection",
                "ConflictStandName:subsection": "4.5.1",
                "NormalStand0:hyperlink": None,
                "NormalStand0:link_type": None,
                "NormalStand0:section": None,
                "NormalStand0:subsection": None,
                "NormalStand1:hyperlink": None,
                "NormalStand1:link_type": None,
                "NormalStand1:section": None,
                "NormalStand1:subsection": None,
            },
        ]

        result = prepare_spreadsheet(
            collection, collection.export(dir=tempfile.mkdtemp())
        )
        self.assertCountEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
