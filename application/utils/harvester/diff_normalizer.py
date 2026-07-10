import textacy.preprocessing as prep

from .models import DiffBlock


class DiffNormalizer:
    def normalize_line(self, line: str) -> str:
        line = prep.normalize.unicode(line)
        line = prep.normalize.whitespace(line)
        return line.strip()

    def normalize(self, blocks: list[DiffBlock]) -> list[DiffBlock]:
        normalized: list[DiffBlock] = []

        for block in blocks:
            cleaned_lines: list[str] = []

            for line in block.added_lines:
                line = self.normalize_line(line)

                if not line:
                    continue

                cleaned_lines.append(line)

            normalized.append(
                DiffBlock(
                    file_path=block.file_path,
                    added_lines=cleaned_lines,
                )
            )

        return normalized
