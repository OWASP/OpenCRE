"""Marshmallow schemas for OpenCRE public REST API documentation (OpenAPI generation)."""

from __future__ import annotations

from marshmallow import Schema, fields, validate

FORMAT_ENUM = ("json", "md", "csv", "oscal")


class FormatQuerySchema(Schema):
    format = fields.Str(
        required=False,
        validate=validate.OneOf(FORMAT_ENUM),
        metadata={"description": "Response format (default: json)"},
    )


class FindCREQuerySchema(FormatQuerySchema):
    source = fields.Str(
        required=False,
        metadata={
            "description": "Integration source identifier for metrics, e.g. wstg"
        },
    )
    include_only = fields.List(
        fields.Str(),
        required=False,
        metadata={"description": "Filter returned fields"},
    )


class CREResponseSchema(Schema):
    data = fields.Dict(
        keys=fields.Str(),
        values=fields.Raw(),
        metadata={"description": "CRE document"},
    )


class NodeListResponseSchema(Schema):
    total_pages = fields.Int(allow_none=True)
    page = fields.Int(allow_none=True)
    standards = fields.List(fields.Dict(keys=fields.Str(), values=fields.Raw()))


class DataListResponseSchema(Schema):
    data = fields.List(fields.Dict(keys=fields.Str(), values=fields.Raw()))
    page = fields.Int(
        required=False,
        metadata={"description": "Current 1-based page (when pagination is applied)"},
    )
    total_pages = fields.Int(
        required=False,
        metadata={
            "description": "Total pages for the result set (when pagination is applied)"
        },
    )


class TagQuerySchema(FormatQuerySchema):
    tag = fields.List(
        fields.Str(),
        required=True,
        metadata={"description": "Tag name(s)"},
    )
    page = fields.Int(
        required=False,
        metadata={"description": "1-based page number for paginated results"},
    )
    items_per_page = fields.Int(
        required=False,
        metadata={"description": "Number of items per page (capped server-side)"},
    )


class TextSearchQuerySchema(FormatQuerySchema):
    text = fields.Str(required=True, metadata={"description": "Search query"})
    page = fields.Int(
        required=False,
        metadata={"description": "1-based page number for paginated results"},
    )
    items_per_page = fields.Int(
        required=False,
        metadata={"description": "Number of items per page (capped server-side)"},
    )


class NodeQuerySchema(FormatQuerySchema):
    section = fields.Str(required=False)
    subsection = fields.Str(required=False)
    sectionID = fields.Str(required=False)
    page = fields.Int(required=False)
    items_per_page = fields.Int(required=False)
    version = fields.Str(required=False)
    hyperlink = fields.Str(required=False)
    include_only = fields.List(fields.Str(), required=False)


class MapAnalysisQuerySchema(Schema):
    standard = fields.List(
        fields.Str(),
        required=True,
        validate=validate.Length(min=2, max=2),
        metadata={"description": "Exactly two standard names"},
    )


class MapAnalysisWeakLinksQuerySchema(Schema):
    standard = fields.List(
        fields.Str(),
        required=True,
        validate=validate.Length(min=2, max=2),
    )
    key = fields.Str(required=True, metadata={"description": "Gap-analysis cache key"})


class JobResultsQuerySchema(Schema):
    id = fields.Str(required=True, metadata={"description": "Background job id"})


class MapAnalysisResponseSchema(Schema):
    result = fields.Raw(metadata={"description": "Gap analysis result payload"})


class JobStatusResponseSchema(Schema):
    status = fields.Str()
    result = fields.Raw(required=False)


class HealthResponseSchema(Schema):
    ok = fields.Bool()
    cre_count = fields.Int(required=False)
    standards_count = fields.Int(required=False)
    message = fields.Str(required=False)


class AllCREsQuerySchema(Schema):
    page = fields.Int(required=False)
    per_page = fields.Int(required=False)


class AllCREsResponseSchema(Schema):
    data = fields.List(fields.Dict(keys=fields.Str(), values=fields.Raw()))
    page = fields.Int()
    total_pages = fields.Int()


class ConfigResponseSchema(Schema):
    CRE_ALLOW_IMPORT = fields.Bool()


class ErrorSchema(Schema):
    message = fields.Str(required=False)
    error = fields.Str(required=False)
