"""
CostorahMiddleware — Starlette integration (EP-18.5).

    from starlette.applications import Starlette
    from costorah.integrations.starlette import CostorahMiddleware

    app = Starlette()
    app.add_middleware(CostorahMiddleware)

This is intentionally the exact same class as
`costorah.integrations.fastapi.CostorahMiddleware` — FastAPI *is* a
Starlette application, and the middleware only ever touches Starlette's
`BaseHTTPMiddleware`/`Request`/`Response` types, so there's nothing
FastAPI-specific to duplicate. This module exists purely so plain
Starlette users (and anyone else built directly on Starlette — the
generic ASGI middleware in `costorah.integrations.asgi` also works, but
this reuses the richer request/response-aware implementation) get an
import path matching their framework's name, and so the fact that it's
a re-export is documented rather than accidental.
"""

from __future__ import annotations

from costorah.integrations.fastapi import CostorahMiddleware

__all__ = ["CostorahMiddleware"]
