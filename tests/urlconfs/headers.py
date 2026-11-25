"""Views that write HX-Trigger by hand, as matorral's do, for checks W024 and W025."""

import json

from django.http import HttpResponse
from django.urls import path


def changed(request):
    response = HttpResponse("")
    response["HX-Trigger"] = '{"issueChanged": true}'
    return response


def saved(request):
    response = HttpResponse("")
    response.headers["HX-Trigger"] = "saved, archived"
    return response


def lead(request):
    return HttpResponse(status=204, headers={"HX-Trigger": json.dumps({"leadUpdated": None})})  # as hypha writes it


urlpatterns = [
    path("h/changed/", changed, name="h-changed"),
    path("h/saved/", saved, name="h-saved"),
    path("h/lead/", lead, name="h-lead"),
]
