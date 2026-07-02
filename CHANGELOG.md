# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the
project is pre-1.0 and not yet versioned — entries are grouped under Unreleased.

## [Unreleased]

### Added
- COSTORAH dashboard frontend: Overview, Analytics, Providers, Models,
  Projects, Organization, Settings, Support, onboarding, org logo upload
- FastAPI backend: auth (JWT + refresh rotation, Argon2id, RBAC), providers,
  usage ingestion, pricing, dashboard/analytics read APIs
- CI: backend lint/typecheck/tests, frontend lint/typecheck/tests/build,
  Docker build checks

### Security
- Production startup now rejects missing/weak `JWT_SECRET`
