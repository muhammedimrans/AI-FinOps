# Development Guide

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.13+ | [python.org](https://www.python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| pnpm | 9+ | `npm install -g pnpm` |
| Docker | 24+ | [docker.com](https://docker.com) |
| Docker Compose | v2 | bundled with Docker Desktop |

## First-Time Setup

```bash
# 1. Clone the repository
git clone https://github.com/muhammedimrans/ai-finops.git
cd ai-finops

# 2. Copy environment file
cp .env.example .env
# Edit .env with your local values if needed

# 3. Install backend dependencies
make install-backend

# 4. Install frontend dependencies
make install-frontend

# 5. Install pre-commit hooks
make pre-commit-install

# 6. Start infrastructure services
make up-infra

# 7. Run database migrations
make migrate
```

## Daily Development

```bash
# Start everything (in separate terminals)
make up-infra      # terminal 1: postgres, clickhouse, redis
make backend       # terminal 2: FastAPI with hot reload
make frontend      # terminal 3: Vite dev server
```

Or use Docker for everything:

```bash
make up
make logs
```

## Code Quality

All checks run automatically on commit via pre-commit hooks.

```bash
make lint          # Ruff (Python) + ESLint (TypeScript)
make format        # Black + Ruff --fix (Python), Prettier (TypeScript)
make typecheck     # mypy (Python) + tsc (TypeScript)
make test          # pytest + vitest
make ci            # lint + typecheck + test (full CI locally)
```

## Branching Strategy

```
main                    # production-ready, protected
feature/<description>   # new features
fix/<description>       # bug fixes
claude/<description>    # AI-assisted implementation branches
```

All branches require CI passing before merge.

## Project Conventions

### Python

- **Formatter**: Black (line length 88)
- **Linter**: Ruff
- **Type checker**: mypy (strict mode)
- **Import style**: absolute imports only
- **Comments**: only when the WHY is non-obvious

### TypeScript

- **Formatter**: Prettier
- **Linter**: ESLint
- **Strict mode**: enabled
- **Path aliases**: `@/` maps to `src/`

### Architecture Rules

- Clean architecture: domain layer -> service layer -> repository layer -> API layer
- No circular imports between layers
- No business logic in API routers
- No database access outside repositories
- Configuration via environment variables only
- Structured JSON logging everywhere

## Environment Variables

See `.env.example` for all variables with descriptions. Never commit `.env`.

## Troubleshooting

**PostgreSQL not starting**

```bash
docker compose logs postgres
make shell-postgres
```

**Port conflicts**

Edit `.env` to change port assignments. All ports are configurable.

**Python import errors**

```bash
make install-backend
```
