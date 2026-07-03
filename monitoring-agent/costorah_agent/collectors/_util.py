"""Small shared helpers for collector implementations."""

from __future__ import annotations

import hashlib
from datetime import datetime


def deterministic_request_id(*parts: str) -> str:
    """
    Build a stable request_id from the pieces that uniquely identify a
    usage record for a given provider (e.g. bucket start/end time + model).

    Deterministic hashing means re-polling an overlapping time window (the
    agent's collection interval is shorter than most providers' bucket
    granularity) naturally produces the *same* request_id for the same
    underlying usage — which EP-16's (organization_id, request_id) unique
    constraint then dedupes for free. This is the agent-side half of "never
    double count usage."
    """
    joined = "|".join(parts)
    digest = hashlib.sha256(joined.encode()).hexdigest()[:32]
    return f"agent_{digest}"


def env_or_config(config: dict[str, object], key: str, env_var: str) -> str | None:
    """Prefer an explicit config value; fall back to an environment variable."""
    import os

    value = config.get(key)
    if isinstance(value, str) and value:
        return value
    env_value = os.environ.get(env_var)
    return env_value if env_value else None


def utc_now_iso() -> str:
    from datetime import UTC

    return datetime.now(UTC).isoformat()
