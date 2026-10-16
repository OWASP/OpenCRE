#!/usr/bin/env bash
# Idempotent OpenCRE dependency install for Cloud Agent builds.
# Runs from the repository root. Must exit. Does not start databases or Flask.
set -euo pipefail

cd "$(dirname "$0")/.."
export DEBIAN_FRONTEND=noninteractive
export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  -o Dpkg::Options::="--force-confdef" \
  -o Dpkg::Options::="--force-confold" \
  --no-install-recommends \
  build-essential \
  ca-certificates \
  curl \
  gnupg \
  git \
  make \
  pkg-config \
  sqlite3 \
  libpq-dev \
  libxml2-dev \
  libxslt-dev \
  libffi-dev \
  fuse-overlayfs \
  iptables

# Python 3.11.9 is pinned in .python-version. The base image ships 3.12.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
sudo ln -sfn "${HOME}/.local/bin/uv" /usr/local/bin/uv

if ! /usr/local/bin/python3.11 -c 'import sys; raise SystemExit(0 if sys.version.startswith("3.11.9") else 1)' 2>/dev/null; then
  uv python install 3.11.9
fi
PY311="$(uv python find 3.11.9)"
sudo ln -sfn "${PY311}" /usr/local/bin/python3.11
sudo ln -sfn "${PY311}" /usr/local/bin/python3
sudo ln -sfn "${PY311}" /usr/local/bin/python

# uv CPython builds are externally managed (PEP 668). Install the virtualenv
# CLI into uv's tool environment so `make install` can call `virtualenv -p python3`.
uv tool install virtualenv
sudo ln -sfn "${HOME}/.local/bin/virtualenv" /usr/local/bin/virtualenv

# Docker-in-Docker: fuse-overlayfs + legacy iptables (Cloud Agent nested containers).
if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl --retry 3 --retry-delay 5 -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  PIN="5:28.5.2-1~ubuntu.24.04~noble"
  if apt-cache show "docker-ce=${PIN}" >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
      -o Dpkg::Options::="--force-confdef" \
      -o Dpkg::Options::="--force-confold" \
      "docker-ce=${PIN}" \
      "docker-ce-cli=${PIN}" \
      containerd.io \
      docker-buildx-plugin \
      docker-compose-plugin
  else
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
      -o Dpkg::Options::="--force-confdef" \
      -o Dpkg::Options::="--force-confold" \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
fi

sudo mkdir -p /etc/docker
printf '%s\n' '{' '  "storage-driver": "fuse-overlayfs"' '}' | sudo tee /etc/docker/daemon.json >/dev/null
if [[ -x /usr/sbin/iptables-legacy ]]; then
  sudo update-alternatives --set iptables /usr/sbin/iptables-legacy
  sudo update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
fi
sudo groupadd -f docker
sudo usermod -aG docker ubuntu

# Yarn Classic is already on the default image via nvm. Fall back to a /usr/local/bin link.
if ! command -v yarn >/dev/null 2>&1; then
  NODE_BIN="$(find "${HOME}/.nvm/versions/node" -maxdepth 2 -type d -name bin | sort | tail -1)"
  sudo ln -sfn "${NODE_BIN}/node" /usr/local/bin/node
  sudo ln -sfn "${NODE_BIN}/npm" /usr/local/bin/npm
  sudo ln -sfn "${NODE_BIN}/yarn" /usr/local/bin/yarn
fi

yarn install --frozen-lockfile
yarn build

if [[ ! -x venv/bin/python ]] || ! venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version.startswith("3.11.9") else 1)'; then
  rm -rf venv
  virtualenv -p /usr/local/bin/python3.11 venv
fi
./venv/bin/pip install --upgrade pip setuptools
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/playwright install chromium
sudo ./venv/bin/playwright install-deps chromium

export FLASK_APP="${PWD}/cre.py"
export FLASK_CONFIG=development
export NO_LOAD_GRAPH_DB=1
./venv/bin/flask db upgrade
