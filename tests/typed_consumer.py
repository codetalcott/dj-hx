"""
README's idioms, type-checked as a project would check its own views against dj-hx.

CI's lint job runs ``mypy --strict --follow-imports=silent tests/typed_consumer.py``: strict here, and
dj-hx's own modules analysed but not reported, as a project's mypy treats an installed package. A verb or
response method that hands the project ``Any`` fails it (``no-any-return``), and so does an unannotated
one (``no-untyped-call``). pytest never imports this file (no ``test_`` prefix).
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse

from dj_hx import (
    current_url,
    fragment,
    interaction,
    invalid,
    is_htmx,
    navigate,
    page,
    redirect,
    removed,
    render,
    text,
    wants_fragment,
    wants_page,
)
from dj_hx.testing import HxTestClient, assert_no_hx_check_issues, hx_check_messages


def contacts(request: HttpRequest) -> HttpResponse:
    return render(request, "index.html", "rows", {"contacts": []}).trigger("contacts-changed")


def contacts_view(request: HttpRequest, contact_id: int) -> HttpResponse:
    if request.method == "DELETE":
        if wants_page(request):
            return redirect(request, "contacts")
        return removed(request).trigger("contacts-changed", target="#count", n=3)
    return page(request, "show.html", {"contact": contact_id})


def archive(request: HttpRequest) -> HttpResponse:
    response = fragment(request, "index.html", "rows", {"contacts": []}).partial("count")
    return response.push_url("/contacts/").replace_url("/contacts/").with_status(200)


def contacts_new(request: HttpRequest) -> HttpResponse:
    return invalid(request, "new.html", "form", {"form": None})


def escape_hatches(request: HttpRequest) -> HttpResponse:
    return render(request, "index.html", "rows").retarget("#rows").reswap("outerHTML")


def login_check(request: HttpRequest) -> HttpResponse:
    return navigate(request, "login")


def contacts_count(request: HttpRequest) -> HttpResponse:
    if is_htmx(request) and wants_fragment(request) and current_url(request) is not None:
        return text(request, "(3 total)")
    return text(request, 3)


def assign_context(request: HttpRequest, contest: str) -> dict[str, Any]:
    return {"contest": contest, "notified": False, "error": None}


@interaction("POST", partial="contests/assign.html#notify", context=assign_context, refuses=(ValueError,), triggers=("notified",))
def notify(request: HttpRequest, contest: str, member: int) -> dict[str, Any]:
    return {"notified": True}


def test_contacts() -> None:
    client = HxTestClient(strict=True, lint_ignore=("duplicate-id",))
    assert client.hx_get("/contacts/").status_code == 200
    assert client.hx_post("/contacts/new/", {"first": "Ada"}, full=True, follow=True).status_code == 200
    assert client.hx_delete("/contacts/3/", full=True, follow=False).status_code == 303
    assert client.hx_put("/contacts/3/", json={"first": "Ada"}).status_code == 200
    assert client.hx_patch("/contacts/3/").status_code == 200
    assert not hx_check_messages(include_warnings=False)
    assert_no_hx_check_issues()
