"""
Integration test package.

Tests in this package require a live PostgreSQL database. They are skipped
automatically when the DATABASE_URL environment variable is not set.

To run integration tests locally:

    export DATABASE_URL="postgresql+asyncpg://user:pass@host/dbname"
    pytest tests/integration/ -v

To run only integration tests in CI:

    pytest tests/integration/ -m integration -v

To run all tests (unit + integration) in CI:

    pytest tests/ -v
"""
