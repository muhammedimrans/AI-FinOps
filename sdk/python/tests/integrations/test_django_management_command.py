from __future__ import annotations

import httpx
import pytest

django = pytest.importorskip("django")

from django.conf import settings  # noqa: E402

if not settings.configured:
    settings.configure(
        DEBUG=True,
        ALLOWED_HOSTS=["testserver"],
        SECRET_KEY="test-secret-key",
        DATABASES={},
        USE_TZ=True,
        INSTALLED_APPS=["costorah.integrations.django"],
    )
    django.setup()

from django.core.management import call_command  # noqa: E402

from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    reset_default_client_for_tests()
    yield
    reset_default_client_for_tests()


def test_costorah_doctor_command_is_registered(capsys: pytest.CaptureFixture[str]) -> None:
    """Confirms the app config's management command is discoverable —
    the real proof that costorah.integrations.django is wired up as a
    proper Django app, not just a plain module."""
    with pytest.raises(SystemExit):
        call_command("costorah_doctor", "--timeout=0.2")
    output = capsys.readouterr().out
    assert "Configuration" in output


def test_costorah_doctor_command_reads_api_key_from_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The management command must pass through a settings-configured
    COSTORAH_API_KEY (not just the environment) to run_doctor — proven
    here by checking the Configuration check passes even though the
    real env var is deliberately unset."""
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)
    monkeypatch.setattr(
        settings, "COSTORAH_API_KEY", "costorah_live_from_settings", raising=False
    )

    from costorah.client import Costorah

    real_init = Costorah.__init__

    def patched_init(self: Costorah, *args: object, **kwargs: object) -> None:
        kwargs["_transport"] = httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "success": True,
                    "usage_id": "u1",
                    "request_id": "r1",
                    "processed_at": "2026-01-01T00:00:00Z",
                    "duplicate": False,
                },
            )
        )
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(Costorah, "__init__", patched_init)

    call_command("costorah_doctor")
    output = capsys.readouterr().out
    assert "COSTORAH_API_KEY is set and well-formed" in output
