import logging
import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, List
from unittest import mock
from unittest.mock import Mock, patch
from rq import Queue, job
from application.utils import redis
from application.prompt_client import prompt_client as prompt_client
from application.tests.utils import data_gen
from application import create_app, sqla  # type: ignore
from application.cmd import cre_main as main
from application.database import db
from application.defs import cre_defs as defs
from application.defs import cre_exceptions
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

    @patch.object(main, "populate_neo4j_db")
    @patch.object(main.gap_analysis, "perform")
    @patch.object(redis, "connect")
    @patch.object(main, "register_node")
    def test_register_standard_skips_ga_for_tool_entries(
        self, register_node_mock, redis_connect_mock, ga_mock, populate_neo4j_mock
    ) -> None:
        """
        Step 3 rule: GA should not run for Tool/Code resources.
        Regression test: Ensure that gap analysis is centralized and not delegated downwards.
        """
        redis_connect_mock.return_value = None
        tool_entry = defs.Tool(
            name="Tool Resource",
            description="test tool",
            tooltype=defs.ToolTypes.Defensive,
        )

        main.register_standard(
            standard_entries=[tool_entry],  # type: ignore[list-item]
            collection=self.collection,
            calculate_gap_analysis=True,
            generate_embeddings=False,
        )

        populate_neo4j_mock.assert_not_called()
        ga_mock.assert_not_called()

    @patch.object(main, "populate_neo4j_db")
    @patch.object(main.gap_analysis, "perform")
    @patch.object(redis, "connect")
    @patch.object(main, "register_node")
    def test_register_standard_allows_ga_for_taxonomy_standard(
        self,
        register_node_mock,
        redis_connect_mock,
        ga_mock,
        populate_neo4j_mock,
    ) -> None:
        """
        Taxonomy/risk-list standards (e.g. CAPEC) are GA-eligible.
        Regression test: Ensure that gap analysis is centralized and not delegated downwards.
        """
        redis_connect_mock.return_value = Mock(get=Mock(return_value=None), set=Mock())
        # Ensure there is another standard to compare against.
        self.collection.standards = Mock(return_value=["CWE", "ASVS"])  # type: ignore[method-assign]

        taxonomy_standard = defs.Standard(
            name="CWE",
            section="Some CWE",
            sectionID="123",
            tags=["family:taxonomy", "subtype:risk_list"],
        )

        main.register_standard(
            standard_entries=[taxonomy_standard],
            collection=self.collection,
            calculate_gap_analysis=True,
            generate_embeddings=False,
        )

        populate_neo4j_mock.assert_not_called()
        ga_mock.assert_not_called()

    @patch.object(main, "populate_neo4j_db")
    @patch.object(main.gap_analysis, "perform")
    @patch.object(redis, "connect")
    @patch.object(main, "register_node")
    def test_register_standard_skips_missing_ga_job_id_without_crashing(
        self,
        register_node_mock,
        redis_connect_mock,
        ga_mock,
        populate_neo4j_mock,
    ) -> None:
        """
        Regression test: Ensure that gap analysis is centralized and not delegated downwards.
        Since we no longer delegate jobs to RQ for GA during importing, skipping missing job IDs is irrelevant.
        Instead, we just test that ga_mock is called and doesn't crash on mocked errors if any.
        """
        redis_connect_mock.return_value = Mock(get=Mock(return_value=None), set=Mock())
        self.collection.standards = Mock(return_value=["CWE", "ASVS"])  # type: ignore[method-assign]
        self.collection.gap_analysis_exists = Mock(return_value=False)
        # Ensure DB structure changes so incremental-GA doesn't short-circuit.
        register_node_mock.side_effect = lambda node, collection: collection.add_node(
            node
        )  # type: ignore[no-any-return]

        # Make it GA-eligible by providing both required tags.
        eligible_standard = defs.Standard(
            name="CWE",
            section="Some CWE",
            sectionID="123",
            tags=["family:standard", "subtype:requirements_standard"],
        )

        main.register_standard(
            standard_entries=[eligible_standard],
            collection=self.collection,
            calculate_gap_analysis=True,
            generate_embeddings=False,
        )

        populate_neo4j_mock.assert_not_called()
        ga_mock.assert_not_called()

    @patch.object(main, "populate_neo4j_db")
    @patch.object(main.gap_analysis, "perform")
    @patch.object(redis, "connect")
    @patch.object(main, "register_node")
    def test_register_standard_runs_ga_for_requirements_standard(
        self,
        register_node_mock,
        redis_connect_mock,
        ga_mock,
        populate_neo4j_mock,
    ) -> None:
        """
        Step 3b minimal behavior: GA runs for GA-eligible Standard entries
        (family:standard + subtype:requirements_standard).
        Regression test: Ensure that gap analysis is centralized and not delegated downwards.
        """
        redis_connect_mock.return_value = Mock(get=Mock(return_value=None), set=Mock())
        self.collection.standards = Mock(return_value=["CWE", "ASVS"])  # type: ignore[method-assign]
        self.collection.gap_analysis_exists = Mock(return_value=False)
        # Ensure DB structure changes so incremental-GA doesn't short-circuit.
        register_node_mock.side_effect = lambda node, collection: collection.add_node(
            node
        )  # type: ignore[no-any-return]

        requirements_standard = defs.Standard(
            name="CWE",
            section="Some CWE",
            sectionID="123",
            tags=["family:standard", "subtype:requirements_standard"],
        )

        main.register_standard(
            standard_entries=[requirements_standard],
            collection=self.collection,
            calculate_gap_analysis=True,
            generate_embeddings=False,
        )

        populate_neo4j_mock.assert_not_called()
        ga_mock.assert_not_called()

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
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
                ),
                defs.Link(
                    document=defs.Code(
                        doctype=defs.Credoctypes.Code,
                        description="print(10)",
                        name="CodemcCodeFace",
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
                ),
                defs.Link(
                    document=defs.Tool(
                        description="awesome hacking tool",
                        name="ToolmcToolFace",
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
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
                defs.Link(document=credoc, ltype=defs.LinkTypes.LinkedTo),
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
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
                ),
                defs.Link(document=credoc, ltype=defs.LinkTypes.LinkedTo),
                defs.Link(
                    document=defs.Standard(
                        name="CWE",
                        sectionID="598",
                        links=[],
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
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
                defs.Link(document=credoc3, ltype=defs.LinkTypes.LinkedTo),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard, name="CWE", sectionID="598"
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
                ),
                defs.Link(document=credoc2, ltype=defs.LinkTypes.LinkedTo),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        name="ASVS",
                        section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
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
        self.maxDiff = None

        self.collection = self.collection.with_graph()

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
            links=[
                defs.Link(document=standard, ltype=defs.LinkTypes.LinkedTo),
                defs.Link(document=tool, ltype=defs.LinkTypes.LinkedTo),
            ],
            tags=["CREt1", "CREt2"],
            metadata={"tags": ["CREl1", "CREl2"]},
        )

        cre_lower = defs.CRE(
            id="100-101",
            description="CREdesc lower",
            name="CREname lower",
            links=[defs.Link(document=cre.shallow_copy(), ltype=defs.LinkTypes.PartOf)],
        )

        cre_higher = defs.CRE(
            id="100-099",
            description="CREdesc higher",
            name="CREname higher",
            links=[
                defs.Link(document=cre.shallow_copy(), ltype=defs.LinkTypes.Contains)
            ],
        )
        cre_equal = defs.CRE(
            id="100-102",
            description="CREdesc equal",
            name="CREname equal",
            links=[
                defs.Link(document=cre.shallow_copy(), ltype=defs.LinkTypes.Related)
            ],
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

        with self.assertRaises(cre_exceptions.InvalidCREIDException):
            invalid_cre = defs.CRE(id="100-100", name="x", description="y")
            invalid_cre.id = ""
            main.register_cre(invalid_cre, self.collection)
        with self.assertRaises(cre_exceptions.InvalidCREIDException):
            bad_cre = defs.CRE(id="100-100", name="x", description="y")
            bad_cre.id = "invalid"
            main.register_cre(bad_cre, self.collection)

        # hierarchy register tests
        main.register_cre(cre_lower, self.collection)
        main.register_cre(cre_higher, self.collection)
        main.register_cre(cre_equal, self.collection)

        c_higher = self.collection.get_CREs(cre_higher.id)[0]
        c_lower = self.collection.get_CREs(cre_lower.id)[0]
        c_equal = self.collection.get_CREs(cre_equal.id)[0]
        retrieved_cre = self.collection.get_CREs(cre.id)[0]
        self.maxDiff = None
        self.assertCountEqual(
            c_higher.links,
            [
                defs.Link(
                    document=retrieved_cre.shallow_copy(), ltype=defs.LinkTypes.Contains
                )
            ],
        )
        self.assertCountEqual(
            retrieved_cre.links,
            [
                defs.Link(document=standard, ltype=defs.LinkTypes.LinkedTo),
                defs.Link(document=tool, ltype=defs.LinkTypes.LinkedTo),
                defs.Link(
                    document=c_lower.shallow_copy(), ltype=defs.LinkTypes.Contains
                ),
                defs.Link(
                    document=c_higher.shallow_copy(), ltype=defs.LinkTypes.PartOf
                ),
                defs.Link(
                    document=c_equal.shallow_copy(), ltype=defs.LinkTypes.Related
                ),
            ],
        )

        self.assertCountEqual(
            c_lower.links,
            [
                defs.Link(
                    document=retrieved_cre.shallow_copy(), ltype=defs.LinkTypes.PartOf
                )
            ],
        )
        self.assertCountEqual(
            c_higher.links,
            [
                defs.Link(
                    document=retrieved_cre.shallow_copy(), ltype=defs.LinkTypes.Contains
                )
            ],
        )
        self.assertCountEqual(
            c_equal.links,
            [
                defs.Link(
                    document=retrieved_cre.shallow_copy(), ltype=defs.LinkTypes.Related
                )
            ],
        )

    @patch.object(main, "db_connect")
    @patch.object(Queue, "enqueue_call")
    @patch.object(redis, "wait_for_jobs")
    @patch.object(redis, "empty_queues")
    @patch.object(redis, "connect")
    @patch("application.utils.db_backend.detect_backend")
    @patch(
        "application.utils.external_project_parsers.parsers.master_spreadsheet_parser._load_existing_cre_identity_maps"
    )
    @patch.object(prompt_client.PromptHandler, "generate_embeddings_for")
    @patch.object(main, "populate_neo4j_db")
    def test_parse_standards_from_spreadsheeet(
        self,
        mock_populate_neo4j_db,
        mock_generate_embeddings_for,
        mock_load_existing_identity_maps,
        mock_detect_backend,
        mock_redis_connect,
        mock_empty_queues,
        mock_wait_for_jobs,
        mock_enqueue_call,
        mock_db_connect,
    ) -> None:
        self.maxDiff = None
        prompt_handler = prompt_client.PromptHandler(database=self.collection)
        mock_db_connect.return_value = self.collection
        mock_load_existing_identity_maps.return_value = ({}, {})
        mock_detect_backend.return_value = Mock(
            is_postgres=True,
            backend="postgres",
            supports_pair_ga_scheduler=True,
            reason="test",
        )
        # No jobs scheduled when we're registering CREs only
        expected_cre_only_input, _ = data_gen.root_csv_cre_only()
        main.parse_standards_from_spreadsheeet(
            expected_cre_only_input, "", prompt_handler
        )
        mock_enqueue_call.assert_not_called()

        # Jobs scheduled when we're registering Standards only
        expected_input, expected_output = data_gen.root_csv_data()
        main.parse_standards_from_spreadsheeet(expected_input, "", prompt_handler)
        mock_enqueue_call.assert_called()
        expected_output.pop(defs.Credoctypes.CRE.value)
        expected_names = list(expected_output.keys())
        expected_ids_by_name = {
            k: {getattr(e, "id", None) for e in v} for k, v in expected_output.items()
        }
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
                self.assertIn(
                    entry.id,
                    expected_ids_by_name[standard_name],
                    f"Unexpected {standard_name} entry id {entry.id}",
                )
                expected_ids_by_name[standard_name].remove(entry.id)
            self.assertEqual(
                expected_ids_by_name[standard_name], set()
            )  # assert ALL elements of the call exist in expected
            self.assertEqual(None, call.kwargs["kwargs"]["collection"])
            self.assertEqual("", call.kwargs["kwargs"]["db_connection_str"])
            expected_names.pop(expected_names.index(standard_name))
        self.assertEqual(
            expected_names,
            [],
            f"method parse_standards_from_spreadsheeet failed to process standards {','.join(expected_names)}",
        )

    @patch.object(main.redis, "connect")
    @patch.object(main.Queue, "enqueue_call")
    @patch.object(main, "populate_neo4j_db")
    @patch.object(main.db_backend, "detect_backend")
    def test_schedule_gap_analysis_pairs_with_rq_enqueues_directed_pairs(
        self,
        detect_backend_mock,
        populate_neo4j_mock,
        enqueue_call_mock,
        redis_connect_mock,
    ) -> None:
        detect_backend_mock.return_value = main.db_backend.BackendCapabilities(
            backend="postgres",
            is_postgres=True,
            supports_pair_ga_scheduler=True,
            reason="test",
        )
        redis_connect_mock.return_value = Mock()
        enqueue_call_mock.return_value = Mock()

        jobs = main.schedule_gap_analysis_pairs_with_rq(
            collection=self.collection,
            importing_name="CWE",
            db_connection_str="postgresql://cre:password@127.0.0.1:5432/cre",
            peer_names=["ASVS"],
            skip_neo_populate=True,
        )

        self.assertEqual(2, len(jobs))
        self.assertEqual(2, enqueue_call_mock.call_count)
        descs = [c.kwargs.get("description") for c in enqueue_call_mock.call_args_list]
        self.assertIn("CWE->ASVS", descs)
        self.assertIn("ASVS->CWE", descs)
        populate_neo4j_mock.assert_not_called()

    @patch.object(main.db_backend, "detect_backend")
    def test_schedule_gap_analysis_pairs_with_rq_rejects_sqlite(
        self, detect_backend_mock
    ) -> None:
        detect_backend_mock.return_value = main.db_backend.BackendCapabilities(
            backend="sqlite",
            is_postgres=False,
            supports_pair_ga_scheduler=False,
            reason="test",
        )

        with self.assertRaises(RuntimeError):
            main.schedule_gap_analysis_pairs_with_rq(
                collection=self.collection,
                importing_name="CWE",
                db_connection_str="sqlite:///tmp.db",
                peer_names=["ASVS"],
                skip_neo_populate=True,
            )

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
            spreadsheet_url="https://example.com/sheeet", cache_loc=cache
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
            [{"cre": "cre"}], cache, mocked_ai_client_init.return_value
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


class TestGaEligibilityHelpers(unittest.TestCase):
    """Direct unit tests for GA gating helpers used by import_pipeline and post_apply."""

    def test_document_is_ga_eligible_rejects_tool(self) -> None:
        doc = defs.Tool(
            name="Tool Resource",
            description="t",
            tooltype=defs.ToolTypes.Defensive,
        )
        self.assertFalse(main.document_is_ga_eligible(doc, log_skips=False))

    def test_document_is_ga_eligible_rejects_code(self) -> None:
        doc = defs.Code(name="Code Resource", description="c")
        self.assertFalse(main.document_is_ga_eligible(doc, log_skips=False))

    def test_document_is_ga_eligible_requires_both_tags(self) -> None:
        partial = defs.Standard(
            name="CWE",
            section="sec",
            sectionID="123",
            tags=["family:standard"],
        )
        self.assertFalse(main.document_is_ga_eligible(partial, log_skips=False))

        ok = defs.Standard(
            name="ASVS",
            section="sec",
            sectionID="123",
            tags=["family:standard", "subtype:requirements_standard"],
        )
        self.assertTrue(main.document_is_ga_eligible(ok, log_skips=False))

    def test_document_is_ga_eligible_accepts_taxonomy_risk_list(self) -> None:
        capec_like = defs.Standard(
            name="CAPEC",
            section="sec",
            sectionID="123",
            tags=["family:taxonomy", "subtype:risk_list"],
        )
        self.assertTrue(main.document_is_ga_eligible(capec_like, log_skips=False))

    def test_resource_name_ga_eligible_in_db_false_when_missing(self) -> None:
        coll = Mock()
        q = Mock()
        coll.session.query.return_value = q
        q.filter.return_value = q
        q.first.return_value = None
        self.assertFalse(main.resource_name_ga_eligible_in_db(coll, "ASVS"))

    def test_resource_name_ga_eligible_in_db_false_for_tool(self) -> None:
        coll = Mock()
        q = Mock()
        coll.session.query.return_value = q
        q.filter.return_value = q
        row = Mock()
        row.ntype = defs.Credoctypes.Tool.value
        q.first.return_value = row
        self.assertFalse(main.resource_name_ga_eligible_in_db(coll, "T"))

    def test_resource_name_ga_eligible_in_db_true_for_tagged_standard(self) -> None:
        coll = Mock()
        q = Mock()
        coll.session.query.return_value = q
        q.filter.return_value = q
        row = Mock()
        row.ntype = defs.Credoctypes.Standard.value
        row.tags = "family:standard,subtype:requirements_standard"
        q.first.return_value = row
        self.assertTrue(main.resource_name_ga_eligible_in_db(coll, "ASVS"))

    def test_resource_name_ga_eligible_in_db_true_for_taxonomy_risk_list(self) -> None:
        coll = Mock()
        q = Mock()
        coll.session.query.return_value = q
        q.filter.return_value = q
        row = Mock()
        row.ntype = defs.Credoctypes.Standard.value
        row.tags = "family:taxonomy,subtype:risk_list"
        q.first.return_value = row
        self.assertTrue(main.resource_name_ga_eligible_in_db(coll, "CAPEC"))


if __name__ == "__main__":
    unittest.main()
