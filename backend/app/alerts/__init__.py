"""Alert Rule Engine & Notification Persistence — EP-19.3.

Reuses everything the ticket named rather than rebuilding it:
  - EP-19.1's EventBus/RealtimeEvent for delivery (app.realtime.event_bus).
  - EP-19.1/EP-19.2's WebSocket gateway for live delivery — an alert is
    published as a `RealtimeEvent` and flows through the exact same
    organization-scoped connection every other event type already uses.
  - EP-19.2's frontend notification center — it already merges live
    `notification.created`/`budget.*`/`provider.*`/etc. events into its
    alert list (see backend/docs/realtime/06-notifications.md's own note
    that this was "wired and ready" pending a real trigger). This EP is
    that trigger.
  - Existing JWT/RBAC/organization-membership auth (no new auth system) —
    NOTIFICATION_READ/NOTIFICATION_WRITE permissions added to the existing
    `Permission` enum, not a parallel authorization scheme.

Submodules:
  conditions.py   — pure condition/operator evaluation (gt/lt/eq/gte/lte),
                     AND/OR/NOT composition.
  rule_engine.py   — evaluates an organization's enabled AlertRule rows for
                     one alert type against a computed value.
  dedup.py         — groups repeated occurrences of the same underlying
                     condition into one Alert row with an occurrence count.
  suppression.py   — checks whether a firing alert should be suppressed
                     (maintenance window, org-wide, provider, or alert-type
                     scoped).
  dispatcher.py    — AlertService: the single public entry point every
                     trigger call site uses to fire an alert (persist +
                     dedup + suppress + publish to the EventBus).
  preferences.py   — per-user preference lookups (severity threshold,
                     quiet hours, enabled types) used to decide whether a
                     fired alert should reach a given user's live view.
  metrics.py       — Prometheus metrics, same pattern as
                     app.realtime.metrics (own CollectorRegistry, appended
                     to GET /metrics alongside the realtime payload).

Honesty note (see docs/realtime/ALERT_ARCHITECTURE.md for the full
accounting): of the 18 ticket-named alert types, this EP wires real
triggers for budget_threshold, budget_exceeded, provider_error,
provider_recovery, api_key_created, api_key_revoked, org_member_added,
and org_member_removed — the alert types with an actual code path that
already runs in this backend to hang a trigger off of. The remaining 10
(daily/hourly spend spike, sdk_offline/reconnected, api_key_expired,
high_latency, rate_limit_spike, large_cost_increase,
usage_ingestion_failure, webhook_delivery_failure) have no existing
signal source in this backend (no SDK heartbeat tracking, no latency/
rate-limit telemetry, no webhook subsystem) and are defined in AlertType
for forward compatibility only, exactly like EP-19.1's own unemitted
event types.
"""
