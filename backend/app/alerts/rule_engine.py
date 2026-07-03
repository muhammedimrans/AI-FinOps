"""Rule Engine — evaluates an organization's persisted AlertRule rows.

Each `AlertRule` is one leaf condition (operator + threshold) for one
`AlertType`. `RuleEngine.evaluate_type()` loads every enabled rule for an
organization + alert type, compares each against a caller-supplied
`current_value`, and returns the rules that matched — the caller (e.g.
the ingestion budget check) decides what to do with a match (fire an
alert via `AlertService`).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.conditions import compare
from app.models.alert import AlertRule, AlertType
from app.repositories.alert_repository import AlertRuleRepository


class RuleEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._rules = AlertRuleRepository(session)

    async def evaluate_type(
        self,
        *,
        organization_id: uuid.UUID,
        alert_type: AlertType,
        current_value: float,
    ) -> list[AlertRule]:
        """Every enabled rule of `alert_type` for this organization whose
        condition matches `current_value`. Never raises on a bad rule —
        one misconfigured rule (which can't really happen given the DB
        constraints, but defensively) should not stop every other rule
        from being evaluated."""
        rules = await self._rules.list_enabled_for_type(organization_id, alert_type)
        matched: list[AlertRule] = []
        for rule in rules:
            if compare(rule.operator, current_value, rule.threshold):
                matched.append(rule)
        return matched
