"""``_fetch_plain_http_text`` must only follow redirects to GitHub raw hosts."""

import unittest
from unittest.mock import patch

from application.prompt_client import prompt_client

_RAW_URL = "https://raw.githubusercontent.com/OWASP/ASVS/master/V2.md"


class _Response:
    def __init__(self, status: int, text: str = "", location: str = "") -> None:
        self.status_code = status
        self.text = text
        self.headers = {"Location": location} if location else {}

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in (
            self.headers
        )

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise prompt_client.requests.HTTPError(str(self.status_code))


class FetchPlainHttpTextTest(unittest.TestCase):
    def test_returns_body_without_redirect(self) -> None:
        with patch.object(
            prompt_client.requests, "get", return_value=_Response(200, "# V2")
        ) as get:
            self.assertEqual(prompt_client._fetch_plain_http_text(_RAW_URL), "# V2")
        self.assertIs(get.call_args.kwargs["allow_redirects"], False)

    def test_follows_redirect_to_github_raw_host(self) -> None:
        responses = [
            _Response(302, location="https://raw.githubusercontent.com/o/r/main/a.md"),
            _Response(200, "body"),
        ]
        with patch.object(prompt_client.requests, "get", side_effect=responses):
            self.assertEqual(prompt_client._fetch_plain_http_text(_RAW_URL), "body")

    def test_refuses_redirect_to_internal_host(self) -> None:
        responses = [
            _Response(302, location="http://169.254.169.254/latest/meta-data"),
            _Response(200, "secret"),
        ]
        with patch.object(prompt_client.requests, "get", side_effect=responses) as get:
            self.assertIsNone(prompt_client._fetch_plain_http_text(_RAW_URL))
        self.assertEqual(get.call_count, 1)

    def test_redirect_loop_is_bounded(self) -> None:
        loop = _Response(302, location=_RAW_URL)
        with patch.object(prompt_client.requests, "get", return_value=loop) as get:
            self.assertIsNone(prompt_client._fetch_plain_http_text(_RAW_URL))
        self.assertEqual(get.call_count, prompt_client._MAX_PLAIN_TEXT_REDIRECTS + 1)


if __name__ == "__main__":
    unittest.main()
