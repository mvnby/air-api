#!/usr/bin/env bash
set -euo pipefail

MODE="docker"
PYTEST_ARGS=()

while (($#)); do
  case "$1" in
    --host)
      MODE="host"
      shift
      ;;
    --docker)
      MODE="docker"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  scripts/test_local.sh [--docker|--host] [pytest args...]

Modes:
  --docker  Run tests inside app container (default, same network mode as CI)
  --host    Run tests from host shell with test DB on localhost:5433

Examples:
  scripts/test_local.sh
  scripts/test_local.sh tests/unit -q
  scripts/test_local.sh --host tests/unit/test_product_filtering_jsonb.py -q
EOF
      exit 0
      ;;
    *)
      PYTEST_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  PYTEST_ARGS=(-v)
fi

if [[ "$MODE" == "docker" ]]; then
  exec docker compose exec -T app pytest "${PYTEST_ARGS[@]}"
fi

# Host mode: align DB creds with local .env when present.
if [[ -f .env ]]; then
  if [[ -z "${POSTGRES_USER:-}" ]]; then
    POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | tail -n1 | cut -d'=' -f2- | tr -d '\r')"
    export POSTGRES_USER
  fi
  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | tail -n1 | cut -d'=' -f2- | tr -d '\r')"
    export POSTGRES_PASSWORD
  fi
fi

export TEST_DB_HOST="${TEST_DB_HOST:-localhost}"
export TEST_DB_PORT="${TEST_DB_PORT:-5433}"
exec pytest "${PYTEST_ARGS[@]}"
