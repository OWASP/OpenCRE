import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DUMP = str(Path(__file__).parent / "data" / "nest" / "projects_dump.json")


def load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "nest_people_file.py"
    spec = importlib.util.spec_from_file_location("nest_people_file", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NestPeopleFileTest(unittest.TestCase):
    def test_offline_dump_is_deduped_sorted_one_per_line(self):
        script = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "leaders.txt")
            self.assertEqual(script.main(["--from-json", DUMP, "--out", out]), 0)
            text = Path(out).read_text(encoding="utf-8")
        self.assertEqual(text, "Carlos Ruiz\nJane Doe\nÅsa Berg\n")

    def test_live_mode_needs_key_and_never_calls_network_without_it(self):
        script = load_script()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "requests.get"
        ) as get:
            self.assertEqual(script.main([]), 2)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
