#!/usr/bin/env bash
# Per-boot services. Safe to rerun. Does not install packages.
set -euo pipefail

cd "$(dirname "$0")/.."

start_dockerd() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  sudo rm -f /var/run/docker.pid
  # Cloud Agent VMs use tini as PID 1. `service docker start` is attempted
  # first; if it does not bring the daemon up, launch dockerd directly.
  timeout 20 sudo service docker start >/tmp/docker-service.log 2>&1 || true
  if ! docker info >/dev/null 2>&1; then
    echo "service docker start did not bring the daemon up; launching dockerd" >&2
    sudo nohup dockerd >/tmp/dockerd.log 2>&1 &
  fi
  for _ in $(seq 1 30); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Docker daemon did not become ready" >&2
  sudo tail -n 80 /tmp/dockerd.log /tmp/docker-service.log 2>/dev/null || true
  return 1
}

wait_http() {
  local url="$1"
  local i
  for i in $(seq 1 60); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for ${url}" >&2
  return 1
}

start_dockerd

make docker-postgres
make docker-redis
make docker-neo4j

for _ in $(seq 1 30); do
  if docker exec cre-redis-stack redis-cli ping 2>/dev/null | grep -q PONG; then
    break
  fi
  sleep 2
done
docker exec cre-redis-stack redis-cli ping | grep -q PONG

wait_http "http://127.0.0.1:7474"

if [[ -x venv/bin/flask ]]; then
  if ! tmux has-session -t opencre-flask 2>/dev/null; then
    tmux new-session -d -s opencre-flask \
      "cd '${PWD}' && . ./venv/bin/activate && INSECURE_REQUESTS=1 FLASK_APP='${PWD}/cre.py' FLASK_CONFIG=development flask run --host=0.0.0.0 --port 5000"
  fi
  wait_http "http://127.0.0.1:5000/"
fi
