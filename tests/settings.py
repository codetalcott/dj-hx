"""The example project's settings for the suite: in-memory database, DEBUG off (as pytest-django runs)."""

from contactapp.settings import *  # noqa: F401,F403

DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
