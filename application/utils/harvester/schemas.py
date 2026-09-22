from cre_logging import get_logger

logger = get_logger(__name__)

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


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


# Root configuration object loaded from repos.yaml.
class ReposFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repositories: list[RepositoryConfig] = Field(
        ...,
        min_length=1,
        description="List of repositories configured for ingestion.",
    )
