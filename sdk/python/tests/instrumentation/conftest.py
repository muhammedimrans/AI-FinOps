from __future__ import annotations

from typing import Any

import pytest

from costorah.instrumentation._submission import reset_default_client_for_tests


@pytest.fixture(autouse=True)
def _clean_submission_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)
    monkeypatch.delenv("COSTORAH_ENDPOINT", raising=False)
    reset_default_client_for_tests()
    yield
    reset_default_client_for_tests()


@pytest.fixture
def captured_submissions(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Patches costorah.instrumentation._submission.submit everywhere it
    was imported (each provider module does `from ._submission import
    submit`), capturing every ExtractedUsage instead of making an HTTP
    call — no real Costorah client/network is involved in unit tests."""
    captured: list[Any] = []

    def fake_submit(usage: Any, *, client: Any = None) -> bool:
        captured.append(usage)
        return True

    import costorah.instrumentation._openai_compatible as openai_compat
    import costorah.instrumentation.anthropic as anthropic_mod
    import costorah.instrumentation.bedrock as bedrock_mod
    import costorah.instrumentation.cohere as cohere_mod
    import costorah.instrumentation.google as google_mod
    import costorah.instrumentation.mistral as mistral_mod

    modules = [
        openai_compat,
        anthropic_mod,
        google_mod,
        mistral_mod,
        cohere_mod,
        bedrock_mod,
    ]

    try:
        import costorah.instrumentation.langchain as langchain_mod
    except ImportError:
        pass
    else:
        modules.append(langchain_mod)

    for mod in modules:
        monkeypatch.setattr(mod, "submit", fake_submit)

    return captured
