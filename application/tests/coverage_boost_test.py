import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from application.defs import cre_defs
from application.prompt_client import prompt_client
from application.utils import gap_analysis, git as git_utils, redis as redis_utils


class TestGitUtilsCoverage(unittest.TestCase):
    @patch("application.utils.git.git.Repo")
    @patch("application.utils.git.git.Git")
    def test_create_branch(self, git_mock, repo_mock):
        repo = MagicMock()
        repo.active_branch.name = "main"
        repo_mock.return_value = repo
        git_inst = MagicMock()
        git_mock.return_value = git_inst

        git_utils.create_branch("feature/test")

        git_inst.checkout.assert_any_call("-b", "feature/test")
        git_inst.checkout.assert_any_call("main")

    @patch("application.utils.git.createPullRequest")
    @patch("application.utils.git.git.Repo")
    @patch("application.utils.git.git.Git")
    def test_add_to_github_success(self, git_mock, repo_mock, pr_mock):
        repo = MagicMock()
        repo.active_branch.name = "main"
        repo.remotes.origin.urls = ["git@github.com:acme/opencre.git"]
        repo_mock.return_value = repo
        git_inst = MagicMock()
        git_mock.return_value = git_inst

        git_utils.add_to_github("application", "alias", "api-key")

        repo.remotes.origin.push.assert_called_once()
        pr_mock.assert_called_once()
        git_inst.checkout.assert_any_call("main")

    @patch("application.utils.git.git.Repo")
    @patch("application.utils.git.git.Git")
    def test_add_to_github_git_error(self, git_mock, repo_mock):
        repo = MagicMock()
        repo.active_branch.name = "main"
        repo_mock.return_value = repo
        git_inst = MagicMock()
        git_inst.commit.side_effect = git_utils.git.exc.GitCommandError(
            "commit", 1, b"", b""
        )
        git_mock.return_value = git_inst

        git_utils.add_to_github("application", "alias", "api-key")
        git_inst.checkout.assert_any_call("main")

    @patch("application.utils.git.Repo.clone_from")
    @patch("application.utils.git.git.Git")
    def test_clone_with_dest(self, git_mock, clone_mock):
        git_inst = MagicMock()
        ctx = MagicMock()
        git_inst.custom_environment.return_value = ctx
        git_mock.return_value = git_inst
        clone_mock.return_value = "repo"

        repo = git_utils.clone("https://example.com/repo.git", "/tmp/repo")

        self.assertEqual(repo, "repo")
        clone_mock.assert_called_once()


class TestRedisUtilsCoverage(unittest.TestCase):
    def test_empty_queues(self):
        redis_client = MagicMock()
        redis_client.scan_iter.return_value = [b"a", b"b", b"c"]
        redis_utils.empty_queues(redis_client)
        self.assertEqual(redis_client.delete.call_count, 3)

    @patch("application.utils.redis.redis.StrictRedis")
    def test_connect_host_port(self, strict_mock):
        with patch.dict(
            os.environ,
            {
                "REDIS_HOST": "localhost",
                "REDIS_PORT": "6379",
                "REDIS_PASSWORD": "pw",
                "REDIS_NO_SSL": "1",
            },
            clear=True,
        ):
            redis_utils.connect()
        strict_mock.assert_called_once()

    @patch("application.utils.redis.redis.from_url")
    def test_connect_default_url(self, from_url_mock):
        with patch.dict(os.environ, {}, clear=True):
            redis_utils.connect()
        from_url_mock.assert_called_once_with("redis://localhost:6379")

    @patch("application.utils.redis.redis.Redis")
    def test_connect_custom_url(self, redis_mock):
        with patch.dict(
            os.environ,
            {"REDIS_URL": "redis://u:p@redis.example.com:6380"},
            clear=True,
        ):
            redis_utils.connect()
        redis_mock.assert_called_once()

    @patch("application.utils.redis.time.sleep", return_value=None)
    def test_wait_for_jobs_terminal_states(self, _sleep_mock):
        callback = MagicMock()
        jobs = []
        for status in ["finished", "failed", "canceled", "stopped"]:
            job = MagicMock()
            job.description = status
            job.is_finished = status == "finished"
            job.is_failed = status == "failed"
            job.is_canceled = status == "canceled"
            job.is_stopped = status == "stopped"
            job.is_queued = False
            job.is_started = False
            jobs.append(job)

        redis_utils.wait_for_jobs(jobs, callback=callback)
        self.assertEqual(callback.call_count, 4)
        self.assertEqual(jobs, [])

    @patch("application.utils.redis.time.sleep")
    def test_wait_for_jobs_queued_and_started(self, sleep_mock):
        class JobState:
            def __init__(self, status: str):
                self.status = status
                self.description = status

            @property
            def is_finished(self):
                return self.status == "finished"

            @property
            def is_failed(self):
                return self.status == "failed"

            @property
            def is_canceled(self):
                return self.status == "canceled"

            @property
            def is_stopped(self):
                return self.status == "stopped"

            @property
            def is_queued(self):
                return self.status == "queued"

            @property
            def is_started(self):
                return self.status == "started"

            def get_status(self):
                return self.status

        queued = JobState("queued")
        started = JobState("started")
        unknown = JobState("unknown")
        jobs = [queued, started, unknown]

        def advance(_):
            for j in jobs:
                j.status = "finished"

        sleep_mock.side_effect = advance
        redis_utils.wait_for_jobs(jobs, callback=None)
        self.assertEqual(jobs, [])


