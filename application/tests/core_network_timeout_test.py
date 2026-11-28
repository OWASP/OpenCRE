import os
import sys
import types
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Provide lightweight stubs for optional heavy DB/queue packages if uninstalled locally
try:
    import flask  # noqa: F401
    import rq  # noqa: F401
    import sqlalchemy  # noqa: F401
except ImportError:
    app_mod = types.ModuleType("application")
    app_mod.__path__ = [str(REPO_ROOT / "application")]
    app_mod.create_app = mock.MagicMock()
    sys.modules["application"] = app_mod

    sys.modules["application.config"] = mock.MagicMock()

    app_db = types.ModuleType("application.database")
    app_db.db = mock.MagicMock()
    sys.modules["application.database"] = app_db
    sys.modules["application.database.db"] = app_db.db

    sys.modules["application.defs.osib_defs"] = mock.MagicMock()

    app_utils = types.ModuleType("application.utils")
    app_utils.__path__ = [str(REPO_ROOT / "application" / "utils")]
    sys.modules["application.utils"] = app_utils
    sys.modules["application.utils.spreadsheet"] = mock.MagicMock()
    sys.modules["application.utils.redis"] = mock.MagicMock()
    sys.modules["application.utils.db_backend"] = mock.MagicMock()

    sys.modules["rq"] = mock.MagicMock()
    sys.modules["flask"] = mock.MagicMock()

    sa = types.ModuleType("sqlalchemy")
    sa.__path__ = []
    sa.not_ = mock.MagicMock()
    sa.func = mock.MagicMock()
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.exc"] = mock.MagicMock()

from application.cmd import cre_main
from application.utils import cres_csv_export
from application.utils import gap_analysis


