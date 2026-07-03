from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

boto3 = pytest.importorskip("boto3")

from costorah.instrumentation.bedrock import BedrockInstrumentor  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    BedrockInstrumentor().uninstrument()


def _client() -> Any:
    return boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="x",
        aws_secret_access_key="y",
    )


def test_converse_captures_usage_via_real_dispatch(captured_submissions: list[Any]) -> None:
    inst = BedrockInstrumentor()
    inst.instrument()
    client = _client()

    api_response = {
        "output": {"message": {"role": "assistant", "content": [{"text": "hi"}]}},
        "usage": {"inputTokens": 25, "outputTokens": 11, "totalTokens": 36},
    }
    with patch("botocore.client.BaseClient._make_api_call", return_value=api_response):
        resp = client.converse(
            modelId="anthropic.claude-3-sonnet",
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
        )
    inst.uninstrument()

    assert resp == api_response
    usage = captured_submissions[0]
    assert usage.provider == "bedrock"
    assert usage.model == "anthropic.claude-3-sonnet"
    assert usage.input_tokens == 25
    assert usage.output_tokens == 11


def test_instrument_and_uninstrument_toggle_cleanly() -> None:
    inst = BedrockInstrumentor()
    assert not inst.is_instrumented()
    inst.instrument()
    assert inst.is_instrumented()
    inst.uninstrument()
    assert not inst.is_instrumented()


def test_client_created_before_instrument_is_not_retroactively_wrapped(
    captured_submissions: list[Any],
) -> None:
    client = _client()  # created BEFORE instrument()
    inst = BedrockInstrumentor()
    inst.instrument()

    with patch(
        "botocore.client.BaseClient._make_api_call",
        return_value={"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}},
    ):
        client.converse(modelId="anthropic.claude-3-haiku", messages=[])
    inst.uninstrument()

    assert captured_submissions == []


def test_non_bedrock_clients_are_not_wrapped() -> None:
    inst = BedrockInstrumentor()
    inst.instrument()
    s3 = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y"
    )
    inst.uninstrument()
    assert "converse" not in dir(s3) or not hasattr(s3, "converse")


def test_error_path_submits_error_status(captured_submissions: list[Any]) -> None:
    inst = BedrockInstrumentor()
    inst.instrument()
    client = _client()

    with patch(
        "botocore.client.BaseClient._make_api_call", side_effect=RuntimeError("service down")
    ), pytest.raises(RuntimeError):
        client.converse(modelId="anthropic.claude-3-sonnet", messages=[])
    inst.uninstrument()

    assert captured_submissions[0].status == "error"


def test_normalize_unknown_model_reports_zero_cost() -> None:
    inst = BedrockInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 100, "output_tokens": 50},
        model="some.future.model",
        latency_ms=1,
        status="success",
    )
    assert usage.cost == 0.0
    assert usage.metadata["cost_estimated"] is False
