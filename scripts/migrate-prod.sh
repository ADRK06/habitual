#!/usr/bin/env bash
# Runs `flask db upgrade` against the Neon main (prod) branch, using
# .env.prod instead of the dev .env. Never prints the connection string.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env.prod"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE" >&2
  echo "Create it from .env.prod.example with the Neon main branch's pooled DATABASE_URL." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL not set in $ENV_FILE" >&2
  exit 1
fi

echo "Running migrations against production (Neon main)..."
(cd "$ROOT_DIR" && flask --app app db upgrade)
echo "Done."
