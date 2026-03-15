import os
import unittest
from unittest.mock import MagicMock, patch

from application.defs import cre_defs as defs
from application.defs import cre_exceptions
from application.prompt_client import prompt_client


class TestCreDefsExtraCoverage(unittest.TestCase):
    def test_export_format_helpers(self):
        self.assertEqual(defs.ExportFormat.node_name_key("A"), "|A|")
        self.assertEqual(defs.ExportFormat.sectionID_key("A"), "A|id")
        self.assertEqual(defs.ExportFormat.description_key("A"), "A|description")
        self.assertEqual(defs.ExportFormat.section_key("A"), "A|name")
        self.assertEqual(defs.ExportFormat.subsection_key("A"), "A|section")
        self.assertEqual(defs.ExportFormat.hyperlink_key("A"), "A|hyperlink")
        self.assertEqual(defs.ExportFormat.get_doctype("CRE|x"), defs.Credoctypes.CRE)
        self.assertIsNone(defs.ExportFormat.get_doctype("x"))

    def test_enum_contains_and_from_str(self):
        self.assertIn("CRE", defs.Credoctypes)
        self.assertEqual(
            defs.Credoctypes.from_str("some Tool value"), defs.Credoctypes.Tool
        )
        self.assertIsNone(defs.Credoctypes.from_str("nothing"))
        self.assertEqual(defs.ToolTypes.from_str("offensive"), defs.ToolTypes.Offensive)
        self.assertIsNone(defs.ToolTypes.from_str(""))
        self.assertEqual(
            defs.LinkTypes.opposite(defs.LinkTypes.Contains), defs.LinkTypes.PartOf
        )
        self.assertEqual(
            defs.LinkTypes.opposite(defs.LinkTypes.PartOf), defs.LinkTypes.Contains
        )
        self.assertEqual(
            defs.LinkTypes.opposite(defs.LinkTypes.RemediatedBy),
            defs.LinkTypes.Remediates,
        )
        self.assertEqual(
            defs.LinkTypes.opposite(defs.LinkTypes.Remediates),
            defs.LinkTypes.RemediatedBy,
        )
        self.assertEqual(
            defs.LinkTypes.opposite(defs.LinkTypes.TestedBy), defs.LinkTypes.Tests
        )
        self.assertEqual(
            defs.LinkTypes.opposite(defs.LinkTypes.Tests), defs.LinkTypes.TestedBy
        )

    def test_link_post_init_and_repr(self):
        link = defs.Link(
            document=defs.Standard(name="ASVS", section="A", sectionID="1"),
            ltype="Linked To",
            tags=None,  # type: ignore[arg-type]
        )
        self.assertEqual(link.ltype, defs.LinkTypes.LinkedTo)
        self.assertEqual(link.tags, [])
        self.assertTrue(isinstance(repr(link), str))

    def test_document_errors_and_helpers(self):
        with self.assertRaises(cre_exceptions.InvalidDocumentNameException):
            defs.Code(name="A")
        with self.assertRaises(cre_exceptions.InvalidCREIDException):
            defs.CRE(id="bad", name="name")

        d1 = defs.Standard(name="Std1", section="A", sectionID="1")
        d2 = defs.Standard(name="Std2", section="B", sectionID="2")
        d1copy = d1.shallow_copy()
        self.assertEqual(d1copy.name, d1.name)
        self.assertEqual(d1copy.links, [])

        d1.add_link(defs.Link(document=d2, ltype=defs.LinkTypes.LinkedTo))
        self.assertTrue(
            d1.has_link(defs.Link(document=d2, ltype=defs.LinkTypes.LinkedTo))
        )
        with self.assertRaises(cre_exceptions.DuplicateLinkException):
            d1.add_link(defs.Link(document=d2, ltype=defs.LinkTypes.LinkedTo))

        with self.assertRaises(ValueError):
            d1.add_link(defs.Link(document=d1, ltype=defs.LinkTypes.LinkedTo))

    def test_from_dict_paths(self):
        cre_dict = {
            "doctype": defs.Credoctypes.CRE,
            "id": "123-123",
            "name": "C",
            "links": [
                {
                    "ltype": "Linked To",
                    "document": {
                        "doctype": defs.Credoctypes.Standard,
                        "name": "ASVS",
                        "section": "A",
                        "sectionID": "1",
                    },
                }
            ],
        }
        doc = defs.Document.from_dict(cre_dict)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.doctype, defs.Credoctypes.CRE)  # type: ignore[union-attr]
        self.assertEqual(len(doc.links), 1)  # type: ignore[union-attr]

        tool_dict = {
            "doctype": defs.Credoctypes.Tool,
            "name": "ToolX",
            "tooltype": "Defensive",
            "links": [],
        }
        tool_doc = defs.Document.from_dict(tool_dict)
        self.assertEqual(tool_doc.tooltype, defs.ToolTypes.Defensive)  # type: ignore[union-attr]
        self.assertIsNone(defs.Document.from_dict({"doctype": "Unknown"}))


