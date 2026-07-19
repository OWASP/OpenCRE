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

    strategy: Literal["markdown_heading", "html_readability", "fixed_size"] = Field(
        ...,
        description="Chunking strategy used for text segmentation",
    )

    max_tokens: int = Field(..., gt=0, description="max token size per chunk")

    overlap_tokens: int = Field(
        ge=0,
        default=20,
        description="token overlap between adjacent chunks",
    )

    @model_validator(mode="after")
    def overlap_must_be_less_than_max(self) -> "ChunkingConfig":
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError(
                f"overlap_tokens ({self.overlap_tokens}) must be less than "
                f"max_tokens ({self.max_tokens})"
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
