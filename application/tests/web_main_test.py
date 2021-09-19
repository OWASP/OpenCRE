import logging
import os
import tempfile
import unittest
from pprint import pprint
from typing import Any, Dict, List

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.web import web_main


class TestMain(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all(app=self.app)
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        sqla.create_all(app=self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.collection = db.Standard_collection()

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
        collection = db.Standard_collection()
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
            res = web_main.extend_cre_with_tag_links(v, collection=collection)
            self.assertCountEqual(res.links, v.links)
            self.assertEqual(res, v)
