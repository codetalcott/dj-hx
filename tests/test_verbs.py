"""
The verbs, one section per row of the design's silent-failure catalogue. Each
test seeds the failure a Django app could contain and asserts that it is loud,
or cannot be represented. Same cases as hx-flask's tests/test_hx.py.
"""

import json
import re

import pytest
from django.test import override_settings

from dj_hx import (
    HxFragmentIntoPage,
    HxMessagesUnconfigured,
    HxNoSwap,
    HxPageIntoFragment,
    HxPartialRootId,
    HxProtocolError,
    HxRedirectIntoFragment,
    HxUnknownPartial,
)
from dj_hx.testing import HxTestClient
from dj_hx.verbs import check_root_id

pytestmark = pytest.mark.usefixtures("lib")


# ------------------------------------------------ full page into a fragment target


def test_render_negotiates_on_request_type(client):
    assert b"<html>" in client.get("/lib/").content  # a browser
    assert b"<html>" in client.hx_get("/lib/", full=True).content  # a boosted link
    body = client.hx_get("/lib/").content  # a control targeting tbody
    assert b"<html>" not in body
    assert body.count(b"<tr>") == 3


def test_render_accepts_a_template_file_as_the_partial(client):
    assert client.hx_get("/lib/file/").content.count(b"<tr>") == 3


def test_page_raises_when_the_request_targets_an_element(client):
    assert client.get("/lib/page/").status_code == 200
    assert client.hx_get("/lib/page/", full=True).status_code == 200
    with pytest.raises(HxPageIntoFragment, match=r"only_page\(\) renders the page index.html"):
        client.hx_get("/lib/page/")


# ------------------------------------------ bare fragment into a boosted request


def test_fragment_is_loud_when_htmx_asked_for_a_page(client):
    assert client.hx_get("/lib/rows/").content.count(b"<tr>") == 3
    assert client.get("/lib/rows/").status_code == 200  # a browser or curl may fetch a fragment
    with pytest.raises(HxFragmentIntoPage, match=r"rows\(\) answers a boosted"):
        client.hx_get("/lib/rows/", full=True)
    with pytest.raises(HxFragmentIntoPage):
        client.hx_get("/lib/count/", full=True)


# ------------------------------------------------- redirect followed into a fragment


def test_redirect_is_a_plain_303_and_refuses_partial_requests(client):
    r = client.post("/lib/save/")
    assert (r.status_code, r["Location"]) == (303, "/lib/")
    r = client.hx_post("/lib/save/", full=True, follow=False)
    assert r.status_code == 303 and "HX-Location" not in r
    with pytest.raises(HxRedirectIntoFragment, match=r"save\(\) redirects to /lib/"):
        client.hx_post("/lib/save/")


def test_guard_catches_a_plain_django_redirect(client):
    with pytest.raises(HxRedirectIntoFragment, match="answered a request that targets an element with a 302"):
        client.hx_post("/lib/plain-redirect/")


def test_guard_names_an_append_slash_redirect(client):
    with pytest.raises(HxRedirectIntoFragment, match="got a redirect from APPEND_SLASH.*'/lib/things'"):
        client.hx_delete("/lib/things")


def test_guard_logs_instead_of_raising_when_not_strict(caplog):
    with caplog.at_level("WARNING", logger="dj_hx"):
        r = HxTestClient(strict=False).hx_post("/lib/plain-redirect/")
    assert r.status_code == 302  # logged, not raised, so the redirect went out
    assert sum("answered a request that targets an element" in m for m in caplog.messages) == 1


# ------------------------------------------------------------- delete outcomes


def test_removed_is_an_empty_200_and_204_is_loud(client):
    r = client.hx_delete("/lib/a/")
    assert (r.status_code, r.content) == (200, b"")
    with pytest.raises(HxNoSwap, match=r"b\(\) answered a request that targets an element with a 204"):
        client.hx_delete("/lib/b/")


# ------------------------------------------------------------ validation errors


def test_invalid_is_422_as_page_or_partial(client):
    r = client.hx_post("/lib/new/", full=True)
    assert r.status_code == 422 and b"<html>" in r.content and b"Email Required" in r.content
    r = client.hx_post("/lib/new/")
    assert r.status_code == 422 and b"<html>" not in r.content and r.content.strip().startswith(b'<form id="form">')


# --------------------------------------------------------------------- events


def test_trigger_always_names_a_target(client):
    r = client.hx_delete("/lib/x/")
    assert json.loads(r["HX-Trigger"]) == {
        "contacts-changed": {"target": "body"},
        "count": {"target": "#count", "n": 3},
    }


# ------------------------------------------------------------------- partials


