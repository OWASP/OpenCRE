import asyncio
import threading
import time
import unittest

from flask import Flask, current_app

from application.mcp.server import run_blocking_with_app


class RunBlockingWithAppTest(unittest.TestCase):
    def test_three_slow_calls_overlap_instead_of_queueing(self) -> None:
        app = Flask(__name__)
        seen_threads = set()

        def slow() -> str:
            seen_threads.add(threading.get_ident())
            assert current_app.name == app.name  # each call has an app context
            time.sleep(0.4)
            return "ok"

        async def run() -> float:
            with app.app_context():
                t0 = time.perf_counter()
                out = await asyncio.gather(
                    *[run_blocking_with_app(slow) for _ in range(3)]
                )
                self.assertEqual(out, ["ok", "ok", "ok"])
                return time.perf_counter() - t0

        elapsed = asyncio.run(run())
        self.assertLess(elapsed, 1.0)  # serial would take ~1.2 s
        self.assertGreater(len(seen_threads), 1)

    def test_runs_inline_without_a_flask_app(self) -> None:
        async def run() -> str:
            return await run_blocking_with_app(lambda: "inline")

        self.assertEqual(asyncio.run(run()), "inline")


if __name__ == "__main__":
    unittest.main()
