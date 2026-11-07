#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== ruff check =="
ruff check .
echo "== ruff format =="
ruff format --check .
echo "== mypy =="
mypy --strict src
echo "== bandit =="
bandit -r src -ll
echo "== vulture =="
vulture src tests --min-confidence 80
echo "== pytest =="
PYTHONPATH=src pytest
echo "== hadolint =="
hadolint -c .hadolint.yaml Dockerfile
echo "== yamllint =="
yamllint -c .yamllint.yml docker-compose.yml docker-compose.ci.yml .github/workflows
echo "== actionlint =="
actionlint .github/workflows/*.yml

echo "Quality pipeline OK"
