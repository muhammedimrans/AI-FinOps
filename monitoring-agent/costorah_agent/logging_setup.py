"""
Structured logging setup with mandatory secret redaction and rotation.

Security requirement (non-negotiable, enforced here rather than trusted to
call sites): the agent must never log an API key, a user prompt, a model
response, or "sensitive metadata". This module installs a structlog
processor that redacts known-sensitive keys from every log event's
key-value pairs before they're rendered, as a last line of defense even if
a call site accidentally passes something it shouldn't.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from typing import Any

import structlog

# Field names that are always redacted, wherever they appear in a log
# event's kwargs (case-insensitive substring match, so "api_key",
# "organization_api_key", "Authorization" etc. are all caught).
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


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _BEARER_TOKEN_RE.sub("costorah_live_***REDACTED***", value)
    return value


def redact_sensitive_fields(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor: redact known-sensitive keys and any embedded
    costorah_live_ API key substrings, regardless of which field they're in."""
    for key in list(event_dict.keys()):
        lowered = key.lower()
        if any(pattern in lowered for pattern in _REDACTED_KEY_PATTERNS):
            event_dict[key] = "***REDACTED***"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def configure_logging(
    *,
    level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Configure structlog + stdlib logging with redaction and optional
    rotating-file output. Safe to call once at agent startup."""
    shared_processors: list[Any] = [
        redact_sensitive_fields,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Quiet third-party HTTP client noise at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
