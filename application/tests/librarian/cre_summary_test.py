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
    MAX_LEAF_CHARS,
    CreRecord,
    apply_summaries_to_cre_texts,
    build_summary_prompt,
    inject_cre_summaries,
    parse_summary_text,
    prose_leaves,
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


if __name__ == "__main__":
    unittest.main()
