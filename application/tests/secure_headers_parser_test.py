from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.prompt_client.prompt_client import PromptHandler
from application.utils.external_project_parsers.parsers import secure_headers
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
            links=[defs.Link(document=cre, ltype=defs.LinkTypes.LinkedTo)],
        )
        for name, nodes in entries.results.items():
            self.assertEqual(name, secure_headers.SecureHeaders().name)

            self.maxDiff = None
            self.assertEqual(len(nodes), 1)
            self.assertCountEqual(expected.todict(), nodes[0].todict())

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
