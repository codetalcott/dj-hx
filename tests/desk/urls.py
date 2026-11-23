"""The desk page, and every interaction's route included once at the site root."""

from django.urls import include, path

from tests.desk import handlers

urlpatterns = [
    path("desk/", handlers.desk, name="desk"),
    path("desk/drop/bare/", handlers.drop_bare, name="desk_drop_bare"),
    path("desk/drop/targeted/", handlers.drop_targeted, name="desk_drop_targeted"),
    path("", include("dj_hx.urls")),
]
