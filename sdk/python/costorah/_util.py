"""Small internal helpers."""

from __future__ import annotations

import os
import time
import uuid


def generate_request_id() -> str:
    """A stable-enough-per-call, globally unique request_id for callers who
    don't supply their own. Uses uuid4 (random) rather than a content hash
    here, since manual track() calls have no natural dedup key the way a
    provider response's own request ID does (that's EP-18.2's automatic
    instrumentation, which can hash the provider's own ID)."""
    return f"sdk_py_{uuid.uuid4().hex}"


def monotonic_ms() -> float:
    return time.monotonic() * 1000


def pid_safe_nonce() -> str:
    """Used only for tests/examples that need a human-inspectable unique
    suffix; not used in production request_id generation."""
    return f"{os.getpid()}_{int(time.time() * 1000)}"
