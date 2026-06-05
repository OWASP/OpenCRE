from dataclasses import dataclass, field
from typing import Dict, List

SUMMARY_MAX_LENGTH = 500


@dataclass
class CheatsheetRecord:
    """Structured representation of an OWASP cheatsheet record."""

    source: str = field(default="owasp_cheatsheets", init=False)
    source_id: str
    title: str
    hyperlink: str
    summary: str
    headings: List[str]
    raw_markdown_path: str
    category_hints: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize and validate CheatsheetRecord fields."""

        required_str_fields = {
            "source_id": self.source_id,
            "title": self.title,
            "hyperlink": self.hyperlink,
            "summary": self.summary,
            "raw_markdown_path": self.raw_markdown_path,
        }

        # Summary-specific normalization
        self.summary = self.summary.strip()[:SUMMARY_MAX_LENGTH]

        # Normalize fields which require string values.
        for field_name, value in required_str_fields.items():
            if isinstance(value, str):
                setattr(self, field_name, value.strip())

        list_str_fields = {
            "headings": self.headings,
            "category_hints": self.category_hints,
        }

        # Validate fields which require string values.
        for field_name in required_str_fields:  
            value = getattr(self, field_name)

            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"CheatsheetRecord: field '{field_name}' "
                    f"must be a non-empty string, got {value!r}"
                )

        # Validate fields which require list[str] values.
        for field_name, value in list_str_fields.items():
            if not isinstance(value, list):
                raise ValueError(
                    f"CheatsheetRecord: field '{field_name}' "
                    f"must be a list[str], got {type(value)!r}"
                )

            for item in value:
                if not isinstance(item, str):
                    raise ValueError(
                        f"CheatsheetRecord: value of '{field_name}' "
                        f"must be a string, got {item!r}"
                    )

        # Validate input for metadata.
        if not isinstance(self.metadata, dict):
            raise ValueError(
                "CheatsheetRecord: field 'metadata' must be a dict[str, str]"
            )

        for key, value in self.metadata.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    "CheatsheetRecord: metadata keys and values must be strings, "
                    f"got {key!r}: {value!r}"
                )
