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
git clone https://github.com/OWASP/OpenCRE
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

You can precompute local gap-analysis cache after imports with:

```bash
make backfill-gap-analysis
```

To run CRE locally then you can do:

```bash
make dev-flask
```

To run the CLI application, you can run:

```bash
python cre.py --help
```

To export the CRE + standards taxonomy to CSV (CI-friendly), run:

```bash
python cre.py --export --csv <path/to/output.csv>
```

Example:

```bash
python cre.py --export --csv artifacts/cres_and_standards.csv
```

Notes:
- `--export` is a dedicated export mode and exits after writing the CSV.
- `--csv` is required when using `--export`.
- This mode exports report data from the OpenCRE API and does not mutate the local DB.

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

To run only missing gap-analysis pair backfill (without starting Flask), use:

```bash
RUN_COUNT=8 bash scripts/backfill_gap_analysis.sh
```

### Production DB Operations (opencreorg)

Prefer the dedicated scripts in `scripts/db/` for production operations. These scripts enforce safety guards and always capture a fresh backup before DB changes.

- Backup only:
  - `APP_NAME=opencreorg scripts/db/backup-opencreorg.sh`
- Sync local Postgres to Heroku:
  - `APP_NAME=opencreorg SOURCE_DB_URL="postgresql://cre:password@127.0.0.1:5432/cre" scripts/db/sync-local-to-opencreorg.sh`
- Targeted SQL surgery:
  - `APP_NAME=opencreorg scripts/db/surgery-opencreorg.sh --sql-file ./tmp/change.sql`

For destructive surgery (`DELETE`, `DROP`, `TRUNCATE`, irreversible `ALTER`), use:

```bash
APP_NAME=opencreorg \
CONFIRM_DESTRUCTIVE=I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION \
scripts/db/surgery-opencreorg.sh --sql-file ./tmp/destructive-change.sql --destructive
```

Runbooks:

- `docs/runbooks/opencreorg-db-sync-and-surgery.md`
- `docs/runbooks/opencreorg-db-destructive-ops-checklist.md`

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

## Environment Configuration

Copy the example configuration file:

```bash
cp .env.example .env
```

Then edit `.env` and provide values appropriate for your environment.

### Variables

* Database: `DEV_DATABASE_URL`
* Neo4j: `NEO4J_URL`
* Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_URL`, `REDIS_NO_SSL`
* Flask: `FLASK_CONFIG`, `INSECURE_REQUESTS`
* Embeddings: `NO_GEN_EMBEDDINGS`, `CRE_EMBED_MODEL`, `CRE_EMBED_EXPECTED_DIM`, `CRE_VALIDATE_EMBED_DIM_ON_INIT`
* LLM models/retries: `CRE_LLM_CHAT_MODEL`, `CRE_EMBED_ALIGN_MODEL`, `CRE_LLM_MAX_RETRIES`, `CRE_LLM_RETRY_SLEEP_SECONDS`
* Provider credentials: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GCP_NATIVE`
* Google Auth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_SECRET_JSON`, `LOGIN_ALLOWED_DOMAINS`
* GCP: `GCP_NATIVE`
* Spreadsheet Auth: `OpenCRE_gspread_Auth`

See `.env.example` for full list and defaults.

### LiteLLM backend (optional)

OpenCRE uses LiteLLM for LLM calls. Configure models and provider credentials via environment variables.

Recommended minimal example:

```bash
# Chat / completion models (LiteLLM model strings)
CRE_LLM_CHAT_MODEL=gemini/gemini-2.5-flash
CRE_EMBED_ALIGN_MODEL=gemini/gemini-2.5-flash

# Embedding model used for persisted vectors
CRE_EMBED_MODEL=gemini/gemini-embedding-001
CRE_EMBED_EXPECTED_DIM=3072
CRE_VALIDATE_EMBED_DIM_ON_INIT=1

# Retry policy
CRE_LLM_MAX_RETRIES=2
CRE_LLM_RETRY_SLEEP_SECONDS=15

# Provider credential (example for Gemini)
GEMINI_API_KEY=your-key
```

Notes:

* Treat changes to `CRE_EMBED_MODEL` or `CRE_EMBED_EXPECTED_DIM` as a data migration event (usually requires re-embedding).
* `CRE_EMBED_EXPECTED_DIM` is a safety guard: writes fail fast on dimension mismatch.
* Keep chat/alignment models and embedding model independently configurable; only embeddings must remain dimension-compatible with stored vectors.

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
