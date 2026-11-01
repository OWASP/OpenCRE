"""Dataclasses for the OWASP metadata index."""

from __future__ import annotations

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
    source: str = ""  # nest | github
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
