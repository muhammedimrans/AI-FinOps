"""Condition matcher — pure, dependency-free comparison + composition logic.

Two layers, deliberately kept separate:

  1. `compare()` — a single leaf comparison (the five `AlertOperator`
     values already persisted on `AlertRule`: gt/lt/eq/gte/lte).
  2. `Condition`/`evaluate()` — a composable AND/OR/NOT tree of leaf
     comparisons, for the ticket's "Multiple Conditions" requirement.
     `AlertRule` (the persisted DB row) only stores one leaf condition per
     rule today — the composite tree is available for any caller that
     wants to combine several signals in memory (e.g. a future EP wiring
     a rule type that needs "cost increased AND request count also
     increased"), but nothing currently persists a composite tree to the
     database. Stated here rather than silently only half-built.

`percent_increase()` and `rolling_average()` are plain functions, not
operators — the ticket's "Percent Increase"/"Rolling Average" rule types
are computed by the caller into a single number, then compared with the
same five operators above (there is no sixth "operator" for these; the
computation happens before the comparison, not instead of it).
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.models.alert import AlertOperator

Number = Decimal | float | int


def compare(operator: AlertOperator, current_value: Number, threshold: Number) -> bool:
    """The single numeric comparison every AlertRule ultimately reduces to."""
    a, b = Decimal(str(current_value)), Decimal(str(threshold))
    if operator == AlertOperator.GT:
        return a > b
    if operator == AlertOperator.LT:
        return a < b
    if operator == AlertOperator.EQ:
        return a == b
    if operator == AlertOperator.GTE:
        return a >= b
    if operator == AlertOperator.LTE:
        return a <= b
    return False  # pragma: no cover — AlertOperator is exhaustive above


def percent_increase(previous: Number, current: Number) -> Decimal:
    """`current` as a percentage increase over `previous`. Returns 0 when
    `previous` is zero (there is no meaningful percentage change from
    nothing — treated as "no increase" rather than raising or returning
    infinity, since callers feed this straight into `compare()`)."""
    prev = Decimal(str(previous))
    curr = Decimal(str(current))
    if prev == 0:
        return Decimal(0)
    return ((curr - prev) / prev) * Decimal(100)


def rolling_average(values: Sequence[Number]) -> Decimal:
    """Plain arithmetic mean. Returns 0 for an empty window rather than
    raising — an alert rule evaluated with no history yet simply doesn't
    fire (0 rarely crosses a meaningful threshold), instead of the
    evaluation itself failing."""
    if not values:
        return Decimal(0)
    total = sum(Decimal(str(v)) for v in values)
    return total / Decimal(len(values))


class LogicalOperator(enum.StrEnum):
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass(frozen=True)
class LeafCondition:
    """One `compare()` call against a named field in the evaluation context."""

    field: str
    operator: AlertOperator
    threshold: Number


@dataclass(frozen=True)
class CompositeCondition:
    """A boolean combination of child conditions. `NOT` uses exactly one
    child (`children[0]`); `AND`/`OR` use all of them."""

    logic: LogicalOperator
    children: Sequence[LeafCondition | CompositeCondition]


Condition = LeafCondition | CompositeCondition


def evaluate(condition: Condition, context: dict[str, Number]) -> bool:
    """Evaluate a `Condition` tree against a context of named values.

    Raises `KeyError` if a `LeafCondition` references a field missing from
    `context` — a misconfigured rule should fail loudly during evaluation,
    not silently evaluate to False and give the illusion the condition was
    checked.
    """
    if isinstance(condition, LeafCondition):
        return compare(condition.operator, context[condition.field], condition.threshold)

    if condition.logic == LogicalOperator.NOT:
        if len(condition.children) != 1:
            raise ValueError("NOT requires exactly one child condition")
        return not evaluate(condition.children[0], context)
    if condition.logic == LogicalOperator.AND:
        return all(evaluate(child, context) for child in condition.children)
    if condition.logic == LogicalOperator.OR:
        return any(evaluate(child, context) for child in condition.children)
    raise ValueError(f"Unknown logical operator: {condition.logic}")  # pragma: no cover
