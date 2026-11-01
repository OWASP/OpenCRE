"""Leaf drill-down: promote Contains children over hub umbrellas when they score better."""

from __future__ import annotations

import unittest
from typing import List, Sequence, Tuple

from application.utils.librarian.leaf_drilldown import (
    apply_leaf_drilldown,
    count_resource_families,
    resource_allows_leaf_drilldown,
    resource_family_key,
    resource_is_fine_grained,
)
from application.utils.librarian.umbrella_promote import ParentIndex


def _score_by_doc_token(
    pairs: Sequence[Tuple[str, str]],
) -> List[float]:
    """Hermetic scorer: higher when query token appears in doc text."""
    out: List[float] = []
    for query, doc in pairs:
        q = (query or "").lower()
        d = (doc or "").lower()
        hits = sum(1 for tok in q.split() if len(tok) >= 4 and tok in d)
        out.append(float(hits) + (0.1 if "leaf" in d else 0.0))
    return out


class LeafDrilldownTest(unittest.TestCase):
    def test_promotes_better_child_ahead_of_hub(self) -> None:
        parents = ParentIndex(
            child_to_parents={
                "leaf-encode": ("hub-appsec",),
                "leaf-other": ("hub-appsec",),
            },
            parent_names={"hub-appsec": "Technical application security controls"},
            parent_to_children={
                "hub-appsec": ("leaf-encode", "leaf-other"),
            },
        )
        cre_texts = {
            "hub-appsec": "broad application security controls umbrella",
            "leaf-encode": "leaf encode output near the consuming interpreter",
            "leaf-other": "leaf password storage hashing",
        }
        out = apply_leaf_drilldown(
            ["hub-appsec", "noise-cre"],
            "Section: Encode output near interpreter context",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
        )
        self.assertEqual(out[0], "leaf-encode")
        self.assertIn("hub-appsec", out)
        self.assertLess(out.index("leaf-encode"), out.index("hub-appsec"))

    def test_attaches_best_child_even_when_hub_wins_ce(self) -> None:
        """Specificity: hub may still lead, but best leaf must appear next."""
        parents = ParentIndex(
            child_to_parents={"leaf-a": ("hub",)},
            parent_to_children={"hub": ("leaf-a",)},
        )
        cre_texts = {
            "hub": "authentication session management leaf umbrella keywords",
            "leaf-a": "unrelated cryptography",
        }
        out = apply_leaf_drilldown(
            ["hub", "noise"],
            "authentication session management",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
        )
        self.assertEqual(out[0], "hub")
        self.assertEqual(out[1], "leaf-a")

    def test_require_beat_hub_keeps_list_when_child_loses(self) -> None:
        parents = ParentIndex(
            child_to_parents={"leaf-a": ("hub",)},
            parent_to_children={"hub": ("leaf-a",)},
        )
        cre_texts = {
            "hub": "authentication session management leaf umbrella keywords",
            "leaf-a": "unrelated cryptography",
        }
        out = apply_leaf_drilldown(
            ["hub"],
            "authentication session management",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
            require_beat_hub=True,
        )
        self.assertEqual(out, ["hub"])

    def test_noop_without_parent_index_or_children(self) -> None:
        ids = ["a", "b"]
        self.assertEqual(
            apply_leaf_drilldown(
                ids,
                "q",
                parent_index=None,
                cre_texts={},
                score_fn=_score_by_doc_token,
            ),
            ids,
        )
        empty = ParentIndex(child_to_parents={}, parent_to_children={})
        self.assertEqual(
            apply_leaf_drilldown(
                ids,
                "q",
                parent_index=empty,
                cre_texts={"a": "x", "b": "y"},
                score_fn=_score_by_doc_token,
            ),
            ids,
        )

    def test_skips_children_without_text(self) -> None:
        parents = ParentIndex(
            child_to_parents={"leaf-ok": ("hub",), "leaf-missing": ("hub",)},
            parent_to_children={"hub": ("leaf-ok", "leaf-missing")},
        )
        cre_texts = {
            "hub": "hub text",
            "leaf-ok": "leaf encode interpreter",
        }
        out = apply_leaf_drilldown(
            ["hub"],
            "encode interpreter",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
        )
        self.assertEqual(out[0], "leaf-ok")
        self.assertNotIn("leaf-missing", out)

    def test_skips_hub_below_min_children(self) -> None:
        parents = ParentIndex(
            child_to_parents={
                "leaf-a": ("skinny",),
                "leaf-b": ("fat",),
                "leaf-c": ("fat",),
                "leaf-d": ("fat",),
            },
            parent_to_children={
                "skinny": ("leaf-a",),
                "fat": ("leaf-b", "leaf-c", "leaf-d"),
            },
        )
        cre_texts = {
            "skinny": "hub skinny",
            "fat": "hub fat",
            "leaf-a": "leaf encode interpreter",
            "leaf-b": "leaf encode interpreter",
            "leaf-c": "other",
            "leaf-d": "other",
        }
        out = apply_leaf_drilldown(
            ["skinny", "fat"],
            "encode interpreter",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
            min_children=3,
        )
        self.assertEqual(out[0], "skinny")
        self.assertNotIn("leaf-a", out)
        self.assertEqual(out[1], "leaf-b")
        self.assertLess(out.index("leaf-b"), out.index("fat"))

    def test_hub_first_keeps_hub_ahead_of_beating_leaf(self) -> None:
        """E2: even when leaf beats hub on CE, hub stays #1 and leaf is #2."""
        parents = ParentIndex(
            child_to_parents={
                "leaf-encode": ("hub-appsec",),
                "leaf-other": ("hub-appsec",),
            },
            parent_to_children={
                "hub-appsec": ("leaf-encode", "leaf-other"),
            },
        )
        cre_texts = {
            "hub-appsec": "broad application security controls umbrella",
            "leaf-encode": "leaf encode output near the consuming interpreter",
            "leaf-other": "leaf password storage hashing",
        }
        out = apply_leaf_drilldown(
            ["hub-appsec", "noise-cre"],
            "Section: Encode output near interpreter context",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
            hub_first=True,
        )
        self.assertEqual(out[0], "hub-appsec")
        self.assertEqual(out[1], "leaf-encode")

    def test_keep_hub_in_top2_when_leaf_displaces_hub(self) -> None:
        """E1: after leaf leads, drilled hub must remain inside scored top-2."""
        parents = ParentIndex(
            child_to_parents={
                "leaf-encode": ("hub-appsec",),
                "leaf-other": ("hub-appsec",),
            },
            parent_to_children={
                "hub-appsec": ("leaf-encode", "leaf-other"),
            },
        )
        cre_texts = {
            "hub-appsec": "broad application security controls umbrella",
            "leaf-encode": "leaf encode output near the consuming interpreter",
            "leaf-other": "leaf password storage hashing",
        }
        # Noise already occupies slot #2 before drill; without keep_hub the hub
        # can fall to #3 after leaf insert-ahead.
        out = apply_leaf_drilldown(
            ["hub-appsec", "noise-cre", "other-noise"],
            "Section: Encode output near interpreter context",
            parent_index=parents,
            cre_texts=cre_texts,
            score_fn=_score_by_doc_token,
            keep_hub_in_top2=True,
        )
        self.assertEqual(out[0], "leaf-encode")
        self.assertIn("hub-appsec", out[:2])


