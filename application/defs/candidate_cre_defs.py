import re
from dataclasses import dataclass


@dataclass
class CandidateCRE:
    """Represents a single CRE candidate match for a CheatsheetRecord."""

    cre_id: str
    name: str
    description: str
    score: float

    def __post_init__(self):
        for field_name, value in [("cre_id", self.cre_id), ("name", self.name)]:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"CandidateCRE: field '{field_name}' must be a non-empty string"
                )

        # description is optional in CRE DB model, empty string allowed.
        if not isinstance(self.description, str):
            raise ValueError("CandidateCRE: field 'description' must be a string")

        if not re.match(r"\d{3}-\d{3}", self.cre_id):
            raise ValueError(
                f"CandidateCRE: field 'cre_id' must match pattern 'NNN-NNN', got {self.cre_id!r}"
            )

        if not isinstance(self.score, float):
            raise ValueError("CandidateCRE: field 'score' must be a float")

        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"CandidateCRE: field 'score' must be between 0.0 and 1.0, got {self.score}"
            )

        self.cre_id = self.cre_id.strip()
        self.name = self.name.strip()
        self.description = self.description.strip()
