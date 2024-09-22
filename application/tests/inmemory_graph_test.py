import unittest
import networkx as nx
from application.defs import cre_defs as defs
from application.database.inmemory_graph import CRE_Graph


class TestCreDefs(unittest.TestCase):
    def test_add_edge(self) -> None:
        cre1 = defs.CRE(name="c1", id="111-111")
        cre2 = defs.CRE(name="c2", id="111-112")
        cre3 = defs.CRE(name="c3", id="111-113")

        g = CRE_Graph()
        g.with_graph(graph=nx.DiGraph(), graph_data=[])
        g.add_cre(cre1)
        g.add_cre(cre2)
        g.add_cre(cre3)

        g.add_link(cre1, defs.Link(document=cre2, ltype=defs.LinkTypes.Contains))
        g.add_link(cre2, defs.Link(document=cre3, ltype=defs.LinkTypes.Contains))
        self.maxDiff = None
        self.assertDictEqual(
            nx.to_dict_of_dicts(g.get_raw_graph()),
            {
                "CRE: 111-111": {
                    "CRE: 111-112": {"ltype": defs.LinkTypes.Contains.value}
                },
                "CRE: 111-112": {
                    "CRE: 111-113": {"ltype": defs.LinkTypes.Contains.value}
                },
                "CRE: 111-113": {},
            },
        )

        g.add_link(
            cre3,
            defs.Link(
                document=defs.CRE(name="c4", id="111-114"), ltype=defs.LinkTypes.PartOf
            ),
        )
        g.add_link(
            cre2,
            defs.Link(
                document=defs.CRE(name="c4", id="111-114"), ltype=defs.LinkTypes.PartOf
            ),
        )

        self.assertDictEqual(
            nx.to_dict_of_dicts(g.get_raw_graph()),
            {
                "CRE: 111-111": {
                    "CRE: 111-112": {"ltype": defs.LinkTypes.Contains.value}
                },
                "CRE: 111-112": {
                    "CRE: 111-113": {"ltype": defs.LinkTypes.Contains.value}
                },
                "CRE: 111-113": {},
                "CRE: 111-114": {
                    "CRE: 111-112": {"ltype": defs.LinkTypes.Contains.value},
                    "CRE: 111-113": {"ltype": defs.LinkTypes.Contains.value},
                },
            },
        )

        s1 = defs.Standard(name="s1", section="s1 section")
        g.add_link(
            cre1,
            defs.Link(
                document=s1,
                ltype=defs.LinkTypes.LinkedTo,
            ),
        )
        s2 = defs.Standard(name="s2", section="s2 section")
        g.add_link(
            cre1,
            defs.Link(
                document=s2,
                ltype=defs.LinkTypes.AutomaticallyLinkedTo,
            ),
        )

        self.assertDictEqual(
            nx.to_dict_of_dicts(g.get_raw_graph()),
            {
                "CRE: 111-111": {
                    "CRE: 111-112": {"ltype": defs.LinkTypes.Contains.value},
                    f"Node: {s2.id}": {
                        "ltype": defs.LinkTypes.AutomaticallyLinkedTo.value
                    },
                    f"Node: {s1.id}": {"ltype": defs.LinkTypes.LinkedTo.value},
                },
                "CRE: 111-112": {
                    "CRE: 111-113": {"ltype": defs.LinkTypes.Contains.value}
                },
                "CRE: 111-113": {},
                "CRE: 111-114": {
                    "CRE: 111-112": {"ltype": defs.LinkTypes.Contains.value},
                    "CRE: 111-113": {"ltype": defs.LinkTypes.Contains.value},
                },
                "Node: s1:s1 section": {},
                "Node: s2:s2 section": {},
            },
        )

    def test_introduces_cycle(self) -> None:
        cre1 = defs.CRE(name="c1", id="111-111")
        cre2 = defs.CRE(name="c2", id="111-112")
        cre3 = defs.CRE(name="c3", id="111-113")

        g = CRE_Graph()
        g.with_graph(graph=nx.DiGraph(), graph_data=[])
        g.add_cre(cre1)
        g.add_cre(cre2)
        g.add_cre(cre3)

        g.add_link(cre1, defs.Link(document=cre2, ltype=defs.LinkTypes.Contains))
        g.add_link(cre2, defs.Link(document=cre3, ltype=defs.LinkTypes.Contains))

        self.assertIsNone(g.has_cycle())

        # cre -> cre cycle tests
        self.assertTrue(
            g.introduces_cycle(
                cre3, defs.Link(document=cre1, ltype=defs.LinkTypes.Contains)
            )
        )
        self.assertFalse(
            g.introduces_cycle(
                cre3, defs.Link(document=cre1, ltype=defs.LinkTypes.PartOf)
            )
        )
        self.assertFalse(
            g.introduces_cycle(
                cre1, defs.Link(document=cre3, ltype=defs.LinkTypes.Contains)
            )
        )
        self.assertFalse(
            g.introduces_cycle(
                cre1, defs.Link(document=cre3, ltype=defs.LinkTypes.Related)
            )
        )

        # cre -> node cycle tests, essentially, we cannot have nodes with cycles
        node1 = defs.Standard(name="s1", section="section1", sectionID="sectionid1")
        g.add_link(cre2, defs.Link(document=node1, ltype=defs.LinkTypes.LinkedTo))
        self.assertFalse(
            g.introduces_cycle(
                cre1, defs.Link(document=node1, ltype=defs.LinkTypes.LinkedTo)
            )
        )
        self.assertFalse(
            g.introduces_cycle(
                cre1,
                defs.Link(document=node1, ltype=defs.LinkTypes.AutomaticallyLinkedTo),
            )
        )
