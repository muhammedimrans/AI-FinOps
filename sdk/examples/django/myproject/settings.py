"""Minimal Django settings for the COSTORAH example app — not production
configuration (SQLite, DEBUG=True, a throwaway SECRET_KEY)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-costorah-example-only"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    # Registers the `manage.py costorah_doctor` management command.
    "costorah.integrations.django",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # The entire integration — one line.
    "costorah.integrations.django.CostorahMiddleware",
]

ROOT_URLCONF = "myproject.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

USE_TZ = True

# Read from the environment — see .env.example. Set these instead of
# hardcoding real credentials in settings.py.
COSTORAH_API_KEY = os.environ.get("COSTORAH_API_KEY")
COSTORAH_ENDPOINT = os.environ.get("COSTORAH_ENDPOINT", "https://api.costorah.com")
