# Rule Engine — EP-19.3

`app/alerts/conditions.py` + `app/alerts/rule_engine.py`.

## Two layers, deliberately kept separate

**Layer 1 — `compare()`**: a single leaf comparison. The five
`AlertOperator` values persisted on `AlertRule`:

```python
GT = "gt"; LT = "lt"; EQ = "eq"; GTE = "gte"; LTE = "lte"
```

Implemented on `Decimal(str(x))` on both sides — never raw `float`
comparison, so `0.1 + 0.2 == 0.3`-style precision bugs can't creep into a
threshold check.

**Layer 2 — `Condition` / `evaluate()`**: a composable AND/OR/NOT tree of
leaf comparisons, satisfying the ticket's "Multiple Conditions"
requirement:

```python
CompositeCondition(
    logic=LogicalOperator.AND,
    children=[
        LeafCondition(field="cost", operator=AlertOperator.GT, threshold=100),
        LeafCondition(field="requests", operator=AlertOperator.GT, threshold=10),
    ],
)
```

**Important scoping note**: the persisted `AlertRule` database row only
stores **one leaf condition** — one `operator` + one `threshold` column,
no JSON tree. The composite AND/OR/NOT evaluator is a real,
fully-tested, general-purpose module any in-memory caller can use, but
nothing today persists a composite tree to the database, because the one
alert type with real data to evaluate (budget) only needs a single
threshold. Building a JSON-tree persistence layer for a feature nothing
uses yet would be exactly the kind of premature abstraction this
project's engineering discipline avoids — the module is ready for a
future EP that needs it.

## Percent Increase / Rolling Average

Not operators — plain functions that produce a number, which is then
compared with the same five operators:

```python
percent_increase(previous=100, current=150)   # -> Decimal(50)
rolling_average([10, 20, 30])                 # -> Decimal(20)
```

`percent_increase()` returns `0` (not infinity) when `previous == 0` —
there's no meaningful percentage change from nothing.
`rolling_average([])` returns `0` for an empty window rather than
raising — a rule evaluated with no history yet simply doesn't fire.

## Severity

Five levels, `AlertSeverity`: `info < low < medium < high < critical`.
`severity_rank()` gives the numeric ordering used for sorting (alert
list, notification center) and preference-threshold comparisons
(`should_surface()` in `preferences.py`). Severity is stored on both
`AlertRule` (the severity an alert should carry when the rule fires) and
`Alert` (the severity the fired instance actually has).

## `RuleEngine.evaluate_type()`

```python
matched: list[AlertRule] = await RuleEngine(session).evaluate_type(
    organization_id=org_id,
    alert_type=AlertType.BUDGET_THRESHOLD,
    current_value=95.0,  # e.g. pct of budget used
)
```

Loads every **enabled** rule of that type for that org, compares each
against `current_value`, returns the matches. Never raises on a
misconfigured rule (can't really happen given DB constraints, but
defensively) — one bad rule doesn't stop every other rule from being
evaluated. The caller (today: `app/api/v1/ingest.py`'s
`_check_budget_alerts()`) decides what to do with a match — call
`AlertService.fire()`.

## Performance

`compare()` and `evaluate()` are pure, allocation-light functions with no
I/O — sub-millisecond per call. `RuleEngine.evaluate_type()`'s cost is
dominated by the `AlertRuleRepository.list_enabled_for_type()` query
(indexed on `(organization_id, alert_type)` and `(organization_id,
enabled)` — see the migration), timed via
`rule_evaluation_latency_seconds` in `app/alerts/metrics.py`.
