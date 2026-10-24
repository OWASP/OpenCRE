from cre_logging import get_logger

logger = get_logger(__name__)

import argparse
import unittest
from typing import Any
from unittest.mock import patch

from application.cmd import cre_main
from application.utils.external_project_parsers.base_parser import BaseParser
from application.utils.external_project_parsers.parsers import (
    agent_evidence_vocabulary,
)


class OnlyFlagsGiven(argparse.Namespace):
    """Answer False for every flag the test does not set."""

    def __getattr__(self, name: str) -> Any:
        return False


class TestAgentEvidenceVocabularyCli(unittest.TestCase):
    @patch.object(BaseParser, "register_resource")
    def test_flag_registers_the_parser(self, register_resource) -> None:
        cre_main.run(
            OnlyFlagsGiven(agent_evidence_vocabulary_in=True, cache_file="cache.sqlite")
        )
        register_resource.assert_called_once_with(
            agent_evidence_vocabulary.AgentEvidenceVocabulary,
            db_connection_str="cache.sqlite",
        )

    @patch.object(BaseParser, "register_resource")
    def test_parser_does_not_run_without_the_flag(self, register_resource) -> None:
        cre_main.run(OnlyFlagsGiven(cache_file="cache.sqlite"))
        register_resource.assert_not_called()
