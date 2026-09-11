"""Views for the map tests: the mismatches a Python attribute DSL could not report."""

from django.urls import path

from dj_hx import fragment, page, redirect, removed


def page_view(request):
    return page(request, "page.html")


def detail(request):
    return page(request, "detail.html")


def rows(request):
    return fragment(request, "page.html", "content").trigger("nobody-listens")


def items(request):
    if request.method == "DELETE":
        ids = request.GET.getlist("id")  # noqa: F841
        return removed(request)
    return page(request, "page.html")


def go(request):
    return redirect(request, "/")


urlpatterns = [
    path("m/page/", page_view, name="m-page"),
    path("m/detail/", detail, name="m-detail"),
    path("m/rows/", rows, name="m-rows"),
    path("m/items/", items, name="m-items"),
    path("m/go/", go, name="m-go"),
]