def test_partial_appends_the_partial_as_an_hx_partial(client):
    body = client.hx_get("/lib/with-partial/").content.decode()
    assert body.count("<tr>") == 3
    assert '<hx-partial hx-target="#count" hx-swap="outerHTML"><span id="count">3</span></hx-partial>' in body
    assert "<hx-partial" not in client.hx_get("/lib/with-partial/", full=True).content.decode()


def test_partial_root_must_carry_the_partial_name_as_id(client):
    with pytest.raises(HxPartialRootId, match='root <span> must carry id="badcount"; it has no id'):
        client.hx_get("/lib/bad-partial/")


@pytest.mark.parametrize(
    "html",
    [
        '<div id="count">3</div>',
        "<div id='count'>3</div>",
        "<div id=count>3</div>",
        '<!-- the count --> <div id="count">3</div>',
        # An attribute value may contain ">", so the root element cannot be found
        # by scanning to the first one.
        '<div hx-on:click="if (a > b) { go() }" id="count">3</div>',
    ],
)
def test_the_root_id_is_read_by_the_parser_not_by_eye(html):
    check_root_id(html, "count", "index.html#count")


@pytest.mark.parametrize(
    ("html", "complaint"),
    [
        ('<div><span id="count">3</span></div>', "must carry"),
        ('<div class="count">3</div>', "it has no id"),
        ('<div id="total">3</div>', 'it has id="total"'),
        ("3 contacts", "does not start with an element"),
    ],
)
def test_a_partial_root_without_the_name_as_its_id_is_loud(html, complaint):
    with pytest.raises(HxPartialRootId, match=re.escape(complaint)):
        check_root_id(html, "count", "index.html#count")


def test_unknown_partial_lists_the_partials_the_template_defines(client):
    with pytest.raises(HxUnknownPartial, match="index.html defines no partial 'rowz'; it defines: badcount, count, extra, rows"):
        client.hx_get("/lib/unknown-partial/")


# -------------------------------------------------------------- partial rendering


def test_partials_see_context_processors(client):
    assert client.hx_get("/lib/extra/").content.strip() == b"<i>processed GET</i>"


# ---------------------------------------------------------------- messages bridge


def test_messages_reach_a_fragment_response_as_a_partial(client):
    body = client.hx_delete("/lib/flash-removed/").content.decode()
    assert body.startswith('\n<hx-partial hx-target="#messages" hx-swap="outerHTML">')
    assert '<p class="flash">Deleted!</p>' in body
    # consumed: the next page does not show it again
    assert b"Deleted!" not in client.get("/lib/").content


def test_messages_on_a_full_response_stay_in_the_page(client):
    body = client.hx_get("/lib/flash-page/", full=True).content.decode()
    assert '<p class="flash">Hello</p>' in body and "<hx-partial" not in body


def test_messages_without_a_template_are_loud(client):
    with override_settings(HX_MESSAGES_TEMPLATE=None):
        with pytest.raises(HxMessagesUnconfigured, match=r"flash_removed\(\) added messages while answering a fragment request"):
            client.hx_delete("/lib/flash-removed/")


def test_messages_bridge_skips_streamed_and_non_html_responses(client):
    r = client.hx_get("/lib/flash-file/")
    assert r.status_code == 200 and r.content == b"[]"
    r = client.hx_get("/lib/flash-stream/")
    assert b"".join(r.streaming_content) == b"<i>streamed</i>"


# ------------------------------------------------------------------- headers


def test_every_response_varies_on_the_htmx_headers(client):
    for r in (client.get("/lib/"), client.hx_get("/lib/"), client.get("/lib/plain/")):
        assert {"HX-Request", "HX-Request-Type"} <= set(r["Vary"].split(", "))


def test_htmx_request_without_request_type_is_a_protocol_error(client):
    with pytest.raises(HxProtocolError, match="needs htmx 4"):
        client.get("/lib/", HTTP_HX_REQUEST="true")  # raised by the verb
    with pytest.raises(HxProtocolError, match="needs htmx 4"):
        client.get("/lib/plain/", HTTP_HX_REQUEST="true")  # raised by the guard


# ------------------------------------------------------------------ text, provenance


def test_text_escapes(client):
    r = client.hx_get("/lib/escaped/")
    assert r.content == b"&lt;b&gt;Email Required&lt;/b&gt;" and r["Content-Type"].startswith("text/html")


def test_the_template_is_named_in_a_header_under_debug(client):
    with override_settings(DEBUG=True):
        assert client.hx_get("/lib/")["X-HX-Template"] == "index.html#rows"
        assert client.hx_get("/lib/", full=True)["X-HX-Template"] == "index.html"
        assert client.hx_get("/lib/file/")["X-HX-Template"] == "rows.html"
    assert "X-HX-Template" not in client.hx_get("/lib/")


def test_request_side_never_exposes_element_ids():
    import dj_hx.request as r

    assert not any(name in ("source", "target", "trigger") for name in dir(r))
