"""The ported contact.app, exercised the way htmx 4 and a browser would (hx-flask's test_contact_app.py)."""

import json
from pathlib import Path

import pytest

from dj_hx import HxFragmentIntoPage, HxPageIntoFragment

pytestmark = pytest.mark.usefixtures("contacts")


def test_index_redirects_to_contacts(client):
    r = client.get("/")
    assert (r.status_code, r["Location"]) == (303, "/contacts/")


def test_contacts_page_for_browsers_and_boosted_links(client):
    for r in (client.get("/contacts/"), client.hx_get("/contacts/", full=True)):
        body = r.content.decode()
        assert r.status_code == 200
        assert 'hx-boost:inherited="true"' in body
        assert body.count("<tr>") == 12  # header, ten rows, the Load More sentinel
        assert 'hx-get="/contacts/?page=2"' in body
        assert "hx-select" not in body


def test_search_and_paging_get_rows_only(client):
    body = client.hx_get("/contacts/?q=a").content.decode()
    assert "<html" not in body and "<table" not in body and "<tr>" in body

    body = client.hx_get("/contacts/?page=2").content.decode()
    assert body.count("<tr>") == 11 and 'hx-get="/contacts/?page=3"' in body


def test_row_delete_removes_and_flashes_in_place(client):
    r = client.hx_delete("/contacts/3/")
    body = r.content.decode()
    assert r.status_code == 200
    assert body.startswith('\n<hx-partial hx-target="#messages" hx-swap="outerHTML">')
    assert '<div class="flash">Deleted Contact!</div>' in body
    assert "<tr>" not in body
    assert b'value="3"' not in client.hx_get("/contacts/").content


def test_edit_page_delete_redirects_to_the_list_with_the_flash(client):
    r = client.hx_delete("/contacts/3/", full=True, follow=False)
    assert (r.status_code, r["Location"]) == (303, "/contacts/")
    page = client.hx_get("/contacts/", full=True).content.decode()
    assert '<div class="flash">Deleted Contact!</div>' in page


def test_bulk_delete_rerenders_rows_and_announces(client):
    r = client.hx_delete("/contacts/?selected_contact_ids=1&selected_contact_ids=2")
    body = r.content.decode()
    assert r.status_code == 200
    assert json.loads(r["HX-Trigger"]) == {"contacts-changed": {"target": "body"}}
    assert "<tr>" in body and 'value="1"' not in body and 'value="2"' not in body
    assert "Deleted Contacts!" in body


def test_new_contact_validation_is_422(client):
    form = {"first_name": "A", "last_name": "B", "phone": "1", "email": ""}
    r = client.hx_post("/contacts/new/", form, full=True)
    assert r.status_code == 422 and b"<html" in r.content and b"Email Required" in r.content
    r = client.hx_post("/contacts/new/", form)
    assert r.status_code == 422 and b"<html" not in r.content and r.content.strip().startswith(b'<form id="form"')


def test_new_contact_success_redirects_and_flashes(client):
    form = {"first_name": "A", "last_name": "B", "phone": "1", "email": "ab@example.com"}
    r = client.hx_post("/contacts/new/", form, full=True, follow=False)
    assert (r.status_code, r["Location"]) == (303, "/contacts/")
    assert b"Created New Contact!" in client.get("/contacts/").content


def test_edit_saves_and_redirects_to_the_contact(client):
    form = {"first_name": "Z", "last_name": "B", "phone": "1", "email": "zb@example.com"}
    r = client.hx_post("/contacts/5/edit/", form, full=True, follow=False)
    assert (r.status_code, r["Location"]) == (303, "/contacts/5/")
    assert b"<h1>Z B</h1>" in client.get("/contacts/5/").content


def test_pages_refuse_to_answer_partial_requests(client):
    with pytest.raises(HxPageIntoFragment):
        client.hx_get("/contacts/5/")
    with pytest.raises(HxPageIntoFragment):
        client.hx_get("/contacts/new/")


def test_email_validation_and_count_are_text_fragments(client):
    assert client.hx_get("/contacts/5/email/?email=").content == b"Email Required"
    assert client.hx_get("/contacts/count/").content == b"(100 total Contacts)"
    with pytest.raises(HxFragmentIntoPage):
        client.hx_get("/contacts/count/", full=True)


def test_archive_states_render_as_fragments(client, contacts, monkeypatch):
    archiver = contacts.Archiver
    monkeypatch.setattr(archiver, "run", lambda self: setattr(archiver, "archive_status", "Running"))
    body = client.hx_get("/contacts/archive/").content.decode()
    assert "Download Contact Archive" in body and 'hx-target="#archive-ui"' in body
    body = client.hx_post("/contacts/archive/").content.decode()
    assert "Creating Archive" in body and 'hx-trigger="load delay:500ms"' in body
    archiver.archive_status = "Complete"
    body = client.hx_get("/contacts/archive/").content.decode()
    assert 'hx-on:load="this.click()"' in body
    body = client.hx_delete("/contacts/archive/").content.decode()
    assert "Download Contact Archive" in body


def test_archive_download_passes_through_untouched(client):
    r = client.hx_get("/contacts/archive/file/")
    assert r.status_code == 200 and r["Content-Disposition"].startswith("attachment")
    assert json.loads(r.content)[0]["id"] == 1


def test_every_control_names_its_view():
    """The templates use {% url %}, so a search for a URL name finds every caller."""
    for path in (Path(__file__).resolve().parent.parent / "example" / "contacts" / "templates").glob("*.html"):
        text = path.read_text()
        assert 'hx-get="/' not in text and 'hx-post="/' not in text and 'hx-delete="/' not in text, path.name


def test_the_contact_app_pages_lint_clean(client):
    """HxTestClient raises on an error-level finding; warnings are checked here."""
    for url, full in (("/contacts/", True), ("/contacts/1/edit/", True), ("/contacts/new/", True), ("/contacts/1/", True), ("/contacts/?q=a", False), ("/contacts/archive/", False)):
        r = client.hx_get(url, full=full)
        assert [f for f in r.hx_lint if f.severity != "info"] == [], url
