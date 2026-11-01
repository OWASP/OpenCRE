"""Hidden CRE summaries for Librarian: prose leaves in, junk chrome out."""

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from application.utils.librarian.config_loader import load_config
from application.utils.librarian.cre_text import LinkedStandardRef
from application.utils.librarian.cre_summary import (
    DOC_TYPE_CRE_SUMMARY,
    MAX_LEAF_CHARS,
    CreRecord,
    apply_summaries_to_cre_texts,
    build_summary_prompt,
    inject_cre_summaries,
    migrate_json_cache_to_db,
    parse_summary_text,
    prose_leaves,
    public_cre_metadata,
    read_oie_summary,
)


def _nist_chrome() -> str:
    return (
        "An official website of the United States government "
        "Here's how you know skip to content navigation menu "
        "unauthorized frame window You have JavaScript disabled. "
        "This is a potential security issue, you are being redirected."
    )


def _zap_junk() -> str:
    return (
        "unauthorized frame window You have JavaScript disabled. "
        "This is a potential security issue, you are being redirected. "
        "ZAP HUD loading"
    )


def _pci_prose() -> str:
    return (
        "Requirement 3.4: Render PAN unreadable anywhere it is stored "
        "by using strong cryptography, truncation, or index tokens so that "
        "a compromise of one store does not expose the full primary account number."
    )


def _asvs_buried() -> str:
    return (
        "skip to content navigation menu platform solutions resources "
        "open source community " * 8
        + "Verify that passwords are at least 12 characters in length "
        "and that the application rejects common passwords from a dictionary."
    )


class ProseLeavesTest(unittest.TestCase):
    def test_skips_nist_chrome_and_zap_junk(self) -> None:
        refs = (
            LinkedStandardRef(
                "NIST 800-53 v5", "AC-2", "Account Management", _nist_chrome()
            ),
            LinkedStandardRef("ZAP", "10010", "Cookie No HttpOnly Flag", _zap_junk()),
        )
        leaves = prose_leaves(refs)
        blob = " ".join(leaves).lower()
        self.assertEqual(leaves, [])
        self.assertNotIn("united states government", blob)
        self.assertNotIn("javascript disabled", blob)

    def test_keeps_standard_and_tool_prose(self) -> None:
        tool_prose = (
            "Semgrep rule: detect hardcoded secrets in source, including AWS "
            "access keys and private tokens committed to the repository history."
        )
        refs = (
            LinkedStandardRef("PCI DSS", "3.4", "Stored PAN", _pci_prose()),
            LinkedStandardRef("Semgrep", "secrets", "Hardcoded secrets", tool_prose),
            LinkedStandardRef(
                "NIST 800-53 v5", "AC-2", "Account Management", _nist_chrome()
            ),
        )
        leaves = prose_leaves(refs)
        blob = " ".join(leaves)
        self.assertIn("Render PAN unreadable", blob)
        self.assertIn("hardcoded secrets", blob)
        self.assertNotIn("official website of the United States", blob)

    def test_salvages_asvs_buried_verify_that(self) -> None:
        leaves = prose_leaves(
            (LinkedStandardRef("ASVS", "V2.1.1", "Password length", _asvs_buried()),)
        )
        self.assertEqual(len(leaves), 1)
        self.assertIn("Verify that passwords are at least 12", leaves[0])
        self.assertNotIn("skip to content", leaves[0].lower())


