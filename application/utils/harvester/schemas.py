from cre_logging import get_logger

logger = get_logger(__name__)

from typing import Any, Literal, Optional
import re
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


_CRON_ATOM = r"(?:\*(?:/\d+)?|\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)"
CRON_RE = re.compile(rf"^{_CRON_ATOM}(?:\s+{_CRON_ATOM}){{4}}$")


def validate_cron_line(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not CRON_RE.fullmatch(text):
        raise ValueError(
            "cron must be a 5-field line (minute hour day-of-month month weekday)"
        )
    return text


# What an OWASP org repo is for. ``standard``/``project``/``other`` feed the
# knowledge-graph expansion path (harvest -> filter -> Librarian); ``chapter``
# and ``event`` repos only feed the OWASP agent's metadata index.
RepoKind = Literal["standard", "project", "chapter", "event", "other"]
HARVESTABLE_KINDS: tuple[str, ...] = ("standard", "project", "other")
# What a harvest run visits when the caller names no kinds: the curated standards
# only, as before repos.yaml covered the whole org. Scheduled runs ask for
# HARVESTABLE_KINDS explicitly.
DEFAULT_HARVEST_KINDS: tuple[str, ...] = ("standard",)


# this will control which repo paths are included and excluded during ingestions
class PathRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(
        ...,
        min_length=1,
        description="Glob patterns to include during ingestions",
    )
    exclude: list[str] = Field(
        default_factory=list, description="Glob patterns to exclude during ingestions"
    )


# this will define how the harvested data should be chunked before downstream
class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal[
        "markdown_heading", "html_readability", "fixed_size", "docling"
    ] = Field(
        ...,
        description="Chunking strategy used for text segmentation",
    )

    max_tokens: int = Field(..., gt=0, description="max token size per chunk")

    overlap_tokens: int = Field(
        ge=0,
        default=20,
        description="token overlap between adjacent chunks",
    )

    # A.2 merge — one algorithm; profiles only set defaults for these knobs.
    merge_profile: Literal["none", "requirements", "narrative"] = Field(
        default="none",
        description=(
            "A.2 merge profile: none=disabled; requirements=split on "
            "requirement ids; narrative=cheat-sheet-like "
            "(merge under the same heading up to max_tokens)."
        ),
    )
    merge_min_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Merge undersized siblings under the same heading (profile default if omitted).",
    )
    merge_max_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Cap for a merged chunk (defaults to max_tokens).",
    )
    split_on_requirement_id: bool | None = Field(
        default=None,
        description=(
            "Do not merge across different requirement ids "
            "(ASVS V2.1.1, NIST AC-2, ISO A.5.1, PCI 3.4, …)."
        ),
    )
    requirement_extract: Literal["off", "auto", "on"] = Field(
        default="auto",
        description=(
            "Requirement extractor: auto (default)=only when "
            "requirements_needed(text) (ASVS-style tables / dense control "
            "catalogs); on=always try; off=never. When extraction yields "
            "segments, they replace primary chunks for that document. "
            "Narrative sources (cheat sheets) usually no-op under auto."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def apply_merge_profile_defaults(cls, data: object) -> object:
        """Fill merge knobs from ``merge_profile`` when left unset."""
        if not isinstance(data, dict):
            return data
        profile = data.get("merge_profile") or "none"
        max_tokens = int(data.get("max_tokens") or 1200)

        def _fill(key: str, value: object) -> None:
            if data.get(key) is None:
                data[key] = value

        if profile == "none":
            _fill("merge_min_tokens", 0)
            _fill("merge_max_tokens", max_tokens)
            _fill("split_on_requirement_id", False)
        elif profile == "requirements":
            _fill("merge_min_tokens", 100)
            _fill("merge_max_tokens", max_tokens)
            _fill("split_on_requirement_id", True)
        else:  # narrative
            _fill("merge_min_tokens", 400)
            _fill("merge_max_tokens", max_tokens)
            _fill("split_on_requirement_id", False)
        return data

    @model_validator(mode="after")
    def overlap_must_be_less_than_max(self) -> "ChunkingConfig":
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError(
                f"overlap_tokens ({self.overlap_tokens}) must be less than "
                f"max_tokens ({self.max_tokens})"
            )
        merge_max = (
            self.merge_max_tokens
            if self.merge_max_tokens is not None
            else self.max_tokens
        )
        merge_min = self.merge_min_tokens if self.merge_min_tokens is not None else 0
        if merge_min > 0 and merge_min >= merge_max:
            raise ValueError(
                f"merge_min_tokens ({merge_min}) must be < merge_max_tokens ({merge_max})"
            )
        return self


# this one defines repository synchronize behaviour
class PollingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["full", "incremental"] = Field(
        ..., description="repository sync mode"
    )

    interval_minutes: int = Field(..., gt=0, description="polling interval in minutes")


# top level repository ingestion configuration
class RepositoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        description="unique repository identifier.",
    )

    type: Literal["github"] = Field(
        ...,
        description="repository source type.",
    )
    kind: RepoKind = Field(
        default="standard",
        description="what the repository is; routes it to the harvest or metadata path.",
    )
    enabled: bool = Field(
        default=True,
        description="whether ingestion is enabled for this repository.",
    )
    owner: str = Field(
        ...,
        min_length=1,
        description="repository organization.",
    )
    repo: str = Field(
        ...,
        min_length=1,
        description="repository name.",
    )
    branch: str = Field(
        default="main",
        min_length=1,
        description="Repository branch to ingest.",
    )

    paths: PathRules
    chunking: ChunkingConfig
    polling: PollingConfig
    cron: Optional[str] = Field(
        default=None,
        description="5-field cron for how often this repository is ingested.",
    )

    @field_validator("cron")
    @classmethod
    def cron_line(cls, value: Optional[str]) -> Optional[str]:
        return validate_cron_line(value)


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(
        ..., min_length=1, description="github.com/org/ or github.com/org/repo"
    )
    cron: Optional[str] = Field(
        default=None,
        description="5-field cron for how often this source is ingested.",
    )
    enabled: bool = Field(default=True)

    @field_validator("cron")
    @classmethod
    def cron_line(cls, value: Optional[str]) -> Optional[str]:
        return validate_cron_line(value)


# Root configuration object loaded from repos.yaml / targets.yaml.
class ReposFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-kind field defaults merged under each repository entry "
            "(an explicit entry value wins), so org-wide files stay compact."
        ),
    )
    sources: list[SourceConfig] = Field(
        default_factory=list,
        description="GitHub org or repo URLs (github.com/OWASP/). "
        "Orgs are expanded by the indexer, not at save time.",
    )
    repositories: list[RepositoryConfig] = Field(
        default_factory=list,
        description="OpenCRE harvest overrides (paths/chunking). Optional when sources is set.",
    )

    @model_validator(mode="before")
    @classmethod
    def apply_kind_defaults(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        defaults = data.get("defaults") or {}
        repositories = data.get("repositories")
        if not defaults or not isinstance(repositories, list):
            return data
        merged = []
        for entry in repositories:
            if isinstance(entry, dict):
                kind = entry.get("kind") or "standard"
                entry = {**(defaults.get(kind) or {}), **entry}
            merged.append(entry)
        return {**data, "repositories": merged}

    @field_validator("sources", mode="before")
    @classmethod
    def coerce_sources(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        out: list[Any] = []
        for item in value:
            if isinstance(item, str):
                out.append({"url": item})
            else:
                out.append(item)
        return out

    @model_validator(mode="after")
    def sources_or_repositories(self) -> "ReposFile":
        if not self.sources and not self.repositories:
            raise ValueError("sources or repositories is required")
        return self
