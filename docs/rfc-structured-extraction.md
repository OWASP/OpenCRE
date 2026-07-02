# RFC Workstream B — Structured Extraction

This document explains the implementation and behavior of RFC Workstream B
(Structured Extraction) from Cheatsheet to CRE Mapping RFC.

The goal of this module is to convert OWASP Cheat Sheet markdown into a
deterministic structured object that downstream RFC workstreams can consume
for categorization, retrieval, reranking, and mapping generation.

The implementation is primarily located in:

* `cheatsheet_defs.py`
* `cheatsheet_extractor.py`

---

## Sources for more context

* RFC:
  `docs/rfc/cheatsheets-llm-autonomous-mapping-rfc.md`

* Checkpoints B1 & B2 implementation PR:
  `https://github.com/OWASP/OpenCRE/pull/912`

* Checkpoints B3 & B4 implementation PR:
  `https://github.com/OWASP/OpenCRE/pull/921`

---

## What Workstream B implements

**The implementation strictly follows the RFC extraction contract and prioritizes deterministic extraction behavior.**

It defines a typed dataclass named `CheatsheetRecord`.

This object represents the structured extraction result returned from:

```python
extract_cheatsheet_record(markdown, source_path)
```

The extractor parses OWASP Cheat Sheet markdown and returns normalized
structured information about a cheatsheet.

`CheatsheetRecord` contains:

* `source`
* `source_id`
* `title`
* `hyperlink`
* `summary`
* `headings`
* `raw_markdown_path`
* `category_hints`
* `metadata`

---

## Fallback behavior

The extractor contains fallback functions capable of handling incomplete or
malformed markdown containing:

* missing titles,
* missing summary sources,
* malformed headings.

These fallback paths ensure that extraction still returns a valid
`CheatsheetRecord` object instead of failing entirely.

Fallback behavior is explicitly surfaced through:

```json
"metadata": {
  "fallback_used": "true"
}
```

This allows downstream workstreams to identify records that required fallback
logic during extraction and downstream normalization.

---

## Fallback decision tree

```text
extract_cheatsheet_record(markdown, source_path)

│
├── _extract_title(markdown)
│     ├── H1 title exists
│     │      → extract and normalize title
│     │
│     └── H1 title missing
│            → _fallback_title()
│            → "No title found."
│            → metadata["fallback_used"] = "true"
│
└── _extract_summary(markdown)
      ├── "Introduction" heading exists with body content
      │      → body beneath "Introduction" extracted as summary
      │      → summary normalized and truncated upto specifc length.
      │
      └── Introduction section missing or invalid
             → _fallback_summary(markdown)
             │
             ├── first heading with body content exists
             │      → its body returned as summary
             │
             └── no usable heading/body content exists
                    → "No summary found."
             → metadata["fallback_used"] = "true"
```

---

## Extraction examples

The following examples demonstrate deterministic extractor behavior across
different markdown shapes.

Notes:

* Currently, `category_hints` is intentionally returned as an initial empty
  list during v1.

* `raw_markdown_path`, `hyperlink`, and `source_id` are derived from
  `source_path` (Module A) and are independent of markdown content.

---

## 1. Normal cheat sheet

### Example Input

```markdown
# Secrets Management Cheat Sheet

## Introduction
Storage guidance.

## Architectural Patterns
Use vaults and environment isolation.
```

### Output

```json
{
  "source": "owasp_cheatsheets",
  "source_id": "Secrets_Management_Cheat_Sheet",
  "title": "Secrets Management Cheat Sheet",
  "hyperlink": "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
  "summary": "Storage guidance.",
  "headings": ["Introduction", "Architectural Patterns"],
  "raw_markdown_path": "cheatsheets/Secrets_Management_Cheat_Sheet.md",
  "category_hints": [],
  "metadata": {
    "parser_version": "v1",
    "fallback_used": "false"
  }
}
```

### Notes

* No fallback logic was required.

---

## 2. Missing H1 (fallback title)

### Input

```markdown
## Introduction
No H1 present.

## Details
More content.
```

### Output

```json
{
  "source": "owasp_cheatsheets",
  "source_id": "Example_Cheat_Sheet",
  "title": "No title found.",
  "hyperlink": "https://cheatsheetseries.owasp.org/cheatsheets/Example_Cheat_Sheet.html",
  "summary": "No H1 present.",
  "headings": ["Introduction", "Details"],
  "raw_markdown_path": "cheatsheets/Example_Cheat_Sheet.md",
  "category_hints": [],
  "metadata": {
    "parser_version": "v1",
    "fallback_used": "true"
  }
}
```

### Notes

* No H1 title exists, so the title defaults to `"No title found."`

---

## 3. Missing Introduction section (summary fallback)

### Input

```markdown
# Single Heading Cheat Sheet

## Authentication

### Storage
Secrets should be encrypted.
```

### Output

```json
{
  "source": "owasp_cheatsheets",
  "source_id": "Single_Heading_Cheat_Sheet",
  "title": "Single Heading Cheat Sheet",
  "hyperlink": "https://cheatsheetseries.owasp.org/cheatsheets/Single_Heading_Cheat_Sheet.html",
  "summary": "Secrets should be encrypted.",
  "headings": ["Authentication"],
  "raw_markdown_path": "cheatsheets/Single_Heading_Cheat_Sheet.md",
  "category_hints": [],
  "metadata": {
    "parser_version": "v1",
    "fallback_used": "true"
  }
}
```

### Notes

* No `Introduction` heading exists, so summary fallback logic is used.
* The fallback scans all headings and returns the first non-empty body it
  finds — in this case the content beneath `### Storage`.
* Only `##`-level headings appear in `headings` — `### Storage` is excluded.

---

## Additional behavior notes

The extractor correctly handles markdown files with malformed titles/headings such as:

* Titles with leading whitespace
* No space after the marker (e.g. `##Authentication`)

---
