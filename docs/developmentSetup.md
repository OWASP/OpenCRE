# Setup for development

This guide aims to help first time contributors to setup and contribute to opencre.org.
It assumes little/no prior development knowledge and an environment without any tools.


#### Table Of Contents

* [Prerequisites](#prerequisites)
    * [Linux](#linux)
    * [MacOS](#macos)
    * [Language Setup](#language-setup)
* [Development Environment Setup](#development-environment-setup)
  
* [Project Setup](#project-setup)
* [Testing That Everything Works](#testing-that-everything-works)
* [Import The Database](#import-the-database)
* [Running Locally](#running-locally)


## Prerequisites

opencre.org is a [Python](https://www.w3schools.com/python/) backend supported by a [React](https://www.w3schools.com/REACT/DEFAULT.ASP) frontend written using [Typescript](https://www.w3schools.com/typescript/) (or typed Javascript).
In order to contribute code to opencre you need a system that is setup for python and Javascript development.

### Linux

Assuming a Debian based system (e.g. ubuntu) you can install supporting tools with the following:
```bash
sudo apt update && sudo apt install -y curl git python3  build-essential curl libpq-devel python3-dev sqlite3
```

### MacOS

Assuming the [Homebrew](https://brew.sh/) package manager is installed, you can run the following.

```zsh
brew install git python curl sqlite3 libpq make
```

The above will install 
* [git](https://www.w3schools.com/git/) , used for source control
* python3 , used for backend development
* build-essential , a package of useful development tools
* [curl](https://curl.se/) , a utility that allows users to make network connections to remote servers, used for testing
* [sqlite3](https://www.sqlite.org/index.html), a file based database used for development
* [make](https://makefiletutorial.com/) a build and execution automation tool

### Language setup
### Linux
We install python's utilities with
* `python3 -m pip install --upgrade pip` [pip](https://pypi.org/project/pip/) is python's package manager
* `python3 -m pip install --upgrade virtualenv`  [python virtual environment](https://docs.python.org/3/tutorial/venv.html), used for python development
* `python3 -m pip install --upgrade setuptools` python's [setuptools](https://pypi.org/project/setuptools/) is the package containing tooling for installing further python tools

### MacOS
We install python's utilities with
* `brew install python3`
* `brew install virtualenv`

Then [nodejs](https://nodejs.org/en/), used for Javascript development can be installed using the [Node Version Manager](https://github.com/nvm-sh/nvm) as such: 
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash && nvm install --lts
```

Then we use `npm` nodejs, package manager to install yarn , a lightweight Javascript build tool.
```
npm install --global yarn
```

## Development environment setup

OpenCRE uses [git](https://docs.github.com/en/get-started/using-git/about-git) and follows the [GitHub](https://docs.github.com/en/get-started/quickstart/github-flow) flow.
To edit files it is suggested that a code editor such as Visual Studio Code is used. Visual Studio Code can be installed on [Linux](https://code.visualstudio.com/docs/setup/linux) and [MacOS](https://formulae.brew.sh/cask/visual-studio-code).

## Project Setup

* Generate an SSH key pair and add it's public component to your Github account as described [here](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account).
* Create a fork of the project following Github's instructions above.
* Open a terminal
* Clone your fork locally with ` git clone <the url of your fork starting with git@github.com>`
* Change into the working directory `cd common-requirement-enumeration`

OpenCRE depends on Makefiles to automate the setup and execution of several aspects.
You can install the project by running `make install`.

### Testing that everything works
If the tests pass, the project should be operational. You can run tests with 
`make test` and `make e2e` which runs both [unit tests](https://en.wikipedia.org/wiki/Unit_testing) and [end to end tests](https://www.browserstack.com/guide/end-to-end-testing).

### Import the database

You can run `cp cres/db.sqlite standards_cache.sqlite`

## Running locally

You can run the backend with `make dev-run`. At the time of writing the backend URL is `http://localhost:5000` by default.

You can run the frontend with `yarn start`. This should open a browser tab at the application's front page and also automatically reload the page whenever changes are detected. At the time of writing the frontend URL is `http://localhost:9001` by default.


This is it, please follow the [CONTRIBUTING](../CONTRIBUTING.md) guidlines while contributing and thank you for your interest in OpenCRE.
