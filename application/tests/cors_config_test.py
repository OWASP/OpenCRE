import unittest

from application import create_app
from application.tests.env_override import environ_override


class CorsConfigTest(unittest.TestCase):
    def _headers(self, origin: str, env: dict):
        unset = [] if "CORS_ALLOWED_ORIGINS" in env else ["CORS_ALLOWED_ORIGINS"]
        with environ_override(env, unset=unset):
            app = create_app(mode="test")
            with app.test_client() as client:
                return client.get(
                    "/rest/v1/capabilities", headers={"Origin": origin}
                ).headers

    def test_unset_allowlist_never_reflects_origin_with_credentials(self) -> None:
        headers = self._headers("https://evil.example", {"NO_LOAD_GRAPH_DB": "1"})
        self.assertIsNone(headers.get("Access-Control-Allow-Credentials"))

    def test_allowlist_enables_credentials_for_listed_origin_only(self) -> None:
        env = {
            "NO_LOAD_GRAPH_DB": "1",
            "CORS_ALLOWED_ORIGINS": "https://staging.example",
        }
        ok = self._headers("https://staging.example", env)
        self.assertEqual(
            ok.get("Access-Control-Allow-Origin"), "https://staging.example"
        )
        self.assertEqual(ok.get("Access-Control-Allow-Credentials"), "true")
        evil = self._headers("https://evil.example", env)
        self.assertIsNone(evil.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()
