"""
Django integration (EP-18.5) — both the middleware and, when added to
`INSTALLED_APPS`, a Django app providing the `costorah_doctor` management
command.

    MIDDLEWARE = [
        ...,
        "costorah.integrations.django.CostorahMiddleware",
    ]

    INSTALLED_APPS = [
        ...,
        "costorah.integrations.django",   # optional — enables `manage.py costorah_doctor`
    ]
"""

from __future__ import annotations

from costorah.integrations.django.middleware import CostorahMiddleware

__all__ = ["CostorahMiddleware"]
