import re

DEFAULT_ALLOWED_EXTENSIONS = {
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".adoc",
}

DEFAULT_EXCLUDE_PATTERNS = [
    r"^\.github/",
    r"^\.git/",
    r"^node_modules/",
    r"^dist/",
    r"^build/",
    r"^coverage/",
    r"^vendor/",
    r".*package-lock\.json$",
    r".*yarn\.lock$",
    r".*pnpm-lock\.yaml$",
]


class FileFilter:
    def __init__(
        self,
        exclude_patterns: list[str] | None = None,
        allowed_extensions: set[str] | None = None,
    ):
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
        self.allowed_extensions = allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS

    def is_excluded_by_pattern(self, file_path: str) -> bool:
        return any(re.search(pattern, file_path) for pattern in self.exclude_patterns)

    def is_allowed_extension(self, file_path: str) -> bool:
        return any(
            file_path.endswith(extension) for extension in self.allowed_extensions
        )

    def filter_files(self, files: list[str]) -> list[str]:
        filtered_files = []

        for file_path in files:
            if self.is_excluded_by_pattern(file_path):
                continue

            if not self.is_allowed_extension(file_path):
                continue

            filtered_files.append(file_path)

        return filtered_files
