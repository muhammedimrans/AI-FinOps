"""
Shared helpers for `costorah.integrations.*` (EP-18.5). Every integration
(FastAPI, Starlette, Flask, Django, Celery, ASGI, WSGI) needs the same
three small things — a way to auto-initialize a client from
`COSTORAH_API_KEY`/`COSTORAH_ENDPOINT`, a generated request ID when the
caller didn't supply one, and a way to check the installed version of
the framework it's integrating with — so they live here once instead of
being copy-pasted into every integration module.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

from costorah._logging import get_logger
from costorah.exceptions import CostorahError

if TYPE_CHECKING:
    from costorah.client import Costorah

_log = get_logger(__name__)


def generate_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def auto_init_client(api_key: str | None, *, integration_name: str) -> Costorah | None:
    """Builds a `Costorah` client from an explicit `api_key`, falling back
    to `COSTORAH_API_KEY`. Returns None (never raises) if no key is
    configured or client construction fails — every integration treats a
    None client as "instrumentation still runs locally, nothing is
    submitted," never as a fatal error."""
    resolved_key = api_key or os.environ.get("COSTORAH_API_KEY")
    if not resolved_key:
        _log.warning(
            "costorah_%s_no_api_key: set COSTORAH_API_KEY, or pass api_key=/client= "
            "explicitly — instrumentation will still capture usage locally "
            "(events_captured_total) but nothing will be submitted",
            integration_name,
        )
        return None

    from costorah.client import Costorah

    try:
        endpoint = os.environ.get("COSTORAH_ENDPOINT", "https://api.costorah.com")
        return Costorah(api_key=resolved_key, endpoint=endpoint)
    except CostorahError as exc:
        _log.warning("costorah_%s_init_failed error=%s", integration_name, exc)
        return None


def parse_version(version_string: str) -> tuple[int, ...]:
    """Best-effort `(major, minor, ...)` int tuple from a version string
    like '2.3.1' or '5.6.3'. Non-numeric trailing segments (e.g. 'rc1')
    are dropped rather than raising, since this is only used for
    coarse-grained "is this at least X.Y" compatibility checks."""
    parts: list[int] = []
    for segment in version_string.split(".")[:3]:
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def check_min_version(
    installed: str, minimum: tuple[int, ...], *, framework_name: str
) -> str | None:
    """Returns a warning string (never raises) if `installed` is below
    `minimum`, else None. Callers log the warning and continue —
    unsupported-version handling in this SDK is always a degrade, never
    a crash."""
    if parse_version(installed) < minimum:
        min_str = ".".join(str(p) for p in minimum)
        return (
            f"costorah's {framework_name} integration targets {framework_name} "
            f">={min_str}; detected {installed}. It may still work, but is untested "
            f"below that version."
        )
    return None
