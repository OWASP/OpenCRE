import unittest
from flask import current_app
from application import create_app, sqla


class DummyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(mode='test')
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def test_app_exists(self):
        self.assertFalse(current_app is None)

    def test_app_is_testing(self):
        self.assertTrue(current_app.config['TESTING'])