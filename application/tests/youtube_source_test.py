import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from application.utils.comprehension import external as ext
from application.utils.comprehension import youtube_source as ys

DATA = str(Path(__file__).parent / "data" / "youtube")


def fake_http(pages):
    """Serves canned Data API responses and records every call."""
    calls = []

    def get(url, params, headers):
        calls.append((url.rsplit("/", 1)[-1], dict(params)))
        endpoint = url.rsplit("/", 1)[-1]
        if endpoint == "channels":
            return {
                "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUx"}}}]
            }
        if endpoint == "playlistItems":
            return pages[params.get("pageToken", "")]
        if endpoint == "videos":
            return {
                "items": [
                    {
                        "id": i,
                        "snippet": {
                            "title": f"Jane Doe - Talk {i}",
                            "description": "desc",
                            "publishedAt": "2024-10-22T10:00:00Z",
                        },
                        "contentDetails": {"duration": "PT1H2M3S"},
                    }
                    for i in params["id"].split(",")
                ]
            }
        raise AssertionError(url)

    get.calls = calls
    return get


PAGES = {
    "": {
        "items": [{"contentDetails": {"videoId": "vid00000001"}}],
        "nextPageToken": "p2",
    },
    "p2": {"items": [{"contentDetails": {"videoId": "vid00000002"}}]},
}


class ApiTest(unittest.TestCase):
    def test_pagination_quota_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = fake_http(PAGES)
            spec = ext.validate_spec(
                {
                    "id": "owasp-yt",
                    "name": "OWASP",
                    "kind": "youtube_channel",
                    "channel_id": "UCx",
                }
            )
            api = ys.YouTubeApi("KEY", http, cache_dir=tmp)
            vids = api.channel_videos(spec)
            self.assertEqual([v.id for v in vids], ["vid00000001", "vid00000002"])
            self.assertEqual(vids[0].published, "2024-10-22")
            self.assertEqual(vids[0].duration_seconds, 3723)
            # channels + 2 playlist pages + 1 videos call
            self.assertEqual(api.quota_used, 4)
            # a second run is served from the cache: no calls, no quota
            http2 = fake_http(PAGES)
            api2 = ys.YouTubeApi("KEY", http2, cache_dir=tmp)
            api2.channel_videos(spec)
            self.assertEqual((http2.calls, api2.quota_used), ([], 0))

    def test_playlist_id_skips_channel_lookup_and_limit(self):
        http = fake_http(PAGES)
        spec = ext.validate_spec(
            {
                "id": "owasp-yt",
                "name": "OWASP",
                "kind": "youtube_channel",
                "playlist_id": "PLx",
            }
        )
        api = ys.YouTubeApi("KEY", http)
        self.assertEqual(len(api.channel_videos(spec, limit=1)), 1)
        self.assertNotIn("channels", [c[0] for c in http.calls])

    def test_missing_key_and_http_error_do_not_leak_key(self):
        with self.assertRaises(RuntimeError):
            ys.YouTubeApi("", fake_http(PAGES)).uploads_playlist("UCx")
        resp = SimpleNamespace(status_code=403, json=lambda: {})
        with mock.patch("requests.get", return_value=resp):
            with self.assertRaises(RuntimeError) as cm:
                ys._requests_get("https://x/y", {"key": "SECRET"}, {})
        self.assertNotIn("SECRET", str(cm.exception))


class CaptionTest(unittest.TestCase):
    def test_vtt_and_srt(self):
        vtt = ys.read_captions(DATA, "vid00000001")
        self.assertEqual(vtt[0], (1.0, "Welcome everyone to this talk"))
        self.assertEqual(vtt[2][0], 95.0)
        srt = ys.read_captions(DATA, "vid00000002")
        self.assertEqual(srt[1], (3.0, "Second line spanning two lines."))
        self.assertEqual(ys.read_captions(DATA, "nope"), [])
        self.assertEqual(ys.read_captions(None, "vid00000001"), [])

    def test_windows_and_deep_links(self):
        cues = [(float(t), "x" * 100) for t in range(0, 400, 10)]
        wins = ys.caption_windows(cues)
        self.assertEqual(wins[0][0], 0)
        self.assertTrue(all(len(t) <= ys.WINDOW_MAX_CHARS + 100 for _, t in wins))
        self.assertTrue(all(b[0] - a[0] >= 60 for a, b in zip(wins, wins[1:])))
        v = ys.Video("vid00000001", "Jane Doe - Talk", published="2024-10-22")
        chunks = ys.video_chunks(v, cues, "OWASP")
        self.assertEqual(chunks[0][0], "vid00000001")
        self.assertEqual(chunks[1][0], "vid00000001#t=0")
        self.assertTrue(
            chunks[1][2].startswith(
                "Talk: Jane Doe - Talk | Speaker: unknown | Published: 2024-10-22 | Channel: OWASP\n"
            )
        )
        spec = ext.ExternalSpec(
            id="a-b", name="n", kind=ext.KIND_YOUTUBE, channel_id="c"
        )
        self.assertTrue(ext.page_url(spec, chunks[2][0]).endswith(f"&t={wins[1][0]}s"))

    def test_catalogue_only_video(self):
        v = ys.Video("vid00000009", "A talk", "About X", "2023-01-02", 600)
        chunks = ys.video_chunks(v, [], "OWASP")
        self.assertEqual(len(chunks), 1)
        text = chunks[0][2]
        for want in (
            "Published: 2023-01-02",
            "Duration: 10 min",
            "About X",
            "Speaker: unknown",
        ):
            self.assertIn(want, text)


