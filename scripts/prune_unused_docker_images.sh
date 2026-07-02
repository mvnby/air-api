#!/usr/bin/env bash
set -euo pipefail

echo "== Disk usage before Docker image prune =="
df -h /
docker system df || true

echo "== Pruning unused Docker images =="
docker image prune -af

echo "== Disk usage after Docker image prune =="
docker system df || true
df -h /
