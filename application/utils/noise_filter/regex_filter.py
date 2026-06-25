"""Module B Stage 1: path-based noise filter.

Checks each ChangeRecord's `locator.path` against a YAML-driven blocklist
(extensions, filenames, path globs) with allow-overrides. Patterns live in
`noise_patterns.yaml` so contributors can extend coverage without code
changes.

Per the recall-first rule (agreed with maintainer 2026-06-01), Stage 1 is
deliberately CONSERVATIVE -- it should only block paths where we're
highly confident no security content lives there. When in doubt, the
path passes through to Stage 1.5 (sanitize) + Stage 2 (LLM classifier).

Usage:
    filt = RegexFilter()
    for rec in records:
        is_noise, reason = filt.is_noise_record(rec)
        if is_noise:
            audit_log(rec.chunk_id, reason)
        else:
            yield rec

Or via the convenience generator:

    accepted = list(RegexFilter().filter_records(records))
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, Iterator, Optional

import yaml

from application.utils.noise_filter.schemas import ChangeRecord

DEFAULT_PATTERNS_PATH = Path(__file__).parent / "noise_patterns.yaml"


class RegexFilter:
    """Path-based noise filter driven by `noise_patterns.yaml`.

    The instance compiles patterns once at construction; `is_noise_*` calls
    are O(deny rules) per path. For typical OWASP-shaped inputs the constant
    is tiny so this is effectively O(1) per record.

    Attributes are populated from the YAML file and are publicly readable for
    tests and introspection.
    """

    def __init__(self, patterns_path: Optional[Path] = None) -> None:
        path = Path(patterns_path) if patterns_path else DEFAULT_PATTERNS_PATH
        data = yaml.safe_load(path.read_text()) or {}
        self.deny_extensions: tuple[str, ...] = tuple(data.get("deny_extensions") or [])
        self.deny_filenames: frozenset[str] = frozenset(
            data.get("deny_filenames") or []
        )
        self.deny_paths: tuple[str, ...] = tuple(data.get("deny_paths") or [])
        self.allow_overrides: tuple[str, ...] = tuple(data.get("allow_overrides") or [])
        self.patterns_path: Path = path

    def is_noise_path(self, path: str) -> tuple[bool, str]:
        """Check a file path against the deny rules.

        Returns:
            (is_noise, reason). `reason` is empty when the path is accepted.
            Reasons are short, machine-readable tags for audit logs:
                "allow_override: <pattern>"
                "deny_extension: <ext>"
                "deny_filename: <basename>"
                "deny_path: <glob>"

        Rule precedence:
            1. allow_overrides win (a matching override forces NOT noise).
            2. deny_extensions
            3. deny_filenames
            4. deny_paths
        """
        # 1. Allow-overrides take precedence over any deny rule.
        for pattern in self.allow_overrides:
            if fnmatch(path, pattern):
                return (False, "")

        # 2. Extension check.
        for ext in self.deny_extensions:
            if path.endswith(ext):
                return (True, f"deny_extension: {ext}")

        # 3. Basename check.
        basename = path.rsplit("/", 1)[-1]
        if basename in self.deny_filenames:
            return (True, f"deny_filename: {basename}")

        # 4. Path glob check.
        for pattern in self.deny_paths:
            if fnmatch(path, pattern):
                return (True, f"deny_path: {pattern}")

        return (False, "")

    def is_noise_record(self, record: ChangeRecord) -> tuple[bool, str]:
        """Check a ChangeRecord by its `locator.path`."""
        return self.is_noise_path(record.locator.path)

    def filter_records(self, records: Iterable[ChangeRecord]) -> Iterator[ChangeRecord]:
        """Yield records whose path is NOT noise. Lazy generator."""
        for record in records:
            is_noise, _ = self.is_noise_record(record)
            if not is_noise:
                yield record


__all__ = [
    "DEFAULT_PATTERNS_PATH",
    "RegexFilter",
]
