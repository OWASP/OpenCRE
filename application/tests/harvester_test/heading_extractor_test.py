from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application.utils.harvester.heading_extractor import (
    HeadingExtractor,
)


class HeadingExtractorTests(unittest.TestCase):
    def test_single_heading(self):
        text = """
# Title

Hello

World
"""

        headings = HeadingExtractor().extract(text)

        self.assertEqual(len(headings), 1)

        self.assertEqual(headings[0].text, "Title")
        self.assertEqual(headings[0].level, 1)
        self.assertEqual(headings[0].start_line, 2)

    def test_nested_headings(self):
        text = """
# Root

## Child One

content

## Child Two

more

# Second Root
"""

        headings = HeadingExtractor().extract(text)

        self.assertEqual(len(headings), 4)

        self.assertEqual(headings[0].text, "Root")
        self.assertEqual(headings[1].text, "Child One")
        self.assertEqual(headings[2].text, "Child Two")
        self.assertEqual(headings[3].text, "Second Root")

    def test_heading_ranges(self):
        text = """
# Root

text

## Child

child

# Next
"""

        headings = HeadingExtractor().extract(text)
        self.assertEqual(headings[0].end_line, 9)
        self.assertEqual(headings[1].end_line, 9)
        self.assertEqual(headings[2].end_line, 10)

    def test_ignore_non_headings(self):
        text = """
Hello

###Heading

####NoSpace

## Valid Heading
"""

        headings = HeadingExtractor().extract(text)
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0].text, "Valid Heading")

    def test_heading_stops_at_same_level(self):
        text = """
# Root

## A

### X

## B

    content
    """

        headings = HeadingExtractor().extract(text)

        self.assertEqual(headings[1].text, "A")
        self.assertEqual(headings[2].text, "X")
        self.assertEqual(headings[3].text, "B")

        self.assertEqual(headings[1].end_line, 7)
        self.assertEqual(headings[2].end_line, 7)

    def test_ignores_headings_inside_fenced_code(self) -> None:
        text = """# Real

```
# Not A Heading
```

## Also Real
"""
        headings = HeadingExtractor().extract(text)
        self.assertEqual([h.text for h in headings], ["Real", "Also Real"])

    def test_ignores_indented_code_headings(self) -> None:
        text = """# Real

    # Indented Fake

## Also Real
"""
        headings = HeadingExtractor().extract(text)
        self.assertEqual([h.text for h in headings], ["Real", "Also Real"])

    def test_shorter_or_different_fences_do_not_expose_code_headings(self) -> None:
        for opening, false_closing in (
            ("````", "```"),
            ("~~~~", "~~~"),
            ("```", "~~~"),
            ("~~~", "```"),
        ):
            with self.subTest(opening=opening, false_closing=false_closing):
                text = f"# Before\n{opening}\n{false_closing}\n# Fake\n{opening}\n# After\n"
                headings = HeadingExtractor().extract(text)
                self.assertEqual([h.text for h in headings], ["Before", "After"])
                self.assertEqual(headings[0].end_line, 5)
                self.assertEqual(headings[1].start_line, 6)

    def test_only_whitespace_may_follow_a_closing_fence(self) -> None:
        for marker in ("```", "~~~"):
            with self.subTest(marker=marker):
                text = f"# Before\n{marker}python\n{marker}not-a-close\n# Fake\n{marker}\n# After\n"
                headings = HeadingExtractor().extract(text)
                self.assertEqual([h.text for h in headings], ["Before", "After"])

    def test_longer_indented_closing_fence_ends_the_code_block(self) -> None:
        for marker in ("```", "~~~"):
            for indent in ("", " ", "  ", "   "):
                with self.subTest(marker=marker, indent=indent):
                    text = f"# Before\n{indent}{marker}python\n# Fake\n   {marker}{marker[0]} \t\n# After\n"
                    headings = HeadingExtractor().extract(text)
                    self.assertEqual([h.text for h in headings], ["Before", "After"])

    def test_indented_code_fence_does_not_hide_later_headings(self) -> None:
        for indent in ("    ", "\t"):
            with self.subTest(indent=indent):
                text = f"# Before\n\n{indent}```\n\n# After\n"
                headings = HeadingExtractor().extract(text)
                self.assertEqual([h.text for h in headings], ["Before", "After"])

    def test_indented_fence_cannot_close_an_open_block(self) -> None:
        text = "# Before\n```\n    ```\n# Fake\n```\n# After\n"
        headings = HeadingExtractor().extract(text)
        self.assertEqual([h.text for h in headings], ["Before", "After"])

    def test_backticks_in_info_string_invalidate_only_backtick_openers(self) -> None:
        invalid = "# Before\n```language`info\n# After\n"
        self.assertEqual(
            [h.text for h in HeadingExtractor().extract(invalid)], ["Before", "After"]
        )
        valid = "# Before\n~~~language`info\n# Fake\n~~~\n# After\n"
        self.assertEqual(
            [h.text for h in HeadingExtractor().extract(valid)], ["Before", "After"]
        )

    def test_unclosed_fence_keeps_headings_hidden_to_end_of_document(self) -> None:
        text = "# Before\n````\n```\n# Fake\n"
        headings = HeadingExtractor().extract(text)
        self.assertEqual([h.text for h in headings], ["Before"])
        self.assertEqual(headings[0].end_line, 4)


if __name__ == "__main__":
    unittest.main()
