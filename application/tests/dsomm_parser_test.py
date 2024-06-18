from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
from unittest.mock import patch
from application.utils.external_project_parsers.parsers import dsomm
from application.prompt_client import prompt_client
import requests


class TestDSOMM(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

        self.collection = db.Node_collection()

    @patch.object(requests, "get")
    def test_parse(self, mock_requests) -> None:
        class fakeRequest:
            status_code = 200
            text = gen_yaml

        mock_requests.return_value = fakeRequest()
        cres = []
        nodes = []
        for item in ["I-SB-2-A", "I-SB-1-A", "14.2.6", "12.1.1", "8.31", "5.37"]:
            dbsamm = self.collection.add_node(
                defs.Standard(name="SAMM", sectionID=item)
            )
            dbiso = self.collection.add_node(
                defs.Standard(name="ISO 27001", sectionID=item)
            )
            cre = defs.CRE(id=f"123-123", name=f"CRE-{item}")
            cres.append(cre)
            dbcre = self.collection.add_cre(cre=cre)
            self.collection.add_link(cre=dbcre, node=dbsamm)
            self.collection.add_link(cre=dbcre, node=dbiso)
        entries = dsomm.DSOMM().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )
        expected = [
            defs.Standard(
                name=dsomm.DSOMM().name,
                doctype=defs.Credoctypes.Standard,
                links=[
                    defs.Link(document=defs.CRE(name="CRE-I-SB-2-A", id="123-123")),
                ],
                description="Description:While building and testing artifacts, third party "
                "systems, application frameworks\n"
                "and 3rd party libraries are used. These might be malicious as "
                "a result of\n"
                "vulnerable libraries or because they are altered during the "
                "delivery phase.\n"
                " Risk:While building and testing artifacts, third party "
                "systems, application frameworks\n"
                "and 3rd party libraries are used. These might be malicious as "
                "a result of\n"
                "vulnerable libraries or because they are altered during the "
                "delivery phase.\n"
                " Measure:Each step during within the build and testing phase "
                "is performed in a separate virtual environments, which is "
                "destroyed afterward.",
                hyperlink="https://capec.mitre.org/data/definitions/1.html",
                sectionID="a340f46b-6360-4cb8-847b-a0d3483d09d3",
                section="Build",
                subsection="Building and testing of artifacts in virtual environments",
            ),
            defs.Standard(
                name=dsomm.DSOMM().name,
                doctype=defs.Credoctypes.Standard,
                links=[
                    defs.Link(document=defs.CRE(name="CRE-5.37", id="537-537")),
                ],
                description="Description:Sample evidence as an attribute in the yaml: The "
                "build process is defined in [REPLACE-ME "
                "Pipeline](https://replace-me/jenkins/job)\n"
                "in the folder _vars_. Projects are using a _Jenkinsfile_ to "
                "use the\n"
                "defined process.\n"
                "\n"
                " Risk:Performing builds without a defined process is error "
                "prone; for example, as a result of incorrect security related "
                "configuration.\n"
                " Measure:A well defined build process lowers the possibility "
                "of errors during the build process.",
                hyperlink="https://capec.mitre.org/data/definitions/1.html",
                sectionID="f6f7737f-25a9-4317-8de2-09bf59f29b5b",
                section="Build",
                subsection="Defined build process",
            ),
        ]
        for name, nodes in entries.results.items():
            self.assertEqual(name, dsomm.DSOMM().name)
            self.assertEqual(len(nodes), 2)
            self.assertCountEqual(nodes[0].todict(), expected[0].todict())
            self.assertCountEqual(nodes[1].todict(), expected[1].todict())


gen_yaml = """
---
Build and Deployment:
  Build:
    Building and testing of artifacts in virtual environments:
      uuid: a340f46b-6360-4cb8-847b-a0d3483d09d3
      description: |-
        While building and testing artifacts, third party systems, application frameworks
        and 3rd party libraries are used. These might be malicious as a result of
        vulnerable libraries or because they are altered during the delivery phase.
      risk: |-
        While building and testing artifacts, third party systems, application frameworks
        and 3rd party libraries are used. These might be malicious as a result of
        vulnerable libraries or because they are altered during the delivery phase.
      measure: Each step during within the build and testing phase is performed in
        a separate virtual environments, which is destroyed afterward.
      meta:
        implementationGuide: Depending on your environment, usage of virtual machines
          or container technology is a good way. After the build, the filesystem should
          not be used again in other builds.
      difficultyOfImplementation:
        knowledge: 2
        time: 2
        resources: 2
      usefulness: 2
      level: 2
      implementation:
      - uuid: b4bfead3-5fb6-4dd0-ba44-5da713bd22e4
        name: CI/CD tools
        tags:
        - ci-cd
        url: https://martinfowler.com/articles/continuousIntegration.html
        description: CI/CD tools such as jenkins, gitlab-ci or github-actions
      references:
        samm2:
        - I-SB-2-A
        iso27001-2017:
        - 14.2.6
        iso27001-2022:
        - 8.31
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
    Defined build process:
      uuid: f6f7737f-25a9-4317-8de2-09bf59f29b5b
      risk: Performing builds without a defined process is error prone; for example,
        as a result of incorrect security related configuration.
      measure: A well defined build process lowers the possibility of errors during
        the build process.
      description: |
        Sample evidence as an attribute in the yaml: The build process is defined in [REPLACE-ME Pipeline](https://replace-me/jenkins/job)
        in the folder _vars_. Projects are using a _Jenkinsfile_ to use the
        defined process.
      difficultyOfImplementation:
        knowledge: 2
        time: 3
        resources: 2
      usefulness: 4
      level: 1
      assessment: |
        - Show your build pipeline and an exemplary job (build + test).
        - Show that every team member has access.
        - Show that failed jobs are fixed.

        Credits: AppSecure-nrw [Security Belts](https://github.com/AppSecure-nrw/security-belts/)
      implementation:
      - uuid: b4bfead3-5fb6-4dd0-ba44-5da713bd22e4
        name: CI/CD tools
        tags:
        - ci-cd
        url: https://martinfowler.com/articles/continuousIntegration.html
        description: CI/CD tools such as jenkins, gitlab-ci or github-actions
      - uuid: ed6b6340-6c7f-4e13-8937-f560d3f5db11
        name: Container technologies and orchestration like Docker, Kubernetes
        tags: []
        url: https://d3fend.mitre.org/dao/artifact/d3f:ContainerOrchestrationSoftware/
      references:
        iso27001-2017:
        - 12.1.1
        iso27001-2022:
        - 5.37
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
"""