class BuildSummaryPromptTest(unittest.TestCase):
    def test_cre_name_always_in_prompt(self) -> None:
        record = CreRecord(
            cre_id="cre-uuid-1",
            name="Access Control",
            description="",
            external_id="481-710",
        )
        system, user = build_summary_prompt(record, ())
        self.assertIn("Access Control", user)
        self.assertIn("481-710", user)
        self.assertIn("cre-uuid-1", user)
        self.assertIn("hidden", system.lower())

    def test_prompt_uses_prose_not_junk_chrome(self) -> None:
        record = CreRecord(
            cre_id="cre-uuid-1",
            name="Stored Account Data",
            description="Protect stored payment account data.",
            external_id="123-456",
        )
        refs = (
            LinkedStandardRef("PCI DSS", "3.4", "Stored PAN", _pci_prose()),
            LinkedStandardRef(
                "NIST 800-53 v5", "AC-2", "Account Management", _nist_chrome()
            ),
            LinkedStandardRef("ZAP", "10010", "Cookie", _zap_junk()),
        )
        _system, user = build_summary_prompt(record, refs)
        self.assertIn("Stored Account Data", user)
        self.assertIn("Render PAN unreadable", user)
        self.assertNotIn("official website of the United States", user)
        self.assertNotIn("unauthorized frame window", user.lower())
        self.assertNotIn("javascript disabled", user.lower())

    def test_name_first_packer_keeps_short_leaf_when_pci_is_huge(self) -> None:
        record = CreRecord(
            cre_id="cre-auth",
            name="Authentication",
            description="",
            external_id="633-428",
        )
        pci = "PCI DSS A3.4 cardholder data environment " + ("verify that " * 400)
        iso = (
            "ISO 27001 8.5 Secure authentication requires managing authentication "
            "information and implementing secure mechanisms for users and devices."
        )
        from application.utils.librarian.cre_summary import pack_linked_prose

        packed_direct = pack_linked_prose((pci, iso))
        self.assertIn("Secure authentication", " ".join(packed_direct))
        self.assertLessEqual(max(len(p) for p in packed_direct), MAX_LEAF_CHARS)

        refs = (
            LinkedStandardRef("PCI DSS", "A3.4", "CDE access", pci),
            LinkedStandardRef("ISO 27001", "8.5", "Secure authentication", iso),
        )
        system, user = build_summary_prompt(record, refs)
        payload = json.loads(user)
        blob = " ".join(payload["linked_prose"])
        self.assertEqual(payload["name"], "Authentication")
        self.assertIn("Secure authentication", blob)
        self.assertLessEqual(
            max(len(p) for p in payload["linked_prose"]), MAX_LEAF_CHARS
        )
        self.assertIn("CRE name is the topic", system)


