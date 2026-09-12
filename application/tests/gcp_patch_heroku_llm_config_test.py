import os
import unittest
from unittest import mock
from urllib.error import HTTPError
from io import BytesIO


class GcpPatchHerokuLlmConfigTest(unittest.TestCase):
    def _run_main(self, env: dict[str, str]) -> int:
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[2]
            / "scripts"
            / "gcp"
            / "patch_heroku_llm_config.py"
        )
        spec = importlib.util.spec_from_file_location("patch_heroku_llm_config", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with mock.patch.dict(os.environ, env, clear=True):
            return int(mod.main())

    def test_missing_env_exits_2(self) -> None:
        self.assertEqual(self._run_main({}), 2)

    def test_heroku_http_error_exits_1_without_raising(self) -> None:
        err = HTTPError("https://api.heroku.com", 401, "nope", hdrs=None, fp=BytesIO())
        env = {
            "HEROKU_API_KEY": "token",
            "HEROKU_APP": "opencreorg",
            "GEMINI_API_KEY": "secret-key",
            "GOOGLE_PROJECT_ID": "demo-proj",
        }
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(self._run_main(env), 1)

    def test_success_patches_expected_keys(self) -> None:
        captured: dict[str, object] = {}

        class _Resp:
            def getcode(self) -> int:
                return 200

            def read(self) -> bytes:
                return b"{}"

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def _urlopen(req: object, timeout: int = 0) -> _Resp:
            captured["full_url"] = getattr(req, "full_url", "")
            captured["data"] = getattr(req, "data", b"")
            return _Resp()

        env = {
            "HEROKU_API_KEY": "token",
            "HEROKU_APP": "opencreorg",
            "GEMINI_API_KEY": "secret-key",
            "GOOGLE_PROJECT_ID": "demo-proj",
        }
        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            self.assertEqual(self._run_main(env), 0)
        self.assertIn("/apps/opencreorg/config-vars", str(captured.get("full_url")))
        body = captured["data"]
        assert isinstance(body, bytes)
        self.assertIn(b"GEMINI_API_KEY", body)
        self.assertIn(b"GOOGLE_PROJECT_ID", body)
        self.assertIn(b"gemini/gemini-2.5-flash", body)
        self.assertNotIn(b"VERTEX_", body)


if __name__ == "__main__":
    unittest.main()
