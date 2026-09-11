from contacts import views
from django.urls import path

urlpatterns = [
    path("", views.index, name="index"),
    path("contacts/", views.contacts, name="contacts"),
    path("contacts/archive/", views.archive, name="archive"),
    path("contacts/archive/file/", views.archive_content, name="archive_content"),
    path("contacts/count/", views.contacts_count, name="contacts_count"),
    path("contacts/new/", views.contacts_new, name="contacts_new"),
    path("contacts/<int:contact_id>/", views.contacts_view, name="contacts_view"),
    path("contacts/<int:contact_id>/edit/", views.contacts_edit, name="contacts_edit"),
    path("contacts/<int:contact_id>/email/", views.contacts_email, name="contacts_email"),
]