class TestGapAnalysisCoverage(unittest.TestCase):
    def test_key_and_path_helpers(self):
        self.assertEqual(gap_analysis.make_resources_key(["A", "B"]), "A >> B")
        self.assertEqual(
            gap_analysis.make_subresources_key(["A", "B"], "k"), "A >> B->k"
        )

        a = SimpleNamespace(id="a")
        b = SimpleNamespace(id="b")
        c = SimpleNamespace(id="c")
        path = {
            "start": a,
            "path": [
                {"start": a, "end": b, "relationship": "LINKED_TO"},
                {"start": b, "end": c, "relationship": "CONTAINS"},
            ],
        }
        score = gap_analysis.get_path_score(path)
        self.assertEqual(score, 2)
        self.assertEqual(
            gap_analysis.get_relation_direction(path["path"][1], "b"), "UP"
        )
        self.assertEqual(gap_analysis.get_next_id(path["path"][1], "b"), "c")

    def test_all_requested_standards_exist(self):
        db_obj = MagicMock()
        db_obj.standards.return_value = ["A", "B"]
        self.assertTrue(gap_analysis._all_requested_standards_exist([], db_obj))
        self.assertTrue(gap_analysis._all_requested_standards_exist(["A"], db_obj))
        self.assertFalse(gap_analysis._all_requested_standards_exist(["Z"], db_obj))

        db_obj.standards.return_value = MagicMock()
        self.assertTrue(gap_analysis._all_requested_standards_exist(["A"], db_obj))

        db_obj.standards.side_effect = RuntimeError("boom")
        self.assertTrue(gap_analysis._all_requested_standards_exist(["A"], db_obj))

    @patch("application.utils.gap_analysis.redis.connect")
    def test_schedule_redis_missing(self, connect_mock):
        connect_mock.return_value = None
        database = MagicMock()
        database.gap_analysis_exists.return_value = False
        result = gap_analysis.schedule(["A", "B"], database)
        self.assertIn("error", result)

    @patch("application.utils.gap_analysis.redis.connect")
    def test_schedule_cached_db(self, connect_mock):
        connect_mock.return_value = MagicMock()
        database = MagicMock()
        database.gap_analysis_exists.return_value = True
        database.get_gap_analysis_result.return_value = '{"result":"ok"}'
        result = gap_analysis.schedule(["A", "B"], database)
        self.assertEqual(result.get("result"), "ok")

    @patch("application.utils.gap_analysis.job.Job.fetch")
    @patch("application.utils.gap_analysis.redis.connect")
    def test_schedule_cached_job_id(self, connect_mock, fetch_mock):
        conn = MagicMock()
        conn.get.return_value = '{"job_id":"abc"}'
        connect_mock.return_value = conn
        res = MagicMock()
        res.get_status.return_value = gap_analysis.job.JobStatus.STARTED
        fetch_mock.return_value = res
        database = MagicMock()
        database.gap_analysis_exists.return_value = False
        result = gap_analysis.schedule(["A", "B"], database)
        self.assertEqual(result, {"job_id": "abc"})

    @patch("application.utils.gap_analysis.Queue.enqueue_call")
    @patch("application.utils.gap_analysis.redis.connect")
    def test_schedule_enqueue(self, connect_mock, enqueue_mock):
        conn = MagicMock()
        conn.get.return_value = None
        connect_mock.return_value = conn
        enqueue_mock.return_value = SimpleNamespace(id="job-1")
        database = MagicMock()
        database.gap_analysis_exists.return_value = False
        database.neo_db = object()
        result = gap_analysis.schedule(["A", "B"], database)
        self.assertEqual(result, {"job_id": "job-1"})
        conn.set.assert_called_once()

    @patch("application.utils.gap_analysis.time.sleep", return_value=None)
    @patch("application.utils.gap_analysis.requests.get")
    def test_preload(self, get_mock, _sleep_mock):
        standards_response = MagicMock()
        standards_response.json.return_value = ["A", "B"]

        map_response = MagicMock()
        map_response.status_code = 200
        map_response.json.return_value = {"result": "ok"}

        get_mock.side_effect = [standards_response, map_response, map_response]
        gap_analysis.preload("http://localhost")


