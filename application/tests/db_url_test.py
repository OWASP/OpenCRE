import unittest

from application.utils.db_url import redact_db_url


class RedactDbUrlTest(unittest.TestCase):
    def test_masks_password_and_keeps_rest(self) -> None:
        self.assertEqual(
            redact_db_url("postgresql://cre:s3cret@127.0.0.1:5432/cre?sslmode=require"),
            "postgresql://cre:***@127.0.0.1:5432/cre?sslmode=require",
        )

    def test_url_without_password_is_unchanged(self) -> None:
        for url in (
            "postgresql://127.0.0.1/cre",
            "postgresql://cre@127.0.0.1/cre",
            "sqlite:///tmp/x.sqlite",
            "standards_cache.sqlite",
            "",
        ):
            self.assertEqual(redact_db_url(url), url)

    def test_password_with_special_characters(self) -> None:
        self.assertEqual(
            redact_db_url("postgres://u:p%40ss:word@db.example.com/x"),
            "postgres://u:***@db.example.com/x",
        )


if __name__ == "__main__":
    unittest.main()
