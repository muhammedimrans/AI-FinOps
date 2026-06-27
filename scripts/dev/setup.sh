#!/usr/bin/env bash
# Sets up a local development environment from scratch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[setup]${NC} $*"; }
warn()    { echo -e "${YELLOW}[setup]${NC} $*"; }
error()   { echo -e "${RED}[setup]${NC} $*" >&2; exit 1; }

# ─── Prerequisites ────────────────────────────────────────────────────────────
info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || error "python3 not found. Install Python 3.13+."
command -v node >/dev/null 2>&1   || error "node not found. Install Node.js 20+."
command -v pnpm >/dev/null 2>&1   || error "pnpm not found. Run: npm install -g pnpm@9"
command -v docker >/dev/null 2>&1 || warn  "docker not found — services won't start locally."

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
NODE_VERSION=$(node --version | tr -d 'v')

info "Python: $PYTHON_VERSION | Node: $NODE_VERSION | pnpm: $(pnpm --version)"

# ─── Environment file ─────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  warn "Review .env and set any required secrets before starting services."
else
  info ".env already exists — skipping."
fi

# ─── Python virtual environment ───────────────────────────────────────────────
info "Setting up Python virtual environment..."
if [[ ! -d backend/.venv ]]; then
  python3 -m venv backend/.venv
fi

source backend/.venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e "backend[dev]"
info "Python dependencies installed."

# ─── Node.js dependencies ─────────────────────────────────────────────────────
info "Installing Node.js dependencies..."
pnpm install
info "Node.js dependencies installed."

# ─── Pre-commit hooks ─────────────────────────────────────────────────────────
if command -v pre-commit >/dev/null 2>&1; then
  info "Installing pre-commit hooks..."
  pre-commit install --install-hooks
else
  warn "pre-commit not found. Install with: pip install pre-commit"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
info "Setup complete! Next steps:"
echo "  • Start services:   docker compose up -d postgres redis clickhouse"
echo "  • Run migrations:   make migrate"
echo "  • Start backend:    make dev-backend"
echo "  • Start frontend:   make dev-frontend"
echo "  • Run all checks:   scripts/dev/check.sh"
