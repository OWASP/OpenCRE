import copy
import unittest
from dataclasses import asdict
from pprint import pprint
from typing import Set

import dacite
from application.defs import cre_defs as defs
from dacite import Config, from_dict


class TestMiscToolsParser(unittest.TestCase):
    def test_document_todict(self) -> None:
        pass