class SpeakerTest(unittest.TestCase):
    PEOPLE = ["José Álvarez", "Jane Doe", "Sam Twin", "sam  twin"]

    def test_guess_patterns(self):
        self.assertEqual(ys.guess_speaker("Jane Doe - Shift Left"), "Jane Doe")
        self.assertEqual(ys.guess_speaker("Shift Left | Jane Doe"), "Jane Doe")
        self.assertEqual(ys.guess_speaker("Shift Left by Jane Doe"), "Jane Doe")
        self.assertEqual(ys.guess_speaker("OWASP AppSec 2024 Keynote"), "")
        self.assertEqual(ys.guess_speaker("Top 10 - Intro"), "")

    def test_matching(self):
        self.assertEqual(ys.match_speaker("jose alvarez", self.PEOPLE), "José Álvarez")
        self.assertEqual(ys.match_speaker("Jane Roe", self.PEOPLE), "")
        self.assertEqual(ys.match_speaker("Jane", self.PEOPLE), "")
        self.assertEqual(ys.match_speaker("Sam Twin", self.PEOPLE), "")  # ambiguous
        vids = [
            ys.Video("a", "José Álvarez - Zero trust"),
            ys.Video("b", "Unknown Person - X"),
        ]
        ys.link_speakers(vids, self.PEOPLE)
        self.assertEqual([v.speaker for v in vids], ["José Álvarez", ""])


class DripTest(unittest.TestCase):
    ENV = {
        "YOUTUBE_OAUTH_REFRESH_TOKEN": "r",
        "YOUTUBE_OAUTH_CLIENT_ID": "i",
        "YOUTUBE_OAUTH_CLIENT_SECRET": "s",
    }

    def test_limiter_counts_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = ["2026-01-01"]
            lim = ys.DripLimiter(
                os.path.join(tmp, "s.json"), per_day=2, today=lambda: day[0]
            )
            lim.record()
            lim.record()
            self.assertFalse(lim.allow())
            day[0] = "2026-01-02"
            self.assertEqual(lim.remaining(), 2)
        self.assertEqual(ys.DEFAULT_DAILY_DOWNLOADS * ys.CAPTION_DOWNLOAD_COST, 9000)

    def test_downloader_off_without_env_and_drips_with_mocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            lim = ys.DripLimiter(os.path.join(tmp, "s.json"), per_day=1)
            off = ys.CaptionDownloader(
                lim, env={}, http_post=mock.Mock(side_effect=AssertionError)
            )
            self.assertFalse(off.enabled())
            self.assertEqual(off.fetch("v1"), [])

            def get_text(url, params, headers):
                self.assertEqual(headers["Authorization"], "Bearer tok")
                if url.endswith("/captions"):
                    return json.dumps({"items": [{"id": "cap1"}]})
                return "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi there\n"

            dl = ys.CaptionDownloader(
                lim,
                http_post=lambda u, d: {"access_token": "tok"},
                http_get_text=get_text,
                env=self.ENV,
                out_dir=os.path.join(tmp, "out"),
            )
            self.assertEqual(dl.fetch("v1"), [(1.0, "hi there")])
            self.assertTrue(os.path.exists(os.path.join(tmp, "out", "v1.en.vtt")))
            self.assertEqual(dl.fetch("v2"), [])  # daily limit reached
            self.assertEqual(lim.remaining(), 0)


def handle_http(items):
    calls = []

    def get(url, params, headers):
        calls.append((url.rsplit("/", 1)[-1], dict(params)))
        if params.get("forHandle"):
            return {"items": items}
        return fake_http(PAGES)(url, params, headers)

    get.calls = calls
    return get


