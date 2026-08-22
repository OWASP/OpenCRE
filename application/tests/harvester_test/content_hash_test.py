import unittest

from application.utils.harvester.content_hash import (
    generate_content_hash,
)


class ContentHashTests(unittest.TestCase):
    def test_same_text_same_hash(self):
        text = "Hello World"

        self.assertEqual(
            generate_content_hash(text),
            generate_content_hash(text),
        )

    def test_different_text_different_hash(self):
        self.assertNotEqual(
            generate_content_hash("Hello"),
            generate_content_hash("World"),
        )

    def test_empty_string(self):
        digest = generate_content_hash("")

        self.assertEqual(len(digest), 64)

    def test_hash_is_hex(self):
        digest = generate_content_hash("OpenCRE")

        int(digest, 16)


if __name__ == "__main__":
    unittest.main()
