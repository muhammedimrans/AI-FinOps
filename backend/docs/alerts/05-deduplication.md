# Deduplication — EP-19.3

`app/alerts/dedup.py`, applied inside `AlertService.fire()`
(`app/alerts/dispatcher.py`).

## The ticket's example, concretely

> 100 provider failures → 1 notification → counter: 100 occurrences

Every call to `AlertService.fire()` computes a **dedup key**:

```python
def build_dedup_key(alert_type: AlertType, scope: str) -> str:
    raw = f"{alert_type.value}:{scope}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
```

`scope` is whatever distinguishes "the same underlying thing" for that
alert type — a project id for budget alerts, a provider name for
provider alerts, an API key id for key events, an
`(organization_id, user_email)` pair for membership events. Hashed (not
the raw scope string) so an arbitrarily long scope value can't blow past
the `dedup_key` column's bound or leak into an index unbounded.

## What happens on a repeat

`AlertRepository.find_open_by_dedup_key(org_id, dedup_key)` looks for an
existing row with the same `(organization_id, dedup_key)` that is still
`status == OPEN`:

- **Found** → `occurrence_count += 1`, `last_occurred_at` and `message`
  updated to the newest occurrence's values, metadata merged. No new row.
  `alerts_deduplicated_total` incremented.
- **Not found** → a new `Alert` row created (`occurrence_count = 1`).
  `alerts_created_total` incremented.

Both paths call `_publish()` — a deduplicated occurrence still gets a
live event (with the updated `occurrence_count` in its payload), so the
notification center shows the running total.

## The "deduplication window" — status-based, not time-based

The ticket asks for a "configurable deduplication window." This
implementation expresses it as **"still OPEN"**, not a fixed duration: an
alert that's still open after an hour is still the same unresolved
problem — folding a new occurrence into it is correct. A fixed timeout
would let a still-ongoing failure spawn a fresh alert every N minutes,
which is the opposite of what deduplication is for.

Once an alert is **resolved or dismissed**, the next occurrence starts a
**fresh** alert rather than reopening the old one. This is deliberate:
resolving is an "I've dealt with this" signal from a human, and a stray
late occurrence silently undoing that would be surprising and
untrustworthy. If the underlying problem recurs after resolution, that's
correctly a new incident with its own timeline.

## Test coverage

`tests/test_ep19_3.py::TestDedup` (key determinism, differentiation by
type/scope, column-length bound) and
`TestAlertServiceFire::test_duplicate_occurrence_increments_existing`
(end-to-end: fire twice with the same scope, assert one row with
`occurrence_count == 2`, not two rows).
