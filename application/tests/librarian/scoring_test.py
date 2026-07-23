import unittest

from application.utils.librarian.scoring import jaccard, score_case


class TestScoring(unittest.TestCase):
    def test_jaccard_values(self):
        self.assertEqual(jaccard([], []), 1.0)
        self.assertEqual(jaccard(["a"], []), 0.0)
        self.assertEqual(jaccard(["a", "b"], ["a", "b"]), 1.0)
        self.assertEqual(jaccard(["a", "b"], ["a"]), 0.5)

    def test_exact_match_is_correct(self):
        self.assertTrue(score_case(["a", "b"], ["a", "b"]))

    def test_jaccard_boundary_with_top1_in_set_is_correct(self):
        # expected {a,b}, predicted [a,c] -> jaccard = 1/3 < 0.5 -> incorrect
        self.assertFalse(score_case(["a", "b"], ["a", "c"]))
        # expected {a,b,c}, predicted [a,b] -> jaccard = 2/3 >= 0.5, top1 in set
        self.assertTrue(score_case(["a", "b", "c"], ["a", "b"]))

    def test_top1_outside_set_is_incorrect(self):
        # jaccard >= 0.5 but top-1 (z) not expected
        self.assertFalse(score_case(["a", "b"], ["z", "a", "b"]))

    def test_empty_prediction(self):
        self.assertTrue(score_case([], []))
        self.assertFalse(score_case(["a"], []))


if __name__ == "__main__":
    unittest.main()
