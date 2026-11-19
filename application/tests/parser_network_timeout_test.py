import sys
import types
from pathlib import Path
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Provide lightweight stubs for heavy DB packages if uninstalled in local environment
try:
    import sqlalchemy
except ImportError:
    app_mod = types.ModuleType("application")
    app_mod.__path__ = [str(REPO_ROOT / "application")]
    sys.modules["application"] = app_mod
    app_db = types.ModuleType("application.database")
    app_db.db = mock.MagicMock()
    sys.modules["application.database"] = app_db
    sys.modules["application.database.db"] = app_db.db
    app_pc = types.ModuleType("application.prompt_client")
    app_pc.prompt_client = mock.MagicMock()
    sys.modules["application.prompt_client"] = app_pc
    sys.modules["application.prompt_client.prompt_client"] = app_pc.prompt_client
    sys.modules["xmltodict"] = mock.MagicMock()
    sa = types.ModuleType("sqlalchemy")
    sa.__path__ = []
    sa.func = mock.MagicMock()
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.exc"] = mock.MagicMock()

from application.utils.external_project_parsers.parsers import capec_parser
from application.utils.external_project_parsers.parsers import cwe
from application.utils.external_project_parsers.parsers import juiceshop


class TestParserNetworkTimeouts(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_cache = mock.MagicMock()
        self.mock_ph = mock.MagicMock()

    @mock.patch(
        "application.utils.external_project_parsers.parsers.capec_parser.requests.get"
    )
    def test_capec_request_uses_timeout(self, mock_get: mock.MagicMock) -> None:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"
        mock_get.return_value = mock_resp

        capec_parser.Capec().parse(cache=self.mock_cache, ph=self.mock_ph)

        mock_get.assert_called_once_with(
            capec_parser.Capec.capec_xml,
            timeout=capec_parser.DEFAULT_HTTP_TIMEOUT,
        )
        self.assertEqual(capec_parser.DEFAULT_HTTP_TIMEOUT, 60)

    @mock.patch("application.utils.external_project_parsers.parsers.cwe.requests.get")
    def test_cwe_request_uses_timeout(self, mock_get: mock.MagicMock) -> None:
        mock_resp = mock.MagicMock()
        mock_resp.iter_content.return_value = []
        mock_get.return_value = mock_resp

        try:
            cwe.CWE().parse(cache=self.mock_cache, ph=self.mock_ph)
        except Exception:
            pass

        mock_get.assert_called_once_with(
            cwe.CWE.cwe_zip,
            stream=True,
            timeout=cwe.DEFAULT_HTTP_TIMEOUT,
        )
        self.assertEqual(cwe.DEFAULT_HTTP_TIMEOUT, 60)

    @mock.patch(
        "application.utils.external_project_parsers.parsers.juiceshop.requests.get"
    )
    def test_juiceshop_request_uses_timeout(self, mock_get: mock.MagicMock) -> None:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        with self.assertRaises(RuntimeError):
            juiceshop.JuiceShop().parse(cache=self.mock_cache, ph=self.mock_ph)

        mock_get.assert_called_once_with(
            juiceshop.JuiceShop.url,
            timeout=juiceshop.DEFAULT_HTTP_TIMEOUT,
        )
        self.assertEqual(juiceshop.DEFAULT_HTTP_TIMEOUT, 60)


if __name__ == "__main__":
    unittest.main()
