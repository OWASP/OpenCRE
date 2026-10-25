import unittest
from types import SimpleNamespace as H

from application.utils.comprehension import authority
from application.utils.comprehension.retrieve import _slug_of


def hit(slug, score, n=0):
    return H(url=f"owasp-agent://evidence/comprehension-{slug}-raw-{n}", score=score)


class TestAuthority(unittest.TestCase):
    def setUp(self):
        self._orig = authority.weights
        self.addCleanup(lambda: setattr(authority, "weights", self._orig))

    def test_validate_drops_neutral_and_rejects_bad_values(self):
        self.assertEqual(
            authority.validate({"a": 1, "b": "1.2", "c": 0}), {"b": 1.2, "c": 0.0}
        )
        for bad in ({"a": 5}, {"a": -1}, {"a": "x"}, {"a": True}, {"": 1.1}, [1]):
            with self.assertRaises(ValueError):
                authority.validate(bad)

    def test_bias_reorders_and_hides(self):
        authority.weights = lambda fresh=False: {"aix": 1.3, "noisy": 0.0}
        hits = [hit("aisvs", 0.70), hit("noisy", 0.69), hit("aix", 0.60)]
        out = authority.bias(hits, _slug_of)
        self.assertEqual([_slug_of(h) for h in out], ["aix", "aisvs"])

    def test_bias_is_a_noop_without_weights(self):
        authority.weights = lambda fresh=False: {}
        hits = [hit("a", 0.5), hit("b", 0.4)]
        self.assertEqual(authority.bias(hits, _slug_of), hits)

    def test_diversify_gives_each_top_project_a_share(self):
        hits = [hit("aisvs", 0.9, i) for i in range(8)] + [
            hit("aix", 0.5, 0),
            hit("llm", 0.4, 0),
        ]
        out = authority.diversify(hits, _slug_of, projects=3, per=2)
        self.assertEqual(
            [_slug_of(h) for h in out[:4]], ["aisvs", "aisvs", "aix", "llm"]
        )
        self.assertEqual(len(out), len(hits))

    def test_diversify_leaves_single_project_results_alone(self):
        hits = [hit("a", 0.9, i) for i in range(3)]
        self.assertEqual(authority.diversify(hits, _slug_of), hits)


if __name__ == "__main__":
    unittest.main()
