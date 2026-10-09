from cre_logging import get_logger

logger = get_logger(__name__)

import os
import unittest

from application import worker


class TestWorkerQueues(unittest.TestCase):
    def test_default_queues_include_ga_not_oie(self) -> None:
        os.environ.pop("CRE_WORKER_QUEUES", None)
        queues = worker._listen_queues()
        self.assertEqual(queues, ["high", "default", "low", "ga"])
        self.assertNotIn("oie", queues)

    def test_env_configured_queues(self) -> None:
        os.environ["CRE_WORKER_QUEUES"] = "ga,default"
        try:
            self.assertEqual(worker._listen_queues(), ["ga", "default"])
        finally:
            os.environ.pop("CRE_WORKER_QUEUES", None)


if __name__ == "__main__":
    unittest.main()