class ApplySummariesTest(unittest.TestCase):
    def test_summary_is_not_written_to_public_description(self) -> None:
        cre = SimpleNamespace(
            id="cre-uuid-1",
            name="Access Control",
            description="Public CRE description that must stay put.",
        )
        cre_texts = {
            "cre-uuid-1": "CRE\n name:Access Control\n description:\n id:cre-uuid-1"
        }
        out = apply_summaries_to_cre_texts(
            cre_texts, {"cre-uuid-1": "Hidden blurb about access control."}
        )
        self.assertEqual(out["cre-uuid-1"], "Hidden blurb about access control.")
        self.assertEqual(cre.description, "Public CRE description that must stay put.")
        self.assertNotEqual(out["cre-uuid-1"], cre.description)

    def test_inject_uses_cache_and_does_not_mutate_cre_description(self) -> None:
        cre = SimpleNamespace(
            id="cre-uuid-1",
            description="Keep me",
        )
        texts = {"cre-uuid-1": "stub hub text"}
        record = CreRecord(
            cre_id="cre-uuid-1",
            name="Access Control",
            description="Keep me",
            external_id="481-710",
        )
        refs = {
            "cre-uuid-1": (
                LinkedStandardRef("PCI DSS", "3.4", "Stored PAN", _pci_prose()),
            )
        }

        def llm(system: str, user: str) -> str:
            self.assertIn("Access Control", user)
            self.assertIn("Render PAN unreadable", user)
            self.assertNotIn("javascript disabled", user.lower())
            return json.dumps({"summary": "Hidden access-control blurb."})

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            out_texts, vectors = inject_cre_summaries(
                cre_texts=texts,
                records={"cre-uuid-1": record},
                linked=refs,
                llm_fn=llm,
                cache_dir=cache,
                embed_fn=None,
            )
            self.assertEqual(out_texts["cre-uuid-1"], "Hidden access-control blurb.")
            self.assertIsNone(vectors)
            cached = json.loads((cache / "cre-uuid-1.json").read_text())
            self.assertEqual(cached["summary"], "Hidden access-control blurb.")
            self.assertEqual(cre.description, "Keep me")

            def boom(_system: str, _user: str) -> str:
                raise AssertionError("cache should skip a second LLM call")

            again, _ = inject_cre_summaries(
                cre_texts=texts,
                records={"cre-uuid-1": record},
                linked=refs,
                llm_fn=boom,
                cache_dir=cache,
                embed_fn=None,
            )
            self.assertEqual(again["cre-uuid-1"], "Hidden access-control blurb.")
            self.assertEqual(cre.description, "Keep me")

    def test_inject_can_embed_in_memory_without_touching_description(self) -> None:
        record = CreRecord(
            cre_id="cre-uuid-1",
            name="Access Control",
            description="Public",
            external_id="481-710",
        )
        texts = {"cre-uuid-1": "stub"}
        calls: list[str] = []

        def llm(_system: str, _user: str) -> str:
            return '{"summary": "Hidden blurb."}'

        def embed(text: str):
            calls.append(text)
            return [0.1, 0.2, 0.3]

        with tempfile.TemporaryDirectory() as tmp:
            out_texts, vectors = inject_cre_summaries(
                cre_texts=texts,
                records={"cre-uuid-1": record},
                linked={},
                llm_fn=llm,
                cache_dir=Path(tmp),
                embed_fn=embed,
            )
        self.assertEqual(out_texts["cre-uuid-1"], "Hidden blurb.")
        self.assertEqual(vectors, {"cre-uuid-1": [0.1, 0.2, 0.3]})
        self.assertEqual(calls, ["Hidden blurb."])
        self.assertEqual(record.description, "Public")

    def test_parse_summary_plain_and_json(self) -> None:
        self.assertEqual(
            parse_summary_text('{"summary": "Blurb about passwords."}'),
            "Blurb about passwords.",
        )
        self.assertEqual(
            parse_summary_text("Plain hidden blurb."), "Plain hidden blurb."
        )


