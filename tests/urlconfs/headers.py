"""
Views that write HX-Trigger by hand, as matorral's and hypha's do, or through django-htmx's trigger_client_event (a
stand-in with its signature: the map reads the call, and the view never runs), for checks W024 and W025.
"""

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


def trigger_client_event(response, name, params=None, *, after="receive"):
    return response


def task_done(request):
    return trigger_client_event(HttpResponse(""), "taskListUpdated", {})  # as hypha's todo view does


def dashboard(request):
    # HX-Trigger-After-Settle, which htmx 4.0.2 does not read: matorral's dashboard-updated
    return trigger_client_event(HttpResponse(""), "dashboardUpdated", after="settle")


def lead(request):
    return HttpResponse(status=204, headers={"HX-Trigger": json.dumps({"leadUpdated": None})})  # as hypha writes it


urlpatterns = [
    path("h/changed/", changed, name="h-changed"),
    path("h/saved/", saved, name="h-saved"),
    path("h/lead/", lead, name="h-lead"),
    path("h/task/", task_done, name="h-task"),
    path("h/dashboard/", dashboard, name="h-dashboard"),
]
