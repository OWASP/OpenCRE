import unittest
from unittest.mock import Mock, patch

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers import pci_dss as pci_mod
from application.utils.external_project_parsers.parsers.pci_dss import (
    PciDss,
    PciDssLinkError,
    best_cre_via_bridge_standard,
    pci_control_embedding_text,
    resolve_cre_for_pci_control,
)


class TestPciDssLinking(unittest.TestCase):
    def test_pci_control_embedding_text_uses_id_section_and_description(self) -> None:
        control = defs.Standard(
            name="PCI DSS",
            sectionID="1.2.3",
            section="Requirement title",
            description="Longer requirement body",
        )
        text = pci_control_embedding_text(control)
        self.assertIn("1.2.3", text)
        self.assertIn("Requirement title", text)
        self.assertIn("Longer requirement body", text)
        self.assertNotIn("family:standard", text)

    def test_resolve_cre_uses_paginated_cre_match_first(self) -> None:
        cache = Mock()
        linked_cre = defs.CRE(id="123-456", name="Linked CRE", description="")
        cache.get_cre_by_db_id.return_value = linked_cre
        prompt = Mock()
        prompt.get_id_of_most_similar_cre_paginated.return_value = ("cre-db-id", 0.82)

        cre = resolve_cre_for_pci_control(prompt, cache, [0.1, 0.2])

        self.assertEqual(linked_cre, cre)
        prompt.get_id_of_most_similar_cre_paginated.assert_called()
        prompt.get_id_of_most_similar_node.assert_not_called()

    def test_resolve_cre_falls_back_to_bridge_standard(self) -> None:
        cache = Mock()
        prompt = Mock()
        prompt.get_id_of_most_similar_cre_paginated.return_value = (None, None)
        bridge_cre = defs.CRE(id="999-001", name="Bridge CRE", description="")

        with patch.object(pci_mod, "PCI_BRIDGE_STANDARDS", ("S1", "S2")), patch.object(
            pci_mod, "best_cre_via_bridge_standard", side_effect=[None, bridge_cre]
        ) as bridge_mock:
            cre = resolve_cre_for_pci_control(prompt, cache, [0.1, 0.2])

        self.assertEqual(bridge_cre, cre)
        self.assertEqual(2, bridge_mock.call_count)

    def test_best_cre_via_bridge_standard_picks_highest_similarity_linked_node(
        self,
    ) -> None:
        cache = Mock()
        low_node = defs.Standard(name="NIST 800-53 v5", section="low", sectionID="a")
        high_node = defs.Standard(name="NIST 800-53 v5", section="high", sectionID="b")
        low_cre = defs.CRE(id="111-111", name="Low", description="")
        high_cre = defs.CRE(id="222-222", name="High", description="")
        cache.get_nodes.return_value = [low_node, high_node]
        cache.get_embeddings_for_doc.side_effect = [[0.0, 1.0], [1.0, 0.0]]
        cache.find_cres_of_node.side_effect = [
            [Mock(id="low-db")],
            [Mock(id="high-db")],
        ]
        cache.get_cre_by_db_id.side_effect = [low_cre, high_cre]

        cre = best_cre_via_bridge_standard(
            cache, [1.0, 0.0], "NIST 800-53 v5", min_similarity=0.0
        )

        self.assertEqual(high_cre, cre)


