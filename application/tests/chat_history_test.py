import os
import unittest
from unittest import mock

from application.utils.owasp_agent import router as r

HISTORY = [
    {"role": "user", "content": "Does the exchange cover agentic AI?"},
    {
        "role": "assistant",
        "content": "Yes, the AI Exchange covers agentic AI threats and controls.",
    },
]


class NeedsContextTest(unittest.TestCase):
    def test_follow_ups_need_context_full_questions_do_not(self):
        for q in (
            "What are some key risks",
            "and the controls?",
            "Why is that?",
            "tell me more",
            "Does it cover prompt injection in production systems?",
        ):
            self.assertTrue(r.needs_context(q), q)
        for q in (
            "What are the three maturity levels defined by OWASP SAMM for each practice?",
            "Who leads the OWASP Developer Guide project and which companies sponsor it?",
        ):
            self.assertFalse(r.needs_context(q), q)


class StandaloneQuestionTest(unittest.TestCase):
    def test_self_contained_question_ignores_history_and_never_calls_the_model(self):
        llm = mock.Mock()
        q = "What are the three maturity levels defined by OWASP SAMM for each practice?"
        self.assertEqual(r.standalone_question(q, HISTORY, llm), q)
        llm.assert_not_called()

    def test_follow_up_is_rewritten_and_does_not_contain_the_previous_question(self):
        llm = mock.Mock(
            return_value="What are some key risks of agentic AI according to the AI Exchange?"
        )
        out = r.standalone_question("What are some key risks", HISTORY, llm)
        self.assertEqual(
            out, "What are some key risks of agentic AI according to the AI Exchange?"
        )
        self.assertNotIn("Does the exchange cover", out)
        system, user = llm.call_args.args
        self.assertIn("Do not add, repeat or combine", system)
        self.assertIn("Last message: What are some key risks", user)

    def test_model_failure_or_glued_questions_fall_back_to_the_current_message_only(
        self,
    ):
        q = "What are some key risks"
        self.assertEqual(
            r.standalone_question(
                q, HISTORY, mock.Mock(side_effect=RuntimeError("503"))
            ),
            q,
        )
        glued = mock.Mock(
            return_value="Does the exchange cover agentic AI? What are some key risks?"
        )
        self.assertEqual(r.standalone_question(q, HISTORY, glued), q)
        self.assertEqual(
            r.standalone_question(q, HISTORY, mock.Mock(return_value="")), q
        )

    def test_no_history_returns_the_prompt(self):
        self.assertEqual(
            r.standalone_question("What are some key risks", None, mock.Mock()),
            "What are some key risks",
        )

    def test_legacy_concat_mode_is_still_available(self):
        with mock.patch.dict(os.environ, {"OWASP_HISTORY_MODE": "concat"}):
            out = r.standalone_question(
                "Berlin", [{"role": "user", "content": "events near me"}]
            )
        self.assertEqual(out, "events near me\nBerlin")

    def test_effective_prompt_uses_the_standalone_logic(self):
        q = "What are the three maturity levels defined by OWASP SAMM for each practice?"
        self.assertEqual(r._effective_prompt(q, HISTORY), q)


class WebWarmUpTest(unittest.TestCase):
    def test_warm_up_is_opt_in(self):
        from application.utils.comprehension import shared

        app = mock.MagicMock()
        with mock.patch.dict(os.environ, {"OWASP_WARMUP_WEB": ""}):
            self.assertFalse(shared.start_background_warm_up(app))
        started = []
        with mock.patch.dict(os.environ, {"OWASP_WARMUP_WEB": "1"}), mock.patch(
            "threading.Thread"
        ) as thread, mock.patch.object(shared, "warm_up"):
            thread.side_effect = (
                lambda target=None, **k: started.append(target) or mock.Mock()
            )
            self.assertTrue(shared.start_background_warm_up(app))
        self.assertEqual(len(started), 1)


class ChatHandlerIsLazyTest(unittest.TestCase):
    def test_agent_answers_do_not_build_the_cre_retrieval_handler(self):
        from application import create_app, sqla

        env = {
            "NO_LOGIN": "1",
            "NO_LOAD_GRAPH_DB": "1",
            "OWASP_AGENT_ENABLED": "1",
            "INSECURE_REQUESTS": "1",
        }
        with mock.patch.dict(os.environ, env):
            app = create_app(mode="test")
            with app.app_context():
                sqla.create_all()
                resp = {
                    "response": "Answer: x",
                    "accurate": True,
                    "owasp_agent": {"ok": True, "citations": []},
                }
                with mock.patch(
                    "application.utils.owasp_agent.service.route_question",
                    return_value=resp,
                ), mock.patch(
                    "application.prompt_client.prompt_client.PromptHandler"
                ) as handler:
                    out = app.test_client().post(
                        "/rest/v1/completion", json={"prompt": "Who leads SAMM?"}
                    )
                sqla.session.remove()
                sqla.drop_all()
        self.assertEqual(out.status_code, 200)
        handler.assert_not_called()


class TestCleanAnswerText(unittest.TestCase):
    def test_links_and_double_brackets_become_plain_markers(self):
        from application.utils.comprehension.synthesize import clean_answer_text

        raw = (
            "Owners attend [[7]](https://github.com/OWASP/x/blob/HEAD/a.md) and "
            "[8](https://github.com/OWASP/x/blob/HEAD/b.md). See [the playbook](https://x.org/p) "
            "or https://github.com/OWASP/y ."
        )
        out = clean_answer_text(raw)
        self.assertNotIn("http", out)
        self.assertIn("[7]", out)
        self.assertNotIn("[[7]]", out)
        self.assertIn("[8].", out)
        self.assertIn("See the playbook", out)

    def test_urls_containing_spaces_are_removed_too(self):
        from application.utils.comprehension.synthesize import clean_answer_text

        raw = (
            "Include owners [[7]](https://github.com/OWASP/t/blob/HEAD/playbook/4. Train your "
            "people to threat model.md) and testers [[8]](https://github.com/OWASP/t/a b.md)."
        )
        self.assertEqual(clean_answer_text(raw), "Include owners [7] and testers [8].")

    def test_plain_markers_are_untouched(self):
        from application.utils.comprehension.synthesize import clean_answer_text

        self.assertEqual(
            clean_answer_text("SAMM has 3 levels [1][2]."), "SAMM has 3 levels [1][2]."
        )


class TestCompoundClausesKeepTheirSubject(unittest.TestCase):
    def test_later_clauses_get_earlier_clauses_as_background(self):
        seen = []

        class Probe(r.OwaspAgentRouter):
            def __init__(self):  # no store needed for this probe
                pass

            def handle(self, prompt, history=None, _clause=False):
                seen.append((prompt, history))
                return {"response": f"Answer: {prompt}", "accurate": True}

        out = Probe()._handle_compound(
            ["Who runs the PwnzzAI training", "how long is it"], None
        )
        self.assertEqual(seen[0], ("Who runs the PwnzzAI training", None))
        self.assertEqual(
            seen[1],
            (
                "how long is it",
                [{"role": "user", "content": "Who runs the PwnzzAI training"}],
            ),
        )
        self.assertIn("how long is it", out["response"])
