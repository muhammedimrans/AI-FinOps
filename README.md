# AI FinOps

**Production-grade AI cost observability and financial operations platform.**

Track, attribute, forecast, and optimize your AI spend across OpenAI, Anthropic, Google, and every major provider — in real time.

---

## Overview

AI FinOps gives engineering, finance, and platform teams a single pane of glass for AI cost management. It ingests usage events via SDK push and provider API pull, reconciles them against authoritative billing records, and exposes rich analytics, budgets, alerts, and forecasts through a modern web dashboard and API.

## Architecture

```
SDK / Gateway push → Collector → Event Log → Processing → Read Models → API → Dashboard
Provider APIs pull ──────────────────────────────↑ (reconciliation)
```

- **Ingestion plane** — push (SDK/gateway) + pull (adapter workers)
- **Processing plane** — normalization, cost attribution, reconciliation, forecasting
- **Serving plane** — REST/GraphQL API, real-time WebSocket updates
- **Frontend** — React + TypeScript dashboard

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic |
| OLTP Store | PostgreSQL 16 |
| Analytics Store | ClickHouse 24 |
| Cache / Queue | Redis 7 |
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| State Management | TanStack Query, React Router |
| Infrastructure | Docker, Docker Compose, GitHub Actions |

## Repository Structure

```
AI-FinOps/
├── backend/              # FastAPI application
│   ├── app/              # Application source
│   │   ├── api/          # HTTP layer (routers, dependencies)
│   │   ├── config/       # Settings and environment
│   │   ├── core/         # Cross-cutting concerns (logging, DI)
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic v2 schemas
│   │   ├── services/     # Business logic
│   │   ├── repositories/ # Data access layer
│   │   ├── workers/      # Background task workers
│   │   └── ...
│   ├── migrations/       # Alembic database migrations
│   └── tests/            # Backend test suite
├── frontend/             # React + TypeScript SPA
├── packages/             # Shared TypeScript packages (monorepo)
│   ├── api-contracts/    # OpenAPI-derived types
│   ├── error-codes/      # Canonical error catalog
│   ├── event-schema/     # Usage event schemas
│   ├── shared-config/    # Runtime configuration helpers
│   └── shared-types/     # Common TypeScript types
├── deployment/           # Docker, Kubernetes, Terraform, Nginx
├── scripts/              # Developer and CI scripts
├── tests/                # Integration, E2E, and load tests
├── docs/                 # Architecture docs, ADRs, runbooks
└── Docs/                 # SDD and engineering specs
```

## Quick Start

### Prerequisites

- Docker 24+ and Docker Compose v2
- Python 3.13 (for local backend development)
- Node.js 20+ and pnpm 9+ (for frontend development)

### Start Everything

```bash
cp .env.example .env
make dev
```

This starts PostgreSQL, ClickHouse, Redis, the backend API, and the frontend dev server.

### Individual Commands

```bash
make help           # Show all available targets
make up             # Start infrastructure services
make down           # Stop all services
make backend        # Start backend only
make frontend       # Start frontend only
make test           # Run all tests
make lint           # Run linters
make format         # Auto-format code
make migrate        # Run database migrations
make logs           # Tail all service logs
```

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for full setup instructions, coding conventions, and workflow guidelines.

## Documentation

| Document | Location |
|---|---|
| Software Design Document | [Docs/SDD/](Docs/SDD/) |
| Architecture Decision Records | [docs/ADR/](docs/ADR/) |
| API Reference | [docs/API/](docs/API/) |
| Runbooks | [docs/Runbooks/](docs/Runbooks/) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
