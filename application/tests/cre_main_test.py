import logging
import os
import shutil
import tempfile
import unittest
from pprint import pprint
from typing import Any, Dict, List
from unittest import mock
from unittest.mock import Mock, patch

from application import create_app, sqla  # type: ignore
from application.cmd import cre_main as main
from application.database import db
from application.defs import cre_defs as defs
from application.defs import osib_defs as odefs
from application.defs.osib_defs import Osib_id, Osib_tree


class TestMain(unittest.TestCase):
    def tearDown(self) -> None:
        for tmpdir in self.tmpdirs:
            shutil.rmtree(tmpdir)
        sqla.session.remove()
        sqla.drop_all(app=self.app)
        self.app_context.pop()

    def setUp(self) -> None:
        self.tmpdirs: List[str] = []
        self.app = create_app(mode="test")
        sqla.create_all(app=self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.collection = db.Node_collection()

    def test_register_node_with_links(self) -> None:
        standard_with_links = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            id="",
            description="",
            name="standard_with_links",
            section="Standard With Links",
            links=[
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        name="CWE",
                        sectionID="598",
                    )
                ),
                defs.Link(
                    document=defs.Code(
                        doctype=defs.Credoctypes.Code,
                        description="print(10)",
                        name="CodemcCodeFace",
                    )
                ),
                defs.Link(
                    document=defs.Tool(
                        description="awesome hacking tool",
                        name="ToolmcToolFace",
                    )
                ),
            ],
        )

        ret = main.register_node(node=standard_with_links, collection=self.collection)
        # assert returned value makes sense
        self.assertEqual(ret.name, "standard_with_links")
        self.assertEqual(ret.section, "Standard With Links")

        # assert db structure makes sense
        # no links since our nodes don't have a CRE to map to
        for thing in self.collection.session.query(db.Links).all():
            self.assertIsNone(thing.cre)

        self.assertEqual(self.collection.session.query(db.Links).all(), [])

        # 4 cre-less nodes in the db
        self.assertEqual(len(self.collection.session.query(db.Node).all()), 4)

    def test_register_node_with_cre(self) -> None:
        known_standard_with_cre = defs.Standard(
            name="CWE",
            sectionID="598",
            links=[
                defs.Link(document=defs.CRE(id="101-202", name="crename")),
            ],
        )
        standard_with_cre = defs.Standard(
            id="",
            description="",
            name="standard_with_cre",
            links=[
                defs.Link(
                    document=defs.Tool(
                        tooltype=defs.ToolTypes.Offensive,
                        name="zap",
                        section="Rule - 9",
                        sectionID="9",
                    )
                ),
                defs.Link(document=defs.CRE(id="101-202", name="crename")),
                defs.Link(
                    document=defs.Standard(
                        name="CWE",
                        sectionID="598",
                        links=[],
                    )
                ),
            ],
            section="standard_with_cre",
        )
        main.register_node(node=known_standard_with_cre, collection=self.collection)
        main.register_node(node=standard_with_cre, collection=self.collection)

        # assert db structure makes sense
        self.assertEqual(
            len(self.collection.session.query(db.Links).all()), 3
        )  # 3 links in the db
        self.assertEqual(
            len(self.collection.session.query(db.Node).all()), 3
        )  # 3 nodes in the db
        self.assertEqual(
            len(self.collection.session.query(db.CRE).all()), 1
        )  # 1 cre in the db

    def test_register_standard_with_groupped_cre_links(self) -> None:
        with_groupped_cre_links = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            id="",
            description="",
            name="standard_with",
            links=[
                defs.Link(
                    document=defs.CRE(
                        id="101-002",
                        description="group desc",
                        name="group name",
                        links=[
                            defs.Link(
                                document=defs.CRE(
                                    doctype=defs.Credoctypes.CRE,
                                    id="101-001",
                                    description="cre2 desc",
                                    name="crename2",
                                )
                            )
                        ],
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        name="CWE",
                        sectionID="598",
                    )
                ),
                defs.Link(
                    document=defs.CRE(
                        doctype=defs.Credoctypes.CRE,
                        id="101-000",
                        description="cre desc",
                        name="crename",
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        name="ASVS",
                        section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                    )
                ),
            ],
            section="Session Management",
        )

        main.register_node(node=with_groupped_cre_links, collection=self.collection)
        # assert db structure makes sense
        self.assertEqual(
            len(self.collection.session.query(db.Links).all()), 5
        )  # 5 links in the db

        self.assertEqual(
            len(self.collection.session.query(db.InternalLinks).all()), 1
        )  # 1 internal link in the db

        self.assertEqual(
            len(self.collection.session.query(db.Node).all()), 3
        )  # 3 standards in the db
        self.assertEqual(
            len(self.collection.session.query(db.CRE).all()), 3
        )  # 2 cres in the db

    def test_register_cre(self) -> None:
        standard = defs.Standard(
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
        )
        tool = defs.Tool(name="Tooly", tooltype=defs.ToolTypes.Defensive)
        cre = defs.CRE(
            id="100",
            description="CREdesc",
            name="CREname",
            links=[defs.Link(document=standard), defs.Link(document=tool)],
            tags=["CREt1", "CREt2"],
            metadata={"tags": ["CREl1", "CREl2"]},
        )
        self.assertEqual(main.register_cre(cre, self.collection).name, cre.name)
        self.assertEqual(main.register_cre(cre, self.collection).external_id, cre.id)
        self.assertEqual(
            len(self.collection.session.query(db.CRE).all()), 1
        )  # 1 cre in the db
        self.assertEqual(
            len(self.collection.session.query(db.Node).all()), 2
        )  # 2 nodes in the db

    def test_parse_file(self) -> None:
        file: List[Dict[str, Any]] = [
            {
                "description": "Verify that approved cryptographic algorithms are used in the generation, seeding, and verification.",
                "doctype": "CRE",
                "id": "001-005-073",
                "links": [
                    {
                        "type": "SAM",
                        "document": {
                            "doctype": "Standard",
                            "name": "TOP10",
                            "section": "https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                        },
                    },
                    {
                        "type": "SAM",
                        "document": {
                            "doctype": "Standard",
                            "name": "ISO 25010",
                            "section": "Secure data storage",
                        },
                    },
                ],
                "name": "CREDENTIALS_MANAGEMENT_CRYPTOGRAPHIC_DIRECTIVES",
            },
            {
                "description": "Desc",
                "doctype": "CRE",
                "id": "14",
                "name": "name",
            },
        ]
        expected = [
            defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="001-005-073",
                description="Verify that approved cryptographic algorithms are used in the generation, seeding, and verification.",
                name="CREDENTIALS_MANAGEMENT_CRYPTOGRAPHIC_DIRECTIVES",
                links=[
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="TOP10",
                            section="https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="ISO 25010",
                            section="Secure data storage",
                        )
                    ),
                ],
            ),
            defs.CRE(id="14", description="Desc", name="name"),
        ]
        with self.assertLogs("application.cmd.cre_main", level=logging.FATAL) as logs:
            # negative test first parse_file accepts a list of objects
            result = main.parse_file(
                filename="tests",
                yamldocs=[
                    "no",
                    "valid",
                    "objects",
                    "here",
                    {
                        1: 2,
                    },
                ],
                scollection=self.collection,
            )

            self.assertEqual(result, None)
            self.assertIn(
                "CRITICAL:application.cmd.cre_main:Malformed file tests, skipping",
                logs.output,
            )

        self.maxDiff = None

        res = main.parse_file(
            filename="tests", yamldocs=file, scollection=self.collection
        )
        self.assertCountEqual(res, expected)

    def test_parse_standards_from_spreadsheeet(self) -> None:
        input = [
            {
                "Standard ASVS 4.0.3 Item": "",
                "Standard ASVS 4.0.3 description": "",
                "Standard ASVS 4.0.3 Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "",
                "Standard Top 10 2017 item": "A2_Broken_Authentication",
                "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
                "CRE ID": "",
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "",
                "Standard NIST 800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG-item": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS 4.0.3 Item": "",
                "Standard ASVS 4.0.3 description": "",
                "Standard ASVS 4.0.3 Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "tag-connection",
                "Standard Top 10 2017 item": "",
                "Standard Top 10 2017 Hyperlink": "",
                "CRE ID": "123",
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "",
                "Standard NIST 800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG-item": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS 4.0.3 Item": "",
                "Standard ASVS 4.0.3 description": "",
                "Standard ASVS 4.0.3 Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "Authentication",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "",
                "Standard Top 10 2017 item": "A2_Broken_Authentication",
                "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
                "CRE ID": 8,
                "Standard CWE (from ASVS)": "19876",
                "Standard CWE (from ASVS)-hyperlink": "https://example.com/cwe19876",
                "Link to other CRE": "FooBar",
                "Standard NIST 800-53 v5": "SA-22 Unsupported System Components",
                "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
                "Standard NIST-800-63 (from ASVS)": "4444/3333",
                "Standard OPC (ASVS source)": "123654",
                "Standard OPC (ASVS source)-hyperlink": "https://example.com/opc",
                "CRE Tags": "tag-connection",
                "Standard WSTG-item": "2.1.2.3",
                "Standard WSTG-Hyperlink": "https://example.com/wstg",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS 4.0.3 Item": "",
                "Standard ASVS 4.0.3 description": "",
                "Standard ASVS 4.0.3 Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "Authentication",
                "CRE hierarchy 2": "Authentication mechanism",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "",
                "Standard Top 10 2017 item": "See higher level topic",
                "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
                "CRE ID": 3,
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
                "Standard NIST-800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG-item": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS 4.0.3 Item": "V1.2.3",
                "Standard ASVS 4.0.3 description": 10,
                "Standard ASVS 4.0.3 Hyperlink": "https://example.com/asvs",
                "ASVS-L1": "",
                "ASVS-L2": "X",
                "ASVS-L3": "X",
                "CRE hierarchy 1": "Authentication",
                "CRE hierarchy 2": "Authentication mechanism",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "Verify that the application uses a single vetted authentication mechanism",
                "Standard Top 10 2017 item": "See higher level topic",
                "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
                "CRE ID": 4,
                "Standard CWE (from ASVS)": 306,
                "Standard CWE (from ASVS)-hyperlink": "https://example.com/cwe306",
                "Link to other CRE": "Logging and Error handling",
                "Standard NIST 800-53 v5": "PL-8 Information Security Architecture\n"
                "SC-39 PROCESS ISOLATION\n"
                "SC-3 SECURITY FUNCTION",
                "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5\n"
                "https://example.com/nist-800-53-v5\n"
                "https://example.com/nist-800-53-v5",
                "Standard NIST-800-63 (from ASVS)": "None",
                "Standard OPC (ASVS source)": "None",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG-item": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS 4.0.3 Item": "",
                "Standard ASVS 4.0.3 description": "",
                "Standard ASVS 4.0.3 Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "FooParent",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "FooBar",
                "Standard Top 10 2017 item": "",
                "Standard Top 10 2017 Hyperlink": "",
                "CRE ID": 9,
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "Authentication mechanism",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "",
                "Standard NIST-800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG-item": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "foo; bar",
                "Standard Cheat_sheets-Hyperlink": "https://example.com/cheatsheetf/foo; https://example.com/cheatsheetb/bar",
            },
        ]
        main.parse_standards_from_spreadsheeet(input, self.collection)
        self.assertEqual(len(self.collection.session.query(db.Node).all()), 14)
        self.assertEqual(len(self.collection.session.query(db.CRE).all()), 7)
        # assert the one CRE in the inpu externally links to all the 8 standards
        self.assertEqual(len(self.collection.session.query(db.Links).all()), 14)
        self.assertEqual(len(self.collection.session.query(db.InternalLinks).all()), 7)

    def test_get_standards_files_from_disk(self) -> None:
        loc = tempfile.mkdtemp()
        ymls = []
        cre = defs.CRE(name="c", description="cd")
        for _ in range(1, 5):
            ymldesc, location = tempfile.mkstemp(dir=loc, suffix=".yaml", text=True)
            os.write(ymldesc, bytes(str(cre), "utf-8"))
            ymls.append(location)
        self.assertCountEqual(ymls, [x for x in main.get_cre_files_from_disk(loc)])

    @patch("application.cmd.cre_main.db_connect")
    @patch("application.cmd.cre_main.parse_standards_from_spreadsheeet")
    @patch("application.utils.spreadsheet.readSpreadsheet")
    @patch("application.database.db.Node_collection.export")
    def test_add_from_spreadsheet(
        self,
        mocked_export: Mock,
        mocked_readSpreadsheet: Mock,
        mocked_parse_standards_from_spreadsheeet: Mock,
        mocked_db_connect: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]

        mocked_db_connect.return_value = self.collection
        mocked_export.return_value = [
            defs.CRE(name="c0"),
            defs.Standard(name="s0", section="s1"),
        ]
        mocked_readSpreadsheet.return_value = {"worksheet0": [{"cre": "cre"}]}

        main.add_from_spreadsheet(
            spreadsheet_url="https://example.com/sheeet", cache_loc=cache, cre_loc=dir
        )

        mocked_db_connect.assert_called_with(path=cache)
        mocked_readSpreadsheet.assert_called_with(
            url="https://example.com/sheeet",
            alias="new spreadsheet",
            validate=False,
        )
        mocked_parse_standards_from_spreadsheeet.assert_called_with(
            [{"cre": "cre"}], self.collection
        )
        mocked_export.assert_called_with(dir)

    @patch("application.cmd.cre_main.prepare_for_review")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.cmd.cre_main.parse_standards_from_spreadsheeet")
    @patch("application.utils.spreadsheet.readSpreadsheet")
    @patch("application.cmd.cre_main.create_spreadsheet")
    @patch("application.database.db.Node_collection.export")
    def test_review_from_spreadsheet(
        self,
        mocked_export: Mock,
        mocked_create_spreadsheet: Mock,
        mocked_readSpreadsheet: Mock,
        mocked_parse_standards_from_spreadsheeet: Mock,
        mocked_db_connect: Mock,
        mocked_prepare_for_review: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        loc = tempfile.mkstemp(dir=dir)[1]
        cache = tempfile.mkstemp(dir=dir)[1]
        mocked_prepare_for_review.return_value = (loc, cache)
        mocked_db_connect.return_value = self.collection

        mocked_create_spreadsheet.return_value = "https://example.com/sheeet"
        mocked_export.return_value = [
            defs.CRE(name="c0"),
            defs.Standard(name="s0", section="s1"),
        ]
        mocked_readSpreadsheet.return_value = {"worksheet0": [{"cre": "cre"}]}

        main.review_from_spreadsheet(
            spreadsheet_url="https://example.com/sheeet",
            cache=cache,
            share_with="foo@example.com",
        )

        mocked_prepare_for_review.assert_called_with(cache)
        mocked_db_connect.assert_called_with(path=cache)
        mocked_parse_standards_from_spreadsheeet.assert_called_with(
            [{"cre": "cre"}], self.collection
        )
        # mocked_create_spreadsheet.assert_called_with(
        #     collection=self.collection,
        #     exported_documents=[
        #         defs.CRE(name="c0"),
        #         defs.Standard(name="s0", section="s1"),
        #     ],
        #     title="cre_review",
        #     share_with=["foo@example.com"],
        # )
        mocked_export.assert_called_with(loc)

    @patch("application.cmd.cre_main.prepare_for_review")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.cmd.cre_main.get_cre_files_from_disk")
    @patch("application.cmd.cre_main.parse_file")
    @patch("application.cmd.cre_main.create_spreadsheet")
    @patch("application.database.db.Node_collection.export")
    def test_review_from_disk(
        self,
        mocked_export: Mock,
        mocked_create_spreadsheet: Mock,
        mocked_parse_file: Mock,
        mocked_get_standards_files_from_disk: Mock,
        mocked_db_connect: Mock,
        mocked_prepare_for_review: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        yml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
        loc = tempfile.mkstemp(dir=dir)[1]
        cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
        mocked_prepare_for_review.return_value = (loc, cache)
        mocked_db_connect.return_value = self.collection
        mocked_get_standards_files_from_disk.return_value = [yml for i in range(0, 3)]
        mocked_export.return_value = [
            defs.CRE(name="c0"),
            defs.Standard(name="s0", section="s1"),
            defs.Code(name="code0", description="code1"),
            defs.Tool(
                name="t0", tooltype=defs.ToolTypes.Offensive, description="tool0"
            ),
        ]
        mocked_create_spreadsheet.return_value = "https://example.com/sheeet"

        main.review_from_disk(
            cache=cache, cre_file_loc=dir, share_with="foo@example.com"
        )

        mocked_db_connect.assert_called_with(path=cache)
        mocked_parse_file.assert_called_with(
            filename=yml, yamldocs=[], scollection=self.collection
        )
        mocked_export.assert_called_with(loc)
        mocked_create_spreadsheet.assert_called_with(
            collection=self.collection,
            exported_documents=mocked_export.return_value,
            title="cre_review",
            share_with=["foo@example.com"],
        )

    @patch("application.cmd.cre_main.db_connect")
    @patch("application.cmd.cre_main.get_cre_files_from_disk")
    @patch("application.cmd.cre_main.parse_file")
    @patch("application.database.db.Node_collection.export")
    def test_add_from_disk(
        self,
        mocked_export: Mock,
        mocked_parse_file: Mock,
        mocked_get_standards_files_from_disk: Mock,
        mocked_db_connect: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        yml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
        loc = tempfile.mkstemp(dir=dir)[1]
        cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
        mocked_db_connect.return_value = self.collection
        mocked_get_standards_files_from_disk.return_value = [yml for i in range(0, 3)]
        mocked_export.return_value = [
            defs.CRE(name="c0"),
            defs.Standard(name="s0", section="s1"),
            defs.Code(name="code0", description="code1"),
            defs.Tool(
                name="t0", tooltype=defs.ToolTypes.Offensive, description="tool0"
            ),
        ]

        main.add_from_disk(cache_loc=cache, cre_loc=dir)

        mocked_db_connect.assert_called_with(path=cache)
        mocked_parse_file.assert_called_with(
            filename=yml, yamldocs=[], scollection=self.collection
        )
        mocked_export.assert_called_with(dir)

    @patch("application.cmd.cre_main.prepare_for_review")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.defs.osib_defs.read_osib_yaml")
    @patch("application.defs.osib_defs.try_from_file")
    @patch("application.defs.osib_defs.osib2cre")
    @patch("application.cmd.cre_main.register_cre")
    @patch("application.cmd.cre_main.register_node")
    @patch("application.cmd.cre_main.create_spreadsheet")
    @patch("application.database.db.Node_collection.export")
    def test_review_osib_from_file(
        self,
        mocked_export: Mock,
        mocked_create_spreadsheet: Mock,
        mocked_register_node: Mock,
        mocked_register_cre: Mock,
        mocked_osib2cre: Mock,
        mocked_try_from_file: Mock,
        mocked_read_osib_yaml: Mock,
        mocked_db_connect: Mock,
        mocked_prepare_for_review: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        osib_yaml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
        loc = tempfile.mkstemp(dir=dir)[1]
        cach = tempfile.mkstemp(dir=dir)[1]
        mocked_prepare_for_review.return_value = (loc, cach)
        mocked_db_connect.return_value = self.collection
        mocked_read_osib_yaml.return_value = [{"osib": "osib"}]
        mocked_try_from_file.return_value = [
            Osib_tree(aliases=[Osib_id("t1")]),
            Osib_tree(aliases=[Osib_id("t2")]),
        ]

        mocked_osib2cre.return_value = (
            [defs.CRE(name="c0")],
            [defs.Standard(name="s0", section="s1")],
        )
        mocked_register_cre.return_value = db.CRE(name="c0")
        mocked_register_node.return_value = db.Node(name="s0", section="s1")
        mocked_create_spreadsheet.return_value = "https://example.com/sheeet"
        mocked_export.return_value = [
            defs.CRE(name="c0"),
            defs.Standard(name="s0", section="s1"),
        ]

        main.review_osib_from_file(file_loc=osib_yaml, cache=cach, cre_loc=dir)

        mocked_prepare_for_review.assert_called_with(cach)
        mocked_db_connect.assert_called_with(path=cach)
        mocked_read_osib_yaml.assert_called_with(osib_yaml)
        mocked_try_from_file.assert_called_with([{"osib": "osib"}])
        mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t1")]))
        mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t2")]))
        mocked_register_cre.assert_called_with(defs.CRE(name="c0"), self.collection)
        mocked_register_node.assert_called_with(
            mocked_osib2cre.return_value[1][0], self.collection
        )

        mocked_create_spreadsheet.assert_called_with(
            collection=self.collection,
            exported_documents=mocked_export.return_value,
            title="osib_review",
            share_with=[],
        )
        mocked_export.assert_called_with(loc)

    @patch("application.cmd.cre_main.db_connect")
    @patch("application.defs.osib_defs.read_osib_yaml")
    @patch("application.defs.osib_defs.try_from_file")
    @patch("application.defs.osib_defs.osib2cre")
    @patch("application.cmd.cre_main.register_cre")
    @patch("application.cmd.cre_main.register_node")
    @patch("application.database.db.Node_collection.export")
    def test_add_osib_from_file(
        self,
        mocked_export: Mock,
        mocked_register_node: Mock,
        mocked_register_cre: Mock,
        mocked_osib2cre: Mock,
        mocked_try_from_file: Mock,
        mocked_read_osib_yaml: Mock,
        mocked_db_connect: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        osib_yaml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
        loc = tempfile.mkstemp(dir=dir)[1]
        cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
        mocked_db_connect.return_value = self.collection
        mocked_read_osib_yaml.return_value = [{"osib": "osib"}]
        mocked_try_from_file.return_value = [
            odefs.Osib_tree(aliases=[Osib_id("t1")]),
            odefs.Osib_tree(aliases=[Osib_id("t2")]),
        ]
        mocked_osib2cre.return_value = (
            [defs.CRE(name="c0")],
            [defs.Standard(name="s0", section="s1")],
        )
        mocked_register_cre.return_value = db.CRE(name="c0")
        mocked_register_node.return_value = db.Node(name="s0", section="s1")
        mocked_export.return_value = [
            defs.CRE(name="c0"),
            defs.Standard(name="s0", section="s1"),
        ]

        main.add_osib_from_file(file_loc=osib_yaml, cache=cache, cre_loc=dir)

        mocked_db_connect.assert_called_with(path=cache)
        mocked_read_osib_yaml.assert_called_with(osib_yaml)
        mocked_try_from_file.assert_called_with([{"osib": "osib"}])
        mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t1")]))
        mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t2")]))
        mocked_register_cre.assert_called_with(defs.CRE(name="c0"), self.collection)
        mocked_register_node.assert_called_with(
            defs.Standard(name="s0", section="s1"), self.collection
        )
        mocked_export.assert_called_with(dir)

    @patch("application.database.db.Node_collection.export")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.defs.osib_defs.cre2osib")
    def test_export_to_osib(
        self,
        mocked_cre2osib: Mock,
        mocked_db_connect: Mock,
        mocked_export: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        # osib_yaml = tempfile.mkstemp(dir=dir,suffix=".yaml")[1]
        loc = tempfile.mkstemp(dir=dir)[1]
        cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
        mocked_db_connect.return_value = self.collection
        mocked_cre2osib.return_value = odefs.Osib_tree(aliases=[Osib_id("t1")])
        mocked_export.return_value = [defs.CRE(name="c0")]

        main.export_to_osib(file_loc=f"{dir}/osib.yaml", cache=cache)
        mocked_db_connect.assert_called_with(path=cache)
        mocked_cre2osib.assert_called_with([defs.CRE(name="c0")])

    # def test_prepare_for_Review(self):
    #     raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
