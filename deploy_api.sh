#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'MESSAGE'
deploy_api.sh is retired because its source bind mount changes the running
application before a health check and cannot provide a real rollback.

Publish a tested commit through the production GitHub Actions image workflow.
See docs/deployment.md and docs/google-oauth-token-runbook.md.
MESSAGE
exit 1
