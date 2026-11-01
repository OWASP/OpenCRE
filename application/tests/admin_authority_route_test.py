import os
import unittest
from unittest import mock

from application import create_app, sqla


class AdminAuthorityRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(
            os.environ,
            {
                "NO_LOGIN": "1",
                "CRE_ALLOW_IMPORT": "1",
                "NO_LOAD_GRAPH_DB": "1",
                "INSECURE_REQUESTS": "1",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_non_object_weights_are_a_400_not_a_500(self) -> None:
        with self.app.test_client() as client:
            for body in ({"weights": [1, 2]}, {"weights": "x"}, {}):
                resp = client.put("/admin/authority", json=body)
                self.assertEqual(resp.status_code, 400, (body, resp.get_data()))


if __name__ == "__main__":
    unittest.main()
