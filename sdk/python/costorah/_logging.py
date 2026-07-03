"""
Structured logging with mandatory secret redaction — the SDK must never
log an API key, a prompt, a model response, or other sensitive metadata,
even at DEBUG level. This is enforced here rather than trusted to call
sites, mirroring the Monitoring Agent's `logging_setup.py`
(`monitoring-agent/costorah_agent/logging_setup.py`, EP-17) so the whole
COSTORAH ecosystem redacts consistently — this is a parallel
implementation, not a shared import (the SDK does not depend on the
Monitoring Agent package).
"""

from __future__ import annotations

import logging
import re
from typing import Any

_REDACTED_KEY_PATTERNS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "prompt",
    "completion",
    "response_body",
    "user_prompt",
    "model_response",
)

_BEARER_TOKEN_RE = re.compile(r"costorah_live_[A-Za-z0-9_-]+")


def _redact_string(value: str) -> str:
    return _BEARER_TOKEN_RE.sub("costorah_live_***REDACTED***", value)


def redact(value: Any) -> Any:
    """Recursively redact known-sensitive keys and any embedded
    costorah_live_ token substring, regardless of which field it's in."""
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, val in value.items():
            if isinstance(key, str) and any(
                pattern in key.lower() for pattern in _REDACTED_KEY_PATTERNS
            ):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact(val)
        return redacted
    if isinstance(value, (list, tuple)):
        return type(value)(redact(item) for item in value)
    return value


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg) if isinstance(record.msg, str) else record.msg
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact(record.args)
            else:
                record.args = tuple(redact(a) for a in record.args)
        return True


def get_logger(name: str = "costorah") -> logging.Logger:
    """Return a logger with the redaction filter attached. Safe to call
    repeatedly — the filter is only attached once per logger instance."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, _RedactingFilter) for f in logger.filters):
        logger.addFilter(_RedactingFilter())
    return logger
