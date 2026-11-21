"""Views for HxTestClient's undefined-variable check: each renders a template tests/test_undefined_variables.py names."""

import threading

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.template import Context, Template, Variable, VariableDoesNotExist
from django.template.loader import get_template
from django.urls import path

from dj_hx import fragment, page
from dj_hx.testing import HxTestClient

ITEMS = ["ada", "grace", "linus"]


class NoProfile:
    @property
    def profile(self):
        raise ObjectDoesNotExist("no profile")  # a template lookup Django silences (silent_variable_failure)


def show(request, name):
    return page(request, name, {"items": ITEMS, "user": NoProfile()})


def box(request):
    return fragment(request, "parts.html", "box", {})


def from_string(request):
    return HttpResponse(Template("{% if nope %}x{% endif %}ok").render(Context()))


def outside(request):
    """A Variable resolved on a plain dict, in no template: Django logs its failure all the same."""
    try:
        Variable("nope").resolve({})
    except VariableDoesNotExist:
        pass
    return page(request, "clean.html", {"items": ITEMS})


def boom(request):
    get_template("loose.html").render({})  # lookups fail, then the view raises
    raise ValueError("boom")


def nested(request):
    """A request that runs another through a second client, and renders how many lookups that one found."""
    inner = HxTestClient(strict=False).get("/u/show/loose.html")
    found = inner.hx_findings[0].lookups if inner.hx_findings else []
    return page(request, "clean.html", {"items": found})


def elsewhere(request):
    """A render on another thread while this request runs, as a live server's thread renders during a test."""
    thread = threading.Thread(target=lambda: get_template("loose.html").render({}))
    thread.start()
    thread.join()
    return page(request, "clean.html", {"items": ITEMS})


urlpatterns = [
    path("u/show/<str:name>", show),
    path("u/box/", box),
    path("u/from-string/", from_string),
    path("u/outside/", outside),
    path("u/boom/", boom),
    path("u/nested/", nested),
    path("u/elsewhere/", elsewhere),
]