class TestPromptClientExtraCoverage(unittest.TestCase):
    def setUp(self):
        self.database = MagicMock()

    def test_find_missing_embeddings(self):
        emb = prompt_client.in_memory_embeddings.instance()
        self.database.list_cre_ids.return_value = [("a",), ("b",)]
        self.database.list_node_ids_by_ntype.side_effect = [
            [("n1",)],
            [("n2",)],
            [("n3",)],
        ]
        self.database.get_embeddings_by_doc_type.side_effect = [
            {"a": [0.1]},  # CRE -> b missing
            {"n1": [0.2]},  # Standard none missing
            {},  # Tool -> n2 missing
            {},  # Code -> n3 missing
        ]
        missing = emb.find_missing_embeddings(self.database)
        self.assertIn("b", missing)
        self.assertIn("n2", missing)
        self.assertIn("n3", missing)

    def test_generate_embeddings_for_filters_missing(self):
        emb = prompt_client.in_memory_embeddings.instance()
        emb.generate_embeddings = MagicMock()
        self.database.list_cre_ids.return_value = [("a",), ("b",)]
        self.database.list_node_ids_by_name.return_value = [("n1",)]
        self.database.get_embedding.side_effect = [None, "exists", None]

        emb.generate_embeddings_for(self.database, defs.Credoctypes.CRE.value)
        emb.generate_embeddings.assert_called_with(self.database, ["a"])
        emb.generate_embeddings.reset_mock()

        emb.generate_embeddings_for(self.database, "ASVS")
        emb.generate_embeddings.assert_called_with(self.database, ["n1"])

    def test_prompt_handler_similarity_methods(self):
        with patch.dict(os.environ, {}, clear=True):
            handler = prompt_client.PromptHandler(self.database)
            self.database.get_embeddings_by_doc_type.return_value = {"id1": [1.0, 0.0]}
            found = handler.get_id_of_most_similar_cre([1.0, 0.0])
            self.assertEqual(found, "id1")

            self.database.get_embeddings_by_doc_type.return_value = {}
            handler2 = prompt_client.PromptHandler(self.database)
            with self.assertRaises(ValueError):
                handler2.get_id_of_most_similar_cre([1.0, 0.0])

            self.database.get_embeddings_by_doc_type.return_value = {"n1": [0.0, 1.0]}
            handler3 = prompt_client.PromptHandler(self.database)
            nid = handler3.get_id_of_most_similar_node([0.0, 1.0])
            self.assertEqual(nid, "n1")

    def test_prompt_handler_paginated_similarity(self):
        with patch.dict(os.environ, {}, clear=True):
            handler = prompt_client.PromptHandler(self.database)
            self.database.get_embeddings_by_doc_type_paginated.side_effect = [
                ({"id1": [1.0, 0.0]}, 2, 1),
                ({"id2": [0.0, 1.0]}, 2, 0),
            ]
            best_id, score = handler.get_id_of_most_similar_cre_paginated(
                [1.0, 0.0], 0.0
            )
            self.assertIn(best_id, {"id1", "id2"})
            self.assertIsNotNone(score)

            self.database.get_embeddings_by_doc_type_paginated.side_effect = [
                ({"n1": [0.2, 0.8]}, 1, 1),
                ({"n1": [0.2, 0.8]}, 1, 0),
            ]
            best_node_id, node_score = handler.get_id_of_most_similar_node_paginated(
                [0.2, 0.8], 0.0
            )
            self.assertEqual(best_node_id, "n1")
            self.assertIsNotNone(node_score)

    @patch(
        "application.prompt_client.prompt_client.vertex_prompt_client.VertexPromptClient"
    )
    def test_prompt_handler_init_vertex(self, vertex_mock):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "x"}, clear=True):
            handler = prompt_client.PromptHandler(self.database)
            self.assertIsNotNone(handler.ai_client)
            vertex_mock.assert_called_once()

    @patch(
        "application.prompt_client.prompt_client.openai_prompt_client.OpenAIPromptClient"
    )
    def test_prompt_handler_load_all_embeddings_flow(self, openai_mock):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}, clear=True):
            openai_mock.return_value = MagicMock()
            handler = prompt_client.PromptHandler(
                self.database, load_all_embeddings=False
            )
            handler.embeddings_instance.find_missing_embeddings = MagicMock(
                return_value=["id1"]
            )
            handler.embeddings_instance.setup_playwright = MagicMock()
            handler.embeddings_instance.generate_embeddings = MagicMock()
            handler.embeddings_instance.teardown_playwright = MagicMock()
            handler.embeddings_instance.find_missing_embeddings(self.database)
            handler.generate_embeddings_for("ASVS")
            handler.embeddings_instance.setup_playwright.assert_called()
            handler.embeddings_instance.teardown_playwright.assert_called()


if __name__ == "__main__":
    unittest.main()
