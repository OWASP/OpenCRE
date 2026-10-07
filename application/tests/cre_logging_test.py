"""Tests for the standalone ``cre_logging`` package.

These tests import ``cre_logging`` only — not ``application`` / Flask —
except the subprocess isolation check which uses a fresh interpreter.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from cre_logging import JSONFormatter, configure_logging, get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestJSONFormatter(unittest.TestCase):
    def test_emits_caller_module_file_and_method(self) -> None:
        stream = StringIO()
        probe = logging.getLogger("cre_logging.test.caller")
        probe.handlers.clear()
        probe.setLevel(logging.DEBUG)
        probe.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        probe.addHandler(handler)

        def sample_method() -> None:
            probe.info("hello from sample_method")

        sample_method()
        parsed = json.loads(stream.getvalue().strip())
        self.assertEqual(parsed["message"], "hello from sample_method")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["method"], "sample_method")
        self.assertEqual(parsed["module"], "cre_logging_test")
        self.assertEqual(parsed["file"], "application/tests/cre_logging_test.py")
        self.assertIn("timestamp", parsed)
        self.assertIn("line", parsed)
        probe.handlers.clear()

    def test_debug_and_error_levels(self) -> None:
        stream = StringIO()
        probe = logging.getLogger("cre_logging.test.levels")
        probe.handlers.clear()
        probe.setLevel(logging.DEBUG)
        probe.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        probe.addHandler(handler)
        probe.debug("dbg")
        probe.error("err")
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        self.assertEqual([row["level"] for row in lines], ["DEBUG", "ERROR"])
        probe.handlers.clear()

    def test_exception_field(self) -> None:
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=exc_info,
        )
        parsed = json.loads(formatter.format(record))
        self.assertIn("ValueError", parsed["exception"])
        self.assertIn("boom", parsed["exception"])

    def test_extra_fields_are_merged(self) -> None:
        stream = StringIO()
        probe = logging.getLogger("cre_logging.test.extra")
        probe.handlers.clear()
        probe.setLevel(logging.INFO)
        probe.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        probe.addHandler(handler)
        probe.info("linked", extra={"cre_id": "123-456"})
        parsed = json.loads(stream.getvalue().strip())
        self.assertEqual(parsed["cre_id"], "123-456")
        probe.handlers.clear()


class TestConfigureLogging(unittest.TestCase):
    def test_log_level_env(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            configure_logging(force=True)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            configure_logging(force=True)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_repeated_configure_does_not_stack_handlers(self) -> None:
        configure_logging(force=True)
        before = [
            h
            for h in logging.getLogger().handlers
            if getattr(h, "name", "") == "cre-json"
        ]
        configure_logging()
        after = [
            h
            for h in logging.getLogger().handlers
            if getattr(h, "name", "") == "cre-json"
        ]
        self.assertEqual(len(before), 1)
        self.assertEqual(len(after), 1)

    def test_get_logger_writes_json_to_stderr(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}):
            configure_logging(force=True)
        buf = StringIO()
        with contextlib.redirect_stderr(buf):
            get_logger("cre_logging.test.emit").warning("structured line")
        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(parsed["message"], "structured line")
        self.assertEqual(parsed["level"], "WARNING")
        self.assertEqual(parsed["logger"], "cre_logging.test.emit")
        logger.debug("example from test method")


class TestStandaloneImport(unittest.TestCase):
    def test_importing_cre_logging_does_not_import_application_or_flask(self) -> None:
        code = (
            "import sys\n"
            "import cre_logging\n"
            "assert 'flask' not in sys.modules, sorted(sys.modules)[:20]\n"
            "assert 'application' not in sys.modules\n"
            "assert 'application.__init__' not in sys.modules\n"
            "cre_logging.get_logger('probe').debug('ok')\n"
        )
        subprocess.check_call(
            [sys.executable, "-c", code],
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
