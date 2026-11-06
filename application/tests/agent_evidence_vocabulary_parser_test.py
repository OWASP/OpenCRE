from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import requests

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import (
    agent_evidence_vocabulary,
)

TAGS_URL = "https://api.github.com/repos/probityai/agent-evidence/tags?per_page=100"
TAGS_URL_PAGE_2 = TAGS_URL + "&page=2"
RAW_PREFIX = "https://raw.githubusercontent.com/probityai/agent-evidence/"
BLOB_PREFIX = "https://github.com/probityai/agent-evidence/blob/"
VOCABULARY_PATH = "packages/vocabulary/vocabulary.yaml"


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        json_body: Optional[List[Dict[str, Any]]] = None,
        next_url: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_body or []
        self.links = {"next": {"url": next_url}} if next_url else {}

    def json(self) -> List[Dict[str, Any]]:
        return self._json


def tag_list(*names: str) -> List[Dict[str, Any]]:
    return [{"name": n} for n in names]


def line_of(text: str, key: str) -> int:
    for number, line in enumerate(text.splitlines(), start=1):
        if line == f"  {key}:":
            return number
    raise AssertionError(f"{key} not in fixture")


class TestAgentEvidenceVocabularyParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        self.parser = agent_evidence_vocabulary.AgentEvidenceVocabulary()
        # 515-021 is deliberately absent, so containment_posture cannot resolve.
        for cre_id, name in [
            ("026-280", "Securely transfer logs (remotely)"),
            ("433-442", "Verification"),
            ("124-564", "Configuration Management"),
            ("547-824", "AI model performance validation"),
        ]:
            self.collection.add_cre(cre=defs.CRE(id=cre_id, name=name))

    def fake_get(self, responses: Dict[str, FakeResponse]):
        def get(url: str, *args: Any, **kwargs: Any) -> FakeResponse:
            if url not in responses:
                raise AssertionError(f"unexpected request to {url}")
            return responses[url]

        return get

    @patch.object(requests, "get")
    def test_parse(self, mock_get) -> None:
        tag = "agent-evidence-vocabulary-v0.6.0"
        mock_get.side_effect = self.fake_get(
            {
                TAGS_URL: FakeResponse(
                    json_body=tag_list(
                        "agent-evidence-vocabulary-python-v0.6.0",
                        "agent-evidence-vocabulary-v0.5.0",
                        tag,
                        "agent-evidence-vocabulary-v0.3.0",
                        "unrelated-v9.9.9",
                    )
                ),
                f"{RAW_PREFIX}{tag}/{VOCABULARY_PATH}": FakeResponse(
                    text=VOCABULARY_YAML
                ),
            }
        )

        result = self.parser.parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )

        self.assertEqual(list(result.results.keys()), [self.parser.name])
        nodes = {n.sectionID: n for n in result.results[self.parser.name]}
        self.assertCountEqual(
            nodes.keys(),
            [
                "evidence_dimensions.observation_vantage",
                "posture_and_coverage.coverage_denominator",
                "change_admission.admission_gate",
            ],
        )

        tags = [
            "family:standard",
            "subtype:requirements_standard",
            "audience:architect",
            "maturity:draft",
            "source:agent_evidence_vocabulary",
        ]
        expected = defs.Standard(
            name="Agent Evidence Vocabulary",
            section="observation_vantage",
            sectionID="evidence_dimensions.observation_vantage",
            version="0.6.0",
            hyperlink=f"{BLOB_PREFIX}{tag}/{VOCABULARY_PATH}#L{line_of(VOCABULARY_YAML, 'observation_vantage')}",
            description=(
                "Where the evidence for a claim was obtained from.\n"
                "CRE 026-280 (partial): The record is kept where the executed "
                "party cannot alter it."
            ),
            tags=tags,
        )
        vantage = nodes["evidence_dimensions.observation_vantage"]
        got = vantage.todict()
        links = got.pop("links")
        self.assertEqual(
            got, {k: v for k, v in expected.todict().items() if k != "links"}
        )
        self.assertEqual([l["document"]["id"] for l in links], ["026-280"])
        self.assertEqual(
            [l["ltype"] for l in links], [defs.LinkTypes.AutomaticallyLinkedTo.value]
        )

        gate = nodes["change_admission.admission_gate"]
        self.assertEqual([l.document.id for l in gate.links], ["124-564", "547-824"])
        self.assertTrue(
            all(l.ltype == defs.LinkTypes.AutomaticallyLinkedTo for l in gate.links)
        )
        self.assertIn("CRE 124-564 (structural):", gate.description)
        self.assertIn("CRE 547-824 (partial):", gate.description)
        self.assertTrue(
            gate.hyperlink.endswith(f"#L{line_of(VOCABULARY_YAML, 'admission_gate')}")
        )

    def test_latest_release_tag_follows_pages_and_skips_older_releases(
        self,
    ) -> None:
        responses = {
            TAGS_URL: FakeResponse(
                json_body=tag_list(
                    "agent-evidence-vocabulary-v0.4.0",
                    "agent-evidence-vocabulary-v0.10.0",
                ),
                next_url=TAGS_URL_PAGE_2,
            ),
            TAGS_URL_PAGE_2: FakeResponse(
                json_body=tag_list(
                    "agent-evidence-vocabulary-v0.9.1",
                    "agent-evidence-vocabulary-v1.0.0-rc1",
                )
            ),
        }
        with patch.object(requests, "get", side_effect=self.fake_get(responses)):
            self.assertEqual(
                self.parser.latest_release_tag(),
                "agent-evidence-vocabulary-v0.10.0",
            )

    def test_latest_release_tag_refuses_releases_without_links(self) -> None:
        responses = {
            TAGS_URL: FakeResponse(
                json_body=tag_list(
                    "agent-evidence-vocabulary-v0.3.0",
                    "agent-evidence-vocabulary-python-v0.6.0",
                )
            )
        }
        with patch.object(requests, "get", side_effect=self.fake_get(responses)):
            with self.assertRaises(RuntimeError):
                self.parser.latest_release_tag()

    def test_failed_download_raises(self) -> None:
        tag = "agent-evidence-vocabulary-v0.6.0"
        responses = {
            TAGS_URL: FakeResponse(json_body=tag_list(tag)),
            f"{RAW_PREFIX}{tag}/{VOCABULARY_PATH}": FakeResponse(status_code=404),
        }
        with patch.object(requests, "get", side_effect=self.fake_get(responses)):
            with self.assertRaises(RuntimeError):
                self.parser.parse(cache=self.collection, ph=None)

    def test_version_comes_from_the_source(self) -> None:
        tag = "agent-evidence-vocabulary-v0.6.0"
        declared = VOCABULARY_YAML.replace('version: "0.6.0"', 'version: "0.6.1"')
        nodes = self.parser.parse_vocabulary(
            text=declared, tag=tag, cache=self.collection
        )
        self.assertEqual({n.version for n in nodes}, {"0.6.1"})

        no_meta = VOCABULARY_YAML.replace("meta:\n", "meta_removed:\n")
        nodes = self.parser.parse_vocabulary(
            text=no_meta, tag=tag, cache=self.collection
        )
        self.assertEqual({n.version for n in nodes}, {"0.6.0"})

    def test_missing_cre_is_skipped_without_breaking_the_import(self) -> None:
        nodes = self.parser.parse_vocabulary(
            text=VOCABULARY_YAML,
            tag="agent-evidence-vocabulary-v0.6.0",
            cache=self.collection,
        )
        section_ids = [n.sectionID for n in nodes]
        self.assertNotIn("posture_and_coverage.containment_posture", section_ids)
        self.assertIn("posture_and_coverage.coverage_denominator", section_ids)

        # once the CRE exists, the same term imports
        self.collection.add_cre(
            cre=defs.CRE(id="515-021", name="Sandbox and isolate applications")
        )
        nodes = self.parser.parse_vocabulary(
            text=VOCABULARY_YAML,
            tag="agent-evidence-vocabulary-v0.6.0",
            cache=self.collection,
        )
        self.assertIn(
            "posture_and_coverage.containment_posture",
            [n.sectionID for n in nodes],
        )

    def test_malformed_entries_are_skipped(self) -> None:
        nodes = self.parser.parse_vocabulary(
            text=VOCABULARY_YAML,
            tag="agent-evidence-vocabulary-v0.6.0",
            cache=self.collection,
        )
        by_id = {n.sectionID: n for n in nodes}
        # bad URL, unknown match value, non-mapping item and opencre not a list
        for broken in [
            "record_lifecycle.revision_reason",
            "record_lifecycle.wrong_match",
            "record_lifecycle.not_a_mapping",
            "record_lifecycle.not_a_list",
        ]:
            self.assertNotIn(broken, by_id)
        # a term with no opencre key is not imported
        self.assertNotIn("evidence_dimensions.observation_directness", by_id)
        # a CRE listed twice is linked once, and the good link next to a broken one stays
        denominator = by_id["posture_and_coverage.coverage_denominator"]
        self.assertEqual([l.document.id for l in denominator.links], ["433-442"])
        self.assertEqual(denominator.description.count("CRE 433-442"), 1)

    def test_top_level_must_be_a_mapping(self) -> None:
        with self.assertRaises(ValueError):
            self.parser.parse_vocabulary(
                text="- a\n- b\n",
                tag="agent-evidence-vocabulary-v0.6.0",
                cache=self.collection,
            )


