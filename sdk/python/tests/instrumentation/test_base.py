from __future__ import annotations

import threading
from typing import Any

import pytest

from costorah.instrumentation.base import BaseInstrumentor, ExtractedUsage, InstrumentationError


class _Target:
    def method(self) -> str:
        return "original"


class _DummyInstrumentor(BaseInstrumentor):
    name = "dummy"

    def __init__(self, *, target: _Target, fail: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._target_cls = type(target)
        self._fail = fail
        self.apply_count = 0

    def _apply_patches(self) -> None:
        self.apply_count += 1
        if self._fail:
            raise InstrumentationError("simulated setup failure")
        self._patch(self._target_cls, "method", lambda self: "patched")

    def extract_usage(self, response: Any) -> dict[str, Any]:
        return {"input_tokens": 1, "output_tokens": 2}

    def normalize(self, raw_usage: dict[str, Any], **kwargs: Any) -> ExtractedUsage:
        return ExtractedUsage(provider="dummy", model="m", **raw_usage)


def test_instrument_applies_patch() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    inst.instrument()
    assert target.method() == "patched"
    assert inst.is_instrumented()
    inst.uninstrument()
    assert target.method() == "original"
    assert not inst.is_instrumented()


def test_double_instrument_is_idempotent() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    inst.instrument()
    inst.instrument()
    assert inst.apply_count == 1
    inst.uninstrument()


def test_double_uninstrument_is_idempotent() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    inst.instrument()
    inst.uninstrument()
    inst.uninstrument()  # must not raise
    assert not inst.is_instrumented()


def test_uninstrument_without_instrument_is_a_noop() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    inst.uninstrument()
    assert not inst.is_instrumented()


def test_disabled_instrumentor_never_patches() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target, enabled=False)
    inst.instrument()
    assert not inst.is_instrumented()
    assert target.method() == "original"


def test_setup_failure_leaves_instrumentor_uninstrumented() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target, fail=True)
    with pytest.raises(InstrumentationError):
        inst.instrument()
    assert not inst.is_instrumented()


def test_events_captured_total_tracks_record_captured() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    assert inst.events_captured_total == 0
    inst._record_captured()
    inst._record_captured(2)
    assert inst.events_captured_total == 3


def test_configuration_flags_default_and_overridable() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    assert inst.enabled is True
    assert inst.capture_metadata is True
    assert inst.calculate_cost_enabled is True

    inst2 = _DummyInstrumentor(
        target=target, enabled=True, capture_metadata=False, calculate_cost=False
    )
    assert inst2.capture_metadata is False
    assert inst2.calculate_cost_enabled is False


def test_instrument_uninstrument_thread_safe_under_concurrency() -> None:
    target = _Target()
    inst = _DummyInstrumentor(target=target)
    errors: list[Exception] = []

    def worker() -> None:
        try:
            inst.instrument()
            inst.uninstrument()
        except Exception as exc:  # pragma: no cover - failure surfaced via assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


def test_extracted_usage_defaults() -> None:
    usage = ExtractedUsage(provider="dummy", model="m")
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cost == 0.0
    assert usage.currency == "USD"
    assert usage.status == "success"
    assert usage.metadata == {}
    assert usage.timestamp is not None
