#!/usr/bin/env python
"""Django's management-command entry point — standard boilerplate."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install it with `pip install django`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
