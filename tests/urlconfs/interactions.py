"""The rota page (and one whose context forgot `error`), and every interaction's route included once at the site root."""

from django.urls import include, path

from dj_hx import page
from tests.interactions_app import views


def rota_without_error(request, contest):
    """The rota page from a context that forgot `error`, which the page's notify partial reads."""
    context = {key: value for key, value in views.rota_context(request, contest).items() if key != "error"}
    return page(request, "rota.html", context)


urlpatterns = [
    path("rota/<str:contest>/", views.rota, name="rota"),
    path("rota/<str:contest>/without-error/", rota_without_error),
    path("", include("dj_hx.urls")),
]
