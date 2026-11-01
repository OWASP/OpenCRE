import unittest
from unittest import mock

from application.utils.oie_scheduler import schedule_settings as ss


class ScheduleSettingsTest(unittest.TestCase):
    def test_effective_interval_uses_valid_override_else_default(self):
        with mock.patch.object(ss.runtime_settings, "get_setting", return_value="30"):
            self.assertEqual(ss.effective_interval_minutes("owasp", 10), 30)
        for bad in ("abc", "0", "-5", str(ss.MAX_INTERVAL_MINUTES + 1)):
            with mock.patch.object(
                ss.runtime_settings, "get_setting", return_value=bad
            ):
                self.assertEqual(ss.effective_interval_minutes("owasp", 10), 10)
        with mock.patch.object(ss.runtime_settings, "get_setting", return_value=None):
            self.assertEqual(ss.effective_interval_minutes("owasp", 10), 10)

    def test_job_enabled_defaults_on_and_respects_off(self):
        with mock.patch.object(ss.runtime_settings, "get_setting", return_value=None):
            self.assertTrue(ss.job_enabled("owasp"))
        with mock.patch.object(ss.runtime_settings, "get_setting", return_value="0"):
            self.assertFalse(ss.job_enabled("owasp"))
        with mock.patch.object(ss.runtime_settings, "get_setting", return_value="true"):
            self.assertTrue(ss.job_enabled("owasp"))

    def test_validate_update(self):
        self.assertEqual(
            ss.validate_update("owasp", "15", None), {"interval_minutes": 15}
        )
        self.assertEqual(ss.validate_update("owasp", None, False), {"enabled": False})
        for args in (
            ("nope", 5, None),
            ("owasp", 0, None),
            ("owasp", "x", None),
            ("owasp", True, None),
            ("owasp", None, "yes"),
            ("owasp", None, None),
        ):
            with self.assertRaises(ValueError):
                ss.validate_update(*args)

    def test_apply_update_writes_both_keys_with_actor(self):
        with mock.patch.object(ss.runtime_settings, "set_setting") as put:
            ss.apply_update(
                "cre_expansion", {"interval_minutes": 60, "enabled": False}, actor="a@b"
            )
        put.assert_any_call("OIE_JOB_CRE_EXPANSION_INTERVAL_MINUTES", "60", actor="a@b")
        put.assert_any_call("OIE_JOB_CRE_EXPANSION_ENABLED", "0", actor="a@b")

    def test_list_schedule_marks_overrides_and_disabled(self):
        def fake(key):
            return {
                "OIE_JOB_OWASP_INTERVAL_MINUTES": "20",
                "OIE_JOB_CRE_EXPANSION_ENABLED": "0",
            }.get(key)

        with mock.patch.object(ss.runtime_settings, "get_setting", side_effect=fake):
            rows = {r["job"]: r for r in ss.list_schedule(None)}
        self.assertTrue(rows["owasp"]["overridden"])
        self.assertEqual(rows["owasp"]["interval_minutes"], 20)
        self.assertFalse(rows["cre_expansion"]["enabled"])
        self.assertIsNone(rows["cre_expansion"]["next_expected"])
        self.assertFalse(rows["cre_expansion"]["overridden"])


if __name__ == "__main__":
    unittest.main()
