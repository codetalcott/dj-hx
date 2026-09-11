"""contact.app on Django, handler-first: the settings dj-hx needs are the last four."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "hypermedia rocks"  # a demo key for the example; generate a real one for anything else
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dj_hx",
    "contacts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "dj_hx.middleware.HxMiddleware",  # after MessageMiddleware: it bridges pending messages into fragments
]

ROOT_URLCONF = "contactapp.urls"
WSGI_APPLICATION = "contactapp.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

# dj-hx ----------------------------------------------------------------------
# Pending messages on a fragment response are rendered through this partial and
# appended as <hx-partial>; its root element is id="messages".
HX_MESSAGES_TEMPLATE = "layout.html#messages"
# Extensions loaded by the pages, for the lint (also detected from <script src>).
HX_EXTENSIONS = ("hx-live",)
