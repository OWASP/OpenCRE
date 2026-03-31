import json
import logging
import unittest
from io import StringIO
from unittest.mock import patch

from application.utils.logging_config import JSONFormatter, configure_logging


class TestJSONFormatter(unittest.TestCase):
    def _make_record(self, msg="hello", level=logging.INFO, name="test"):
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_output_is_valid_json(self):
        formatter = JSONFormatter()
        record = self._make_record()
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertIsInstance(parsed, dict)

    def test_required_fields_present(self):
        formatter = JSONFormatter()
        record = self._make_record(msg="test message", name="mylogger")
        parsed = json.loads(formatter.format(record))
        self.assertIn("timestamp", parsed)
        self.assertIn("level", parsed)
        self.assertIn("logger", parsed)
        self.assertIn("message", parsed)

    def test_message_and_level_values(self):
        formatter = JSONFormatter()
        record = self._make_record(msg="check value", level=logging.WARNING, name="mod")
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["message"], "check value")
        self.assertEqual(parsed["level"], "WARNING")
        self.assertEqual(parsed["logger"], "mod")

    def test_exception_included_when_present(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error",
            args=(),
            exc_info=exc_info,
        )
        parsed = json.loads(formatter.format(record))
        self.assertIn("exception", parsed)
        self.assertIn("ValueError", parsed["exception"])


class TestConfigureLogging(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        root.handlers.clear()

    def test_default_level_is_info(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            os.environ.pop("LOG_FORMAT", None)
            configure_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_log_level_env_respected(self):
        with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
            configure_logging()
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_text_format_uses_standard_formatter(self):
        with patch.dict("os.environ", {"LOG_FORMAT": "text"}):
            configure_logging()
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertNotIsInstance(root.handlers[0].formatter, JSONFormatter)

    def test_json_format_uses_json_formatter(self):
        with patch.dict("os.environ", {"LOG_FORMAT": "json"}):
            configure_logging()
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertIsInstance(root.handlers[0].formatter, JSONFormatter)

    def test_repeated_calls_do_not_add_handlers(self):
        configure_logging()
        configure_logging()
        self.assertEqual(len(logging.getLogger().handlers), 1)

    def test_json_output_is_parseable(self):
        stream = StringIO()
        with patch.dict("os.environ", {"LOG_FORMAT": "json"}):
            configure_logging()
        root = logging.getLogger()
        root.handlers[0].stream = stream
        logging.getLogger("test.json").info("structured message")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["message"], "structured message")
        self.assertEqual(parsed["level"], "INFO")


import os

if __name__ == "__main__":
    unittest.main()
