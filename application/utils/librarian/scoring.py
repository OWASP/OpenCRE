"""Golden-set scoring for the eval harness.

Implements the multi-link correctness rule. The rule itself (Q-D) is provisional
pending mentor confirmation at the Friday call — keep it isolated here so a
change touches one function only.
"""

from typing import List, Sequence

# TODO(Q-D): provisional default — confirm with mentor before relying on results.
# A predicted set is correct iff Jaccard(expected, predicted) >= 0.5 AND the
# top-1 prediction is in the expected set.
JACCARD_THRESHOLD = 0.5


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def score_case(expected_cre_ids: Sequence[str], predicted_cre_ids: List[str]) -> bool:
    """True if the prediction counts as correct under the Q-D default rule.

    predicted_cre_ids is rank-ordered; index 0 is the top-1 prediction.
    """
    if not predicted_cre_ids:
        return not expected_cre_ids  # correct only if nothing was expected
    if jaccard(expected_cre_ids, predicted_cre_ids) < JACCARD_THRESHOLD:
        return False
    return predicted_cre_ids[0] in set(expected_cre_ids)
