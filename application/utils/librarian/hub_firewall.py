"""TRACT-style hub-firewall for honest evaluation.

Many golden standards (ASVS, WSTG, ...) are already linked into OpenCRE, so the
CRE "hub" representation can contain the exact text under test — retrieval then
echoes it back and inflates accuracy. Before scoring a row, strip that row's
text from the hub.

The real CRE vector hub arrives W3; W1 models the hub as (cre_id, text) reps so
the methodology and its test exist before any accuracy number is claimed.
"""

import re
from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class HubRep:
    cre_id: str
    text: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def leaks(row_text: str, hub: Iterable[HubRep]) -> bool:
    """True if any hub rep contains the row's text (i.e. would leak)."""
    needle = _norm(row_text)
    if not needle:
        return False
    return any(needle in _norm(rep.text) for rep in hub)


def firewall(row_text: str, hub: Iterable[HubRep]) -> List[HubRep]:
    """Return the hub with every rep echoing row_text removed."""
    needle = _norm(row_text)
    if not needle:
        return list(hub)
    return [rep for rep in hub if needle not in _norm(rep.text)]
