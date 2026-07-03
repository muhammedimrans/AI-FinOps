from __future__ import annotations

from django.apps import AppConfig


class CostorahDjangoConfig(AppConfig):  # type: ignore[misc]
    name = "costorah.integrations.django"
    # Explicit label: the default (derived from the last path segment,
    # "django") would collide with Django's own "django" app namespace
    # in some app-registry lookups, so this is pinned to something
    # unambiguous.
    label = "costorah_django"
    verbose_name = "COSTORAH"