class ResourceGrainHelpersTest(unittest.TestCase):
    def test_family_key_b2_and_github(self) -> None:
        self.assertEqual(
            resource_family_key("art:B2/owasp_top10_2025:A01"),
            "art:B2/owasp_top10_2025",
        )
        self.assertEqual(
            resource_family_key("art:OWASP/ASVS:5.0/en/x.md"),
            "art:OWASP/ASVS",
        )

    def test_count_and_fine_grained(self) -> None:
        counts = count_resource_families(
            [
                "art:B2/owasp_top10_2025:A01",
                "art:B2/owasp_top10_2025:A02",
                "art:OWASP/ASVS:a.md",
            ]
            + [f"art:OWASP/ASVS:{i}.md" for i in range(25)]
        )
        self.assertEqual(counts["art:B2/owasp_top10_2025"], 2)
        self.assertGreaterEqual(counts["art:OWASP/ASVS"], 20)
        self.assertFalse(resource_is_fine_grained(2, 20))
        self.assertTrue(resource_is_fine_grained(26, 20))
        self.assertTrue(resource_is_fine_grained(1, 1))


class ResourceAllowsLeafDrilldownTest(unittest.TestCase):
    def test_empty_or_star_allows_all(self) -> None:
        self.assertTrue(
            resource_allows_leaf_drilldown(
                artifact_id="art:B2/owasp_top10_2025:A01",
                text="Standard: OWASP Top 10",
                allowed=(),
            )
        )
        self.assertTrue(
            resource_allows_leaf_drilldown(
                artifact_id="art:B2/owasp_top10_2025:A01",
                text="",
                allowed=("*",),
            )
        )

    def test_asvs_artifact_allowed(self) -> None:
        self.assertTrue(
            resource_allows_leaf_drilldown(
                artifact_id="art:OWASP/ASVS:5.0/en/0x10.md",
                text="Standard: OWASP ASVS\nSection: V1.2.3",
                allowed=("asvs", "aisvs"),
            )
        )

    def test_aisvs_not_matched_by_asvs_token_alone(self) -> None:
        self.assertFalse(
            resource_allows_leaf_drilldown(
                artifact_id="art:OWASP/AISVS:1.0/en/x.md",
                text="Standard: OWASP AISVS",
                allowed=("asvs",),
            )
        )
        self.assertTrue(
            resource_allows_leaf_drilldown(
                artifact_id="art:OWASP/AISVS:1.0/en/x.md",
                text="Standard: OWASP AISVS",
                allowed=("asvs", "aisvs"),
            )
        )

    def test_coarse_top10_denied(self) -> None:
        self.assertFalse(
            resource_allows_leaf_drilldown(
                artifact_id="art:B2/owasp_top10_2025:A01",
                text="Standard: OWASP Top 10 2025",
                allowed=("asvs", "aisvs"),
            )
        )

    def test_standard_header_alone_can_allow(self) -> None:
        self.assertTrue(
            resource_allows_leaf_drilldown(
                artifact_id="art:unknown/source:1",
                text="Standard: OWASP Application Security Verification Standard (ASVS)\n",
                allowed=("asvs",),
            )
        )

    def test_api_token_matches_b2_api_fixture(self) -> None:
        self.assertTrue(
            resource_allows_leaf_drilldown(
                artifact_id="art:B2/owasp_api_top10_2023:API4",
                text="Standard: OWASP API Security Top 10",
                allowed=("api",),
            )
        )
        self.assertFalse(
            resource_allows_leaf_drilldown(
                artifact_id="art:B2/owasp_top10_2025:A01",
                text="Standard: OWASP Top 10 2025",
                allowed=("api",),
            )
        )


if __name__ == "__main__":
    unittest.main()
