# Architecture Overview

This document is a concise reference. The authoritative specification is in [docs/SDD/](docs/SDD/).

## Architectural Style

Event-driven system with CQRS-style read/write separation.

- **Write path**: asynchronous, event-driven (ingestion -> event log -> processing -> read models)
- **Read path**: synchronous, low-latency request/response (API -> read models)
- **Ingestion**: push (SDK/gateway) + pull (adapter workers polling provider APIs)
- **Reconciliation**: merges provisional push events with authoritative pull data

## Services

| Service | Responsibility |
|---|---|
| API | Public REST interface, BFF for dashboard |
| Collector | Receives SDK push events, validates, enqueues |
| Adapter Workers | Polls provider APIs (OpenAI, Anthropic, etc.) |
| Processing | Normalizes events, computes costs, runs reconciliation |
| Scheduler | Triggers periodic jobs (adapter pulls, reports) |

## Data Stores

| Store | Usage |
|---|---|
| PostgreSQL | OLTP — organizations, projects, budgets, config |
| ClickHouse | OLAP — usage events, cost analytics, time-series aggregates |
| Redis | Cache, session store, task queue |

## Communication

- Synchronous: HTTP/REST between API and clients
- Asynchronous: Redis queues between services

## Key Principles

1. Single-writer ownership — every dataset has exactly one service that writes to it
2. No circular dependencies between service layers
3. All configuration via environment variables
4. Structured JSON logging everywhere
5. Health, readiness, and metrics endpoints on every service

For the full design, see the [SDD](docs/SDD/).
