"""
`manage.py costorah_doctor` — the Django-native entry point for the same
checks `costorah doctor` runs from the shell (SDK import, configuration,
connectivity, authentication, framework/provider detection), reusing
`costorah.cli.run_doctor` rather than duplicating its logic. The one
Django-specific addition: `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` are read
from `django.conf.settings` first, falling back to the environment —
matching `costorah.integrations.django.middleware`'s own configuration
precedence.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from costorah.cli import _print_doctor_report, run_doctor


class Command(BaseCommand):  # type: ignore[misc]
    help = (
        "Validate the COSTORAH SDK/Django integration: configuration, connectivity, "
        "authentication, and framework/provider detection."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--timeout", type=float, default=10.0)

    def handle(self, *args: Any, **options: Any) -> None:
        env = dict(os.environ)
        settings_api_key = getattr(settings, "COSTORAH_API_KEY", None)
        settings_endpoint = getattr(settings, "COSTORAH_ENDPOINT", None)
        if settings_api_key:
            env["COSTORAH_API_KEY"] = settings_api_key
        if settings_endpoint:
            env["COSTORAH_ENDPOINT"] = settings_endpoint

        report = run_doctor(env, timeout=options["timeout"])
        _print_doctor_report(report)
        if not report.all_ok:
            raise SystemExit(1)
