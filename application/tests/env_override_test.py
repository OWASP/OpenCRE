import os
import unittest

from application.tests.env_override import environ_override, set_environ_for_test

_KEY = "ENV_OVERRIDE_TEST_KEY"
_OTHER = "ENV_OVERRIDE_TEST_OTHER"


class TestEnvironOverride(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop(_KEY, None)
        os.environ[_OTHER] = "kept"
        self.addCleanup(os.environ.pop, _OTHER, None)

    def test_sets_and_restores_values(self) -> None:
        with environ_override({_KEY: "1"}):
            self.assertEqual(os.environ[_KEY], "1")
        self.assertNotIn(_KEY, os.environ)

    def test_restores_a_changed_and_an_unset_key(self) -> None:
        with environ_override({_OTHER: "changed"}):
            self.assertEqual(os.environ[_OTHER], "changed")
        self.assertEqual(os.environ[_OTHER], "kept")
        with environ_override(unset=[_OTHER]):
            self.assertNotIn(_OTHER, os.environ)
        self.assertEqual(os.environ[_OTHER], "kept")

    def test_restores_keys_the_body_added_or_removed_itself(self) -> None:
        with environ_override({_KEY: "1"}):
            os.environ["ENV_OVERRIDE_TEST_ADDED"] = "x"
            del os.environ[_OTHER]
        self.assertNotIn("ENV_OVERRIDE_TEST_ADDED", os.environ)
        self.assertEqual(os.environ[_OTHER], "kept")

    def test_clear_starts_from_an_empty_environment(self) -> None:
        with environ_override({_KEY: "1"}, clear=True):
            self.assertEqual(dict(os.environ), {_KEY: "1"})
        self.assertEqual(os.environ[_OTHER], "kept")

    def test_restores_when_the_body_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            with environ_override({_KEY: "1"}):
                raise RuntimeError("boom")
        self.assertNotIn(_KEY, os.environ)

    def test_set_environ_for_test_restores_after_the_test(self) -> None:
        class Inner(unittest.TestCase):
            def runTest(self) -> None:
                set_environ_for_test(self, {_KEY: "inner"})
                assert os.environ[_KEY] == "inner"

        result = unittest.TestResult()
        Inner().run(result)
        self.assertTrue(result.wasSuccessful())
        self.assertNotIn(_KEY, os.environ)


if __name__ == "__main__":
    unittest.main()
