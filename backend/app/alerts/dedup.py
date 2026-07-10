"""Deduplication — group repeated occurrences of the same underlying
condition into one Alert row with an incrementing `occurrence_count`,
instead of one row per occurrence (the ticket's "100 provider failures →
1 notification → counter: 100 occurrences" example).

The dedup key groups by (organization, alert_type, scope) — `scope` is
whatever distinguishes "the same underlying thing" for that alert type
(e.g. a provider name for provider_error, a project id for
budget_exceeded). A new occurrence folds into an existing OPEN alert with
the same key; once that alert is resolved/dismissed, the next occurrence
starts a new alert rather than reopening the old one — resolving is a
deliberate "I've dealt with this" signal, not something a stray late
occurrence should silently undo.

The "configurable deduplication window" from the ticket is expressed as
"still OPEN", not a fixed time duration — an alert that's still open
after an hour is still the same unresolved problem; the window is
naturally bounded by however long it takes a human (or a future
auto-resolve policy) to close it out, rather than an arbitrary timeout
that would let a still-ongoing failure spawn a fresh alert every N
minutes.
"""

from __future__ import annotations

import hashlib
import uuid

from app.models.alert import AlertType


def build_dedup_key(alert_type: AlertType, scope: str) -> str:
    """A short, stable key for grouping. Hashed (not the raw scope string)
    so an arbitrarily long/weird scope value (e.g. a full error message)
    can't blow past the column's 255-char limit or leak into an index key
    unbounded."""
    raw = f"{alert_type.value}:{scope}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def budget_scope(project_id: uuid.UUID) -> str:
    return f"project:{project_id}"


def provider_scope(provider_name: str) -> str:
    return f"provider:{provider_name}"


def api_key_scope(api_key_id: uuid.UUID) -> str:
    return f"api_key:{api_key_id}"


def membership_scope(organization_id: uuid.UUID, user_email: str) -> str:
    return f"membership:{organization_id}:{user_email}"


def budget_threshold_scope(budget_id: uuid.UUID, period_key: str, threshold_pct: float) -> str:
    """Scope for EP-24.2's first-class `Budget` alerts — deliberately
    distinct from `budget_scope()` above (which is the older, project-only,
    single-threshold ingest-time check in app/api/v1/ingest.py, left
    unchanged).

    Qualified by (budget, period, threshold) rather than just budget id, so:
      - each configured threshold (50%/75%/90%/100%/110%/...) gets its own
        independent OPEN/resolved lifecycle instead of all thresholds
        folding into one alert and only ever showing whichever fired first;
      - a new period (e.g. next month) is never suppressed by a still-open
        alert from a prior period — `period_key` (e.g. "2026-07" for a
        monthly budget) changes every period, so the dedup key changes too
        and a fresh occurrence starts a new alert rather than reopening an
        old, already-resolved one.
    """
    return f"budget:{budget_id}:{period_key}:{threshold_pct}"