class TestPromptClientCoverage(unittest.TestCase):
    def test_is_valid_url(self):
        self.assertTrue(prompt_client.is_valid_url("https://example.com"))
        self.assertFalse(prompt_client.is_valid_url("ftp://example.com"))

    @patch("application.prompt_client.prompt_client.word_tokenize")
    def test_clean_content(self, tokenize_mock):
        tokenize_mock.return_value = ["HELLO", "World"]
        emb = prompt_client.in_memory_embeddings.instance()
        self.assertEqual(emb.clean_content("  hello world  "), "hello world")

    def test_generate_embeddings_requires_ai(self):
        emb = prompt_client.in_memory_embeddings.instance()
        emb.ai_client = None
        with self.assertRaises(RuntimeError):
            emb.generate_embeddings(MagicMock(), ["id1"])

    @patch("application.prompt_client.prompt_client.db.dbNodeFromNode")
    def test_generate_embeddings_node_path(self, db_node_from_node_mock):
        emb = prompt_client.in_memory_embeddings.instance()
        emb.ai_client = MagicMock()
        emb.ai_client.get_text_embeddings.return_value = [0.1, 0.2]
        emb.get_content = MagicMock(return_value="Some text")
        emb.clean_content = MagicMock(return_value="some text")
        db_node_from_node_mock.return_value = SimpleNamespace(id=None)

        database = MagicMock()
        node = cre_defs.Standard(
            name="ASVS", section="A", sectionID="1", hyperlink="https://x"
        )
        database.get_cre_by_db_id.return_value = None
        database.get_nodes.return_value = [node]
        emb.generate_embeddings(database, ["db-id"])
        database.add_embedding.assert_called_once()

    @patch("application.prompt_client.prompt_client.db.dbCREfromCRE")
    def test_generate_embeddings_cre_path(self, db_cre_from_cre_mock):
        emb = prompt_client.in_memory_embeddings.instance()
        emb.ai_client = MagicMock()
        emb.ai_client.get_text_embeddings.return_value = [0.1, 0.2]
        db_cre_from_cre_mock.return_value = SimpleNamespace(id=None)

        database = MagicMock()
        cre = cre_defs.CRE(id="123-123", name="C", description="d")
        database.get_cre_by_db_id.return_value = cre
        database.get_nodes.return_value = []
        emb.generate_embeddings(database, ["db-id"])
        database.add_embedding.assert_called_once()

    @patch(
        "application.prompt_client.prompt_client.openai_prompt_client.OpenAIPromptClient"
    )
    def test_prompt_handler_get_text_embeddings(self, openai_mock):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=False):
            database = MagicMock()
            openai_inst = MagicMock()
            openai_inst.get_text_embeddings.return_value = [1.0]
            openai_mock.return_value = openai_inst
            handler = prompt_client.PromptHandler(database)
            self.assertEqual(handler.get_text_embeddings("hello"), [1.0])

    def test_prompt_handler_get_text_embeddings_without_ai(self):
        with patch.dict(os.environ, {}, clear=True):
            handler = prompt_client.PromptHandler(MagicMock())
            handler.ai_client = None
            with self.assertRaises(ValueError):
                handler.get_text_embeddings("hello")

    def test_generate_text_no_prompt_or_ai(self):
        with patch.dict(os.environ, {}, clear=True):
            handler = prompt_client.PromptHandler(MagicMock())
            self.assertEqual(handler.generate_text("").get("response"), "")
            handler.ai_client = None
            result = handler.generate_text("hello")
            self.assertEqual(result.get("response"), "")

    def test_generate_text_with_closest_object(self):
        with patch.dict(os.environ, {}, clear=True):
            database = MagicMock()
            handler = prompt_client.PromptHandler(database)
            ai = MagicMock()
            ai.get_text_embeddings.return_value = [0.1]
            ai.create_chat_completion.return_value = "answer"
            ai.get_model_name.return_value = "model-x"
            handler.ai_client = ai
            handler.get_id_of_most_similar_node_paginated = MagicMock(
                return_value=("node-1", 0.9)
            )
            node = cre_defs.Standard(name="ASVS", section="A", sectionID="1")
            database.get_nodes.return_value = [node]
            database.get_embedding.return_value = [
                SimpleNamespace(embeddings_content="cached")
            ]
            result = handler.generate_text("prompt")
            self.assertTrue(result.get("accurate"))
            self.assertEqual(result.get("model_name"), "model-x")

    def test_generate_text_without_match(self):
        with patch.dict(os.environ, {}, clear=True):
            database = MagicMock()
            handler = prompt_client.PromptHandler(database)
            ai = MagicMock()
            ai.get_text_embeddings.return_value = [0.1]
            ai.query_llm.return_value = "fallback"
            ai.get_model_name.return_value = "model-y"
            handler.ai_client = ai
            handler.get_id_of_most_similar_node_paginated = MagicMock(
                return_value=(None, None)
            )
            result = handler.generate_text("prompt")
            self.assertFalse(result.get("accurate"))
            self.assertEqual(result.get("model_name"), "model-y")


if __name__ == "__main__":
    unittest.main()