class HandleTest(unittest.TestCase):
    def test_handle_forms_and_passthrough(self):
        self.assertEqual(ys.handle_of("@FooSec"), "@FooSec")
        self.assertEqual(
            ys.handle_of("https://www.youtube.com/@FooSec/videos"), "@FooSec"
        )
        self.assertEqual(ys.handle_of("UCabc"), "")
        http = handle_http([])
        self.assertEqual(ys.resolve_channel_id("UCabc", http), "UCabc")
        self.assertEqual(
            ys.resolve_channel_id("https://youtube.com/channel/UCabc", http), "UCabc"
        )
        self.assertEqual(http.calls, [])

    def test_resolves_spec_caches_and_hides_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = handle_http([{"id": "UCfoo"}])
            api = ys.YouTubeApi("SECRET", http, cache_dir=tmp)
            spec = ext.ExternalSpec(
                id="a-b", name="n", kind=ext.KIND_YOUTUBE, channel_id="@FooSec"
            )
            self.assertEqual(ys.resolve_channel_id(spec, api), "UCfoo")
            self.assertEqual(api.quota_used, 1)
            self.assertEqual(http.calls[0][1]["forHandle"], "@FooSec")
            self.assertEqual(http.calls[0][1]["part"], "id")
            api2 = ys.YouTubeApi("SECRET", handle_http([]), cache_dir=tmp)
            self.assertEqual(api2.resolve_channel_id("@FooSec"), "UCfoo")
            self.assertEqual(api2.quota_used, 0)
            for f in Path(tmp).iterdir():
                self.assertNotIn("SECRET", f.name + f.read_text())

    def test_listing_path_resolves_handle(self):
        http = handle_http([{"id": "UCfoo"}])
        spec = ext.ExternalSpec(
            id="a-b", name="n", kind=ext.KIND_YOUTUBE, channel_id="@FooSec"
        )
        vids = ys.YouTubeApi("KEY", http).channel_videos(spec)
        self.assertEqual(len(vids), 2)
        ch = [c[1] for c in http.calls if c[0] == "channels" and "id" in c[1]]
        self.assertEqual(ch[0]["id"], "UCfoo")

    def test_not_found_and_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            ys.resolve_channel_id("@Nope", ys.YouTubeApi("K", handle_http([])))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            ys.resolve_channel_id(
                "@Dup", ys.YouTubeApi("K", handle_http([{"id": "UC1"}, {"id": "UC2"}]))
            )


def load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ingest_youtube.py"
    spec = importlib.util.spec_from_file_location("ingest_youtube", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class IngestScriptTest(unittest.TestCase):
    SPEC = json.dumps(
        {
            "id": "owasp-yt",
            "name": "OWASP",
            "kind": "youtube_channel",
            "channel_id": "UCx",
            "status": "approved",
        }
    )

    def run_main(self, *extra):
        script = load_script()
        write_raw = mock.Mock(return_value=7)
        self.delete_stale = mock.Mock(return_value=2)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"YOUTUBE_API_KEY": "KEY"}
        ), mock.patch.object(ys, "_requests_get", fake_http(PAGES)), mock.patch.object(
            script, "open_database", return_value=object()
        ), mock.patch(
            "application.utils.comprehension.store.write_raw", write_raw
        ), mock.patch(
            "application.utils.comprehension.store.delete_stale_raw", self.delete_stale
        ), mock.patch(
            "application.utils.comprehension.shared.shared_handler"
        ):
            rc = script.main(
                [
                    "--spec-json",
                    self.SPEC,
                    "--captions-dir",
                    DATA,
                    "--cache-dir",
                    tmp,
                    *extra,
                ]
            )
        return rc, write_raw

    def test_full_apply_removes_stale_videos_but_a_limited_run_does_not(self):
        rc, _ = self.run_main("--apply")
        self.assertEqual(rc, 0)
        self.delete_stale.assert_called_once()
        self.assertEqual(self.delete_stale.call_args[0][1], "ext-owasp-yt")
        rc, _ = self.run_main("--apply", "--limit", "1")
        self.delete_stale.assert_not_called()

    def test_dry_run_writes_nothing(self):
        rc, write_raw = self.run_main()
        self.assertEqual(rc, 0)
        write_raw.assert_not_called()

    def test_dry_run_prints_resolved_handle_and_reports_missing(self):
        script = load_script()
        spec = json.dumps({**json.loads(self.SPEC), "channel_id": "@FooSec"})
        for items, rc_expected, needle in (
            ([{"id": "UCfoo"}], 0, "resolved @FooSec -> UCfoo"),
            ([], 1, "not found"),
        ):
            out, err = io.StringIO(), io.StringIO()
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
                os.environ, {"YOUTUBE_API_KEY": "KEY"}
            ), mock.patch.object(
                ys, "_requests_get", handle_http(items)
            ), contextlib.redirect_stdout(
                out
            ), contextlib.redirect_stderr(
                err
            ):
                rc = script.main(["--spec-json", spec, "--cache-dir", tmp])
            self.assertEqual(rc, rc_expected)
            self.assertIn(needle, out.getvalue() + err.getvalue())

    def test_apply_calls_write_raw_with_slug_and_url(self):
        rc, write_raw = self.run_main("--apply")
        self.assertEqual(rc, 0)
        args, kwargs = write_raw.call_args
        self.assertEqual(args[1], "ext-owasp-yt")
        paths = [c[0] for c in args[2]]
        self.assertIn("vid00000001", paths)
        self.assertIn("vid00000001#t=1", paths)
        self.assertEqual(
            kwargs["url_for"]("vid00000001#t=95"),
            "https://www.youtube.com/watch?v=vid00000001&t=95s",
        )


if __name__ == "__main__":
    unittest.main()
