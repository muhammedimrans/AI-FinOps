from __future__ import annotations

import httpx
import pytest

from costorah import cli
from costorah.client import Costorah
from costorah.version import __version__


def test_run_version() -> None:
    assert cli.run_version() == f"costorah {__version__}"


def test_run_config_masks_api_key() -> None:
    result = cli.run_config({"COSTORAH_API_KEY": "costorah_live_abcdefghijklmnopqrstuvwxyz"})
    assert result["api_key_set"] is True
    assert result["api_key"].startswith("costorah_live_")
    assert "abcdefghijklmnopqrstuvwxyz" not in result["api_key"]
    assert result["api_key"].endswith("wxyz")


def test_run_config_reports_unset_key() -> None:
    result = cli.run_config({})
    assert result["api_key_set"] is False
    assert result["api_key"] == "<not set>"
    assert result["endpoint"] == "https://api.costorah.com"


def test_run_config_custom_endpoint() -> None:
    result = cli.run_config({"COSTORAH_ENDPOINT": "https://staging.costorah.com"})
    assert result["endpoint"] == "https://staging.costorah.com"


def test_run_init_without_api_key_flags_it_as_a_next_step() -> None:
    report = cli.run_init({})
    assert report.api_key_configured is False
    assert any("COSTORAH_API_KEY" in step for step in report.next_steps)


def test_run_init_with_api_key_configured() -> None:
    report = cli.run_init({"COSTORAH_API_KEY": "costorah_live_x"})
    assert report.api_key_configured is True


def test_run_init_detects_installed_providers_and_frameworks() -> None:
    # openai and fastapi are installed in this dev environment (pyproject
    # dev extras) — a real, not mocked, detection.
    report = cli.run_init({})
    assert "openai" in report.detected_providers
    assert "fastapi" in report.detected_frameworks


def test_run_doctor_missing_api_key_skips_connectivity() -> None:
    report = cli.run_doctor({})
    by_name = {c.name: c for c in report.checks}
    assert by_name["SDK import"].ok is True
    assert by_name["Configuration"].ok is False
    assert by_name["Connectivity"].ok is False
    assert "skipped" in by_name["Connectivity"].detail
    assert by_name["Authentication"].ok is False
    assert report.all_ok is False


def test_run_doctor_malformed_api_key_fails_configuration() -> None:
    report = cli.run_doctor({"COSTORAH_API_KEY": "sk-not-costorah-prefixed"})
    by_name = {c.name: c for c in report.checks}
    assert by_name["Configuration"].ok is False


def test_run_doctor_successful_delivery_confirms_connectivity_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "r1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    real_init = Costorah.__init__

    def spy_init(self: Costorah, *args: object, **kwargs: object) -> None:
        kwargs["_transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Costorah, "__init__", spy_init)

    report = cli.run_doctor({"COSTORAH_API_KEY": "costorah_live_x"}, timeout=5)
    by_name = {c.name: c for c in report.checks}
    assert by_name["Connectivity"].ok is True
    assert by_name["Authentication"].ok is True
    assert report.all_ok is True


def test_run_doctor_permanent_rejection_confirms_connectivity_but_fails_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid key"})

    real_init = Costorah.__init__

    def spy_init(self: Costorah, *args: object, **kwargs: object) -> None:
        kwargs["_transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Costorah, "__init__", spy_init)

    report = cli.run_doctor({"COSTORAH_API_KEY": "costorah_live_x"}, timeout=5)
    by_name = {c.name: c for c in report.checks}
    assert by_name["Connectivity"].ok is True
    assert by_name["Authentication"].ok is False
    assert report.all_ok is False


def test_run_doctor_unreachable_endpoint_does_not_falsely_confirm_connectivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A network error is retried indefinitely (retry_count > 0) — the
    doctor must not misclassify a still-retrying transient failure as a
    confirmed connectivity+bad-auth outcome."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    real_init = Costorah.__init__

    def spy_init(self: Costorah, *args: object, **kwargs: object) -> None:
        kwargs["_transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Costorah, "__init__", spy_init)

    report = cli.run_doctor({"COSTORAH_API_KEY": "costorah_live_x"}, timeout=2)
    by_name = {c.name: c for c in report.checks}
    assert by_name["Connectivity"].ok is False
    assert by_name["Authentication"].ok is False


def test_run_health_without_api_key_returns_error() -> None:
    result = cli.run_health({})
    assert "error" in result


def test_run_health_returns_live_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "r1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    real_init = Costorah.__init__

    def spy_init(self: Costorah, *args: object, **kwargs: object) -> None:
        kwargs["_transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Costorah, "__init__", spy_init)

    result = cli.run_health({"COSTORAH_API_KEY": "costorah_live_x"})
    # health() is snapshotted while the worker is still running, before
    # run_health()'s own shutdown() cleanup.
    assert result["worker"] == "running"
    assert "queue_stats" in result
    assert set(result.keys()) >= {"worker", "queue_depth", "retry_queue", "circuit", "compression"}


def test_build_parser_requires_a_subcommand() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_main_version(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["version"])
    assert exit_code == 0
    assert __version__ in capsys.readouterr().out


def test_main_config(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["config"])
    assert exit_code == 0
    assert "endpoint" in capsys.readouterr().out


def test_main_doctor_returns_nonzero_on_failure(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)
    exit_code = cli.main(["doctor"])
    assert exit_code == 1
    assert "Configuration" in capsys.readouterr().out
