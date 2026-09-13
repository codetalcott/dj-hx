"""Views for the map tests: the book's idioms that htmx 4 breaks silently, in Django's spelling."""

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path


def contacts(request):
    if request.META.get("HTTP_HX_TRIGGER") == "search":  # htmx 4 sends no HX-Trigger request header
        return render(request, "rows.html")
    return render(request, "index.html")


def panel(request):
    if "HX-Target" in request.headers:
        return HttpResponse("<p>panel</p>")
    return render(request, "index.html")


def delete_all(request):
    if request.method == "DELETE":
        for contact_id in request.POST.getlist("selected_contact_ids"):  # always empty on DELETE
            pass
        return render(request, "index.html")
    if request.method == "POST":
        request.POST.get("name")  # a body read on POST is fine
    return HttpResponse("")


urlpatterns = [
    path("b/contacts/", contacts, name="b-contacts"),
    path("b/panel/", panel, name="b-panel"),
    path("b/delete/", delete_all, name="b-delete"),
]
