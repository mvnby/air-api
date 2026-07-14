#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' \
  'configure_patroni_pitr_env.sh is permanently disabled: it exposed PITR credentials to API/bot environments.' \
  'Use apply_postgres_pitr_primary_prerequisites.py through the reviewed two-node cluster transaction.' >&2
exit 64
