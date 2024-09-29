import json
from typing import Any, Dict, List, Tuple
import unittest

from application.defs import cre_defs as defs

from application.utils import oscal_utils


def remove_empty_elements(d):
    """recursively remove empty lists, empty dicts, or None elements from a dictionary"""

    def empty(x):
        return x is None or x == {} or x == []

    if not isinstance(d, (dict, list)):
        return d
    elif isinstance(d, list):
        return [v for v in (remove_empty_elements(v) for v in d) if not empty(v)]
    else:
        return {
            k: v
            for k, v in ((k, remove_empty_elements(v)) for k, v in d.items())
            if not empty(v)
        }


class TestOSCALUtils(unittest.TestCase):
    def test_cre_document_to_oscal(self) -> None:
        cre = defs.CRE(name="cre-1", id="001-001", description="cre-desc")
        for i in range(0, 5):
            if i % 5 == 0:
                cre.add_link(
                    defs.Link(
                        document=defs.CRE(name=f"cre-{i}", id=f"{i}{i}{i}-{i}{i}{i}"),
                        ltype=defs.LinkTypes.LinkedTo,
                    )
                )
            elif i % 5 == 1:
                cre.add_link(
                    defs.Link(
                        document=defs.Standard(
                            name=f"standard-{i}",
                            section=f"{i}",
                            hyperlink=f"https://example.com/{i}",
                        ),
                        ltype=defs.LinkTypes.LinkedTo,
                    )
                )
            else:
                cre.add_link(
                    defs.Link(
                        document=defs.Tool(
                            name=f"tool-{i}",
                            sectionID=f"{i}",
                            hyperlink=f"https://example.com/{i}",
                        ),
                        ltype=defs.LinkTypes.LinkedTo,
                    )
                )

        expected = {
            "uuid": "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
            "metadata": {
                "title": "cre-1",
                "remarks": "cre-desc",
                "last_modified": "2023-02-03T16:17:31.695+00:00",
                "version": "0.0",
                "oscal_version": "1.0.0",
                "links": [
                    {
                        "href": f"https://opencre.org/cre/001-001",
                    }
                ],
            },
            "controls": [
                {
                    "id": "_000-000",
                    "title": "cre-0",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/000-000",
                        }
                    ],
                },
                {
                    "id": "_1",
                    "title": "standard-1",
                    "links": [
                        {
                            "href": "https://example.com/1",
                        }
                    ],
                },
                {
                    "id": "_2",
                    "title": "tool-2",
                    "links": [{"href": "https://example.com/2"}],
                },
                {
                    "id": "_3",
                    "title": "tool-3",
                    "links": [{"href": "https://example.com/3"}],
                },
                {
                    "id": "_4",
                    "title": "tool-4",
                    "links": [{"href": "https://example.com/4"}],
                },
            ],
        }
        self.maxDiff = None
        result = json.loads(
            oscal_utils.document_to_oscal(
                cre,
                "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
                "2023-02-03T16:17:31.695+00:00",
            )
        )

        self.assertDictEqual(remove_empty_elements(result), expected)

    def test_standard_document_to_oscal(self) -> None:
        standard = defs.Standard(
            name="s-1",
            id="111-111",
            version="v0.1.2",
            section="s-section",
            hyperlink="https://example.com/s-1/s-section",
        )
        for i in range(0, 5):
            standard.add_link(
                defs.Link(
                    document=defs.CRE(
                        name=f"cre-{i}",
                        id=f"{i}{i}{i}-{i}{i}{i}",
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
                )
            )

        expected = {
            "uuid": "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
            "metadata": {
                "title": "s-1",
                "last_modified": "2023-02-03T16:17:31.695+00:00",
                "version": "v0.1.2",
                "oscal_version": "1.0.0",
                "links": [
                    {
                        "href": "https://example.com/s-1/s-section",
                    }
                ],
            },
            "controls": [
                {
                    "id": "_000-000",
                    "title": "cre-0",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/000-000",
                        }
                    ],
                },
                {
                    "id": "_111-111",
                    "title": "cre-1",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/111-111",
                        }
                    ],
                },
                {
                    "id": "_222-222",
                    "title": "cre-2",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/222-222",
                        }
                    ],
                },
                {
                    "id": "_333-333",
                    "title": "cre-3",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/333-333",
                        }
                    ],
                },
                {
                    "id": "_444-444",
                    "title": "cre-4",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/444-444",
                        }
                    ],
                },
            ],
        }
        self.maxDiff = None
        result = json.loads(
            oscal_utils.document_to_oscal(
                standard,
                "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
                "2023-02-03T16:17:31.695+00:00",
            )
        )

        self.assertDictEqual(remove_empty_elements(result), expected)

    def test_tool_document_to_oscal(self) -> None:
        tool = defs.Tool(
            name="t-1",
            id="111-111",
            version="v0.1.2",
            sectionID="t-rule",
            hyperlink="https://example.com/t-1/t-rule",
        )
        for i in range(0, 5):
            tool.add_link(
                defs.Link(document=defs.CRE(name=f"cre-{i}", id=f"{i}{i}{i}-{i}{i}{i}"))
            )

        expected = {
            "uuid": "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
            "metadata": {
                "title": "t-1",
                "last_modified": "2023-02-03T16:17:31.695+00:00",
                "version": "v0.1.2",
                "oscal_version": "1.0.0",
                "links": [
                    {
                        "href": "https://example.com/t-1/t-rule",
                    }
                ],
            },
            "controls": [
                {
                    "id": "_000-000",
                    "title": "cre-0",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/000-000",
                        }
                    ],
                },
                {
                    "id": "_111-111",
                    "title": "cre-1",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/111-111",
                        }
                    ],
                },
                {
                    "id": "_222-222",
                    "title": "cre-2",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/222-222",
                        }
                    ],
                },
                {
                    "id": "_333-333",
                    "title": "cre-3",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/333-333",
                        }
                    ],
                },
                {
                    "id": "_444-444",
                    "title": "cre-4",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/444-444",
                        }
                    ],
                },
            ],
        }
        self.maxDiff = None
        result = json.loads(
            oscal_utils.document_to_oscal(
                tool,
                "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
                "2023-02-03T16:17:31.695+00:00",
            )
        )

        self.assertDictEqual(remove_empty_elements(result), expected)

    def test_list_to_oscal(self) -> None:
        standards = []
        for i in range(0, 4):
            standard = defs.Standard(
                name=f"s-{i}",
                id=f"{i}{i}{i}-{i}{i}{i}",
                version="v0.1.2",
                section="s-section",
                hyperlink=f"https://example.com/s-{i}/s-section",
            )
            for j in range(0, 5):
                standard.add_link(
                    defs.Link(
                        document=defs.CRE(name=f"cre-{j}", id=f"{j}{j}{j}-{j}{j}{j}"),
                        ltype=defs.LinkTypes.LinkedTo,
                    )
                )
            standards.append(standard)

        expected = {
            "controls": [
                {
                    "id": "_000-000",
                    "links": [{"href": "https://opencre.org/cre/000-000"}],
                    "title": "cre-0",
                },
                {
                    "id": "_111-111",
                    "links": [{"href": "https://opencre.org/cre/111-111"}],
                    "title": "cre-1",
                },
                {
                    "id": "_222-222",
                    "links": [{"href": "https://opencre.org/cre/222-222"}],
                    "title": "cre-2",
                },
                {
                    "id": "_333-333",
                    "links": [{"href": "https://opencre.org/cre/333-333"}],
                    "title": "cre-3",
                },
                {
                    "id": "_444-444",
                    "links": [{"href": "https://opencre.org/cre/444-444"}],
                    "title": "cre-4",
                },
            ],
            "metadata": {
                "last_modified": "2023-02-03T16:17:31.695+00:00",
                "links": [{"href": "https://example.com/s-3/s-section"}],
                "oscal_version": "1.0.0",
                "title": "s-3",
                "version": "v0.1.2",
            },
            "uuid": "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
        }
        self.maxDiff = None
        result = json.loads(
            oscal_utils.document_to_oscal(
                standard,
                "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
                "2023-02-03T16:17:31.695+00:00",
            )
        )
        self.assertDictEqual(remove_empty_elements(result), expected)

    def test_tool_document_to_oscal(self) -> None:
        tool = defs.Tool(
            name="t-1",
            id="-1",
            version="v0.1.2",
            sectionID="t-rule",
            hyperlink="https://example.com/t-1/t-rule",
        )
        for i in range(0, 5):
            tool.add_link(
                defs.Link(
                    document=defs.CRE(
                        name=f"cre-{i}",
                        id=f"{i}{i}{i}-{i}{i}{i}",
                    ),
                    ltype=defs.LinkTypes.LinkedTo,
                )
            )

        expected = {
            "uuid": "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
            "metadata": {
                "title": "t-1",
                "last_modified": "2023-02-03T16:17:31.695+00:00",
                "version": "v0.1.2",
                "oscal_version": "1.0.0",
                "links": [
                    {
                        "href": "https://example.com/t-1/t-rule",
                    }
                ],
            },
            "controls": [
                {
                    "id": "_000-000",
                    "title": "cre-0",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/000-000",
                        }
                    ],
                },
                {
                    "id": "_111-111",
                    "title": "cre-1",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/111-111",
                        }
                    ],
                },
                {
                    "id": "_222-222",
                    "title": "cre-2",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/222-222",
                        }
                    ],
                },
                {
                    "id": "_333-333",
                    "title": "cre-3",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/333-333",
                        }
                    ],
                },
                {
                    "id": "_444-444",
                    "title": "cre-4",
                    "links": [
                        {
                            "href": "https://opencre.org/cre/444-444",
                        }
                    ],
                },
            ],
        }
        self.maxDiff = None
        result = json.loads(
            oscal_utils.document_to_oscal(
                tool,
                "46c335c9-b9b7-4043-a722-2e5fdc3ccf67",
                "2023-02-03T16:17:31.695+00:00",
            )
        )
        self.assertDictEqual(remove_empty_elements(result), expected)


if __name__ == "__main__":
    unittest.main()
