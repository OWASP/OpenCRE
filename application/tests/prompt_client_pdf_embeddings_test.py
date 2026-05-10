import unittest
from unittest.mock import Mock, patch

from application.prompt_client import prompt_client as pc


class TestPdfEmbeddingHelpers(unittest.TestCase):
    def test_is_likely_pdf_url(self):
        self.assertTrue(pc._is_likely_pdf_url("https://example.com/doc.PDF?q=1"))
        self.assertFalse(pc._is_likely_pdf_url("https://example.com/page.html"))

    def test_playwright_forced_download_error(self):
        err = Exception("Page.goto: Download is starting")
        self.assertTrue(pc._playwright_forced_download_error(err))
        self.assertFalse(pc._playwright_forced_download_error(Exception("timeout")))

    @patch.object(pc, "PdfReader")
    @patch("application.prompt_client.prompt_client.requests.get")
    def test_fetch_pdf_text_for_embeddings(self, mock_get, mock_pdf_reader_cls):
        mock_resp = Mock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.raise_for_status = Mock()
        mock_resp.iter_content = Mock(return_value=[b"%PDF-1.4", b" rest"])
        mock_get.return_value = mock_resp

        mock_page = Mock()
        mock_page.extract_text.return_value = "  hello world  "
        mock_reader = Mock()
        mock_reader.pages = [mock_page]
        mock_pdf_reader_cls.return_value = mock_reader

        out = pc._fetch_pdf_text_for_embeddings("https://example.com/x.pdf")
        self.assertEqual(out, "hello world")


if __name__ == "__main__":
    unittest.main()
