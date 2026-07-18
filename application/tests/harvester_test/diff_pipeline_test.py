from datetime import UTC, datetime
import subprocess
import time
import unittest

from application.utils.harvester.diff_normalizer import DiffNormalizer
from application.utils.harvester.diff_parser import DiffParser
from application.utils.harvester.diff_retriever import DiffRetriever
from application.utils.harvester.git_repository_client import GitRepositoryClient


class DiffPipelineBenchmark(unittest.TestCase):
    """
    Simple benchmark to ensure the complete diff pipeline remains fast.

    This is not intended as a strict performance benchmark, only as a
    regression guard against accidental slowdowns.
    """

    def test_pipeline_benchmark(self):
        client = GitRepositoryClient(
            "OWASP",
            "ASVS",
            "master",
        )
        client.sync()

        head_commit = client.get_current_commit_sha()

        previous_commit = subprocess.run(
            [
                "git",
                "-C",
                str(client.get_local_path()),
                "rev-parse",
                "HEAD~1",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        ).stdout.strip()

        retriever = DiffRetriever(client)
        parser = DiffParser()
        normalizer = DiffNormalizer()

        start = time.perf_counter()

        diff = retriever.get_diff(
            previous_commit,
            head_commit,
        )

        blocks = parser.parse(
            diff,
            repository="OWASP/ASVS",
            commit_sha=head_commit,
            committed_at=datetime.now(UTC),
        )

        normalizer.normalize(blocks)

        elapsed = time.perf_counter() - start

        print(f"\nPipeline took {elapsed:.3f}s")

        self.assertLess(elapsed, 5)
