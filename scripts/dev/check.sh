#!/usr/bin/env bash
# Runs all lint, typecheck, and test steps locally — mirrors CI exactly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

FAILED=()

run_step() {
  local name="$1"
  shift
  echo -e "\n${BOLD}▶ $name${NC}"
  if "$@"; then
    echo -e "${GREEN}✔ $name passed${NC}"
  else
    echo -e "${RED}✘ $name failed${NC}"
    FAILED+=("$name")
  fi
}

# ─── Backend ──────────────────────────────────────────────────────────────────
cd "$ROOT/backend"

run_step "Backend: Ruff lint"   ruff check app tests
run_step "Backend: Black format" black --check app tests
run_step "Backend: mypy"         mypy app
run_step "Backend: pytest"       pytest tests/ -q --tb=short

# ─── Frontend & packages ──────────────────────────────────────────────────────
cd "$ROOT"

run_step "TypeScript: build check" pnpm --recursive --if-present typecheck
run_step "Frontend: ESLint"        pnpm --filter @ai-finops/frontend lint

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}All checks passed.${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}Failed steps:${NC}"
  for step in "${FAILED[@]}"; do
    echo -e "  ${RED}• $step${NC}"
  done
  exit 1
fi
