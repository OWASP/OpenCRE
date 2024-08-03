import logging
import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, List
from unittest import mock
from unittest.mock import Mock, patch
from rq import Queue
from application.utils import redis
from application.prompt_client import prompt_client as prompt_client
from application.tests.utils import data_gen
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
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.tmpdirs: List[str] = []
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
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
        # no links since our nodes do not have a CRE to map to
        for thing in self.collection.session.query(db.Links).all():
            self.assertIsNone(thing.cre)

        self.assertEqual(self.collection.session.query(db.Links).all(), [])

        # 4 cre-less nodes in the db
        self.assertEqual(len(self.collection.session.query(db.Node).all()), 4)

    def test_register_node_with_cre(self) -> None:
        credoc = defs.CRE(id="101-202", name="crename")
        known_standard_with_cre = defs.Standard(
            name="CWE",
            sectionID="598",
            links=[
                defs.Link(document=credoc),
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
                defs.Link(document=credoc),
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
        self.collection.add_cre(credoc)
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
        credoc = defs.CRE(
            doctype=defs.Credoctypes.CRE,
            id="101-001",
            description="cre2 desc",
            name="crename2",
        )
        credoc2 = defs.CRE(
            doctype=defs.Credoctypes.CRE,
            id="101-000",
            description="cre desc",
            name="crename",
        )
        credoc3 = defs.CRE(
            id="101-002",
            description="group desc",
            name="group name",
            links=[defs.Link(document=credoc, ltype=defs.LinkTypes.Contains)],
        )
        with_groupped_cre_links = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            id="",
            description="",
            name="standard_with",
            links=[
                defs.Link(document=credoc3),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard, name="CWE", sectionID="598"
                    )
                ),
                defs.Link(document=credoc2),
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
        self.collection.add_cre(credoc)
        self.collection.add_cre(credoc2)
        self.collection.add_cre(credoc3)

        main.register_node(
            node=with_groupped_cre_links, collection=self.collection.with_graph()
        )
        # assert db structure makes sense
        self.assertEqual(
            len(self.collection.session.query(db.Links).all()), 5
        )  # 5 links in the db

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
            id="100-100",
            description="CREdesc",
            name="CREname",
            links=[defs.Link(document=standard), defs.Link(document=tool)],
            tags=["CREt1", "CREt2"],
            metadata={"tags": ["CREl1", "CREl2"]},
        )
        c, _ = main.register_cre(cre, self.collection)
        self.assertEqual(c.name, cre.name)

        self.assertEqual(c.external_id, cre.id)
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
                "id": "157-573",
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
                "id": "141-141",
                "name": "name",
            },
        ]
        expected = [
            defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="157-573",
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
            defs.CRE(id="141-141", description="Desc", name="name"),
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

    @patch.object(main, "db_connect")
    @patch.object(Queue, "enqueue_call")
    @patch.object(redis, "connect")
    @patch.object(prompt_client.PromptHandler, "generate_embeddings_for")
    @patch.object(main, "populate_neo4j_db")
    def test_parse_standards_from_spreadsheeet(
        self,
        mock_populate_neo4j_db,
        mock_generate_embeddings_for,
        mock_redis_connect,
        mock_enqueue_call,
        mock_db_connect,
    ) -> None:
        self.maxDiff = None
        prompt_handler = prompt_client.PromptHandler(database=self.collection)
        mock_db_connect.return_value = self.collection
        # No jobs scheduled when we're registering CREs only
        expected_input, _ = data_gen.root_csv_cre_only()
        main.parse_standards_from_spreadsheeet(expected_input, "", prompt_handler)
        mock_enqueue_call.assert_not_called()

        # Jobs scheduled when we're registering Standards only
        expected_input, expected_output = data_gen.root_csv_data()
        main.parse_standards_from_spreadsheeet(expected_input, "", prompt_handler)
        mock_enqueue_call.assert_called()
        expected_output.pop(defs.Credoctypes.CRE.value)
        expected_names = list(expected_output.keys())
        # This is a roundabout way of doing mock_enqueue_call.assert_has_calls([calls])
        # the reason is: in its current implementation assert_has_calls()
        # serialises kwargs to str, this ends up serialising a defs.Document
        #  using single quotes, meanwhile the standard library uses double quotes,
        # this causes the call to fail.
        for call in mock_enqueue_call.mock_calls:
            if not call.kwargs:
                continue
            standard_name = call.kwargs.get("kwargs").get("standard_entries")[0].name
            for entry in call.kwargs.get("kwargs").get("standard_entries"):
                self.assertIn(entry, expected_output[standard_name])
                expected_output[standard_name].pop(
                    expected_output[standard_name].index(entry)
                )
            self.assertEqual(
                expected_output[standard_name], []
            )  # assert ALL elements of the call exist in expected
            self.assertEqual(None, call.kwargs["kwargs"]["collection"])
            self.assertEqual("", call.kwargs["kwargs"]["db_connection_str"])
            expected_names.pop(expected_names.index(standard_name))
        self.assertEqual(
            expected_names,
            [],
            f"method parse_standards_from_spreadsheeet failed to process standards {','.join(expected_names)}",
        )

    def test_get_standards_files_from_disk(self) -> None:
        loc = tempfile.mkdtemp()
        ymls = []
        cre = defs.CRE(id="333-333", name="ccc", description="cd")
        for _ in range(1, 5):
            ymldesc, location = tempfile.mkstemp(dir=loc, suffix=".yaml", text=True)
            os.write(ymldesc, bytes(str(cre), "utf-8"))
            ymls.append(location)
        self.assertCountEqual(ymls, [x for x in main.get_cre_files_from_disk(loc)])

    @patch("application.cmd.cre_main.ai_client_init")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.cmd.cre_main.parse_standards_from_spreadsheeet")
    @patch("application.utils.spreadsheet.read_spreadsheet")
    @patch("application.database.db.Node_collection.export")
    def test_add_from_spreadsheet(
        self,
        mocked_export: Mock,
        mocked_readSpreadsheet: Mock,
        mocked_parse_standards_from_spreadsheeet: Mock,
        mocked_db_connect: Mock,
        mocked_ai_client_init: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]

        mocked_ai_client_init.return_value = prompt_client.PromptHandler(
            self.collection
        )
        mocked_db_connect.return_value = self.collection
        mocked_export.return_value = [
            defs.CRE(id="000-000", name="c0"),
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
            [{"cre": "cre"}], cache, mocked_ai_client_init.return_value
        )
        # mocked_export.assert_called_with(dir) we don't export anymore

    @patch("application.cmd.cre_main.ai_client_init")
    @patch("application.cmd.cre_main.prepare_for_review")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.cmd.cre_main.parse_standards_from_spreadsheeet")
    @patch("application.utils.spreadsheet.read_spreadsheet")
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
        mocked_ai_client_init: Mock,
    ) -> None:
        dir = tempfile.mkdtemp()
        self.tmpdirs.append(dir)
        loc = tempfile.mkstemp(dir=dir)[1]
        cache = tempfile.mkstemp(dir=dir)[1]
        mocked_prepare_for_review.return_value = (loc, cache)
        mocked_db_connect.return_value = self.collection
        mocked_ai_client_init.return_value = prompt_client.PromptHandler(
            self.collection
        )

        mocked_create_spreadsheet.return_value = "https://example.com/sheeet"
        mocked_export.return_value = [
            defs.CRE(id="000-000", name="c0"),
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
            [{"cre": "cre"}], self.collection, mocked_ai_client_init.return_value
        )
        # mocked_export.assert_called_with(loc) #we don't export anymore

    # @patch("application.cmd.cre_main.prepare_for_review")
    # @patch("application.cmd.cre_main.db_connect")
    # @patch("application.cmd.cre_main.get_cre_files_from_disk")
    # @patch("application.cmd.cre_main.parse_file")
    # @patch("application.cmd.cre_main.create_spreadsheet")
    # @patch("application.database.db.Node_collection.export")
    # def test_review_from_disk(
    #     self,
    #     mocked_export: Mock,
    #     mocked_create_spreadsheet: Mock,
    #     mocked_parse_file: Mock,
    #     mocked_get_standards_files_from_disk: Mock,
    #     mocked_db_connect: Mock,
    #     mocked_prepare_for_review: Mock,
    # ) -> None:
    #     dir = tempfile.mkdtemp()
    #     self.tmpdirs.append(dir)
    #     yml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
    #     loc = tempfile.mkstemp(dir=dir)[1]
    #     cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
    #     mocked_prepare_for_review.return_value = (loc, cache)
    #     mocked_db_connect.return_value = self.collection
    #     mocked_get_standards_files_from_disk.return_value = [yml for i in range(0, 3)]
    #     mocked_export.return_value = [
    #         defs.CRE(id="000-000", name="c0"),
    #         defs.Standard(name="s0", section="s1"),
    #         defs.Code(name="code0", description="code1"),
    #         defs.Tool(
    #             name="t0", tooltype=defs.ToolTypes.Offensive, description="tool0"
    #         ),
    #     ]
    #     mocked_create_spreadsheet.return_value = "https://example.com/sheeet"

    #     main.review_from_disk(
    #         cache=cache, cre_file_loc=dir, share_with="foo@example.com"
    #     )

    #     mocked_db_connect.assert_called_with(path=cache)
    #     mocked_parse_file.assert_called_with(
    #         filename=yml, yamldocs=[], scollection=self.collection
    #     )
    #     mocked_export.assert_called_with(loc)
    #     mocked_create_spreadsheet.assert_called_with(
    #         collection=self.collection,
    #         exported_documents=mocked_export.return_value,
    #         title="cre_review",
    #         share_with=["foo@example.com"],
    #     )

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
            defs.CRE(id="000-000", name="c0"),
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
        # mocked_export.assert_called_with(dir) # we don't export anymore

    # @patch("application.cmd.cre_main.prepare_for_review")
    # @patch("application.cmd.cre_main.db_connect")
    # @patch("application.defs.osib_defs.read_osib_yaml")
    # @patch("application.defs.osib_defs.try_from_file")
    # @patch("application.defs.osib_defs.osib2cre")
    # @patch("application.cmd.cre_main.register_cre")
    # @patch("application.cmd.cre_main.register_node")
    # @patch("application.cmd.cre_main.create_spreadsheet")
    # @patch("application.database.db.Node_collection.export")
    # def test_review_osib_from_file(
    #     self,
    #     mocked_export: Mock,
    #     mocked_create_spreadsheet: Mock,
    #     mocked_register_node: Mock,
    #     mocked_register_cre: Mock,
    #     mocked_osib2cre: Mock,
    #     mocked_try_from_file: Mock,
    #     mocked_read_osib_yaml: Mock,
    #     mocked_db_connect: Mock,
    #     mocked_prepare_for_review: Mock,
    # ) -> None:
    #     dir = tempfile.mkdtemp()
    #     self.tmpdirs.append(dir)
    #     osib_yaml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
    #     loc = tempfile.mkstemp(dir=dir)[1]
    #     cach = tempfile.mkstemp(dir=dir)[1]
    #     mocked_prepare_for_review.return_value = (loc, cach)
    #     mocked_db_connect.return_value = self.collection
    #     mocked_read_osib_yaml.return_value = [{"osib": "osib"}]
    #     mocked_try_from_file.return_value = [
    #         Osib_tree(aliases=[Osib_id("t1")]),
    #         Osib_tree(aliases=[Osib_id("t2")]),
    #     ]

    #     mocked_osib2cre.return_value = (
    #         [defs.CRE(name="c0", id="000-000")],
    #         [defs.Standard(name="s0", section="s1")],
    #     )
    #     mocked_register_cre.return_value = db.CRE(name="c0", id="000-000")
    #     mocked_register_node.return_value = db.Node(name="s0", section="s1")
    #     mocked_create_spreadsheet.return_value = "https://example.com/sheeet"
    #     mocked_export.return_value = [
    #         defs.CRE(name="c0", id="000-000"),
    #         defs.Standard(name="s0", section="s1"),
    #     ]

    #     main.review_osib_from_file(file_loc=osib_yaml, cache=cach, cre_loc=dir)

    #     mocked_prepare_for_review.assert_called_with(cach)
    #     mocked_db_connect.assert_called_with(path=cach)
    #     mocked_read_osib_yaml.assert_called_with(osib_yaml)
    #     mocked_try_from_file.assert_called_with([{"osib": "osib"}])
    #     mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t1")]))
    #     mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t2")]))
    #     mocked_register_cre.assert_called_with(
    #         defs.CRE(id="000-000", name="c0"), self.collection
    #     )
    #     mocked_register_node.assert_called_with(
    #         mocked_osib2cre.return_value[1][0], self.collection
    #     )

    #     mocked_create_spreadsheet.assert_called_with(
    #         collection=self.collection,
    #         exported_documents=mocked_export.return_value,
    #         title="osib_review",
    #         share_with=[],
    #     )
    #     mocked_export.assert_called_with(loc)

    # @patch("application.cmd.cre_main.db_connect")
    # @patch("application.defs.osib_defs.read_osib_yaml")
    # @patch("application.defs.osib_defs.try_from_file")
    # @patch("application.defs.osib_defs.osib2cre")
    # @patch("application.cmd.cre_main.register_cre")
    # @patch("application.cmd.cre_main.register_node")
    # @patch("application.database.db.Node_collection.export")
    # def test_add_osib_from_file(
    #     self,
    #     mocked_export: Mock,
    #     mocked_register_node: Mock,
    #     mocked_register_cre: Mock,
    #     mocked_osib2cre: Mock,
    #     mocked_try_from_file: Mock,
    #     mocked_read_osib_yaml: Mock,
    #     mocked_db_connect: Mock,
    # ) -> None:
    #     dir = tempfile.mkdtemp()
    #     self.tmpdirs.append(dir)
    #     osib_yaml = tempfile.mkstemp(dir=dir, suffix=".yaml")[1]
    #     loc = tempfile.mkstemp(dir=dir)[1]
    #     cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
    #     mocked_db_connect.return_value = self.collection
    #     mocked_read_osib_yaml.return_value = [{"osib": "osib"}]
    #     mocked_try_from_file.return_value = [
    #         odefs.Osib_tree(aliases=[Osib_id("t1")]),
    #         odefs.Osib_tree(aliases=[Osib_id("t2")]),
    #     ]
    #     mocked_osib2cre.return_value = (
    #         [defs.CRE(id="000-000", name="c0")],
    #         [defs.Standard(name="s0", section="s1")],
    #     )
    #     mocked_register_cre.return_value = db.CRE(name="c0")
    #     mocked_register_node.return_value = db.Node(name="s0", section="s1")
    #     mocked_export.return_value = [
    #         defs.CRE(id="000-000", name="c0"),
    #         defs.Standard(name="s0", section="s1"),
    #     ]

    #     main.add_osib_from_file(file_loc=osib_yaml, cache=cache, cre_loc=dir)

    #     mocked_db_connect.assert_called_with(path=cache)
    #     mocked_read_osib_yaml.assert_called_with(osib_yaml)
    #     mocked_try_from_file.assert_called_with([{"osib": "osib"}])
    #     mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t1")]))
    #     mocked_osib2cre.assert_called_with(odefs.Osib_tree(aliases=[Osib_id("t2")]))
    #     mocked_register_cre.assert_called_with(
    #         defs.CRE(id="000-000", name="c0"), self.collection
    #     )
    #     mocked_register_node.assert_called_with(
    #         defs.Standard(name="s0", section="s1"), self.collection
    #     )
    #     mocked_export.assert_called_with(dir)

    # @patch("application.database.db.Node_collection.export")
    # @patch("application.cmd.cre_main.db_connect")
    # @patch("application.defs.osib_defs.cre2osib")
    # def test_export_to_osib(
    #     self,
    #     mocked_cre2osib: Mock,
    #     mocked_db_connect: Mock,
    #     mocked_export: Mock,
    # ) -> None:
    #     dir = tempfile.mkdtemp()
    #     self.tmpdirs.append(dir)
    #     loc = tempfile.mkstemp(dir=dir)[1]
    #     cache = tempfile.mkstemp(dir=dir, suffix=".sqlite")[1]
    #     mocked_db_connect.return_value = self.collection
    #     mocked_cre2osib.return_value = odefs.Osib_tree(aliases=[Osib_id("t1")])
    #     mocked_export.return_value = [defs.CRE(id="000-000", name="c0")]

    #     main.export_to_osib(file_loc=f"{dir}/osib.yaml", cache=cache)
    #     mocked_db_connect.assert_called_with(path=cache)
    #     mocked_cre2osib.assert_called_with([defs.CRE(id="000-000", name="c0")])


if __name__ == "__main__":
    unittest.main()
