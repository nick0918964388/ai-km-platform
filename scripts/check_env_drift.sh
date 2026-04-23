#!/usr/bin/env bash
# check_env_drift.sh — verify .env.example covers every ${VAR} referenced in docker-compose.yml
# Usage: bash scripts/check_env_drift.sh
# Exit 0 = ok, Exit 1 = drift detected

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
EXAMPLE_FILE="$REPO_ROOT/.env.example"

# Variables that compose references but are intentionally absent from .env.example.
# These are docker-compose built-ins or host-level vars that users never set in .env.
EXCEPTIONS=(
  COMPOSE_PROJECT_NAME
  COMPOSE_FILE
  COMPOSE_PROFILES
)

# ---- extract VAR names from docker-compose.yml ----
# Matches ${VAR}, ${VAR:-default}, ${VAR:?error}, ${VAR:+val}
compose_vars=$(COMPOSE_FILE="$COMPOSE_FILE" python3 -c "
import re, os
with open(os.environ['COMPOSE_FILE']) as f:
    content = f.read()
pattern = re.compile(r'\\\$\{([A-Z][A-Z0-9_]*)(?::[?!+\-][^}]*)?\}')
for v in sorted(set(pattern.findall(content))):
    print(v)
")

# ---- extract KEY names from .env.example ----
example_keys=$(EXAMPLE_FILE="$EXAMPLE_FILE" python3 -c "
import re, os
with open(os.environ['EXAMPLE_FILE']) as f:
    content = f.read()
pattern = re.compile(r'^([A-Z][A-Z0-9_]*)=', re.MULTILINE)
for k in sorted(set(pattern.findall(content))):
    print(k)
")

# ---- compare: compose vars missing from example ----
missing=()
for var in $compose_vars; do
    # skip exception list
    skip=0
    for exc in "${EXCEPTIONS[@]}"; do
        if [[ "$var" == "$exc" ]]; then
            skip=1
            break
        fi
    done
    [[ $skip -eq 1 ]] && continue

    if ! printf '%s\n' $example_keys | grep -qx "$var"; then
        missing+=("$var")
    fi
done

compose_count=$(printf '%s\n' $compose_vars | wc -l | tr -d ' ')
exception_count=${#EXCEPTIONS[@]}

if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: .env.example is missing the following keys referenced in docker-compose.yml:"
    for m in "${missing[@]}"; do
        echo "  - $m"
    done
    echo ""
    echo "Add them to .env.example (even with an empty value) to fix this drift."
    echo "See docs/ENV_RUNBOOK.md for guidance."
    exit 1
fi

echo "OK: .env.example covers all $compose_count compose vars (exceptions: $exception_count)."
exit 0
