"""Durable OIE_GRAPH_FILING_ENABLED in admin_runtime_setting."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from application import create_app, sqla
from application.utils.admin_panel import runtime_settings


class TestAdminRuntimeSettings(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, {"NO_LOAD_GRAPH_DB": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ.pop(runtime_settings.FILING_KEY, None)

    def tearDown(self) -> None:
        os.environ.pop(runtime_settings.FILING_KEY, None)
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_set_and_read_filing(self) -> None:
        self.assertFalse(runtime_settings.filing_enabled())
        runtime_settings.set_setting(
            runtime_settings.FILING_KEY, "1", actor="tester@example.com"
        )
        self.assertEqual(os.environ.get(runtime_settings.FILING_KEY), "1")
        self.assertTrue(runtime_settings.filing_enabled())
        # Env wins over DB when set.
        os.environ[runtime_settings.FILING_KEY] = "0"
        self.assertFalse(runtime_settings.filing_enabled())


if __name__ == "__main__":
    unittest.main()
