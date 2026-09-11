"""Views exercising the library directly, one per row of the silent-failure catalogue."""

from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.urls import path

from dj_hx import fragment, invalid, page, redirect, removed, render, text

ITEMS = ["ada", "grace", "linus"]


def index(request):
    return render(request, "index.html", "rows", {"items": ITEMS})


def index_file(request):
    return render(request, "index.html", "rows.html", {"items": ITEMS})


def only_page(request):
    return page(request, "index.html", {"items": ITEMS})


def rows(request):
    return fragment(request, "index.html", "rows", {"items": ITEMS})


def count(request):
    return text(request, "3 items")


def save(request):
    return redirect(request, "/lib/")


def plain_redirect(request):
    return HttpResponseRedirect("/lib/")  # bypassed the verbs


def things(request):
    return removed(request)


def a(request):
    return removed(request)


def b(request):
    return HttpResponse(status=204)


def new(request):
    return invalid(request, "form.html", "form", {"error": "Email Required"})


def x(request):
    return removed(request).trigger("contacts-changed").trigger("count", n=3, target="#count")


def with_partial(request):
    return render(request, "index.html", "rows", {"items": ITEMS}).partial("count")


def bad_partial(request):
    return render(request, "index.html", "rows", {"items": ITEMS}).partial("badcount")


def unknown_partial(request):
    return render(request, "index.html", "rowz", {"items": ITEMS})


def extra(request):
    return fragment(request, "index.html", "extra", {"items": ITEMS, "extra": "processed"})


def flash_removed(request):
    messages.success(request, "Deleted!")
    return removed(request)


def flash_page(request):
    messages.success(request, "Hello")
    return render(request, "index.html", "rows", {"items": ITEMS})


def flash_file(request):
    messages.success(request, "pending")
    response = HttpResponse(b"[]", content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="archive.json"'
    return response


def flash_stream(request):
    messages.success(request, "pending")
    return StreamingHttpResponse([b"<i>streamed</i>"], content_type="text/html")


def plain(request):
    return HttpResponse("plain")


def escaped(request):
    return text(request, "<b>Email Required</b>")


def lint_bad(request):
    return fragment(request, "bad.html")


def lint_warn(request):
    return fragment(request, "warn.html")


def as_json(request):
    return JsonResponse({"hx-get": "not html, not linted"})


def echo(request):
    body = request.POST.get("a") or request.GET.get("a") or ""
    return HttpResponse(
        f"{request.method} hx={request.headers.get('HX-Request')} type={request.headers.get('HX-Request-Type')} "
        f"ct={request.content_type} a={body}"
    )


urlpatterns = [
    path("lib/", index, name="lib-index"),
    path("lib/file/", index_file),
    path("lib/page/", only_page),
    path("lib/rows/", rows),
    path("lib/count/", count),
    path("lib/save/", save),
    path("lib/plain-redirect/", plain_redirect),
    path("lib/things/", things),
    path("lib/a/", a),
    path("lib/b/", b),
    path("lib/new/", new),
    path("lib/x/", x),
    path("lib/with-partial/", with_partial),
    path("lib/bad-partial/", bad_partial),
    path("lib/unknown-partial/", unknown_partial),
    path("lib/extra/", extra),
    path("lib/flash-removed/", flash_removed),
    path("lib/flash-page/", flash_page),
    path("lib/flash-file/", flash_file),
    path("lib/flash-stream/", flash_stream),
    path("lib/plain/", plain),
    path("lib/escaped/", escaped),
    path("lib/lint-bad/", lint_bad),
    path("lib/lint-warn/", lint_warn),
    path("lib/json/", as_json),
    path("lib/echo/", echo),
]
