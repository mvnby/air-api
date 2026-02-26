#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

chmod +x .githooks/pre-commit
chmod +x scripts/sync_manager_api_client.sh
git config core.hooksPath .githooks

echo "Git hooks are configured."
echo "core.hooksPath=$(git config --get core.hooksPath)"
