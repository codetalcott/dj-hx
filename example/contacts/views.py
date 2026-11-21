"""
contact.app, handler-first. Same routes and outcomes as the book's Flask
app; the difference is that every response-side decision is a verb.
"""

from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from dj_hx import fragment, invalid, page, redirect, removed, render, text, wants_page

from .models import Archiver, Contact


def index(request):
    return redirect(request, "contacts")


@require_http_methods(["GET", "DELETE"])
def contacts(request):
    if request.method == "DELETE":
        # DELETE is a query-parameter method in htmx 4; the ids arrive because the
        # button says hx-include="closest form".
        for contact_id in request.GET.getlist("selected_contact_ids"):
            Contact.find(contact_id).delete()
        messages.success(request, "Deleted Contacts!")
        return render(
            request, "index.html", "rows", {"contacts": Contact.all(1), "page": 1, "archiver": Archiver.get()}
        ).trigger("contacts-changed")

    search = request.GET.get("q")
    page_number = int(request.GET.get("page", 1))
    if search is not None:
        contacts_set = Contact.search(search)
    else:
        contacts_set = Contact.all(page_number)
    return render(
        request, "index.html", "rows", {"contacts": contacts_set, "page": page_number, "archiver": Archiver.get()}
    )


@require_http_methods(["GET", "POST", "DELETE"])
def archive(request):
    archiver = Archiver.get()
    if request.method == "POST":
        archiver.run()
    elif request.method == "DELETE":
        archiver.reset()
    return fragment(request, "archive_ui.html", context={"archiver": archiver})


def archive_content(request):
    response = HttpResponse(Archiver.get().archive_content(), content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="archive.json"'
    return response


def contacts_count(request):
    return text(request, f"({Contact.count()} total Contacts)")


@require_http_methods(["GET", "POST"])
def contacts_new(request):
    if request.method == "GET":
        return page(request, "new.html", {"contact": Contact()})
    c = Contact(
        first=request.POST["first_name"],
        last=request.POST["last_name"],
        phone=request.POST["phone"],
        email=request.POST["email"],
    )
    if not c.validate():
        return invalid(request, "new.html", "form", {"contact": c})
    c.save()
    messages.success(request, "Created New Contact!")
    return redirect(request, "contacts")


@require_http_methods(["GET", "DELETE"])
def contacts_view(request, contact_id):
    contact = Contact.find(contact_id)
    if request.method == "DELETE":
        contact.delete()
        messages.success(request, "Deleted Contact!")
        if wants_page(request):  # the edit page's button targets the body
            return redirect(request, "contacts")
        return removed(request)  # a row's link says hx-swap="delete"
    return page(request, "show.html", {"contact": contact})


@require_http_methods(["GET", "POST"])
def contacts_edit(request, contact_id):
    c = Contact.find(contact_id)
    if request.method == "GET":
        return page(request, "edit.html", {"contact": c})
    c.update(request.POST["first_name"], request.POST["last_name"], request.POST["phone"], request.POST["email"])
    if not c.validate():
        return invalid(request, "edit.html", "form", {"contact": c})
    c.save()
    messages.success(request, "Updated Contact!")
    return redirect(request, "contacts_view", contact_id=contact_id)


def contacts_email(request, contact_id):
    c = Contact.find(contact_id)
    c.email = request.GET.get("email", "")
    c.validate()
    return text(request, c.errors.get("email", ""))
