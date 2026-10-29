import json
import unittest
from types import SimpleNamespace

from application.utils.comprehension import external as ext


def site(**kw):
    base = {
        "id": "owasp-benelux",
        "name": "OWASP Benelux",
        "start_urls": ["https://owaspbenelux.eu/"],
    }
    base.update(kw)
    return base


class TestExternalContract(unittest.TestCase):
    def test_valid_site_and_slug(self):
        s = ext.validate_spec(site(aliases=[" Benelux Day ", ""]))
        self.assertEqual(s.status, ext.STATUS_SUGGESTED)
        self.assertEqual(s.aliases, ["Benelux Day"])
        self.assertEqual(ext.slug_for(s), "ext-owasp-benelux")
        self.assertTrue(ext.is_external_slug("ext-x"))
        self.assertFalse(ext.is_external_slug("owasp-aisvs"))

    def test_invalid_specs_are_rejected(self):
        for bad in (
            site(id="Bad Id"),
            site(name=" "),
            site(kind="nope"),
            site(status="maybe"),
            site(weight=4),
            site(start_urls=[]),
            site(start_urls=["ftp://x"]),
            site(max_pages=0),
            site(max_depth=True),
            {"id": "yt-owasp", "name": "OWASP", "kind": ext.KIND_YOUTUBE},
            "not a dict",
        ):
            with self.assertRaises(ValueError, msg=str(bad)):
                ext.validate_spec(bad)

    def test_youtube_spec_and_page_url(self):
        s = ext.validate_spec(
            {
                "id": "yt-owasp",
                "name": "OWASP",
                "kind": ext.KIND_YOUTUBE,
                "channel_id": "UC123",
            }
        )
        self.assertEqual(
            ext.page_url(s, "abc123"), "https://www.youtube.com/watch?v=abc123"
        )
        self.assertEqual(
            ext.page_url(s, "abc123#t=90"),
            "https://www.youtube.com/watch?v=abc123&t=90s",
        )
        site_spec = ext.validate_spec(site())
        self.assertEqual(
            ext.page_url(site_spec, "https://owaspbenelux.eu/x"),
            "https://owaspbenelux.eu/x",
        )

    def test_spec_from_target_roundtrip_and_non_external(self):
        spec = ext.validate_spec(site(status=ext.STATUS_APPROVED))
        row = SimpleNamespace(
            id="owasp-benelux",
            name="OWASP Benelux",
            kind=ext.KIND_SITE,
            spec_json=ext.spec_to_json(spec),
            enabled=True,
        )
        self.assertEqual(ext.spec_from_target(row), spec)
        self.assertIsNone(
            ext.spec_from_target(
                SimpleNamespace(kind="oie_repo", spec_json="{}", id="x", name="x")
            )
        )
        broken = SimpleNamespace(
            id="b",
            name="b",
            kind=ext.KIND_SITE,
            spec_json=json.dumps({"start_urls": []}),
            enabled=True,
        )
        self.assertIsNone(ext.spec_from_target(broken))


if __name__ == "__main__":
    unittest.main()
