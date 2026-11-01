import unittest

from application.utils.noise_filter.schemas import ChangeRecord


def _record(source):
    return {
        "schema_version": "0.2.0",
        "chunk_id": "c",
        "artifact_id": "a",
        "pipeline_run_id": "r",
        "text": "t",
        "span": {"index": 0, "total": 1},
        "source": source,
        "locator": {"kind": "url", "id": "https://x.org/p", "path": "https://x.org/p"},
    }


class UrlSourceTest(unittest.TestCase):
    def test_url_source_is_accepted(self) -> None:
        rec = ChangeRecord.model_validate(
            _record(
                {
                    "type": "url",
                    "url": "https://x.org/p",
                    "committed_at": "2026-11-01T00:00:00Z",
                }
            )
        )
        self.assertEqual(rec.source.url, "https://x.org/p")

    def test_url_source_needs_a_url(self) -> None:
        with self.assertRaises(Exception):
            ChangeRecord.model_validate(_record({"type": "url"}))

    def test_unknown_source_type_still_rejected(self) -> None:
        with self.assertRaises(Exception):
            ChangeRecord.model_validate(_record({"type": "ftp", "url": "x"}))


if __name__ == "__main__":
    unittest.main()
