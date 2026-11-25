"""
The verbs, one section per row of the design's silent-failure catalogue. Each
test seeds the failure a Django app could contain and asserts that it is loud,
or cannot be represented. Same cases as hx-flask's tests/test_hx.py.
"""

import json
import re

import pytest
from django.test import Client, override_settings

from dj_hx import (
    HxError,
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
from tests.conftest import PARTIAL, locmem

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


def test_navigate_leaves_the_page_whatever_the_control_targets(client):
    for r in (client.get("/lib/leave/"), client.hx_get("/lib/leave/", full=True, follow=False)):
        assert (r.status_code, r["Location"]) == (303, "/lib/") and "HX-Redirect" not in r
    r = client.hx_get("/lib/leave/")  # fetch would follow a 303 into the target; HX-Redirect is a full load
    assert (r.status_code, r.content, r["HX-Redirect"]) == (200, b"", "/lib/") and "Location" not in r
    assert r.hx_kind == "navigate" and "HX-Request-Type" in r["Vary"]


def test_navigate_leaves_the_messages_for_the_page_it_loads(client):
    assert client.hx_get("/lib/flash-leave/").content == b""  # no <hx-partial>: that would consume them
    assert b"Please log in" in client.get("/lib/").content


def test_a_plain_redirect_is_judged_where_fetch_follows_it(client):
    """fetch follows a 3xx with the request's headers (measured in Chromium, experiment 2), so the guard judges what it reaches."""
    r = client.hx_post("/lib/plain-redirect/")  # to /lib/, which answers this request with its rows
    assert r.status_code == 302 and r.hx_findings == []
    assert client.hx_post("/lib/plain-redirect/", follow=True).content.count(b"<tr>") == 3
    with pytest.raises(HxPageIntoFragment, match=r"bare_page\(\) answered .* with a whole page.* If a redirect led here"):
        client.hx_post("/lib/redirect-to-page/", follow=True)


def test_hx_require_verbs_records_the_redirect_itself(client):
    with override_settings(HX_REQUIRE_VERBS=True):
        with pytest.raises(HxRedirectIntoFragment, match=r"with a 302 \(HX_REQUIRE_VERBS is set\).*navigate\(\) to leave the page"):
            client.hx_post("/lib/plain-redirect/")


def test_guard_names_an_append_slash_redirect(client):
    with pytest.raises(HxRedirectIntoFragment, match="got a redirect from APPEND_SLASH.*'/lib/things'"):
        client.hx_delete("/lib/things")


def test_guard_logs_instead_of_raising_when_not_strict(caplog):
    with caplog.at_level("WARNING", logger="dj_hx"):
        r = HxTestClient(strict=False).hx_get("/lib/bare-page/")
    assert r.status_code == 200  # logged, not raised, so the page went out
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


@pytest.mark.parametrize(("url", "kind"), [("/lib/removed-partial/", "removed"), ("/lib/text-partial/", "text")])
def test_partial_on_a_response_with_no_context_raises(client, url, kind):
    """removed() and text() have nothing to render #count from; a silent no-op left the region as it was."""
    with pytest.raises(HxError, match=re.escape(f"partial('count') on {kind}(), which has no context to render #count")):
        client.hx_get(url)


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


def test_a_fragment_that_shows_its_own_messages_gets_no_second_copy(client):
    """A django-htmx habit: the fragment's template shows the messages (often out of band), which consumes them."""
    body = client.hx_get("/lib/flash-shown/").content.decode()
    assert body.count('<p class="flash">Shown</p>') == 1 and "<hx-partial" not in body
    assert b"Shown" not in client.get("/lib/").content  # consumed by the fragment that showed them
    with override_settings(HX_MESSAGES_TEMPLATE=None):
        client.hx_get("/lib/flash-shown/")  # HxTestClient would raise an HxMessagesUnconfigured recorded here
        assert b"Shown" not in client.get("/lib/").content


@pytest.mark.parametrize(("header", "value"), [("HX-Redirect", "/lib/"), ("HX-Refresh", "true"), ("HX-Location", "/lib/")])
@pytest.mark.parametrize("status", [200, 204])
def test_a_response_htmx_obeys_before_any_swap_is_not_judged_and_keeps_its_messages(client, header, value, status):
    """htmx 4.0.2 obeys HX-Refresh, HX-Redirect and HX-Location before any swap (its #de), so no body is swapped."""
    url = f"/lib/navigates/?header={header}&value={value}&status={status}"
    with override_settings(HX_REQUIRE_VERBS=True):
        r = client.hx_post(url)  # HxTestClient: a finding (a whole page, a 204, no verb) would raise
    assert b"<hx-partial" not in r.content
    assert b'<p class="flash">Moved</p>' in client.get("/lib/").content  # left for the page htmx loads
    with override_settings(HX_MESSAGES_TEMPLATE=None):
        client.hx_post(url)  # and no HxMessagesUnconfigured
    with pytest.raises(HxPageIntoFragment):
        client.hx_post("/lib/navigates/?header=HX-Refresh&value=false&status=200")  # htmx refreshes only on "true"


def test_messages_on_a_full_response_stay_in_the_page(client):
    body = client.hx_get("/lib/flash-page/", full=True).content.decode()
    assert '<p class="flash">Hello</p>' in body and "<hx-partial" not in body


def test_messages_without_a_template_are_loud(client):
    with override_settings(HX_MESSAGES_TEMPLATE=None):
        with pytest.raises(HxMessagesUnconfigured, match=r"flash_removed\(\) added messages while answering a fragment request"):
            client.hx_delete("/lib/flash-removed/")


FLASH = '{% partialdef messages inline %}<div id="flash">{% for m in messages %}<p class="flash">{{ m }}</p>{% endfor %}</div>{% endpartialdef %}'


@pytest.mark.parametrize(
    ("setting", "error", "complaint"),
    [
        ("flash.html#messages", HxPartialRootId, 'its root <div> must carry id="messages"; it has id="flash"'),
        ("layout.html#flash", HxUnknownPartial, "layout.html defines no partial 'flash'"),
    ],
)
def test_a_messages_partial_that_fails_is_recorded_and_its_messages_wait(caplog, setting, error, complaint):
    """
    HxMiddleware never raises a finding: in production, a messages partial that is missing or has the
    wrong root would otherwise turn every fragment response that carries a message into a 500.
    """
    browser = Client()  # production's view: nothing raises a recorded finding
    with override_settings(TEMPLATES=locmem({"flash.html": FLASH}), HX_MESSAGES_TEMPLATE=setting):
        with caplog.at_level("WARNING", logger="dj_hx"):
            r = browser.delete("/lib/flash-removed/", **PARTIAL)
        assert r.status_code == 200 and r.content == b""
        assert [type(f) for f in r.hx_findings] == [error]
        assert sum(complaint in m for m in caplog.messages) == 1
        with pytest.raises(error, match=re.escape(complaint)):
            HxTestClient().hx_delete("/lib/flash-removed/")  # a test still fails on it
    assert b'<p class="flash">Deleted!</p>' in browser.get("/lib/").content  # not shown, so kept for the next page


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
    # DEBUG is off in tests.settings: the verb answers with the page, the guard records, the client raises.
    with pytest.raises(HxProtocolError, match="needs htmx 4"):
        client.get("/lib/", HTTP_HX_REQUEST="true")
    with pytest.raises(HxProtocolError, match="needs htmx 4"):
        client.get("/lib/plain/", HTTP_HX_REQUEST="true")  # no verb: the guard alone
    with override_settings(DEBUG=True), pytest.raises(HxProtocolError, match="Under DEBUG this raises"):
        # The verb raises inside the view. A plain client, because HxTestClient would raise the guard's
        # recorded copy of the same message, and the test would pass whether or not the verb raised.
        Client().get("/lib/", HTTP_HX_REQUEST="true")


def test_in_production_a_missing_request_type_is_answered_as_full_and_logged(caplog):
    """A proxy that strips the header must not 500 every htmx request: the page goes out, and the log says so."""
    client = HxTestClient(strict=False)
    with caplog.at_level("WARNING", logger="dj_hx"):
        r = client.get("/lib/", HTTP_HX_REQUEST="true")
    assert r.status_code == 200 and b"<html>" in r.content
    assert [type(f) for f in r.hx_findings] == [HxProtocolError]
    assert sum("HX-Request-Type is not" in m for m in caplog.messages) == 1


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
