"""Markdown importers must read UTF-8 even with a Windows default code page."""

import builtins
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, IO
from unittest.mock import Mock, patch

from application.utils.external_project_parsers.parsers import (
    cheatsheets_parser,
    misc_tools_parser,
    zap_alerts_parser,
)

_open = builtins.open


def windows_default_open(
    path: str | os.PathLike[str], mode: str = "r", *, encoding: str | None = None
) -> IO[Any]:
    return _open(path, mode, encoding=encoding or "cp1252")


class TestMarkdownParserEncoding(unittest.TestCase):
    def test_cheatsheet_reads_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cheatsheets"
            source.mkdir()
            (source / "Example.md").write_text(
                "# Testing Cheat Sheet\nA curly quote: ”\n"
                "https://www.opencre.org/cre/123-456\n",
                encoding="utf-8",
            )
            repo = SimpleNamespace(working_dir=directory)
            cache = Mock()
            cache.get_CREs.return_value = []
            with patch.object(
                cheatsheets_parser, "open", windows_default_open, create=True
            ):
                entries = cheatsheets_parser.Cheatsheets().register_cheatsheets(
                    cache, repo, "cheatsheets", "unused"
                )
            self.assertEqual(["Testing Cheat Sheet"], [e.section for e in entries])

    def test_zap_alert_reads_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / zap_alerts_parser.ZAP.alerts_path
            source.mkdir(parents=True)
            (source / "12345.md").write_text(
                'title: "UTF-8 Alert"\n'
                "alertid: 12345\n"
                'alerttype: "Passive"\n'
                'solution: "Check the header”"\n'
                "code: https://example.org/rule\n",
                encoding="utf-8",
            )
            cache = Mock()
            with patch.object(
                zap_alerts_parser.git,
                "clone",
                return_value=SimpleNamespace(working_dir=directory),
            ):
                with patch.object(
                    zap_alerts_parser, "open", windows_default_open, create=True
                ):
                    entries = zap_alerts_parser.ZAP().parse(cache=cache, ph=Mock())
            self.assertEqual(
                ["UTF-8 Alert"], [e.section for e in entries.results["ZAP Rule"]]  # type: ignore[attr-defined]
            )

    def test_misc_tool_reads_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "README.md").write_text(
                "# Example Tool\nA curly quote: ”\n"
                "[CRE](https://www.opencre.org/cre/123-456?register=true"
                "&type=tool&tool_type=training&description=Example)\n",
                encoding="utf-8",
            )
            cache = Mock()
            cache.get_CREs.return_value = []
            with patch.object(
                misc_tools_parser.git,
                "clone",
                return_value=SimpleNamespace(working_dir=directory),
            ):
                with patch.object(
                    misc_tools_parser, "open", windows_default_open, create=True
                ):
                    entries = misc_tools_parser.MiscTools().parse_tool(
                        "https://example.org/tool.git", cache
                    )
            self.assertEqual(["Example Tool"], [e.name for e in entries])
