#!/usr/bin/env bash
set -euo pipefail

echo "==> Waiting for the database"
python -m scripts.wait_for_db

echo "==> Applying database migrations"
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "==> Seeding demo data"
  python -m scripts.seed
fi

echo "==> Starting: $*"
exec "$@"
