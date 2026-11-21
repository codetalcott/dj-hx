"""
Fixtures. The contact app's hundred contacts are loaded per test, and the
model's sleep is switched off the way the Flask suite does it.
"""

import importlib
import sys
import types
from pathlib import Path

import django
import pytest
from django.test import override_settings
from django.urls import clear_url_caches

from dj_hx.testing import HxTestClient

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_JSON = ROOT / "example" / "contacts" / "contacts.json"
DESK_PAGES = ROOT / "tests" / "desk" / "pages"

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


def locmem(templates=None, *, dirs=(), **options):
    """A TEMPLATES setting serving in-memory templates, for exercising the library directly; ``dirs`` adds files."""
    loaders = [("django.template.loaders.locmem.Loader", {**TEMPLATES_IN_MEMORY, **(templates or {})})]
    if dirs:
        loaders.append("django.template.loaders.filesystem.Loader")
    return _templates(loaders, dirs=dirs, **options)


def on_disk(directory, **options):
    """A TEMPLATES setting reading ``directory``: the start-up checks read template files, which locmem has none of."""
    return _templates(["django.template.loaders.filesystem.Loader"], dirs=[directory], **options)


def _templates(loaders, dirs=(), **options):
    builtins = []
    if django.VERSION < (6, 0):
        # django-template-partials wraps settings.TEMPLATES at startup only, so an
        # overridden setting has to carry its loader and tag library itself.
        loaders = [("template_partials.loader.Loader", loaders)]
        builtins = ["template_partials.templatetags.partials"]
    return [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": list(dirs),
            "OPTIONS": {
                "loaders": loaders,
                "builtins": builtins,
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
def no_interactions():
    """No interactions, as in the example project and the per-area URLconfs; the rota app's are put back after."""
    from dj_hx.interactions import registry

    saved = dict(registry)
    registry.clear()
    yield
    registry.update(saved)


@pytest.fixture
def desk():
    """
    The desk app (tests/desk) as a project would run it: its interactions alone in the registry, routed,
    its pages on disk and its URLconf the root. Returns its handlers module, freshly imported, so its state
    starts over; the rota app's interactions and routes are put back after.
    """
    import dj_hx.urls  # noqa: F401  binds the rota app's routes first, so what is put back is what was routed
    from dj_hx.interactions import bind_routes, registry, urlpatterns

    saved_registry, saved_routes = dict(registry), list(urlpatterns)
    modules = ("tests.desk.handlers", "tests.desk.urls")
    try:
        registry.clear()
        urlpatterns.clear()
        for name in modules:
            sys.modules.pop(name, None)
        handlers = importlib.import_module("tests.desk.handlers")
        bind_routes()
        with override_settings(ROOT_URLCONF="tests.desk.urls", TEMPLATES=on_disk(DESK_PAGES)):
            yield handlers
    finally:
        registry.clear()
        registry.update(saved_registry)
        urlpatterns[:] = saved_routes
        for name in modules:
            sys.modules.pop(name, None)
        clear_url_caches()


@pytest.fixture(scope="module")
def browser():
    """Chromium, for tests marked ``browser``: pip install playwright; playwright install chromium."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with pytest.MonkeyPatch.context() as env:
        # Playwright's sync API runs an event loop in this thread, and Django refuses database work from a
        # thread with a running loop. Test-only, and the reason pytest-django documents this variable for.
        env.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
        with sync_api.sync_playwright() as p:
            b = p.chromium.launch()
            yield b
            b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    page.on("dialog", lambda d: d.accept())
    console_errors = []
    # A 4xx response is logged by the browser as a failed resource; that is the
    # status doing its job, not an error in the page.
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.console_errors = console_errors
    yield page
    context.close()


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
