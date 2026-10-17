"""Dataclasses for the OWASP metadata index."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


CONCEPT_CATEGORIES = frozenset(
    {
        "Community",
        "Project",
        "Governance",
        "EventTopic",
        "Committee",
        "Other",
    }
)


@dataclass
class Chapter:
    key: str
    name: str
    country: str = ""
    region: str = ""
    city: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    url: str = ""
    tags: List[str] = field(default_factory=list)
    leaders: List[str] = field(default_factory=list)
    active: Optional[bool] = None
    level: str = ""
    meetings: int = 0
    source: str = ""  # nest | github | site
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Project:
    key: str
    name: str
    level: str = ""
    description: str = ""
    url: str = ""
    tags: List[str] = field(default_factory=list)
    leaders: List[str] = field(default_factory=list)
    source: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    key: str
    name: str
    start_date: str = ""  # ISO date or datetime string
    end_date: str = ""
    chapter_key: str = ""
    city: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    url: str = ""
    description: str = ""
    topics: List[str] = field(default_factory=list)
    talks: List[str] = field(default_factory=list)
    source: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BoardMember:
    year: int
    name: str
    role: str = "member"
    notes: str = ""
    source: str = "github"
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BoardCandidate:
    year: int
    name: str
    notes: str = ""
    statement: str = ""
    url: str = ""
    source: str = "github"
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Concept:
    key: str
    name: str
    category: str
    description: str = ""
    evidence_urls: List[str] = field(default_factory=list)
    entity_keys: List[str] = field(default_factory=list)
    merged_into: str = ""
    source: str = "auto"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QueryResult:
    ok: bool
    kind: str
    data: Any = None
    message: str = ""
    citations: List[str] = field(default_factory=list)
    clarify: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Template/placeholder text that chapter pages put in the "leaders" list.
_NON_NAME_TOKENS = frozenset(
    "location everyone welcome speaker name mailing list calendar google corporate "
    "supporter sponsor exhibit become usual meeting meetings chapter owasp global "
    "join contact email newsletter slack twitter linkedin youtube meetup tbd none "
    "volunteer volunteers needed website update the our your".split()
)


def is_plausible_person_name(value: str) -> bool:
    """True when a leader string looks like a real person (2-5 name-like words)."""
    text = (value or "").strip()
    if not text or re.search(r"[\d@/:_]", text):
        return False
    words = text.replace(".", " ").split()
    if not 2 <= len(words) <= 5:
        return False
    return not any(w.lower().strip(",'") in _NON_NAME_TOKENS for w in words)


def clean_leaders(names: Any) -> List[str]:
    """Drop template noise ('Meeting Location', 'Everyone is welcome') and dupes."""
    out: List[str] = []
    for n in names or []:
        n = str(n).strip()
        if is_plausible_person_name(n) and n not in out:
            out.append(n)
    return out
