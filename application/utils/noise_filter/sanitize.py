"""Module B Stage 1.5: defensive text sanitization.

Adapted from TRACT (https://github.com/rocklambros/TRACT) at
tract/sanitize.py (blob SHA b3feb8781b199252fef4c0e4ac0716c01c5fe4c3,
fetched 2026-06-07). TRACT is licensed under CC0 1.0 Universal (public
domain dedication) -- no attribution legally required, but we credit
explicitly anyway because it's the right thing to do.

Purpose: rescue chunk text whose original source was PDF or HTML, where
Module A's normalization rules couldn't perfectly clean things like:
  - PDF ligatures (ﬀ, ﬁ, ﬂ, ﬃ, ﬄ) left from PDF text extraction
  - Zero-width characters from copy/paste (can shift embedding spaces)
  - Broken hyphenation from PDF line-wrapping ("word-\\nbreak" -> "wordbreak")
  - HTML entities and tags that leaked through

Adaptations from TRACT's version:
  1. We do NOT collapse all whitespace. TRACT's pipeline ends with
     `re.sub(r"\\s+", " ", text)` which flattens newlines too -- that's
     right for embedding-similarity use cases but destroys the structure
     Module A's contract preserves (code fences, paragraph breaks). The
     LLM benefits from that structure. We keep the line-level layout.
  2. Drop TRACT's max_length / return_full machinery -- Module B controls
     chunk truncation separately at the LLM classifier in Week 3.
  3. Drop TRACT's sanitize_control(dict) helper -- it's TRACT's domain
     model (controls have title/description/full_text fields), not ours.

Idempotency: sanitize_text(sanitize_text(x)) == sanitize_text(x). For
clean Module A output, the function is effectively a no-op (all
transformations are guards, not state changes).
"""

from __future__ import annotations

import html
import re
import unicodedata

# PDF ligature replacements. Order matters: longer ligatures first to
# avoid partial replacement (e.g. ﬄ -> ffl must come before ﬀ -> ff).
_LIGATURE_MAP: list[tuple[str, str]] = [
    ("ﬄ", "ffl"),  # ﬄ
    ("ﬃ", "ffi"),  # ﬃ
    ("ﬀ", "ff"),  # ﬀ
    ("ﬁ", "fi"),  # ﬁ
    ("ﬂ", "fl"),  # ﬂ
]

# word-\nword continuation from PDF line-wrapping. Matches "foo-\nbar" -> "foobar".
_HYPHEN_BREAK_RE: re.Pattern[str] = re.compile(r"(\w)-\n(\w)")

# HTML/XML tags. <p>, </script>, <br/>, etc. Doesn't match `<` followed by space.
_HTML_TAG_RE: re.Pattern[str] = re.compile(r"</?[a-zA-Z][^>]*>")

# Zero-width characters that shift embedding spaces but render invisibly:
# ZWSP (U+200B), ZWNJ (U+200C), ZWJ (U+200D), BOM/ZWNBSP (U+FEFF).
# Escapes are used instead of literal codepoints so the source is grep-able
# and lint tools (Ruff PLE2515) don't flag invisible characters.
_ZERO_WIDTH_RE: re.Pattern[str] = re.compile("[\u200B\u200C\u200D\uFEFF]")


def _strip_null_bytes(text: str) -> str:
    """Replace null bytes with spaces (avoid concatenating adjacent tokens)."""
    return text.replace("\x00", " ")


def _normalize_unicode(text: str) -> str:
    """Normalize to Unicode NFC form for consistent byte representation."""
    return unicodedata.normalize("NFC", text)


def _strip_zero_width(text: str) -> str:
    """Remove zero-width characters that can shift embedding spaces."""
    return _ZERO_WIDTH_RE.sub("", text)


def strip_html(text: str) -> str:
    """Unescape HTML entities, then remove HTML/XML tags.

    Unescape first so double-encoded tags (e.g., &lt;script&gt;) are decoded
    and then stripped -- otherwise the literal tag text would survive.
    """
    unescaped = html.unescape(text)
    return _HTML_TAG_RE.sub("", unescaped)


def _fix_ligatures(text: str) -> str:
    """Replace common PDF ligature characters with ASCII equivalents."""
    for ligature, replacement in _LIGATURE_MAP:
        text = text.replace(ligature, replacement)
    return text


def _fix_hyphenation(text: str) -> str:
    """Rejoin words broken by PDF line-wrapping (word-\\nword -> wordword)."""
    return _HYPHEN_BREAK_RE.sub(r"\1\2", text)


def sanitize_text(text: str) -> str:
    """Run the defensive sanitization pipeline on a text field.

    Pipeline (in order):
      1. Strip null bytes
      2. Unicode NFC normalization
      3. Strip zero-width characters
      4. HTML unescape + strip tags
      5. Fix PDF ligatures
      6. Fix hyphenated PDF line-breaks
      7. Strip leading/trailing whitespace (line structure preserved)

    Unlike TRACT's original, this does NOT collapse interior whitespace --
    Module A's normalization already governs that, and the LLM benefits
    from preserved structure (paragraph breaks, code fences).

    The function is idempotent: sanitize_text(sanitize_text(x)) == sanitize_text(x).

    Raises:
        ValueError: if the result is empty after all transformations and
            the input was non-empty. Empty input returns empty without raising.
    """
    if not text:
        return text

    cleaned = text
    cleaned = _strip_null_bytes(cleaned)
    cleaned = _normalize_unicode(cleaned)
    cleaned = _strip_zero_width(cleaned)
    cleaned = strip_html(cleaned)
    cleaned = _fix_ligatures(cleaned)
    cleaned = _fix_hyphenation(cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError(
            f"Sanitization produced empty text from non-empty input. "
            f"Original (first 100 chars): {text[:100]!r}"
        )

    return cleaned


__all__ = [
    "sanitize_text",
    "strip_html",
]
