"""Fragments carrying a project's own hx-* attribute, which a script in another template reads (hypha's hx-noprog)."""

from django.urls import path

from dj_hx import fragment


def button(request):
    return fragment(request, "button.html")


def typo(request):
    return fragment(request, "typo.html")


urlpatterns = [path("button/", button), path("typo/", typo)]
