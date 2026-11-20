"""The rota page, and every interaction's route included once at the site root."""

from django.urls import include, path

from tests.interactions_app import views

urlpatterns = [
    path("rota/<str:contest>/", views.rota, name="rota"),
    path("", include("dj_hx.urls")),
]
