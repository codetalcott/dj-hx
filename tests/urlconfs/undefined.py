"""Views for HxTestClient's undefined-variable check: each renders a template tests/test_undefined_variables.py names."""

import threading

from asgiref.sync import sync_to_async
from contacts.models import Contact
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


class Holder:
    name = "holder"
    rel = None  # an optional object that is not there: a nullable foreign key, say


def show(request, name):
    return page(
        request,
        name,
        {
            "items": ITEMS,
            "user": NoProfile(),
            "holder": Holder(),
            "contact": Contact(first="Ada"),
            "labels": {"name": "Name"},
            "empty": [],
            "pair": ("a", "b"),
            "nothing_yet": Contact.objects.none(),
        },
    )


async def asynchronous(request):
    """An async view: Django runs it on an event loop in another thread, in a copy of the request's context."""
    return page(request, "loose.html", {"items": ITEMS})


def broken(request):
    raise RuntimeError("broken")


def box(request):
    return fragment(request, "parts.html", "box", {})


def from_string(request):
    return HttpResponse(Template("{% if nope %}x{% endif %}ok").render(Context()))


def outside(request):
    """A Variable resolved on a Context, in no template: Django logs its failure all the same."""
    try:
        Variable("nope").resolve(Context())  # a top-level name, which would count inside a template
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


def nested_then_miss(request):
    """Another client's request inside this one, then this request's own render, which reads a name nobody supplies."""
    inner = HxTestClient(strict=False).get("/u/show/loose.html")
    return page(request, "after_inner.html", {"items": inner.hx_findings[0].lookups})


async def nested_async_then_miss(request):
    """The same from an async view, its inner client run through sync_to_async."""
    inner = await sync_to_async(HxTestClient(strict=False).get)("/u/show/loose.html")
    return page(request, "after_inner.html", {"items": inner.hx_findings[0].lookups})


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
    path("u/async/", asynchronous),
    path("u/broken/", broken),
    path("u/nested/", nested),
    path("u/nested-then-miss/", nested_then_miss),
    path("u/nested-async-then-miss/", nested_async_then_miss),
    path("u/elsewhere/", elsewhere),
]
