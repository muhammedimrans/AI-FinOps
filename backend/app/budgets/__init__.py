"""EP-24.2 — budget evaluation engine.

A thin layer over the existing analytics/repository aggregation
(`UsageCostRecordRepository`) and the existing alert dispatcher
(`AlertService`) — see `app/budgets/service.py`. No aggregation logic or
alert-persistence logic is duplicated here.
"""
