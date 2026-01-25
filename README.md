# OpenCRE

Go to [https://www.opencre.org](https://www.opencre.org) to see OpenCRE working and more explanation.
OpenCRE stands for Open Common Requirement enumeration. It is an interactive content linking platform for uniting security standards and guidelines. It offers easy and robust access to relevant information when designing, developing, testing and procuring secure software.

OpenCRE consists of:

* The application: a python web and cli application to access the data, running publicly at opencre.org
* The catalog data: a catalog of Common Requirements (CREs)
* The mapping data: links from each CRE to relevant sections in a range of standards
* Tools and guidelines to contribute to the data and to run the application locally

# Contribute code or mappings

To see how you can contribute to the application or to the data (catalog or standard mappings), see [Contributing](docs/CONTRIBUTING.md).
We really welcome you!

# Roadmap

For a roadmap please see the [issues](https://github.com/OWASP/OpenCRE/issues).

# Running your own OpenCRE

You are free to use the public opencre application at opencre.org. Apart from that, you can run your own if you want to include your own security standards and guidelines for example. We call that myOpenCRE.

## Locally

### Docker

The easiest way to run OpenCRE locally is by running the published docker container.
You can do so by running:

```bash
docker run -p 5000:5000 ghcr.io/owasp/opencre/opencre:latest
```

After the container has finished downloading the remote information you can access it in [http://127.0.0.1:5000](http://127.0.0.1:5000).

If you want to develop on OpenCRE or docker is not available in your environment, you can alternatively run it via CLI.

### Command Line

To run outside of Docker you need to install OpenCRE.
To install this application you need python3, yarn and virtualenv.

Clone the repository:

```bash
git clone https://github.com/OWASP/OpenCRE.git
```

(Recommended) Create and activate a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
make install
```

Download the latest CRE graph from upstream by running:

```bash
make upstream-sync
```

Keep in mind that until [Issue #534](https://github.com/OWASP/OpenCRE/issues/534) is fixed you won't have access to gap analysis results locally.

To run CRE locally then you can do:

```bash
make dev-flask
```

To run the CLI application, you can run:

```bash
python cre.py --help
```

To download a remote CRE spreadsheet locally you can run:

```bash
python cre.py --review --from_spreadsheet <google sheets url>
```

To add a remote spreadsheet to your local database you can run:

```bash
python cre.py --add --from_spreadsheet <google sheets url>
```

To run the web application for development you can run:

```bash
make start-containers
make start-worker

# in a separate shell
make dev-flask
```

Alternatively, you can use the dockerfile with:

```bash
make docker && make docker-run
```

Some features like Gap Analysis require a neo4j DB running, you can start this with:

```bash
make docker-neo4j
```

Environment variables for app to connect to neo4jDB (default):

* `NEO4J_URL` (neo4j//neo4j:password@localhost:7687)

To run the web application for production you need gunicorn and you can run from within the cre_sync dir:

```bash
make prod-run
```

---

### macOS Notes (Apple Silicon & Intel)

OpenCRE is fully supported on macOS. The following notes are optional and intended to help contributors running OpenCRE locally on macOS systems.

#### Prerequisites

Install required tools using Homebrew:

```bash
brew install python@3.11 yarn make
```

> Note: Python 3.11 is recommended. Newer Python versions may cause dependency incompatibilities.

Verify Python version:

```bash
python3 --version
```

#### Virtual Environment Setup

Create and activate a virtual environment explicitly using Python 3:

```bash
python3 -m venv venv
source venv/bin/activate
```

Upgrade pip:

```bash
pip install --upgrade pip
```

#### Dependency Installation

Install dependencies using the standard workflow:

```bash
make install
```

If you encounter build issues, ensure Xcode Command Line Tools are installed:

```bash
xcode-select --install
```

#### Running Locally

Sync upstream CRE data (requires internet access):

```bash
make upstream-sync
```

Then start the local server:

```bash
make dev-flask
```

The application will be available at:

```
http://127.0.0.1:5000
```

> Tip: For most macOS users, running via Docker is the simplest and most reliable approach.

---

## Using the OpenCRE API

See [the myOpenCRE user guide](docs/my-opencre-user-guide.md) on using the OpenCRE API to, for example, add your own security guidelines and standards.

## Docker building and running

You can build the production or the development docker images with:

```bash
make docker-prod
make docker-dev
```

The environment variables used by OpenCRE are:

```
- NEO4J_URL
- NO_GEN_EMBEDDINGS
- FLASK_CONFIG
- DEV_DATABASE_URL
- INSECURE_REQUESTS
- REDIS_HOST
- REDIS_PORT
- REDIS_NO_SSL
- REDIS_URL
- GCP_NATIVE
- GOOGLE_SECRET_JSON
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- LOGIN_ALLOWED_DOMAINS
- OpenCRE_gspread_Auth
```

You can run the containers with:

```bash
make docker-prod-run
make docker-dev-run
```

## Developing

You can run backend tests with:

```bash
make test
```

You can get a coverage report with:

```bash
make cover
```

Try to keep the coverage above 70%.

---

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![GitHub Super-Linter](https://github.com/OWASP/common-requirement-enumeration/workflows/Lint%20Code%20Base/badge.svg)](https://github.com/marketplace/actions/super-linter)
[![Main Branch Build](https://github.com/OWASP/common-requirement-enumeration/workflows/Test/badge.svg?branch=main)](https://github.com/OWASP/common-requirement-enumeration/workflows/Test)

[![Issues](https://img.shields.io/github/issues/owasp/common-requirement-enumeration)](https://github.com/OWASP/common-requirement-enumeration/issues)
[![PR's Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)](http://makeapullrequest.com)
![GitHub contributors](https://img.shields.io/github/contributors/owasp/common-requirement-enumeration)
![GitHub last commit](https://img.shields.io/github/last-commit/owasp/common-requirement-enumeration)
![GitHub commit activity](https://img.shields.io/github/commit-activity/y/owasp/common-requirement-enumeration)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=400297709&machine=standardLinux32gb&devcontainer_path=.devcontainer%2Fdevcontainer.json&location=WestEurope)
