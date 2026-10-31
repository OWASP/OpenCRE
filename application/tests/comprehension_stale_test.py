import unittest
from unittest import mock

from application.utils.comprehension import store

CHUNKS = [(f"vid{i}", 0, f"talk {i}") for i in range(4)]


def urls(chunks):
    return [
        f"owasp-agent://evidence/{d[0]}" for d in store.raw_documents("ext-yt", chunks)
    ]


class FakeSession:
    def __init__(self, stored):
        self.stored, self.deleted, self.commits = stored, [], 0

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.lstrip().upper().startswith("SELECT"):
            return mock.Mock(fetchall=lambda: [(u,) for u in self.stored])
        self.deleted.append(params["u"])
        return mock.Mock()

    def commit(self):
        self.commits += 1


class StaleRawTest(unittest.TestCase):
    def test_lists_stored_chunks_missing_from_the_new_run(self):
        stored = urls(CHUNKS)  # 4 stored, run now only has the first 3
        db = mock.Mock(session=FakeSession(stored))
        self.assertEqual(store.stale_raw_urls(db, "ext-yt", CHUNKS[:3]), [stored[3]])

    def test_delete_removes_and_commits(self):
        stored = urls(CHUNKS)
        s = FakeSession(stored)
        n = store.delete_stale_raw(mock.Mock(session=s), "ext-yt", CHUNKS[:3])
        self.assertEqual((n, s.deleted, s.commits), (1, [stored[3]], 1))

    def test_empty_run_never_wipes_the_source(self):
        s = FakeSession(urls(CHUNKS))
        with self.assertRaises(ValueError):
            store.delete_stale_raw(mock.Mock(session=s), "ext-yt", [])
        self.assertEqual(s.deleted, [])

    def test_large_deletion_needs_force(self):
        s = FakeSession(urls(CHUNKS))
        with self.assertRaises(ValueError):
            store.delete_stale_raw(mock.Mock(session=s), "ext-yt", CHUNKS[:1])
        self.assertEqual(s.deleted, [])
        n = store.delete_stale_raw(
            mock.Mock(session=s), "ext-yt", CHUNKS[:1], force=True
        )
        self.assertEqual(n, 3)

    def test_nothing_stale_is_a_noop(self):
        s = FakeSession(urls(CHUNKS))
        self.assertEqual(
            store.delete_stale_raw(mock.Mock(session=s), "ext-yt", CHUNKS), 0
        )
        self.assertEqual(s.commits, 0)


if __name__ == "__main__":
    unittest.main()


class ApiCacheTtlTest(unittest.TestCase):
    def test_old_cached_responses_are_refetched(self):
        import os
        import tempfile
        import time

        from application.utils.comprehension import youtube_source as ys

        calls = []

        def get(url, params, headers):
            calls.append(url)
            return {"items": [len(calls)]}

        with tempfile.TemporaryDirectory() as tmp:
            api = ys.YouTubeApi(api_key="k", http_get=get, cache_dir=tmp)
            self.assertEqual(api._call("videos", {"id": "a"}), {"items": [1]})
            self.assertEqual(
                api._call("videos", {"id": "a"}), {"items": [1]}
            )  # fresh: cached
            self.assertEqual(len(calls), 1)
            for f in os.listdir(tmp):  # age the cache past the TTL
                old = time.time() - ys.CACHE_MAX_AGE_SECONDS - 60
                os.utime(os.path.join(tmp, f), (old, old))
            self.assertEqual(api._call("videos", {"id": "a"}), {"items": [2]})
