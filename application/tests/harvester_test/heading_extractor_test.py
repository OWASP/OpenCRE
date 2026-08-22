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


if __name__ == "__main__":
    unittest.main()
