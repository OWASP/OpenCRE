from cre_logging import get_logger

logger = get_logger(__name__)

from datetime import datetime

from .models import DiffBlock

_DIFF_GIT_PREFIX = "diff --git "


def _decode_quoted_path(quoted_body: str) -> str:
    """
    Decode the body of a git C-quoted path.

    With ``core.quotePath`` enabled (the default) git escapes every non-ASCII
    byte in octal, so ``café.md`` arrives as ``"caf\\303\\251.md"``. With it
    disabled git leaves those bytes raw but still escapes characters such as
    ``"`` and ``\\``, so a quoted path can mix raw UTF-8 with C escapes. Both
    forms have to survive decoding.
    """
    # Recover the bytes git actually emitted; raw non-ASCII stays intact here
    # instead of being flattened into an ASCII escape.
    raw = quoted_body.encode("utf-8")

    # latin-1 is a lossless 1:1 byte<->character map, so the C escapes can be
    # decoded as text without discarding any non-ASCII byte.
    decoded = (
        raw.decode("latin-1")
        .encode("ascii", "backslashreplace")
        .decode("unicode_escape")
    )

    # The decoded characters are byte values; read them back as UTF-8.
    return decoded.encode("latin-1").decode("utf-8", errors="replace")


def _split_quoted_header(remainder: str) -> list[str]:
    """Return the C-quoted path bodies from a quoted ``diff --git`` header."""
    parts: list[str] = []
    index = 0

    while index < len(remainder):
        if remainder[index] != '"':
            index += 1
            continue

        cursor = index + 1
        body: list[str] = []

        while cursor < len(remainder):
            char = remainder[cursor]
            if char == "\\" and cursor + 1 < len(remainder):
                body.append(remainder[cursor : cursor + 2])
                cursor += 2
                continue
            if char == '"':
                break
            body.append(char)
            cursor += 1

        parts.append("".join(body))
        index = cursor + 1

    return parts


def _strip_side_prefix(path: str, prefix: str) -> str | None:
    return path[len(prefix) :] if path.startswith(prefix) else None


def _parse_header_path(line: str) -> str | None:
    """
    Extract the file path from a ``diff --git a/<path> b/<path>`` header.

    The header is ambiguous when parsed naively: a path may itself contain the
    ``" b/"`` separator sequence, and quoted paths do not start with a bare
    ``a/`` at all. Both cases are handled here rather than by regex.
    """
    remainder = line[len(_DIFF_GIT_PREFIX) :]
    if not remainder:
        return None

    if remainder.startswith('"'):
        quoted = _split_quoted_header(remainder)
        for candidate, prefix in ((quoted[-1:], "b/"), (quoted[:1], "a/")):
            if candidate:
                side = _strip_side_prefix(candidate[0], prefix)
                if side is not None:
                    return _decode_quoted_path(side)
        return None

    if not remainder.startswith("a/"):
        return None

    # Outside of renames both sides name the same path, so the header is
    # exactly ``a/<path> b/<path>``. That symmetry pins down the path length
    # without having to guess which " b/" is the separator.
    body_length = len(remainder) - len("a/") - len(" b/")
    if body_length > 0 and body_length % 2 == 0:
        candidate = remainder[2 : 2 + body_length // 2]
        if remainder == f"a/{candidate} b/{candidate}":
            return candidate

    # Renamed file: the two sides differ, so fall back to the b-side, which is
    # where any added lines live.
    separator = remainder.rfind(" b/")
    if separator > len("a/"):
        return remainder[separator + len(" b/") :] or None

    return None


def _parse_side_path(line: str, prefix: str) -> str | None:
    """
    Extract the path from a ``--- a/<path>`` or ``+++ b/<path>`` header line.

    These lines carry a single path each, so they are unambiguous and are
    preferred over the combined ``diff --git`` header when present.
    """
    target = line[4:].split("\t", 1)[0]
    if not target or target == "/dev/null":
        return None

    if target.startswith('"') and target.endswith('"') and len(target) > 1:
        side = _strip_side_prefix(target[1:-1], prefix)
        return _decode_quoted_path(side) if side is not None else None

    return _strip_side_prefix(target, prefix)


class DiffParser:
    """
    Parses unified git diffs into DiffBlock objects.

    Only added lines are extracted.
    Deleted lines and diff metadata are ignored.
    """

    def parse(
        self, diff: str, repository: str, commit_sha: str, committed_at: datetime
    ) -> list[DiffBlock]:
        """
        Convert a unified git diff into DiffBlock objects.
        """
        blocks: list[DiffBlock] = []

        current_file: str | None = None
        added_lines: list[str] = []
        in_hunk = False

        for line in diff.splitlines():
            if line.startswith(_DIFF_GIT_PREFIX):
                if current_file is not None:
                    blocks.append(
                        DiffBlock(
                            file_path=current_file,
                            added_lines=added_lines,
                            repository=repository,
                            commit_sha=commit_sha,
                            committed_at=committed_at,
                        )
                    )

                current_file = _parse_header_path(line)
                added_lines = []
                in_hunk = False

                continue

            # ``---``/``+++`` are file headers only before the first hunk; once
            # inside a hunk a line such as ``+++ foo`` is added content.
            if not in_hunk and line.startswith("+++ "):
                side_path = _parse_side_path(line, "b/")
                if side_path is not None:
                    current_file = side_path
                continue

            if not in_hunk and line.startswith("--- "):
                continue

            if line.startswith("@@"):
                in_hunk = True
                continue

            if line.startswith("+"):
                added_lines.append(line[1:])

        if current_file is not None:
            blocks.append(
                DiffBlock(
                    file_path=current_file,
                    added_lines=added_lines,
                    repository=repository,
                    commit_sha=commit_sha,
                    committed_at=committed_at,
                )
            )

        return blocks
