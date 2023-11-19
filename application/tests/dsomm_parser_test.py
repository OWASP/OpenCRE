from cmath import exp
from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
import tempfile
import os

from application.utils.external_project_parsers import zap_alerts_parser


class TestZAPAlertsParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

        self.collection = db.Node_collection()

    def test_parse(self) -> None:
        # mock prompt client to return static embeddings, ensure things are in tables as expected
        pass


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
      - uuid: ed6b6340-6c7f-4e13-8937-f560d3f5db11
        name: Container technologies and orchestration like Docker, Kubernetes
        tags: []
        url: https://d3fend.mitre.org/dao/artifact/d3f:ContainerOrchestrationSoftware/
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
        samm2:
        - I-SB-1-A
        iso27001-2017:
        - 12.1.1
        - 14.2.2
        iso27001-2022:
        - 5.37
        - 8.32
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
  Deployment:
    Blue/Green Deployment:
      uuid: 0cb2626b-fb0d-4a0f-9688-57f787310d97
      risk: A new artifact's version can have unknown defects.
      measure: |-
        Using a blue/green deployment strategy increases application availability
        and reduces deployment risk by simplifying the rollback process if a deployment fails.
      difficultyOfImplementation:
        knowledge: 1
        time: 2
        resources: 1
      usefulness: 2
      level: 5
      implementation:
      - uuid: 4fb3d95c-07c0-4cbb-b396-5054aba751c2
        name: Blue/Green Deployments
        tags: []
        url: https://martinfowler.com/bliki/BlueGreenDeployment.html
      dependsOn:
      - Smoke Test
      references:
        samm2:
        - TODO
        iso27001-2017:
        - 17.2.1
        - 12.1.1
        - 12.1.2
        - 12.1.4
        - 12.5.1
        - 14.2.9
        iso27001-2022:
        - 8.14
        - 5.37
        - 8.31
        - 8.32
        - 8.19
        - 8.29
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
    Defined decommissioning process:
      uuid: da4ff665-dcb9-4e93-9d20-48cdedc50fc2
      description: |-
        The decommissioning process in the context of Docker and Kubernetes involves
        retiring Docker containers, images, and Kubernetes resources that are no longer
        needed or have been replaced. This process must be carefully executed to avoid
        impacting other services and applications.
      risk: Unused applications are not maintained and may contain vulnerabilities.
        Once exploited they can be used to attack other applications or to perform
        lateral movements within the organization.
      measure: A clear decommissioning process ensures the removal of unused applications.
      difficultyOfImplementation:
        knowledge: 1
        time: 2
        resources: 1
      usefulness: 2
      level: 2
      references:
        samm2:
        - O-OM-2-B
        iso27001-2017:
        - 11.2.7
        iso27001-2022:
        - 7.14
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
Culture and Organization:
  Design:
    Conduction of advanced threat modeling:
      uuid: ae22dafd-bcd6-41ee-ba01-8b7fe6fc1ad9
      risk: Inadequate identification of business and technical risks.
      measure: Threat modeling is performed by using reviewing user stories and producing
        security driven data flow diagrams.
      difficultyOfImplementation:
        knowledge: 4
        time: 3
        resources: 2
      usefulness: 3
      level: 4
      dependsOn:
      - Conduction of simple threat modeling on technical level
      - Creation of threat modeling processes and standards
      description: |
        **Example High Maturity Scenario:**

        Based on a detailed threat model defined and updated through code, the team decides the following:

        * Local encrypted caches need to expire and auto-purged.
        * Communication channels encrypted and authenticated.
        * All secrets persisted in shared secrets store.
        * Frontend designed with permissions model integration.
        * Permissions matrix defined.
        * Input is escaped output is encoded appropriately using well established libraries.

        Source: OWASP Project Integration Project
      implementation:
      - uuid: c0533602-11b7-4838-93cc-a40556398163
        name: Whiteboard
        tags:
        - defender
        - threat-modeling
        - collaboration
        - whiteboard
        url: https://en.wikipedia.org/wiki/Whiteboard
      - uuid: 965c3814-b6df-4ead-a096-1ed78ce1c7c1
        name: Miro (or any other collaborative board)
        tags:
        - defender
        - threat-modeling
        - collaboration
        - whiteboard
        url: https://miro.com/
      - uuid: 088794c4-3424-40d4-9084-4151587fc84d
        name: Draw.io
        tags:
        - defender
        - threat-modeling
        - whiteboard
        url: https://github.com/jgraph/drawio-desktop
      - uuid: fd0f282b-a065-4464-beed-770c604a5f52
        name: Threat Modeling Playbook
        tags:
        - owasp
        - defender
        - threat-modeling
        - whiteboard
        url: https://github.com/Toreon/threat-model-playbook
      - uuid: b5eaf710-e05f-49e5-a649-13afde9aeb52
        name: OWASP SAMM
        tags:
        - threat-modeling
        - owasp
        - defender
        url: https://owaspsamm.org/model/design/threat-assessment/stream-b/
      - uuid: e8332407-5149-459e-a2fe-c5c78c7ec55c
        name: Threagile
        tags:
        - threat-modeling
        url: https://github.com/Threagile/threagile
      - uuid: 1c56dbea-e067-44e2-8d3b-0a1205a70617
        name: Threat Matrix for Storage
        url: https://www.microsoft.com/security/blog/2021/04/08/threat-matrix-for-storage/
        tags:
        - documentation
        - storage
        - cluster
        - kubernetes
      references:
        samm2:
        - D-TA-2-B
        iso27001-2017:
        - Not explicitly covered by ISO 27001
        - May be part of risk assessment
        - 8.2.1
        - 14.2.1
        iso27001-2022:
        - Not explicitly covered by ISO 27001
        - May be part of risk assessment
        - 5.12
        - 8.25
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
    Conduction of simple threat modeling on business level:
      uuid: 48f97f31-931c-46eb-9b3e-e2fec0cd0426
      risk: Business related threats are discovered too late in the development and
        deployment process.
      measure: Threat modeling of business functionality is performed during the product
        backlog creation to facilitate early detection of security defects.
      difficultyOfImplementation:
        knowledge: 2
        time: 3
        resources: 1
      usefulness: 3
      level: 3
      implementation: []
      references:
        samm2:
        - D-TA-2-B
        iso27001-2017:
        - Not explicitly covered by ISO 27001
        - May be part of risk assessment
        - 8.2.1
        - 14.2.1
        iso27001-2022:
        - Not explicitly covered by ISO 27001
        - May be part of risk assessment
        - 5.12
        - 8.25
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
  Education and Guidance:
    Ad-Hoc Security trainings for software developers:
      uuid: 12c90cc6-3d58-4d9b-82ff-d469d2a0c298
      risk: Understanding security is hard and personnel needs to be trained on it.
        Otherwise, flaws like an SQL Injection might be introduced into the software
        which might get exploited.
      measure: Provide security awareness training for all personnel involved in software
        development Ad-Hoc.
      difficultyOfImplementation:
        knowledge: 2
        time: 1
        resources: 1
      usefulness: 3
      level: 1
      implementation:
      - uuid: 1fff917f-205e-4eab-ae0e-1fab8c04bf3a
        name: OWASP Juice Shop
        tags:
        - training
        url: https://github.com/bkimminich/juice-shop
        description: In case you do not have the budget to hire an external security
          expert, an option is to use the OWASP JuiceShop on a "hacking Friday"
      - uuid: 1c3f2f7a-5031-4687-9d69-76c5178c74e1
        name: OWASP Cheatsheet Series
        tags:
        - secure coding
        url: https://cheatsheetseries.owasp.org/
      references:
        samm2:
        - G-EG-1-A
        iso27001-2017:
        - 7.2.2
        iso27001-2022:
        - 6.3
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
    Simple mob hacking:
      uuid: 535f301a-e8e8-4eda-ad77-a08b035c92de
      risk: Understanding security is hard.
      measure: |
        Participate with your whole team in a simple mob hacking session organized by the Security Champion Guild.
        In the session the guild presents a vulnerable application and together you look at possible exploits.
        Just like in mob programming there is one driver and several navigators.
      description: |
        ### Guidelines for your simple mob hacking session
        - All exploits happen via the user interface.
        - No need for security/hacking tools.
        - No need for deep technical or security knowledge.
        - Use an insecure training app, e.g., [DVWA](https://dvwa.co.uk/) or [OWASP Juice Shop](https://owasp.org/www-project-juice-shop/).
        - Encourage active participation, e.g., use small groups.
        - Allow enough time for everyone to run at least one exploit.

        ### Benefits
        - The team gets an idea of how exploits can look like and how easy applications can be attacked.
        - The team understands functional correct working software can be highly insecure and easy to exploit.
      difficultyOfImplementation:
        knowledge: 5
        time: 3
        resources: 1
      usefulness: 3
      level: 3
      credits: |
        AppSecure-nrw [Security Belts](https://github.com/AppSecure-nrw/security-belts/)
      implementation:
      - uuid: 1fff917f-205e-4eab-ae0e-1fab8c04bf3a
        name: OWASP Juice Shop
        tags:
        - training
        url: https://github.com/bkimminich/juice-shop
        description: In case you do not have the budget to hire an external security
          expert, an option is to use the OWASP JuiceShop on a "hacking Friday"
      - uuid: a8cd9acb-ad22-44d6-b177-1154c65a8529
        name: Damn Vulnerable Web Application
        tags:
        - training
        description: Simple Application with intended vulnerabilities. HTML based.
      references:
        samm2:
        - G-EG-1-A
        iso27001-2017:
        - 7.2.2
        iso27001-2022:
        - 6.3
      isImplemented: false
      comments: ""
      tags:
      - none
      teamsImplemented:
        Default: false
        B: false
        C: false
"""
