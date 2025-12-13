# OpenCRE

Go to [https://www.opencre.org](https://www.opencre.org) to see OpenCRE working and more explanation.

OpenCRE stands for **Open Common Requirement Enumeration**. It is an interactive content linking platform for uniting security standards and guidelines. It offers easy and robust access to relevant information when designing, developing, testing and procuring secure software.

---

## What is OpenCRE?

OpenCRE consists of:

* **The application**: a Python web and CLI application to access the data, running publicly at opencre.org
* **The catalog data**: a catalog of Common Requirements (CREs)
* **The mapping data**: links from each CRE to relevant sections in a range of standards
* **Tools and guidelines** to contribute to the data and to run the application locally

---

## Contribute Code or Mappings

To see how you can contribute to the application or to the data (catalog or standard mappings), see **Contributing**.

We really welcome you!

---

## Roadmap

For a roadmap please see the **Issues**.

---

## Running Your Own OpenCRE

You are free to use the public OpenCRE application at [https://www.opencre.org](https://www.opencre.org).
You can also run your own instance if you want to include your own security standards and guidelines. We call that **myOpenCRE**.

---

## Running OpenCRE Locally

### Docker (Recommended)

The easiest way to run OpenCRE locally is by using Docker:

```bash
docker run -p 5000:5000 ghcr.io/owasp/opencre/opencre:latest
```

After the container has finished downloading the remote information, you can access the application at:

```
http://localhost:5000
```

If you want to develop OpenCRE or Docker is not available in your environment, you can run it via the command line.

---

## Command Line Setup

To run OpenCRE outside Docker you need:

* Python 3
* Yarn
* virtualenv

Clone the repository:

```bash
git clone https://github.com/OWASP/OpenCRE.git
cd OpenCRE
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

Download the latest CRE graph from upstream:

```bash
make upstream-sync
```

> ⚠️ Until Issue #534 is fixed, Gap Analysis results may not be available locally.

Run OpenCRE locally:

```bash
make dev-flask
```

---

## macOS Local Development Setup

This section documents common issues and solutions when setting up OpenCRE locally on **macOS**, based on contributor experience.

### Tested Environment

* macOS (Intel & Apple Silicon)
* Python 3.10 – 3.13
* Node.js 18+
* Yarn 1.x

---

### 1. Virtual Environment Setup

We recommend using Python’s built-in `venv`:

```bash
python3 -m venv venv
source venv/bin/activate
```

> **Important Note**
> The Makefile currently invokes `virtualenv` internally.
> On macOS, this can cause setup failures even when `venv` is used.
>
> To avoid this, install `virtualenv` inside the active virtual environment:

```bash
pip install virtualenv
```

---

### 2. Installing Dependencies

```bash
make install
```

If you encounter the error:

```text
make: virtualenv: No such file or directory
```

Ensure that:

* the virtual environment is activated
* `virtualenv` is installed inside the environment

---

### 3. Syncing Upstream Data (Known Limitation)

```bash
make upstream-sync
```

> **Known Issue**
> On macOS, this command may fail with:
>
> ```text
> sqlite3.OperationalError: no such table: cre
> ```
>
> This is a known upstream limitation (see Issue #534).
> The application can still be run locally for development even if this step fails.

---

### 4. Running the Development Server

```bash
make dev-flask
```

Then open:

```
http://127.0.0.1:5000
```

---

### Notes

* Webpack and Yarn peer-dependency warnings during installation are expected and can be safely ignored.
* Some features (such as Gap Analysis) require Neo4j and may not function fully in local development environments.

---

## CLI Usage

```bash
python cre.py --help
```

```bash
python cre.py --review --from_spreadsheet <google_sheets_url>
```

```bash
python cre.py --add --from_spreadsheet <google_sheets_url>
```

---

## Running the Web Application for Development

```bash
make start-containers
make start-worker

# in a separate shell
make dev-flask
```

Alternatively:

```bash
make docker
make docker-run
```

---

## Neo4j (Optional)

```bash
make docker-neo4j
```

```
NEO4J_URL=neo4j://neo4j:password@localhost:7687
```

---

## Developing

```bash
make test
```

```bash
make cover
```

Try to keep coverage above **70%**.

Code style is enforced using **Black** and **GitHub Super-Linter**.

---

## License

This project is licensed under **CC0-1.0**.

PRs welcome ❤️
