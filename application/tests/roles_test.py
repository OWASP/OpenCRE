import os
import unittest
from unittest import mock

from application.utils import roles


def env(**kw):
    base = {
        "ADMIN_EMAILS": "",
        "LOGIN_ALLOWED_EMAILS": "",
        "LOGIN_ALLOWED_DOMAINS": "",
        "FLASK_CONFIG": "",
    }
    base.update(kw)
    return mock.patch.dict(os.environ, base)


class RolesTest(unittest.TestCase):
    def test_roles_model(self):
        with env(
            ADMIN_EMAILS="Boss@owasp.org, ops@example.com",
            LOGIN_ALLOWED_DOMAINS="owasp.org",
        ):
            self.assertEqual(roles.role_for("boss@owasp.org"), roles.ADMIN)
            self.assertEqual(
                roles.role_for("ops@example.com"), roles.ADMIN
            )  # named admin outside the domain
            self.assertEqual(roles.role_for("anyone@owasp.org"), roles.USER)
            self.assertIsNone(roles.role_for("x@gmail.com"))
            self.assertIsNone(
                roles.role_for("x@evilowasp.org")
            )  # suffix tricks do not match
            self.assertIsNone(roles.role_for(""))
            self.assertTrue(roles.has_role("anyone@owasp.org", roles.USER))
            self.assertFalse(roles.has_role("anyone@owasp.org", roles.ADMIN))
            self.assertTrue(roles.has_role("boss@owasp.org", roles.USER))

    def test_subdomain_and_star_domains(self):
        with env(ADMIN_EMAILS="a@x.org", LOGIN_ALLOWED_DOMAINS="@owasp.org"):
            self.assertEqual(roles.role_for("u@chapters.owasp.org"), roles.USER)
        with env(ADMIN_EMAILS="a@x.org", LOGIN_ALLOWED_DOMAINS="*"):
            self.assertEqual(roles.role_for("u@anything.io"), roles.USER)

    def test_no_domain_configured_fails_closed(self):
        with env(ADMIN_EMAILS="a@x.org"):
            self.assertIsNone(roles.role_for("u@owasp.org"))
            self.assertEqual(roles.role_for("a@x.org"), roles.ADMIN)

    def test_legacy_mode_keeps_the_old_allowlist(self):
        with env(LOGIN_ALLOWED_EMAILS="a@x.org", LOGIN_ALLOWED_DOMAINS="owasp.org"):
            self.assertFalse(roles.roles_enabled())
            self.assertEqual(roles.role_for("a@x.org"), roles.ADMIN)
            self.assertIsNone(roles.role_for("u@owasp.org"))
        with env(FLASK_CONFIG="production"):
            self.assertIsNone(roles.role_for("a@x.org"))
        with env():
            self.assertEqual(
                roles.role_for("a@x.org"), roles.ADMIN
            )  # dev convenience as before


class McpToolRolesTest(unittest.TestCase):
    def test_tool_roles(self):
        from application.mcp import remote_auth as ra

        cre = frozenset({"list_standards"})
        self.assertEqual(ra.min_role_for_tool("ask", cre), roles.USER)
        self.assertEqual(ra.min_role_for_tool("rate_answer", cre), roles.USER)
        self.assertEqual(
            ra.min_role_for_tool("owasp_meta_sources_search", cre), roles.USER
        )
        self.assertIsNone(
            ra.min_role_for_tool("list_standards", cre)
        )  # public CRE read tool
        self.assertEqual(
            ra.min_role_for_tool("some_future_tool", cre), roles.ADMIN
        )  # deny by default
        with mock.patch.object(ra, "ADMIN_ONLY_TOOLS", frozenset({"ask"})):
            self.assertEqual(ra.min_role_for_tool("ask", cre), roles.ADMIN)
