"""
CostorahExtension — Flask integration (EP-18.5).

    from flask import Flask
    from costorah.integrations.flask import CostorahExtension

    app = Flask(__name__)
    CostorahExtension(app)

Also supports the application-factory pattern:

    ext = CostorahExtension()

    def create_app():
        app = Flask(__name__)
        ext.init_app(app)
        return app

With `COSTORAH_API_KEY` set in the environment, this is the entire
integration — no other setup. Internally it wraps `app.wsgi_app` with
`costorah.integrations.wsgi.CostorahWSGIMiddleware` (no duplicate
request-context logic), so it inherits that middleware's behavior
exactly: auto-init from `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT`, request
context capture (request ID, path, method, organization ID), and an
echoed `X-Costorah-Request-Id` response header.

Because the wrapping happens at the WSGI level (below Flask's routing),
it works uniformly across blueprints (a blueprint's routes are still
served through the same `app.wsgi_app`) and across multiple, independent
`Flask` app instances (each gets its own `CostorahExtension`/wrapped
`wsgi_app` and, if constructed with an explicit `client=`, its own
`Costorah` client) — the one piece of state that *is* process-global is
`costorah.instrumentation`'s "default client" (see
`costorah.instrumentation.set_default_client`), same as the FastAPI/
Starlette integrations: if two apps in the same process both auto-init
from `COSTORAH_API_KEY`, the instrumentation default client is whichever
app initialized last. Pass an explicit `client=` per app to avoid this
when running multiple apps with different credentials in one process.
"""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING, Any

from costorah._logging import get_logger
from costorah.integrations._common import check_min_version
from costorah.integrations.wsgi import CostorahWSGIMiddleware

if TYPE_CHECKING:
    from flask import Flask

    from costorah.client import Costorah

try:
    import flask as _flask_module  # noqa: F401 - import error is the actual check
except ImportError as exc:  # pragma: no cover - exercised only without flask installed
    raise ImportError(
        "costorah.integrations.flask requires 'flask' to be installed. "
        "Install it with `pip install flask` to use this integration."
    ) from exc

_log = get_logger(__name__)

_MIN_FLASK_VERSION = (2, 0)


class CostorahExtension:
    def __init__(
        self,
        app: Flask | None = None,
        *,
        api_key: str | None = None,
        client: Costorah | None = None,
        organization_id: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._organization_id = organization_id
        self.middleware: CostorahWSGIMiddleware | None = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Wires this extension onto a Flask app instance. Safe to call
        once per app — supports both `CostorahExtension(app)` and the
        deferred application-factory pattern (`ext.init_app(app)`)."""
        installed_version = importlib.metadata.version("flask")
        warning = check_min_version(installed_version, _MIN_FLASK_VERSION, framework_name="Flask")
        if warning:
            _log.warning(warning)

        self.middleware = CostorahWSGIMiddleware(
            app.wsgi_app,
            api_key=self._api_key,
            client=self._client,
            organization_id=self._organization_id,
        )
        app.wsgi_app = self.middleware  # type: ignore[method-assign]

        extensions: dict[str, Any] = getattr(app, "extensions", None) or {}
        extensions["costorah"] = self
        app.extensions = extensions
