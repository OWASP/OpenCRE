import unittest
from unittest.mock import Mock, patch

from application.utils.external_project_parsers.parsers.pci_dss import PciDss


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
        cache.find_cres_of_node.return_value = []
        cache.get_cre_by_db_id.return_value = None
        cache.get_embeddings_by_doc_type.return_value = {}

        prompt = Mock()
        prompt.get_text_embeddings.return_value = [0.1, 0.2]
        prompt.get_id_of_most_similar_cre.return_value = None
        prompt.get_id_of_most_similar_node.return_value = None
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

        out = parser.parse_4(pci_file=pci_file, cache=cache)

        self.assertEqual(1, len(out))
        self.assertEqual(1, cache.get_nodes.call_count)
        self.assertEqual(
            {
                "name": "PCI DSS",
                "section": "Test requirement text",
                "sectionID": "1.1.1",
            },
            cache.get_nodes.call_args.kwargs,
        )
        prompt.generate_embeddings_for.assert_called_once()


if __name__ == "__main__":
    unittest.main()
