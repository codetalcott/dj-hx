"""The desk page, and every interaction's route included once at the site root."""

from django.urls import include, path

from tests.desk import handlers

urlpatterns = [
    path("desk/", handlers.desk, name="desk"),
    path("", include("dj_hx.urls")),
]
