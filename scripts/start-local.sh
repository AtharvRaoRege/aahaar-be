#!/usr/bin/env bash
set -euo pipefail

# Local Aahaar API (same idea as menumind-backend/scripts/start_local.sh).
#   ./scripts/start-local           Postgres in Docker, API in a venv on :8001
#   ./scripts/start-local --docker  Full stack via docker compose

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8001}"
COMPOSE=(docker compose)

section() {
  echo
  echo "============================================================"
  echo "$1"
  echo "============================================================"
}

ensure_env_file() {
  if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
      cp .env.example .env
      echo "Created .env from .env.example — add CLERK_SECRET_KEY for Google login."
    else
      echo "Missing .env and .env.example"
      exit 1
    fi
  fi
}

start_postgres() {
  section "Starting Postgres"
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required (used for Postgres)."
    exit 1
  fi
  "${COMPOSE[@]}" up -d db
  echo "Waiting for Postgres to become healthy..."
  local attempts=0
  while (( attempts < 40 )); do
    if "${COMPOSE[@]}" exec -T db pg_isready -U aahaar -d aahaar >/dev/null 2>&1; then
      echo "Postgres is ready."
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  echo "Postgres did not become ready in time."
  "${COMPOSE[@]}" logs db --tail 40
  exit 1
}

USE_DOCKER=false
if [[ "${1:-}" == "--docker" ]]; then
  USE_DOCKER=true
fi

ensure_env_file

if [[ "$USE_DOCKER" == true ]]; then
  section "Running with Docker Compose"
  "${COMPOSE[@]}" up --build
  exit 0
fi

start_postgres

# Local uvicorn needs host port 8001. Stop the API container if it is bound there.
if docker ps --format '{{.Names}} {{.Ports}}' | grep -q 'aahaar-be-api-1'; then
  section "Stopping API container (keeping Postgres)"
  "${COMPOSE[@]}" stop api >/dev/null 2>&1 || true
fi

section "Python virtualenv"
if [[ ! -d venv ]]; then
  echo "Creating venv..."
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install -q --upgrade pip
echo "Installing dependencies..."
python -m pip install -q -r requirements-dev.txt

section "Database"
python -m scripts.wait_for_db
alembic upgrade head
python -m scripts.seed

section "Starting FastAPI"
echo "API:   http://localhost:${API_PORT}"
echo "Docs:  http://localhost:${API_PORT}/docs"
echo "Health: http://localhost:${API_PORT}/health"
echo "Demo:   owner@aahaar.app / Password123!"
echo

set +e
uvicorn app.main:app --reload --host 0.0.0.0 --port "${API_PORT}"
UVICORN_EXIT_CODE=$?
set -e

if [[ $UVICORN_EXIT_CODE -eq 130 ]]; then
  exit 130
fi
exit "$UVICORN_EXIT_CODE"