VOCABULARY_YAML = """# agent-evidence-vocabulary test fixture
meta:
  version: "0.6.0"
  status: "draft - open for review"

evidence_dimensions:
  observation_vantage:
    status: proposed
    values: [substrate, artifact]
    definition: >
      Where the evidence for a claim
      was obtained from.
    opencre:
      - cre: https://www.opencre.org/cre/026-280
        match: partial
        basis: "The record is kept where the executed party cannot alter it."

  observation_directness:
    status: proposed
    values: [intercepted, reconstructed]
    definition: >
      Whether a claim rests on events captured as they occurred.

posture_and_coverage:
  containment_posture:
    definition: >
      The network isolation the artifact ran inside.
    opencre:
      - cre: https://www.opencre.org/cre/515-021
        match: structural
        basis: "The term records the isolation the artifact ran inside."

  coverage_denominator:
    definition: >
      The population a result assessed.
    opencre:
      - cre: https://www.opencre.org/cre/433-442
        match: partial
        basis: "A test result names the population it assessed."
      - cre: https://www.opencre.org/cre/433-442
        match: partial
        basis: "The same CRE listed a second time."
      - cre: https://example.com/cre/433-442
        match: partial
        basis: "Not an opencre.org URL."

record_lifecycle:
  revision_reason:
    definition: >
      Why a published record changed.
    opencre:
      - cre: https://www.opencre.org/cre/757-27
        match: partial
        basis: "The id is too short."

  wrong_match:
    definition: >
      A term whose match value is not in the closed set.
    opencre:
      - cre: https://www.opencre.org/cre/433-442
        match: close-enough
        basis: "Unknown match value."

  not_a_mapping:
    definition: >
      A term whose link item is a bare string.
    opencre:
      - https://www.opencre.org/cre/433-442

  not_a_list:
    definition: >
      A term whose opencre field is a single mapping.
    opencre:
      cre: https://www.opencre.org/cre/433-442
      match: partial
      basis: "Not a list."

change_admission:
  admission_gate:
    values: [replay, heldout]
    definition: >
      The closed names of the checks an admission rests on.
    opencre:
      - cre: https://www.opencre.org/cre/124-564
        match: structural
        basis: "The checks a change passes before it is admitted."
      - cre: https://www.opencre.org/cre/547-824
        match: partial
        basis: "Held-out runs validate the changed agent's behaviour."

crosswalk_match_types:
  exact:
    definition: >
      Same meaning, same shape.

out_of_scope:
  - identity
"""
