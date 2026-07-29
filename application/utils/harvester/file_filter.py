from pathlib import PurePosixPath
from pathlib import Path
import pathspec

DEFAULT_ALLOWED_EXTENSIONS = {
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".adoc",
}

DEFAULT_EXCLUDE_PATTERNS = tuple(
    line.strip()
    for line in (
        Path(__file__)
        .with_name("exclude_patterns.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    if line.strip() and not line.lstrip().startswith("#")
)


class FileFilter:
    def __init__(
        self,
        exclude_patterns: list[str] | None = None,
        allowed_extensions: set[str] | None = None,
    ):
        self.exclude_patterns: list[str] = (
            list(DEFAULT_EXCLUDE_PATTERNS)
            if exclude_patterns is None
            else list(exclude_patterns)
        )

        self.allowed_extensions: set[str] = (
            set(DEFAULT_ALLOWED_EXTENSIONS)
            if allowed_extensions is None
            else set(allowed_extensions)
        )

        self._validate_patterns()

        try:
            self._exclude_spec = pathspec.PathSpec.from_lines(
                "gitignore",
                self.exclude_patterns,
            )
        except Exception as exc:
            raise ValueError("Invalid exclude glob") from exc

    def _validate_patterns(self) -> None:
        if any(not pattern for pattern in self.exclude_patterns):
            raise ValueError("Exclude pattern cannot be empty")

    def _normalize_path(self, file_path: str) -> str:
        return PurePosixPath(file_path).as_posix()

    def is_excluded_by_pattern(self, file_path: str) -> bool:
        normalized = self._normalize_path(file_path)
        return self._exclude_spec.match_file(normalized)

    def is_allowed_extension(self, file_path: str) -> bool:
        return any(
            file_path.endswith(extension) for extension in self.allowed_extensions
        )

    def filter_files(self, files: list[str]) -> list[str]:
        filtered = []

        for file_path in files:
            if self.is_excluded_by_pattern(file_path):
                continue

            if not self.is_allowed_extension(file_path):
                continue

            filtered.append(file_path)

        return filtered