class TestCoreNetworkTimeouts(unittest.TestCase):
    def test_cre_main_default_http_timeout(self) -> None:
        self.assertEqual(cre_main.DEFAULT_HTTP_TIMEOUT, 60)

    def test_gap_analysis_default_http_timeout(self) -> None:
        self.assertEqual(gap_analysis.DEFAULT_HTTP_TIMEOUT, 60)

    @mock.patch.dict(os.environ, {"BENCHMARK_MODE": "0"}, clear=False)
    @mock.patch("application.cmd.cre_main.db_connect")
    @mock.patch(
        "application.cmd.cre_main.gap_analysis.primary_gap_analysis_payload_is_material",
        return_value=True,
    )
    @mock.patch("application.cmd.cre_main.requests.get")
    def test_download_gap_analysis_standard_mode_uses_timeout(
        self,
        mock_get: mock.MagicMock,
        _mock_material: mock.MagicMock,
        mock_db_connect: mock.MagicMock,
    ) -> None:
        mock_collection = mock.MagicMock()
        mock_db_connect.return_value.with_graph.return_value = mock_collection

        standards_resp = mock.MagicMock(status_code=200)
        standards_resp.json.return_value = ["ASVS", "CWE"]
        pair_resp = mock.MagicMock(status_code=200)
        pair_resp.json.return_value = {"result": {"ASVS": []}}
        mock_get.side_effect = [standards_resp, pair_resp, pair_resp]

        cre_main.download_gap_analysis_from_upstream(cache="sqlite:///tmp.sqlite")

        self.assertEqual(mock_get.call_count, 3)
        expected_base = "https://opencre.org/rest/v1"
        mock_get.assert_has_calls(
            [
                mock.call(
                    f"{expected_base}/standards",
                    timeout=cre_main.DEFAULT_HTTP_TIMEOUT,
                ),
                mock.call(
                    f"{expected_base}/map_analysis?standard=ASVS&standard=CWE",
                    timeout=cre_main.DEFAULT_HTTP_TIMEOUT,
                ),
                mock.call(
                    f"{expected_base}/map_analysis?standard=CWE&standard=ASVS",
                    timeout=cre_main.DEFAULT_HTTP_TIMEOUT,
                ),
            ]
        )

    @mock.patch.dict(os.environ, {"BENCHMARK_MODE": "1"}, clear=False)
    @mock.patch("application.cmd.cre_main.db_connect")
    @mock.patch(
        "application.cmd.cre_main.gap_analysis.primary_gap_analysis_payload_is_material",
        return_value=True,
    )
    @mock.patch("application.cmd.cre_main.requests.get")
    def test_download_gap_analysis_benchmark_mode_uses_timeout(
        self,
        mock_get: mock.MagicMock,
        _mock_material: mock.MagicMock,
        mock_db_connect: mock.MagicMock,
    ) -> None:
        mock_collection = mock.MagicMock()
        mock_db_connect.return_value.with_graph.return_value = mock_collection

        standards_resp = mock.MagicMock(status_code=200)
        standards_resp.json.return_value = ["ASVS", "CWE"]
        pair_resp = mock.MagicMock(status_code=200)
        pair_resp.json.return_value = {"result": {"ASVS": []}}
        mock_get.side_effect = [standards_resp, pair_resp, pair_resp]

        @contextmanager
        def fake_alive_bar(*_args, **_kwargs):
            yield lambda: None

        fake_alive_progress = types.ModuleType("alive_progress")
        fake_alive_progress.alive_bar = fake_alive_bar

        with mock.patch.dict(sys.modules, {"alive_progress": fake_alive_progress}):
            cre_main.download_gap_analysis_from_upstream(cache="sqlite:///tmp.sqlite")

        self.assertEqual(mock_get.call_count, 3)
        for call in mock_get.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), cre_main.DEFAULT_HTTP_TIMEOUT)

    @mock.patch("application.utils.gap_analysis.time.sleep")
    @mock.patch("application.utils.gap_analysis.requests.get")
    def test_gap_analysis_preload_uses_timeout(
        self,
        mock_get: mock.MagicMock,
        _mock_sleep: mock.MagicMock,
    ) -> None:
        standards_resp = mock.MagicMock()
        standards_resp.json.return_value = ["ASVS", "CWE"]
        pair_resp = mock.MagicMock(status_code=200)
        pair_resp.json.return_value = {"result": [{"ok": True}]}
        mock_get.side_effect = [standards_resp, pair_resp, pair_resp]

        gap_analysis.preload("http://localhost:5000")

        self.assertEqual(mock_get.call_count, 3)
        mock_get.assert_has_calls(
            [
                mock.call(
                    "http://localhost:5000/rest/v1/standards",
                    timeout=gap_analysis.DEFAULT_HTTP_TIMEOUT,
                ),
                mock.call(
                    "http://localhost:5000/rest/v1/map_analysis?standard=ASVS&standard=CWE",
                    timeout=gap_analysis.DEFAULT_HTTP_TIMEOUT,
                ),
                mock.call(
                    "http://localhost:5000/rest/v1/map_analysis?standard=CWE&standard=ASVS",
                    timeout=gap_analysis.DEFAULT_HTTP_TIMEOUT,
                ),
            ]
        )

    @mock.patch("application.utils.cres_csv_export.requests.get")
    def test_cres_csv_export_requests_use_timeout(
        self, mock_get: mock.MagicMock
    ) -> None:
        std_resp = mock.MagicMock()
        std_resp.json.return_value = {"standards": []}
        all_resp = mock.MagicMock()
        all_resp.json.return_value = {"data": [], "total_pages": 1}
        cre_resp = mock.MagicMock()
        cre_resp.json.return_value = {"data": {"id": "123-456"}}
        mock_get.side_effect = [std_resp, all_resp, cre_resp]

        cres_csv_export._collect_target_cre_ids(
            base_url="http://localhost:5000/rest/v1",
            timeout_seconds=45,
            direct_cre_ids=[],
            standard_names=["ASVS"],
        )
        cres_csv_export._collect_target_cre_ids(
            base_url="http://localhost:5000/rest/v1",
            timeout_seconds=45,
            direct_cre_ids=[],
            standard_names=[],
        )
        cres_csv_export._fetch_cre(
            base_url="http://localhost:5000/rest/v1",
            cre_id="123-456",
            timeout_seconds=45,
            cache={},
        )

        self.assertEqual(mock_get.call_count, 3)
        for call in mock_get.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), 45)


if __name__ == "__main__":
    unittest.main()
