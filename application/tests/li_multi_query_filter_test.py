"""TASK-14.12: LI multi-query expand + metadata URL filter."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class LiMultiQueryFilterTest(unittest.TestCase):
    def test_retrieve_wires_expand_queries(self) -> None:
        from pathlib import Path

        src = Path("application/utils/comprehension/retrieve.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("expand_queries", src)
        self.assertIn("_li_metadata_filter_hits", src)
        self.assertIn("OWASP_CX_LI_URL_SUBSTR", src)

    def test_metadata_filter_by_url_substr(self) -> None:
        from application.utils.comprehension.retrieve import _li_metadata_filter_hits
        from application.utils.owasp_agent.lane_similarity import LaneHit

        hits = [
            LaneHit(channel="c", score=1.0, url="owasp-agent://evidence/comprehension-a-raw-1"),
            LaneHit(channel="c", score=0.9, url="owasp-agent://evidence/comprehension-b-overview"),
        ]
        with mock.patch.dict(os.environ, {"OWASP_CX_LI_URL_SUBSTR": "-raw-"}):
            out = _li_metadata_filter_hits(hits)
        self.assertEqual([h.url for h in out], [hits[0].url])


if __name__ == "__main__":
    unittest.main()
