"""The example project's settings for the suite: in-memory database, DEBUG off (as pytest-django runs)."""

from contactapp.settings import *  # noqa: F401,F403

DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# The interactions apps: @interaction mints its routes from an installed app's label. The desk's
# interactions are registered only by the `desk` fixture; it is installed for its label and its static
# files (htmx 4.0.2, _hyperscript 0.9.94). Auth, so a test can show @login_required written above
# @interaction applies to the route.
INSTALLED_APPS = [*INSTALLED_APPS, "django.contrib.auth", "tests.interactions_app", "tests.desk"]  # noqa: F405
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405  (a copy: contactapp.settings keeps its own)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.contrib.sessions.middleware.SessionMiddleware") + 1,
    "django.contrib.auth.middleware.AuthenticationMiddleware",
)
