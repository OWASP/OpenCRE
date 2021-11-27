from pprint import pprint
import unittest
import yaml
from application.defs import osib_defs as defs
import tempfile
import os


class TestCreDefs(unittest.TestCase):
    def setUp(self) -> None:
        self.yaml_file = open(
            f"{os.path.dirname(os.path.abspath(__file__))}/data/osib_example.yml"
        ).read()
        ymldesc, self.location = tempfile.mkstemp(suffix=".yaml", text=True)
        with os.fdopen(ymldesc, "wb") as yd:
            yd.write(bytes(self.yaml_file, "utf-8"))

    def tearDown(self) -> None:
        os.unlink(self.location)

    def test_from_yml_to_classes(self) -> None:
        datad = defs.read_osib_yaml(self.location)
        osib = defs.try_from_file(datad)
        self.assertDictEqual(yaml.safe_load(self.yaml_file), osib[0].to_dict())


if __name__ == "__main__":
    unittest.main()
