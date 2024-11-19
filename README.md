# OpenCRE readme

Go to https://www.opencre.org to see OpenCRE working and more explanation.  
OpenCRE stands for Open Common Requirement enumeration. It is an interactive content linking platform for uniting security standards and guidelines. It offers easy and robust access to relevant information when designing, developing, testing and procuring secure software.  

OpenCRE consists of:
- The application: a python web and cli application to access the data, running publicly at opencre.org
- The catalog data: a catalog of Common Requirements (CREs)
- The mapping data: links from each CRE to relevant sections in a range of standards
- Tools and guidelines to contribute to the data and to run the application locally

# Contribute code or mappings
To see how you can contribute to the application or to the data (catalog or standard mappings), see [Contributing](docs/CONTRIBUTING.md).  
We really welcome you!

# Roadmap
For a roadmap please see the [issues](https://github.com/OWASP/common-requirement-enumeration/issues).

# Running your own OpenCRE

You are free to use the public opencre application at opencre.org. Apart from that, you can run your own if you want to include your own security standards and guidelines for example. We call that myOpenCRE.

### Locally

#### Docker
The easiest way to run OpenCRE locally is by running the published docker container.
You can do so by running:
`docker run -p 5000:5000  ghcr.io/owasp/opencre/opencre:latest`
After the container has finished downloading the remote information you can access it in [localhost](http://127.0.0.1:5000)

#### Command Line

To run outside of Docker you need to install OpenCRE.
To install this application you need python3, yarn and virtualenv.
* Clone the repository:
<pre>git clone https://github.com/OWASP/common-requirement-enumeration </pre>

* Install dependencies
<pre> make install </pre>

* Download the latest CRE graph from upstream by running
<pre>python cre.py --upstream_sync</pre>
Keep in mind that until [Issue #534](https://github.com/OWASP/OpenCRE/issues/534) is fixed you won't have access to gap analysis results locally

To run the CLI application, you can run
<pre>python cre.py --help</pre>

To download a remote cre spreadsheet locally you can run
<pre>python cre.py --review --from_spreadsheet < google sheets url></pre>

To add a remote spreadsheet to your local database you can run
<pre>python cre.py --add --from_spreadsheet < google sheets url></pre>

To run the web application for development you can run
<pre>
$ make start-containers
$ make start-worker 

# in a seperate shell
$ make dev-flask
</pre>

Alternatively, you can use the dockerfile with
<pre>make docker && make docker-run</pre>

Some features like Gap Analysis require a neo4j DB running, you can start this with
<pre>make docker-neo4j</pre>
enviroment varaibles for app to connect to neo4jDB (default):
- NEO4J_URL (neo4j//neo4j:password@localhost:7687)

To run the web application for production you need gunicorn and you can run from within the cre_sync dir
<pre>make prod-run</pre>


### Using the OpenCRE API
See [the myOpenCRE user guide](docs/my-opencre-user-guide.md) on using the OpenCRE API to for example add your own security guidelines and standards.


### Docker building and running
You can build the production or the development docker images with 
`make docker-prod` and `make docker-dev` respectively
The environment variables used by OpenCRE are:
```
        - name: NEO4J_URL
        - name: NO_GEN_EMBEDDINGS
        - name: FLASK_CONFIG
        - name: DEV_DATABASE_URL
        - name: INSECURE_REQUESTS # development or TLS terminated environments only
        - name: REDIS_HOST
        - name: REDIS_PORT
        - name: REDIS_NO_SSL
        - name: REDIS_URL # in case REDIS_HOST and REDIS_PORT are unavailable
        - name: GCP_NATIVE # if there are ambient GCP credentials, only useful for VERTEX chatbot
        - name: GOOGLE_SECRET_JSON # if not running on GCP
        - name: GOOGLE_CLIENT_ID # useful for login only
        - name: GOOGLE_CLIENT_SECRET # useful for login only
        - name: LOGIN_ALLOWED_DOMAINS # useful for login only
        - name: OpenCRE_gspread_Auth # useful only when importing data, possible values 'oauth' or 'service_account'
```
You can run the containers with `make docker-prod-run` and `make-docker-dev-run`

### Developing

You can run backend tests with
<pre>make test</pre>
You can run get a coverage report with 
<pre>make cover</pre>
Try to keep the coverage above 70%


[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![GitHub Super-Linter](https://github.com/OWASP/common-requirement-enumeration/workflows/Lint%20Code%20Base/badge.svg)](https://github.com/marketplace/actions/super-linter)
[![Main Branch Build](https://github.com/OWASP/common-requirement-enumeration/workflows/Test/badge.svg?branch=main)](https://github.com/OWASP/OWASP/common-requirement-enumeration/workflows/Test)

[![Issues](https://img.shields.io/github/issues/owasp/common-requirement-enumeration)](https://github.com/OWASP/common-requirement-enumeration/issues)  
[![PR's Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)](http://makeapullrequest.com)
![GitHub contributors](https://img.shields.io/github/contributors/owasp/common-requirement-enumeration)
![GitHub last commit](https://img.shields.io/github/last-commit/owasp/common-requirement-enumeration)
![GitHub commit activity](https://img.shields.io/github/commit-activity/y/owasp/common-requirement-enumeration)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=400297709&machine=standardLinux32gb&devcontainer_path=.devcontainer%2Fdevcontainer.json&location=WestEurope)
