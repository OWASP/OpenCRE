import unittest
from datetime import datetime
from unittest import mock

from application.utils.comprehension import external, youtube_ingest
from application.utils.comprehension import youtube_source as ys
from application.utils.oie_scheduler import external_sources, jobs

NOW = datetime(2026, 10, 29, 9, 0)


def yt(sid="yt-owasp", **kw):
    kw.setdefault("status", external.STATUS_APPROVED)
    return external.ExternalSpec(
        id=sid, name="OWASP", kind=external.KIND_YOUTUBE, channel_id="UC1", **kw
    )


class YoutubeDueTest(unittest.TestCase):
    def due(self, last):
        with mock.patch.object(external_sources, "last_run", return_value=last):
            return external_sources.due_specs([yt()], NOW)

    def test_never_ingested_is_due(self):
        self.assertEqual(len(self.due(None)), 1)

    def test_refreshes_before_the_30_day_limit_not_at_it(self):
        # refresh_days 30 minus a 5 day safety margin: due from day 25 on
        self.assertEqual(self.due(datetime(2026, 10, 10)), [])  # 19 days old
        self.assertEqual(len(self.due(datetime(2026, 10, 4))), 1)  # 25 days old

    def test_unapproved_youtube_is_not_due(self):
        spec = yt(status=external.STATUS_SUGGESTED)
        with mock.patch.object(external_sources, "last_run", return_value=None):
            self.assertEqual(external_sources.due_specs([spec], NOW), [])


class YoutubeStageTest(unittest.TestCase):
    def stage(self, refresh, dry_run=False):
        ctx = mock.Mock(now=NOW, dry_run=dry_run)
        with mock.patch.object(
            external_sources.external, "load_specs", return_value=[yt()]
        ), mock.patch.object(
            external_sources, "last_run", return_value=None
        ), mock.patch(
            "application.prompt_client.prompt_client.PromptHandler"
        ), mock.patch.object(
            youtube_ingest, "refresh_channel", refresh
        ), mock.patch.object(
            external_sources.runtime_settings, "set_setting"
        ) as put:
            return jobs.stage_external_sources(ctx), put

    def test_youtube_refresh_runs_and_records_last_run(self):
        refresh = mock.Mock(return_value={"videos": 3, "written": 5, "removed": 1})
        result, put = self.stage(refresh)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.summary["sites"]["yt-owasp"]["removed"], 1)
        self.assertTrue(refresh.call_args.kwargs["apply"])
        put.assert_called_once_with("OIE_EXT_LAST_RUN_YT_OWASP", "2026-10-29T09:00:00")

    def test_failure_is_degraded_and_not_recorded(self):
        result, put = self.stage(mock.Mock(side_effect=RuntimeError("quota")))
        self.assertEqual(result.status, "degraded")
        self.assertIn("quota", result.summary["sites"]["yt-owasp"]["error"])
        put.assert_not_called()

    def test_dry_run_does_not_apply(self):
        refresh = mock.Mock(return_value={"videos": 3})
        self.stage(refresh, dry_run=True)
        self.assertFalse(refresh.call_args.kwargs["apply"])


class FakeApi:
    quota_used = 0

    def __init__(self, videos):
        self.videos = videos

    def channel_videos(self, spec, limit=0):
        return list(self.videos)


class RefreshChannelTest(unittest.TestCase):
    def run_refresh(self, apply=True, force_delete=False, stale=2):
        videos = [
            ys.Video(
                id=f"v{i}", title=f"Talk {i}", description="d", published="2026-01-01"
            )
            for i in range(3)
        ]
        db = mock.Mock()
        with mock.patch.object(
            ys, "YouTubeApi", return_value=FakeApi(videos)
        ), mock.patch(
            "application.utils.comprehension.store.write_raw", return_value=3
        ) as write, mock.patch(
            "application.utils.comprehension.store.delete_stale_raw", return_value=stale
        ) as delete:
            out = youtube_ingest.refresh_channel(
                yt(),
                db,
                embed=lambda t: [0.0],
                apply=apply,
                cache_dir="/tmp/yt-test-cache",
                extract=False,
                force_delete=force_delete,
            )
        return out, write, delete

    def test_apply_writes_and_removes_stale(self):
        out, write, delete = self.run_refresh()
        self.assertEqual(out, {"videos": 3, "chunks": 3, "written": 3, "removed": 2})
        self.assertEqual(write.call_args[0][1], "ext-yt-owasp")
        self.assertEqual(delete.call_args[0][1], "ext-yt-owasp")

    def test_dry_run_writes_nothing(self):
        out, write, delete = self.run_refresh(apply=False)
        self.assertEqual(out["written"], 0)
        write.assert_not_called()
        delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