class ConfigFlagTest(unittest.TestCase):
    def test_cre_summary_and_dual_default_on(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
            self.assertTrue(cfg.cre_summary)
            self.assertTrue(cfg.dual_index)

    def test_cre_summary_env_disables(self) -> None:
        with mock.patch.dict(
            os.environ, {"CRE_LIBRARIAN_CRE_SUMMARY": "0"}, clear=True
        ):
            self.assertFalse(load_config().cre_summary)


class PublicCreMetadataRedactionTest(unittest.TestCase):
    def test_public_cre_metadata_strips_summary_and_embedding_id(self) -> None:
        meta = {
            "oie": {
                "class_id": "auth",
                "families": ["identity"],
                "summary": "HIDDEN_BLURB",
                "embedding_id": "emb-uuid-1",
            },
            "other": 1,
        }
        public = public_cre_metadata(meta)
        public_oie = public["oie"]
        assert isinstance(public_oie, dict)
        self.assertEqual(public_oie["class_id"], "auth")
        self.assertEqual(public_oie["families"], ["identity"])
        self.assertNotIn("summary", public_oie)
        self.assertNotIn("embedding_id", public_oie)
        self.assertEqual(public["other"], 1)
        # Original untouched.
        self.assertEqual(meta["oie"]["summary"], "HIDDEN_BLURB")
        self.assertEqual(read_oie_summary(meta), ("HIDDEN_BLURB", "emb-uuid-1"))


class PublicCrePayloadHidingTest(unittest.TestCase):
    """End users must never see the librarian blurb on the CRE page or REST body."""

    _BLURB = "HIDDEN_LIBRARIAN_BLURB_MUST_NOT_APPEAR_IN_REST_OR_SPA"

    def test_cre_todict_keeps_public_description_empty(self) -> None:
        from application.defs import cre_defs as defs

        cre = defs.CRE(id="481-710", name="Access Control", description="")
        apply_summaries_to_cre_texts(
            {"cre-uuid-1": "stub hub text"},
            {"cre-uuid-1": self._BLURB},
        )
        payload = json.dumps(cre.todict())
        self.assertNotIn(self._BLURB, payload)
        self.assertNotIn("description", cre.todict())
        self.assertEqual(cre.description, "")
        self.assertNotIn("embeddings_content", payload)
        self.assertNotIn("librarian_summary", payload)

    def test_cre_from_db_redacts_oie_summary(self) -> None:
        from application.database.db import CRE, CREfromDB

        dbcre = CRE(
            id="cre-uuid-1",
            external_id="481-710",
            name="Access Control",
            description="Public description",
            metadata_json={
                "oie": {
                    "class_id": "auth",
                    "summary": self._BLURB,
                    "embedding_id": "emb-1",
                }
            },
        )
        cre = CREfromDB(dbcre)
        payload = json.dumps(cre.todict())
        self.assertNotIn(self._BLURB, payload)
        self.assertNotIn("emb-1", payload)
        self.assertEqual(cre.metadata.get("oie", {}).get("class_id"), "auth")
        self.assertNotIn("summary", cre.metadata.get("oie", {}))
        self.assertNotIn("embedding_id", cre.metadata.get("oie", {}))
        self.assertEqual(cre.description, "Public description")

    def test_frontend_cre_page_renders_public_description_only(self) -> None:
        tsx = Path(
            "application/frontend/src/pages/CommonRequirementEnumeration/"
            "CommonRequirementEnumeration.tsx"
        ).read_text()
        self.assertIn("cre-page__description", tsx)
        self.assertIn("display.description", tsx)
        self.assertNotIn("embeddings_content", tsx)
        self.assertNotIn("librarian_summary", tsx)
        self.assertNotIn("oie_cre_summaries", tsx)
        self.assertNotIn("embeddings_text", tsx)

    def test_rest_serializer_is_cre_todict(self) -> None:
        from application.web import web_main

        src = Path(web_main.__file__).read_text()
        self.assertIn("cre.todict()", src)
        self.assertNotIn("embeddings_content", src)

    def test_generate_script_refuses_database_cre(self) -> None:
        import importlib.util

        path = Path("scripts/oie_generate_cre_summaries.py")
        spec = importlib.util.spec_from_file_location(
            "oie_generate_cre_summaries", path
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with self.assertRaises(SystemExit):
            mod._assert_local_clone_url("postgresql://cre:password@127.0.0.1:5432/cre")
        mod._assert_local_clone_url(
            "postgresql://cre:password@127.0.0.1:5432/cre_prodclone"
        )


class CreSummaryDbStoreTest(unittest.TestCase):
    """First-class oie.summary + embedding_id → embeddings(doc_type=CRE_SUMMARY)."""

    def setUp(self) -> None:
        from application import create_app, sqla
        from application.database import db as database_db

        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.sqla = sqla
        self.database_db = database_db
        self.collection = database_db.Node_collection()
        self.sqla.session.add(
            database_db.CRE(
                id="cre-uuid-1",
                external_id="481-710",
                name="Access Control",
                description="Public description",
                metadata_json={"oie": {"class_id": "auth", "families": ["identity"]}},
            )
        )
        self.sqla.session.commit()

    def tearDown(self) -> None:
        self.sqla.session.remove()
        self.sqla.drop_all()
        self.ctx.pop()

    def test_inject_persists_summary_and_embedding_id_without_touching_hub(
        self,
    ) -> None:
        from application.database.db import CRE, Embeddings
        from application.database.pgvector_utils import parse_stored_embedding_vec
        from application.defs import cre_defs as defs

        hub = self.collection.add_embedding(
            self.database_db.CRE(
                id="cre-uuid-1",
                external_id="481-710",
                name="Access Control",
                description="Public description",
            ),
            defs.Credoctypes.CRE,
            [9.0, 9.0, 9.0],
            "hub CRE embeddings_content",
        )
        hub_id = hub.id if hasattr(hub, "id") else hub[0].id

        record = CreRecord(
            cre_id="cre-uuid-1",
            name="Access Control",
            description="Public description",
            external_id="481-710",
        )

        def llm(_system: str, _user: str) -> str:
            return '{"summary": "Hidden access-control blurb."}'

        def embed(text: str):
            self.assertEqual(text, "Hidden access-control blurb.")
            return [0.1, 0.2, 0.3]

        with tempfile.TemporaryDirectory() as tmp:
            out, vectors = inject_cre_summaries(
                cre_texts={"cre-uuid-1": "stub hub text"},
                records={"cre-uuid-1": record},
                linked={},
                llm_fn=llm,
                cache_dir=Path(tmp),
                embed_fn=embed,
                database=self.collection,
            )
        self.assertEqual(out["cre-uuid-1"], "Hidden access-control blurb.")
        self.assertEqual(vectors, {"cre-uuid-1": [0.1, 0.2, 0.3]})

        cre = self.sqla.session.query(CRE).filter(CRE.id == "cre-uuid-1").one()
        summary, emb_id = read_oie_summary(cre.metadata_json)
        self.assertEqual(summary, "Hidden access-control blurb.")
        self.assertTrue(emb_id)
        self.assertEqual(cre.description, "Public description")
        self.assertEqual(cre.metadata_json["oie"]["class_id"], "auth")

        summary_row = (
            self.sqla.session.query(Embeddings).filter(Embeddings.id == emb_id).one()
        )
        self.assertEqual(summary_row.doc_type, DOC_TYPE_CRE_SUMMARY)
        self.assertEqual(summary_row.cre_id, "cre-uuid-1")
        self.assertEqual(summary_row.embeddings_content, "Hidden access-control blurb.")
        self.assertEqual(
            parse_stored_embedding_vec(summary_row.embedding_vec), [0.1, 0.2, 0.3]
        )

        hub_row = (
            self.sqla.session.query(Embeddings).filter(Embeddings.id == hub_id).one()
        )
        self.assertEqual(hub_row.doc_type, defs.Credoctypes.CRE.value)
        self.assertEqual(
            parse_stored_embedding_vec(hub_row.embedding_vec), [9.0, 9.0, 9.0]
        )
        self.assertEqual(hub_row.embeddings_content, "hub CRE embeddings_content")

        def boom(_system: str, _user: str) -> str:
            raise AssertionError("DB summary should skip a second LLM call")

        with tempfile.TemporaryDirectory() as tmp:
            again, again_vecs = inject_cre_summaries(
                cre_texts={"cre-uuid-1": "stub hub text"},
                records={"cre-uuid-1": record},
                linked={},
                llm_fn=boom,
                cache_dir=Path(tmp),
                embed_fn=None,
                database=self.collection,
            )
        self.assertEqual(again["cre-uuid-1"], "Hidden access-control blurb.")
        self.assertIsNone(again_vecs)

    def test_migrate_json_cache_into_oie_and_embeddings(self) -> None:
        from application.database.db import CRE, Embeddings
        from application.database.pgvector_utils import parse_stored_embedding_vec

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "cre-uuid-1.json").write_text(
                json.dumps(
                    {
                        "cre_id": "cre-uuid-1",
                        "external_id": "481-710",
                        "name": "Access Control",
                        "summary": "Migrated hidden blurb.",
                        "embedding": [1.0, 2.0, 3.0],
                    }
                )
            )
            n = migrate_json_cache_to_db(database=self.collection, cache_dir=cache)
        self.assertEqual(n, 1)
        cre = self.sqla.session.query(CRE).filter(CRE.id == "cre-uuid-1").one()
        summary, emb_id = read_oie_summary(cre.metadata_json)
        self.assertEqual(summary, "Migrated hidden blurb.")
        self.assertTrue(emb_id)
        row = self.sqla.session.query(Embeddings).filter(Embeddings.id == emb_id).one()
        self.assertEqual(row.doc_type, DOC_TYPE_CRE_SUMMARY)
        self.assertEqual(parse_stored_embedding_vec(row.embedding_vec), [1.0, 2.0, 3.0])


if __name__ == "__main__":
    unittest.main()
