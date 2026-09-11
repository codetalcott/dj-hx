"""
Fixtures. The contact app's hundred contacts are loaded per test, and the
model's sleep is switched off the way the Flask suite does it.
"""

import types
from pathlib import Path

import pytest
from django.test import override_settings

from dj_hx.testing import HxTestClient

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_JSON = ROOT / "example" / "contacts" / "contacts.json"

PARTIAL = {"HTTP_HX_REQUEST": "true", "HTTP_HX_REQUEST_TYPE": "partial", "HTTP_ACCEPT": "text/html"}
FULL = {"HTTP_HX_REQUEST": "true", "HTTP_HX_REQUEST_TYPE": "full", "HTTP_ACCEPT": "text/html"}

LAYOUT = """<!doctype html><html><head><script src="/static/js/htmx-4.0.0.js"></script></head><body hx-boost:inherited="true">
{% partialdef messages inline %}<div id="messages">{% for m in messages %}<p class="flash">{{ m }}</p>{% endfor %}</div>{% endpartialdef %}
{% block content %}{% endblock %}
</body></html>"""

INDEX = """{% extends "layout.html" %}{% block content %}
<table><tbody>{% partialdef rows inline %}{% for item in items %}<tr><td>{{ item }}</td></tr>{% endfor %}{% endpartialdef %}</tbody></table>
{% partialdef count inline %}<span id="count">{{ items|length }}</span>{% endpartialdef %}
{% partialdef badcount inline %}<span class="count">{{ items|length }}</span>{% endpartialdef %}
{% partialdef extra inline %}<i>{{ extra }} {{ request.method }}</i>{% endpartialdef %}
{% endblock %}"""

FORM = """{% extends "layout.html" %}{% block content %}
{% partialdef form inline %}<form id="form"><span class="error">{{ error }}</span></form>{% endpartialdef %}
{% endblock %}"""

ROWS_FILE = """{% for item in items %}<tr><td>{{ item }}</td></tr>{% endfor %}"""
BAD = '<div hx-get="/x" hx-swap="outerhtml"></div>'
WARN = '<div hx-target="#t"><button hx-post="/a">a</button></div>'

TEMPLATES_IN_MEMORY = {"layout.html": LAYOUT, "index.html": INDEX, "form.html": FORM, "rows.html": ROWS_FILE, "bad.html": BAD, "warn.html": WARN}


def locmem(templates=None, **options):
    """A TEMPLATES setting serving in-memory templates, for exercising the library directly."""
    return [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "OPTIONS": {
                "loaders": [("django.template.loaders.locmem.Loader", {**TEMPLATES_IN_MEMORY, **(templates or {})})],
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.messages.context_processors.messages",
                ],
                **options,
            },
        }
    ]


@pytest.fixture
def lib(request):
    """Library tests: the tests.urlconfs.lib URLconf and in-memory templates."""
    with override_settings(ROOT_URLCONF="tests.urlconfs.lib", TEMPLATES=locmem()):
        yield


@pytest.fixture
def client():
    return HxTestClient()


@pytest.fixture
def contacts(db, monkeypatch):
    """The book's contact app: database loaded, archiver idle, sleeps off."""
    from contacts import models

    monkeypatch.setattr(models, "time", types.SimpleNamespace(sleep=lambda s: None))
    models.Contact.load_from_json(CONTACTS_JSON)
    models.Archiver.archive_status = "Waiting"
    models.Archiver.archive_progress = 0
    return models
