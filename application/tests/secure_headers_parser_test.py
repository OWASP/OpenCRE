from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.prompt_client.prompt_client import PromptHandler
from application.utils.external_project_parsers.parsers import secure_headers
from application.utils.external_project_parsers.parsers.secure_headers import (
    SecureHeadersLinkError,
)
from application.database import db
from application.utils import git
import tempfile
from unittest.mock import patch
import os


class TestSecureHeadersParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(git, "clone")
    def test_register_headers(self, mock_clone) -> None:
        cs = self.md

        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        tmpdir = os.path.join(loc, "content")
        os.mkdir(tmpdir)
        repo.working_dir = loc
        cre = defs.CRE(name="blah", id="223-780")
        self.collection.add_cre(cre)
        with open(os.path.join(tmpdir, "cs.md"), "w") as mdf:
            mdf.write(cs)
        mock_clone.return_value = repo
        entries = secure_headers.SecureHeaders().parse(
            cache=self.collection, ph=PromptHandler(database=self.collection)
        )
        expected = defs.Standard(
            name="Secure Headers",
            hyperlink="https://example.com/foo/bar",
            section="headerAsection",
            links=[
                defs.Link(
                    document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo
                )
            ],
            tags=[
                "family:guidance",
                "subtype:cheatsheet",
                "source:owasp_secure_headers",
                "audience:developer",
                "maturity:stable",
            ],
        )
        for name, nodes in entries.results.items():
            self.assertEqual(name, secure_headers.SecureHeaders().name)

            self.maxDiff = None
            self.assertEqual(len(nodes), 1)
            self.assertCountEqual(expected.todict(), nodes[0].todict())

    @patch.object(git, "clone")
    def test_register_headers_creates_one_entry_per_opencre_link(self, mock_clone) -> None:
        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        tmpdir = os.path.join(loc, "content")
        os.mkdir(tmpdir)
        repo.working_dir = loc
        cre_a = defs.CRE(name="HTTP security headers", id="636-347")
        cre_b = defs.CRE(
            name="Do not disclose technical information in HTTP header or response",
            id="743-110",
        )
        self.collection.add_cre(cre_a)
        self.collection.add_cre(cre_b)
        md = """See [first](https://www.opencre.org/cre/636-347?name=Secure+Headers&section=First&link=https%3A%2F%2Fexample.com%2Ffirst)
and [second](https://www.opencre.org/cre/403-005?name=Secure+Headers&section=Second&link=https%3A%2F%2Fexample.com%2Fsecond)
"""
        with open(os.path.join(tmpdir, "cs.md"), "w") as mdf:
            mdf.write(md)
        mock_clone.return_value = repo
        entries = secure_headers.SecureHeaders().parse(
            cache=self.collection, ph=PromptHandler(database=self.collection)
        )
        nodes = entries.results[secure_headers.SecureHeaders().name]
        self.assertEqual(2, len(nodes))
        self.assertEqual({"First", "Second"}, {node.section for node in nodes})
        self.assertEqual(
            {"636-347", "743-110"},
            {node.links[0].document.id for node in nodes},
        )

    @patch.object(git, "clone")
    def test_register_headers_raises_for_unknown_cre_id(self, mock_clone) -> None:
        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        tmpdir = os.path.join(loc, "content")
        os.mkdir(tmpdir)
        repo.working_dir = loc
        md = """See [missing](https://www.opencre.org/cre/999-999?name=Secure+Headers&section=Missing&link=https%3A%2F%2Fexample.com%2Fmissing)
"""
        with open(os.path.join(tmpdir, "cs.md"), "w") as mdf:
            mdf.write(md)
        mock_clone.return_value = repo

        with self.assertRaises(SecureHeadersLinkError):
            secure_headers.SecureHeaders().parse(
                cache=self.collection, ph=PromptHandler(database=self.collection)
            )

    @patch.object(git, "clone")
    def test_register_headers_keeps_first_link_when_it_is_the_only_valid_one(
        self, mock_clone
    ) -> None:
        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        tmpdir = os.path.join(loc, "content")
        os.mkdir(tmpdir)
        repo.working_dir = loc
        cre = defs.CRE(name="HTTP security headers", id="636-347")
        self.collection.add_cre(cre)
        md = """See [first](https://www.opencre.org/cre/636-347?name=Secure+Headers&section=First&link=https%3A%2F%2Fexample.com%2Ffirst)
"""
        with open(os.path.join(tmpdir, "cs.md"), "w") as mdf:
            mdf.write(md)
        mock_clone.return_value = repo

        entries = secure_headers.SecureHeaders().register_headers(
            cache=self.collection, repo=repo, file_path="./", repo_path=""
        )

        self.assertEqual(1, len(entries))
        self.assertEqual("First", entries[0].section)
        self.assertEqual("636-347", entries[0].links[0].document.id)

    @patch.object(git, "clone")
    def test_register_headers_raises_when_later_link_is_unknown(
        self, mock_clone
    ) -> None:
        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        tmpdir = os.path.join(loc, "content")
        os.mkdir(tmpdir)
        repo.working_dir = loc
        cre = defs.CRE(name="HTTP security headers", id="636-347")
        self.collection.add_cre(cre)
        md = """See [first](https://www.opencre.org/cre/636-347?name=Secure+Headers&section=First&link=https%3A%2F%2Fexample.com%2Ffirst)
and [missing](https://www.opencre.org/cre/999-999?name=Secure+Headers&section=Missing&link=https%3A%2F%2Fexample.com%2Fmissing)
"""
        with open(os.path.join(tmpdir, "cs.md"), "w") as mdf:
            mdf.write(md)
        mock_clone.return_value = repo

        with self.assertRaises(SecureHeadersLinkError):
            secure_headers.SecureHeaders().register_headers(
                cache=self.collection, repo=repo, file_path="./", repo_path=""
            )

    md = """ # Secure Headers

1. [Introduction](#1-Introduction)
2. [General](#2-General)
3. [Continuous Integration (CI) and Continuous Deployment (CD)](#3-Continuous-Integration-(CI)-and-Continuous-Deployment-(CD))
4. [Cloud Providers](#4-Cloud-Providers)
5. [Containers and Orchestration](#5-Containers-&-Orchestrators)
6. [Implementation Guidance](#6-Implementation-Guidance)

## 1 Introduction
blah
## 2 General
blah
### 2.1 High Availability


See [the Open CRE project](https://www.opencre.org/cre/223-780?name=Secure+Headers&section=headerAsection&link=https%3A%2F%2Fexample.comfoo%2Fbar) for more technical recommendations.

"""