class TestPciDssParser(unittest.TestCase):
    @patch(
        "application.utils.external_project_parsers.parsers.pci_dss.prompt_client.PromptHandler"
    )
    def test_parse_skips_standard_fallback_when_no_standard_id(
        self, prompt_handler_mock
    ):
        parser = PciDss()

        cache = Mock()
        cache.get_nodes.return_value = None
        linked_cre = defs.CRE(id="123-456", name="Linked CRE", description="")
        cache.get_embeddings_by_doc_type.return_value = {"cre-1": [0.1]}

        prompt = Mock()
        prompt.get_text_embeddings.return_value = [0.1, 0.2]
        prompt_handler_mock.return_value = prompt

        pci_file = {
            "Original Content": [
                {
                    "Defined Approach Requirements": "Test requirement text",
                    "PCI DSS ID": "1.1.1",
                    "Requirement Description": "desc",
                }
            ]
        }

        with patch.object(
            pci_mod, "resolve_cre_for_pci_control", return_value=linked_cre
        ):
            out = parser.parse_4(pci_file=pci_file, cache=cache)

        self.assertEqual(1, len(out))
        self.assertEqual(1, len(out[0].links))
        prompt.generate_embeddings_for.assert_not_called()

    @patch(
        "application.utils.external_project_parsers.parsers.pci_dss.prompt_client.PromptHandler"
    )
    def test_parse_raises_when_control_cannot_be_linked(self, prompt_handler_mock):
        parser = PciDss()

        cache = Mock()
        cache.get_nodes.return_value = None
        cache.get_embeddings_by_doc_type.return_value = {"cre-1": [0.1]}

        prompt = Mock()
        prompt.get_text_embeddings.return_value = [0.1, 0.2]
        prompt_handler_mock.return_value = prompt

        pci_file = {
            "Original Content": [
                {
                    "Defined Approach Requirements": "Test requirement text",
                    "PCI DSS ID": "1.1.1",
                    "Requirement Description": "desc",
                }
            ]
        }

        with patch.object(pci_mod, "resolve_cre_for_pci_control", return_value=None):
            with self.assertRaises(PciDssLinkError):
                parser.parse_4(pci_file=pci_file, cache=cache)

    @patch(
        "application.utils.external_project_parsers.parsers.pci_dss.prompt_client.PromptHandler"
    )
    def test_parse_raises_when_any_control_in_batch_is_unlinked(
        self, prompt_handler_mock
    ):
        parser = PciDss()
        cache = Mock()
        cache.get_nodes.return_value = None
        linked_cre = defs.CRE(id="123-456", name="Linked CRE", description="")
        cache.get_embeddings_by_doc_type.return_value = {"cre-1": [0.1]}

        prompt = Mock()
        prompt.get_text_embeddings.return_value = [0.1, 0.2]
        prompt_handler_mock.return_value = prompt

        pci_file = {
            "Original Content": [
                {
                    "Defined Approach Requirements": "Linked requirement",
                    "PCI DSS ID": "1.1.1",
                    "Requirement Description": "desc",
                },
                {
                    "Defined Approach Requirements": "Unlinked requirement",
                    "PCI DSS ID": "1.1.2",
                    "Requirement Description": "desc",
                },
            ]
        }

        with patch.object(
            pci_mod,
            "resolve_cre_for_pci_control",
            side_effect=[linked_cre, None],
        ):
            with self.assertRaisesRegex(PciDssLinkError, "1 control\\(s\\) failed"):
                parser.parse_4(pci_file=pci_file, cache=cache)

    @patch(
        "application.utils.external_project_parsers.parsers.pci_dss.prompt_client.PromptHandler"
    )
    def test_parse_adds_single_automatic_link_per_control(self, prompt_handler_mock):
        parser = PciDss()
        cache = Mock()
        cache.get_nodes.return_value = None
        linked_cre = defs.CRE(id="123-456", name="Linked CRE", description="")
        cache.get_embeddings_by_doc_type.return_value = {"cre-1": [0.1]}

        prompt = Mock()
        prompt.get_text_embeddings.return_value = [0.1, 0.2]
        prompt_handler_mock.return_value = prompt

        pci_file = {
            "Original Content": [
                {
                    "Defined Approach Requirements": "Test requirement text",
                    "PCI DSS ID": "1.1.1",
                    "Requirement Description": "desc",
                }
            ]
        }

        with patch.object(
            pci_mod, "resolve_cre_for_pci_control", return_value=linked_cre
        ):
            out = parser.parse_4(pci_file=pci_file, cache=cache)

        self.assertEqual(1, len(out))
        self.assertEqual(1, len(out[0].links))
        self.assertEqual(defs.LinkTypes.AutomaticallyLinkedTo, out[0].links[0].ltype)
        self.assertEqual("123-456", out[0].links[0].document.id)


if __name__ == "__main__":
    unittest.main()
