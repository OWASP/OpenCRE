import os
import tempfile
from typing import Any, Dict, List, Tuple
import unittest
from pprint import pprint

import yaml
from application.defs import cre_defs as cdefs
from application.defs import osib_defs as defs
from application.defs.osib_defs import (
    _Link,
    _Source,
    Lang,
    Node_attributes,
    Osib_tree,
    Osib_node,
)
from application.defs.cre_defs import LinkTypes
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
        self.assertDictEqual(yaml.safe_load(self.yaml_file), osib[0].todict())

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
        tools = [
            cdefs.Tool(
                tooltype=cdefs.ToolTypes.Offensive,
                name="ZAP",
                description="zed attack proxy",
                hyperlink="https://www.zaproxy.org/",
            ),
            cdefs.Tool(
                tooltype=cdefs.ToolTypes.Defensive,
                name="SKF",
                description="security knowledge framework",
                hyperlink="https://www.securityknowledgeframework.org/",
            ),
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
        top10.extend(
            [
                cdefs.Standard(
                    name="top10",
                    doctype=cdefs.Credoctypes.Standard,
                    metadata={"source_id": "Portswigger"},
                    section="202110.references.portswigger",
                ),
                cdefs.Standard(
                    name="top10",
                    doctype=cdefs.Credoctypes.Standard,
                    links=[
                        cdefs.Link(
                            ltype=cdefs.LinkTypes.PartOf,
                            document=cdefs.Standard(name="top10", section="202110"),
                        )
                    ],
                    metadata={"source_id": "A11:2021"},
                    hyperlink="https://owasp.org/Top10/A11_2021-Next_Steps",
                    section="202110.11",
                ),
            ]
        )

        tools.extend(top10)
        self.maxDiff = None
        expected: Tuple[List[cdefs.CRE], List[cdefs.Standard]] = ([], tools)
        cre_arr = defs.osib2cre(data[0])
        for el in expected[1]:
            cre_ell = [e for e in cre_arr[1] if e.hyperlink == el.hyperlink]
            self.assertDictEqual(el.todict(), cre_ell[0].todict())

    def test_cre2osib(self) -> None:
        cres = {}
        osibs = {}
        res: Dict[str, Osib_node] = {}
        for i in range(0, 13):
            cres[i] = cdefs.CRE(
                name=f"cre-{i}", id=f"{i}", description=f"description-{i}"
            )
            osibs[i] = defs.Osib_node(
                attributes=defs.Node_attributes(
                    source_id=str(i),
                    sources_i18n={
                        Lang("en"): defs._Source(
                            name=f"cre-{i}", description=f"description-{i}"
                        )
                    },
                ),
                children={},
            )
        osibs[14] = defs.Osib_node(
            attributes=defs.Node_attributes(
                source_id="999-999",
                sources_i18n={Lang("en"): defs._Source(name=f"LinksTool")},
            ),
            children={
                "SKF": defs.Osib_node(
                    attributes=defs.Node_attributes(
                        categories=["Defensive", "Tool"],
                        sources_i18n={
                            Lang("en"): defs._Source(
                                source="https://example.com/skf", name=f"SKF"
                            )
                        },
                    )
                )
            },
        )
        cres[14] = cdefs.CRE(
            name="LinksTool",
            id="999-999",
            links=[
                cdefs.Link(
                    ltype=cdefs.LinkTypes.LinkedTo,
                    document=cdefs.Tool(
                        tooltype=cdefs.ToolTypes.Defensive,
                        name="SKF",
                        section="",
                        sectionID="",
                        hyperlink="https://example.com/skf",
                    ),
                )
            ],
        )
        osibs["ZAP"] = defs.Osib_node(
            attributes=defs.Node_attributes(
                categories=["Offensive", "Tool"],
                sources_i18n={
                    Lang("en"): defs._Source(
                        source="https://example.com/zap", name=f"zap"
                    )
                },
            )
        )

        cres[15] = cdefs.Tool(
            tooltype=cdefs.ToolTypes.Offensive,
            name="zap",
            hyperlink="https://example.com/zap",
        )
        res = {
            "0": osibs[0],
            "1": osibs[1],
            "2": osibs[2],
            "9": osibs[9],
            "10": osibs[10],
            "11": osibs[11],
            "12": osibs[12],
        }
        res["0"].attributes.links = [
            _Link(type=LinkTypes.LinkedTo.value, link=f"OSIB.OWASP.CRE.1")
        ]
        res["1"].attributes.links = [
            _Link(type=LinkTypes.LinkedTo.value, link=f"OSIB.OWASP.CRE.0"),
            _Link(type=LinkTypes.LinkedTo.value, link=f"OSIB.OWASP.CRE.2"),
        ]
        res["2"].attributes.links = [
            _Link(type=LinkTypes.LinkedTo.value, link=f"OSIB.OWASP.CRE.1")
        ]
        osibs[8].attributes.links = [
            _Link(type=LinkTypes.Related.value, link=f"OSIB.OWASP.CRE.9")
        ]
        osibs[7].children = {"8": osibs[8]}
        osibs[6].children = {"7": osibs[7]}
        osibs[5].children = {"6": osibs[6]}
        osibs[4].children = {"5": osibs[5]}
        osibs[3].children = {"4": osibs[4]}
        res["2"].children = {"3": osibs[3]}
        res["9"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.2.3.4.5.6.7.8")
        ]

        res["9"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.10")
        ]
        res["10"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.9")
        ]
        res["10"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.11")
        ]
        res["11"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.10")
        ]
        res["11"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.12")
        ]
        res["12"].attributes.links = [
            _Link(type=LinkTypes.Related.value, link="OSIB.OWASP.CRE.11")
        ]

        cres[1].add_link(cdefs.Link(ltype=LinkTypes.LinkedTo, document=cres[0]))
        cres[0].add_link(cdefs.Link(ltype=LinkTypes.LinkedTo, document=cres[1]))
        cres[1].add_link(cdefs.Link(ltype=LinkTypes.LinkedTo, document=cres[2]))
        cres[2].add_link(cdefs.Link(ltype=LinkTypes.LinkedTo, document=cres[1]))
        cres[8].add_link(cdefs.Link(ltype=LinkTypes.LinkedTo, document=cres[9]))

        cres[2].add_link(cdefs.Link(ltype=LinkTypes.Contains, document=cres[3]))
        cres[3].add_link(cdefs.Link(ltype=LinkTypes.Contains, document=cres[4]))
        cres[4].add_link(cdefs.Link(ltype=LinkTypes.Contains, document=cres[5]))
        cres[5].add_link(cdefs.Link(ltype=LinkTypes.Contains, document=cres[6]))
        cres[7].add_link(cdefs.Link(ltype=LinkTypes.PartOf, document=cres[6]))
        cres[8].add_link(cdefs.Link(ltype=LinkTypes.PartOf, document=cres[7]))

        cres[9].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[8]))
        cres[9].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[10]))
        cres[10].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[9]))
        cres[10].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[11]))
        cres[11].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[10]))
        cres[11].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[12]))
        cres[12].add_link(cdefs.Link(ltype=LinkTypes.Related, document=cres[11]))
        owasp = Osib_node(
            attributes=Node_attributes(
                sources_i18n={
                    Lang("en"): _Source(
                        name="Open Web Application Security Project",
                        source="https://owasp.org",
                    )
                }
            )
        )
        root = Osib_node(
            attributes=Node_attributes(
                sources_i18n={
                    Lang("en"): _Source(
                        name="Common Requirements Enumeration",
                        source="https://www.opencre.org",
                    )
                }
            )
        )
        root.children = res
        owasp.children = {"CRE": root, "ZAP": osibs["ZAP"]}
        tree = Osib_tree(children={"OWASP": owasp})
        self.assertEqual(tree, defs.cre2osib(list(cres.values())))
        # self.fail()

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
                    categories=[cdefs.Credoctypes.CRE],
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
        expected_tree = defs.Osib_tree(children={"OWASP": owasp})
        tree = defs.paths_to_osib(osib_paths=paths, cres=cres, related_nodes=[])
        self.assertDictEqual(tree.todict(), expected_tree.todict())


if __name__ == "__main__":
    unittest.main()
