from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.prompt_client.prompt_client import PromptHandler
from application.utils.external_project_parsers.parsers import cheatsheets_parser
from application.database import db
from application.utils import git
import tempfile
from unittest.mock import patch
import os


class TestCheatsheetsParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(git, "clone")
    def test_register_cheatsheet(self, mock_clone) -> None:
        cs = self.cheatsheets_md

        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        os.mkdir(os.path.join(loc, "cheatsheets"))
        repo.working_dir = loc
        cre = defs.CRE(name="blah", id="223-780")
        self.collection.add_cre(cre)
        with open(os.path.join(os.path.join(loc, "cheatsheets"), "cs.md"), "w") as mdf:
            mdf.write(cs)
        mock_clone.return_value = repo
        entries = cheatsheets_parser.Cheatsheets().parse(
            cache=self.collection, ph=PromptHandler(database=self.collection)
        )
        expected = defs.Standard(
            name="OWASP Cheat Sheets",
            hyperlink="https://github.com/foo/bar/tree/master/cs.md",
            section="Secrets Management Cheat Sheet",
            links=[defs.Link(document=cre, ltype=defs.LinkTypes.LinkedTo)],
        )
        self.maxDiff = None
        for name, nodes in entries.results.items():
            self.assertEqual(name, cheatsheets_parser.Cheatsheets().name)
            self.assertEqual(len(nodes), 1)
            self.assertCountEqual(expected.todict(), nodes[0].todict())

    cheatsheets_md = """ # Secrets Management Cheat Sheet

1. [Introduction](#1-Introduction)
2. [General Secrets Management](#2-General-Secrets-Management)
3. [Continuous Integration (CI) and Continuous Deployment (CD)](#3-Continuous-Integration-(CI)-and-Continuous-Deployment-(CD))
4. [Cloud Providers](#4-Cloud-Providers)
5. [Containers and Orchestration](#5-Containers-&-Orchestrators)
6. [Implementation Guidance](#6-Implementation-Guidance)
7. [Encryption](#7-Encryption)
8. [Secret detection](#8-Detection)
9. [Incident Response](#9-Incident-Response)

## 1 Introduction
blah
## 2 General Secrets Management
blah
### 2.1 High Availability
blah
### 2.2 Centralize and Standardize
blah
### 2.3 Access Control
blah
### 2.4 Automate Secrets Management
blahblah
### 2.5 Auditing
blah
### 2.6 Secret Lifecycle
blah
#### 2.6.1 Creation

See [the Open CRE project on secrets lookup](https://www.opencre.org/cre/223-780) for more technical recommendations on secret creation.

#### 2.6.2 Rotation
1. Revocation: Keys that were exposed should ensure immediate revocation. The secret must be able to be de-authorized quickly, and systems must be in place to identify the revocation status.
2. Rotation: A new secret must be able to be quickly created and implemented, preferably via an automated process to ensure repeatability, low rate of implementation error, and least-privilege (not directly human-readable).
3. Deletion: Secrets revoked/rotated must be removed from the exposed system immediately, including secrets discovered in code or logs. Secrets in code should have commit history for the exposure squashed to before the introduction of the secret, and logs must have a process for removing the secret while maintaining log integrity.
4. Logging: Incident response teams must have access to information about the lifecycle of a secret to aid in containment and remediation, including:
    - Who had access?
    - When did they use it?
    - When was it previously rotated?


## 10 Related Cheat Sheets & further reading

- [Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP WrongSecrets project](https://github.com/commjoen/wrongsecrets/)
- [Blog: 10 Pointers on Secrets Management](https://xebia.com/blog/secure-deployment-10-pointers-on-secrets-management/)
- [Blog: From build to run: pointers on secure deployment](https://xebia.com/from-build-to-run-pointers-on-secure-deployment/)
- [Listing of possible secret management tooling](https://gist.github.com/maxvt/bb49a6c7243163b8120625fc8ae3f3cd)
- [Github listing on secrets detection tools](https://github.com/topics/secrets-detection)
- [OpenCRE References to secrets](https://www.opencre.org/search/secret)
- [NIST SP 800-57 Recommendation for Key Management](https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final)


"""
