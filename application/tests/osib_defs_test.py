import os
import tempfile
import unittest
from pprint import pprint

import yaml
from application.defs import cre_defs as cdefs
from application.defs import osib_defs as defs
from networkx import networkx as nx
from networkx.algorithms.simple_paths import all_simple_paths


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
        for i in range(1, 11):
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
                    hyperlink=top10_hyperlinks[i - 1],
                )
            )
        expected = ([], top10)
        cre_arr = defs.osib2cre(data[0])
        for x, y in zip(expected[1], cre_arr[1]):
            self.assertEquals(x, y)

    @unittest.skip("tmp")
    def test_cre2osib(self) -> None:
        defs.cre2osib([])

    # def test_update_paths(self)->None:
    #     data = ["1.2","1.6","2.3","2.4","4.5","4.5","5.8","4.8","3.6","3.5","3.7","3.4","0.4","6.7"]
    #     g = nx.DiGraph()
    #     for d in data:
    #         g = defs.update_paths(paths=g, pid = d.split(".")[0],cid=d.split(".")[1])
    #     print("       ")
    #     roots = [node for node in g.nodes if g.in_degree(node) == 0]
    #     leaves = [node for node in g.nodes if g.out_degree(node) == 0]
    #     for root in roots :
    #         for leaf in leaves :
    #             for path in nx.all_simple_paths(g, root, leaf):
    #                 print(".".join(path))

    def test_paths_to_osib(self) -> None:
        """
        Given: CRES from 0 to 8 and the parent-child relationship described in paths, make an osib tree with two root CRE nodes
        node 1 holding 2,3,4,5,6,7,8
        node 0 holding 4,5,8
        """
        paths = [
            "1.2.3.6.7",
            "1.6.7",
            "1.2.3.5.8",
            "1.2.3.4.5.8",
            "1.2.3.4.8",
            "1.2.4.5.8",
            "1.2.4.8",
            "1.2.3.7",
            "0.4.5.8",
            "0.4.8",
        ]
        cres = {}
        osibs = {}
        for i in range(0, 9):
            cres[f"{i}"] = cdefs.CRE(
                name=f"cre-{i}", id=f"{i}", description=f"description-{i}"
            )
            osibs[f"{i}"] = defs.Osib_node(
                attributes=defs.Node_attributes(
                    source_id=str(i),
                    sources_i18n={
                        "en": defs._Source(
                            name=f"cre-{i}", description=f"description-{i}"
                        )
                    },
                ),
                children={},
            )
        owasp = defs.Osib_node(
            attributes=defs.Node_attributes(
                sources_i18n={
                    defs.Lang("en"): defs._Source(
                        name="Open Web Application Security Project",
                        source="https://owasp.org",
                    )
                }
            )
        )
        cre = defs.Osib_node(
            attributes=defs.Node_attributes(
                sources_i18n={
                    defs.Lang("en"): defs._Source(
                        name="Common Requirements Enumeration",
                        source="https://www.opencre.org",
                    )
                }
            )
        )
        owasp.children = {"CRE": cre}
        osibs["5"].children = {"8": osibs["8"]}
        osibs["4"].children = {"8": osibs["8"], "5": osibs["5"]}
        osibs["0"].children = {"4": osibs["4"]}

        osibs["1"].children = {"2": osibs["2"], "6": osibs["6"]}
        osibs["2"].children = {"3": osibs["3"], "4": osibs["4"]}
        osibs["3"].children = {
            "6": osibs["6"],
            "5": osibs["5"],
            "4": osibs["4"],
            "7": osibs["7"],
        }
        osibs["6"].children = {"7": osibs["7"]}
        cre.children = {"0": osibs["0"], "1": osibs["1"]}
        exprected_tree = defs.Osib_tree(children={"OWASP": owasp})
        tree = defs.paths_to_osib(osib_paths=paths, cres=cres)
        self.assertDictEqual(tree.to_dict(), exprected_tree.to_dict())


if __name__ == "__main__":
    unittest.main()
