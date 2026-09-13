"""Views for the map tests: the mismatches a Python attribute DSL could not report."""

from django.urls import path

from dj_hx import fragment, navigate, page, redirect, removed


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


def guarded(request):
    if "user" not in request.session:
        return navigate(request, "/login/")
    return page(request, "detail.html")  # the login check must not hide this


def gone(request):
    return navigate(request, "/elsewhere/")  # right for a partial control and a boosted link alike


urlpatterns = [
    path("m/guarded/", guarded, name="m-guarded"),
    path("m/gone/", gone, name="m-gone"),
    path("m/page/", page_view, name="m-page"),
    path("m/detail/", detail, name="m-detail"),
    path("m/rows/", rows, name="m-rows"),
    path("m/items/", items, name="m-items"),
    path("m/go/", go, name="m-go"),
]
