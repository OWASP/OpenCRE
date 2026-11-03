"""Approval table writers for proposed CRE descriptions."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence, Tuple

APPROVAL_COLUMNS: Tuple[str, ...] = (
    "cre_id",
    "name",
    "proposed_description",
    "grounding_snippet",
    "model",
    "prompt_hash",
)


@dataclass(frozen=True)
class ApprovalRow:
    cre_id: str
    name: str
    proposed_description: str
    grounding_snippet: str
    model: str
    prompt_hash: str


def write_approval_csv(path: Path, rows: Sequence[ApprovalRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(APPROVAL_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_approval_markdown(path: Path, rows: Sequence[ApprovalRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "| " + " | ".join(APPROVAL_COLUMNS) + " |",
        "| " + " | ".join("---" for _ in APPROVAL_COLUMNS) + " |",
    ]
    for row in rows:
        data = asdict(row)
        cells = [_md_cell(str(data[col])) for col in APPROVAL_COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


__all__ = [
    "APPROVAL_COLUMNS",
    "ApprovalRow",
    "write_approval_csv",
    "write_approval_markdown",
]
