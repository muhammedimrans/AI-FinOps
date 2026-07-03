from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from costorah_agent.collectors.base import BaseCollector
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent
from costorah_agent.collectors.registry import CollectorRegistry
from costorah_agent.config import AgentConfig


class OneShotCollector(BaseCollector):
    """Emits exactly one event on its first poll, then nothing — enough to
    exercise a full collect -> queue -> deliver cycle deterministically.

    Registered under the "openai" key (a name AgentConfig actually
    recognizes) rather than a synthetic name, since AgentConfig's
    provider-name validation is intentionally stricter than the
    CollectorRegistry's forward-compatible skip-unknown-names behavior.
    """

    name = "openai"
    _fired = False

    async def collect(self) -> list[NormalizedUsageEvent]:
        if OneShotCollector._fired:
            return []
        OneShotCollector._fired = True
        event = self.normalize({})
        self._record_collected(1)
        return [event]

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        return NormalizedUsageEvent(
            provider="openai", model="gpt-4o", request_id="agent_test_evt_1", cost=0.01
        )

    async def health(self) -> CollectorHealth:
        return CollectorHealth(name=self.name, enabled=True, healthy=True, detail="ok")


class UnhealthyOneShotCollector(OneShotCollector):
    """Same collection behavior as OneShotCollector, but always reports
    itself unhealthy — used to exercise the health endpoint's
    collector-driven "degraded" branch specifically."""

    async def health(self) -> CollectorHealth:
        return CollectorHealth(
            name=self.name, enabled=True, healthy=False, detail="simulated failure"
        )


@pytest.fixture(autouse=True)
def _reset_one_shot_collector() -> None:
    OneShotCollector._fired = False


@pytest.fixture
def dummy_registry() -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register("openai", OneShotCollector)
    return registry


@pytest.fixture
def unhealthy_dummy_registry() -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register("openai", UnhealthyOneShotCollector)
    return registry


@pytest.fixture
def agent_config(tmp_path: Path, valid_api_key: str) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "server": {"endpoint": "https://api.costorah.test"},
            "organization": {"api_key": valid_api_key},
            "collection": {"interval_seconds": 0.05, "batch_size": 50},
            "providers": {"openai": True},
            "retry": {"backoff_seconds": [0.05, 0.05], "max_attempts": None},
            "queue": {"max_memory_events": 100, "sqlite_path": str(tmp_path / "queue.db")},
            "http_server": {"enabled": False},
        }
    )


async def wait_until(condition: Any, *, timeout: float = 2.0, interval: float = 0.02) -> bool:
    """Poll `condition()` until it returns truthy or `timeout` elapses."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if condition():
            return True
        await asyncio.sleep(interval)
    return bool(condition())
