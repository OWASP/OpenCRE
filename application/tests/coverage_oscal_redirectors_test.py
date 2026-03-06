import unittest
from datetime import datetime

from application.defs import cre_defs as defs
from application.utils import oscal_utils, redirectors


class TestOscalUtilsCoverage(unittest.TestCase):
    def test_document_to_oscal_cre_and_standard(self):
        cre = defs.CRE(id="123-123", name="C", description="desc")
        cre.add_link(
            defs.Link(
                document=defs.CRE(id="124-124", name="C2"),
                ltype=defs.LinkTypes.LinkedTo,
            )
        )
        out_cre = oscal_utils.document_to_oscal(cre, None, datetime.now().astimezone())
        self.assertIn('"title": "C"', out_cre)
        self.assertIn("123-123", out_cre)

        std = defs.Standard(
            name="ASVS",
            section="A",
            sectionID="1",
            hyperlink="https://example.com/std",
            version="4.0",
        )
        std.add_link(
            defs.Link(
                document=defs.Standard(
                    name="CWE", section="79", sectionID="79", hyperlink="https://cwe"
                ),
                ltype=defs.LinkTypes.LinkedTo,
            )
        )
        valid_uuid = "123e4567-e89b-42d3-a456-426614174000"
        out_std = oscal_utils.document_to_oscal(
            std, valid_uuid, datetime.now().astimezone()
        )
        self.assertIn(f'"uuid": "{valid_uuid}"', out_std)
        self.assertIn("https://example.com/std", out_std)

    def test_list_to_oscal_standard_and_tool(self):
        standards = [
            defs.Standard(
                name="ASVS", section="A", sectionID="1", hyperlink="https://a"
            )
        ]
        out_std = oscal_utils.list_to_oscal(standards)
        self.assertIn('"title": "ASVS"', out_std)
        self.assertIn("sectionID", out_std)

        tools = [
            defs.Tool(
                name="ToolX",
                section="Rule",
                sectionID="R1",
                hyperlink="https://tool",
                tooltype=defs.ToolTypes.Defensive,
            )
        ]
        out_tool = oscal_utils.list_to_oscal(tools)
        self.assertIn('"title": "ToolX"', out_tool)
        self.assertIn("https://tool", out_tool)


class TestRedirectorsCoverage(unittest.TestCase):
    def test_redirector_helpers_and_dispatch(self):
        self.assertIn("definitions/79.html", redirectors.cwe_redirector(79))
        self.assertIn("definitions/100.html", redirectors.capec_redirector(100))
        self.assertIn("definitions/79.html", redirectors.redirect("cwe", 79))
        self.assertIn("definitions/100.html", redirectors.redirect("capec", 100))
        self.assertIsNone(redirectors.redirect("unknown", 1))


if __name__ == "__main__":
    unittest.main()
