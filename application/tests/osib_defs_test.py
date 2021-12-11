from pprint import pprint
import unittest
import yaml
from application.defs import osib_defs as defs
from application.defs import cre_defs as cdefs
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

    def test_osib2cre(self) -> None:
        data = defs.try_from_file(defs.read_osib_yaml(self.location))
        data[0].children["OWASP"].children.pop("ASVS")
        top10 = []
        top10_hyperlinks = [
            "https://owasp.org/Top10/A01_2021-Broken_Access_Control",
            "https://owasp.org/Top10/A02_2021-Cryptographic_Failures",
            "https://owasp.org/Top10/A03_2021-Injection",
            "https://owasp.org/Top10/A04_2021-Insecure_Design",
            "https://owasp.org/Top10/A05_2021-Security_Misconfiguration",
            "https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components",
            "https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures",
            "https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures",
            "https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures",
            "https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29",
            "https://owasp.org/Top10/A11_2021-Next_Steps",
        ]
        for i in range(1,11):
            top10.append(
                cdefs.Standard(
                    name="top10",
                    links=[
                        cdefs.Link(
                            ltype=cdefs.LinkTypes.PartOf,
                            document=cdefs.Standard(name="top10", section="202110"),
                        )
                    ],
                    metadata={"source_id": f"A{'{:02}'.format(i)}:2021"},
                    section=f"202110.{i}",
                    subsection="",
                    hyperlink=top10_hyperlinks[i-1],
                )
            )
        expected = ([], top10)
        cre_arr = defs.osib2cre(data[0])
        for x,y in zip(expected[1],cre_arr[1]):
            self.assertEquals(x,y)


if __name__ == "__main__":
    unittest.main()
