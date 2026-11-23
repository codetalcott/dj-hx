"""
Interactions in Chromium, against the desk app (tests/desk) on htmx 4.0.2 and _hyperscript 0.9.94, the
versions the start-up checks' rulings were read from (their sources and hashes: tests/desk/static/desk/).

What a reply does to the page: feedback only after it, a refusal's message with the controls kept, and
README's status policy (``hx-status`` on each interaction partial's root, and the layout's alert) against a
405, a 404, a 500 and a request that gets no reply, while a boosted link to a missing page still shows the
404 page, which a global ``noSwap`` would keep from it. Then six of the forms checks E011 to E013 accept, each measured once: an outer morph and an
outer sync (E013), a self-replacing control, click-to-edit's ``hx-target:inherited="this"`` and
``closest #<partial>`` (E012), and a ``<form method="post" hx-action>`` (E011); the other forms they accept
are read from htmx 4.0.2's source. Then what the swaps E013 rejects do instead, and what an ``hx-select`` that
reaches a control does (E026), with the ``hx-select=""`` that stops an inherited one. tests/test_interactions.py
shows the desk passes every check.
"""

from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.browser
sync_api = pytest.importorskip("playwright.sync_api")  # `browser` and `page` are tests/conftest.py's
expect = sync_api.expect

HOLD_MS = 1200  # as long as the probe harness's pending.spec.ts holds a write
POLICY = ' hx-status:40x:inherited="swap:none" hx-status:5xx:inherited="swap:none"'  # on each partial's root
GLOBAL_NO_SWAP = """<meta name="htmx-config" content='{"noSwap": [204, 304, "40x", "5xx"]}'>"""
# htmx's last event of each request, after its swap. It reaches document even when the swap removed the
# element that sent the request (htmx dispatches on document then), so it counts every request.
COUNT_FINISHED = "document.addEventListener('htmx:finally:request', () => { window.finished = (window.finished || 0) + 1 })"


@pytest.fixture
def live(desk, live_server):
    return f"{live_server.url}/desk/"


def open_desk(page, url):
    page.goto(url)
    page.evaluate(COUNT_FINISHED)


def finished(page, requests):
    """Wait until htmx has finished ``requests`` requests, swaps included."""
    page.wait_for_function(f"(window.finished || 0) >= {requests}")


def hold_writes(page):
    """Hold every request but a GET in the browser, until the test lets it go; returns the held routes."""
    held = []
    page.route("**/*", lambda route: route.continue_() if route.request.method == "GET" else held.append(route))
    return held


def one(page, element_id):
    """Every element carrying ``element_id``: a duplicate id would be two."""
    return page.locator(f'[id="{element_id}"]')


# ------------------------------------------------------------- what the reply does


def test_an_event_without_a_target_lands_on_document_after_a_delete_swap_where_from_body_cannot_hear_it(page, live, desk):
    """Why .trigger() always writes a target: htmx 4 dispatches on the source element, or document once a swap removed it."""
    open_desk(page, live)
    page.evaluate("document.addEventListener('dropped', e => { window.heardAt = (window.heardAt || []).concat(e.target === document ? 'document' : e.target.tagName) })")

    page.get_by_test_id("drop-bare").click()
    finished(page, 1)
    expect(one(page, "drop-bare")).to_have_count(0)  # the delete swap ran
    assert page.evaluate("window.heardAt") == ["document"]  # dispatched on document: the row is gone
    assert page.get_by_test_id("drops").inner_text() == "No row dropped yet."  # a `from body` listener never hears it

    page.get_by_test_id("drop-targeted").click()
    finished(page, 2)
    expect(one(page, "drop-targeted")).to_have_count(0)
    assert page.evaluate("window.heardAt") == ["document", "BODY"]  # target: body, which bubbles to document
    expect(page.get_by_test_id("drops")).to_have_text("A row was dropped.")
    assert page.console_errors == []


def test_feedback_appears_only_after_the_reply(page, live, desk):
    open_desk(page, live)
    held = hold_writes(page)
    page.get_by_test_id("notify-3").click()
    page.wait_for_timeout(HOLD_MS)
    assert len(held) == 1 and desk.DESK["notified"] == set()  # pending: held in the browser, unseen by the server
    assert "Notified" not in page.locator("#notify").inner_text()
    assert page.get_by_test_id("notices").inner_text() == "No one notified yet."

    held[0].continue_()
    finished(page, 1)
    expect(page.get_by_test_id("notified")).to_have_text("Notified Ada.")
    expect(page.get_by_test_id("notices")).to_have_text("A member was notified.")  # the trigger, heard by hyperscript
    assert desk.DESK["notified"] == {3}
    assert page.console_errors == []


def test_a_refusal_shows_its_message_and_keeps_the_controls(page, live, desk):
    desk.DESK["notified"].add(3)
    open_desk(page, live)
    with page.expect_response(lambda r: r.request.method == "POST") as reply:
        page.get_by_test_id("notify-3").click()
    finished(page, 1)
    assert reply.value.status == 422
    expect(page.get_by_test_id("refusal")).to_have_text("Ada was notified already.")
    expect(one(page, "notify")).to_have_count(1)
    expect(page.locator("#notify button")).to_have_text(["Notify Ada", "Notify Bo", "Check Ada"])
    expect(page.locator("#trouble")).to_be_hidden()  # the layout's alert ignores 422
    expect(page.get_by_test_id("notices")).to_have_text("No one notified yet.")  # a refusal announces nothing
    assert page.console_errors == []


def fail(desk, page, status):
    """Make the next control fail with ``status``, and return the control to click."""
    if status == 405:
        return page.get_by_test_id("stale-get")  # sends GET to the POST interaction
    if status == 404:
        del desk.DESK["members"][7]  # Bo has left the desk since the page was rendered
        return page.get_by_test_id("notify-7")
    desk.DESK["mail_down"] = True  # an exception notify() does not declare
    return page.get_by_test_id("notify-3")


STATUSES = pytest.mark.parametrize("status", [405, 404, 500])


@STATUSES
def test_under_the_status_policy_an_error_keeps_the_controls_and_the_alert_shows_until_the_next_request(page, live, desk, status):
    open_desk(page, live)
    control = fail(desk, page, status)
    with page.expect_response(lambda r: "/x/desk/" in r.url) as reply:
        control.click()
    finished(page, 1)
    assert reply.value.status == status
    expect(one(page, "notify")).to_have_count(1)
    expect(page.locator("#notify button")).to_have_text(["Notify Ada", "Notify Bo", "Check Ada"])
    expect(page.locator("#trouble")).to_be_visible()

    desk.DESK["mail_down"] = False  # so the next request, on a control the error kept, succeeds
    page.get_by_test_id("notify-3").click()
    finished(page, 2)
    expect(page.locator("#trouble")).to_be_hidden()
    expect(page.get_by_test_id("notified")).to_have_text("Notified Ada.")
    assert page.console_errors == []


@STATUSES
def test_without_the_status_policy_an_error_wipes_the_controls(page, live, desk, status):
    stripped = []

    def without_the_policy(route):
        response = route.fetch()
        body = response.text()
        stripped.append(body.count(POLICY))
        route.fulfill(response=response, body=body.replace(POLICY, ""))

    page.route(live, without_the_policy)
    open_desk(page, live)
    assert stripped == [7]  # the page was served without the policy on its seven partials' roots
    with page.expect_response(lambda r: "/x/desk/" in r.url) as reply:
        fail(desk, page, status).click()
    finished(page, 1)
    assert reply.value.status == status
    expect(one(page, "notify")).to_have_count(0)  # htmx 4 swapped the error's body over the region
    assert page.console_errors == []


def test_an_alert_hidden_with_the_hidden_attribute_never_shows(page, live, desk):
    # Why the layout hides its alert with style="display: none": hyperscript's `show` clears only an inline display.
    open_desk(page, live)
    alert = page.locator("#trouble")
    alert.evaluate("alert => { alert.hidden = true }")  # beside its style="display: none"
    page.get_by_test_id("stale-get").click()
    finished(page, 1)
    assert alert.evaluate("alert => alert.style.display") == ""  # `show me` ran: it cleared the inline none
    expect(alert).to_be_hidden()  # and left the hidden attribute alone
    assert page.console_errors == []


def test_the_alert_shows_when_the_request_never_gets_a_reply_and_clears_on_the_next(page, live, desk):
    # A failed fetch (the server down, a timeout) has no status: htmx 4.0.2 fires htmx:error, not htmx:response:error.
    open_desk(page, live)
    page.route("**/x/desk/notify/3/", lambda route: route.abort(), times=1)
    page.get_by_test_id("notify-3").click()
    finished(page, 1)
    expect(page.locator("#trouble")).to_be_visible()
    expect(page.locator("#notify button")).to_have_text(["Notify Ada", "Notify Bo", "Check Ada"])
    assert desk.DESK["notified"] == set()  # the request never reached the server
    assert [error[:18] for error in page.console_errors] == ["htmx: htmx:error: "]  # htmx logs the error it fires
    page.get_by_test_id("notify-3").click()
    finished(page, 2)
    expect(page.locator("#trouble")).to_be_hidden()
    expect(page.get_by_test_id("notified")).to_have_text("Notified Ada.")
    assert len(page.console_errors) == 1  # the second request logged nothing


def follow_the_boosted_link_to_a_missing_page(page):
    with page.expect_response(lambda r: r.url.endswith("/desk/gone/")) as reply:
        page.get_by_test_id("gone").click()
    finished(page, 1)
    assert reply.value.status == 404
    assert urlparse(page.url).path == "/desk/gone/"


def test_a_boosted_link_to_a_missing_page_shows_the_404_page(page, live, desk):
    # The policy is scoped to the interactions' partials, so boosted navigation keeps htmx's own noSwap.
    open_desk(page, live)
    follow_the_boosted_link_to_a_missing_page(page)
    expect(page.locator("h1")).to_have_text("Not Found")  # Django's 404 page, swapped into the body
    expect(one(page, "notify")).to_have_count(0)
    assert page.console_errors == []


def test_under_a_global_no_swap_a_boosted_404_leaves_the_old_page_under_the_new_url(page, live, desk):
    # Why the policy is not htmx-config's noSwap: that applies to every htmx request on the page, boosted
    # navigation included, and htmx 4.0.2 checks it before any hx-status, so no element can opt back in.
    page.route(live, lambda route: route.fulfill(response=(r := route.fetch()), body=r.text().replace("<head>", "<head>" + GLOBAL_NO_SWAP)))
    open_desk(page, live)
    follow_the_boosted_link_to_a_missing_page(page)
    expect(page.locator("h1")).to_have_text("The desk")  # the 404 was not swapped in
    expect(one(page, "notify")).to_have_count(1)
    assert page.console_errors == []


# ------------------------------------------------------ what the start-up checks accept


def test_a_post_form_with_hx_action_posts_to_the_route_it_chose(page, live, desk):
    # E011 reads hx-action's method from the form's method attribute; route= chose the path.
    open_desk(page, live)
    with page.expect_response(lambda r: "sign-off" in r.url) as reply:
        page.get_by_test_id("sign-off").click()
    finished(page, 1)
    assert (reply.value.request.method, reply.value.status) == ("POST", 200)
    assert urlparse(reply.value.url).path == "/desk/members/3/sign-off"
    assert desk.DESK["signed"] == {3}
    expect(page.get_by_test_id("signed")).to_have_text("Signed off.")
    expect(one(page, "signoff")).to_have_count(1)
    assert page.console_errors == []


@pytest.mark.parametrize(
    "control, partial",
    [
        ("morph", "morphed"),  # hx-swap="outerMorph" (E013)
        ("sync", "synced"),  # hx-swap="outerSync" (E013)
        ("selfswap", "selfswap"),  # the control is the partial's root, with no hx-target (E012)
        ("retitle", "title"),  # click-to-edit: hx-target:inherited="this" on the partial's root (E012)
        ("nearest", "nearest"),  # hx-target="closest #nearest" (E012)
    ],
    ids=["outerMorph", "outerSync", "self-replacing", "inherited-this", "closest"],
)
def test_the_reply_replaces_the_partial_and_leaves_one_element_with_its_id(page, live, desk, control, partial):
    open_desk(page, live)
    for replies in (1, 2):  # the second click is on what the first reply put back
        page.get_by_test_id(control).click()
        finished(page, replies)
        expect(one(page, partial)).to_have_count(1)
        expect(page.locator(f"#{partial} .replies")).to_have_text(str(replies))
    assert desk.DESK["replies"][control] == 2
    assert page.console_errors == []


def test_an_outer_sync_reply_copies_the_root_attributes(page, live, desk):
    open_desk(page, live)
    page.get_by_test_id("sync").click()
    finished(page, 1)
    expect(one(page, "synced")).to_have_attribute("data-replies", "1")
    assert page.console_errors == []


# --------------------------------------------- what the swaps E013 rejects do instead


def swap_with(page, control, swap):
    """The same control with another hx-swap, set in the page (htmx reads it per request), so the desk's
    templates keep passing the checks."""
    page.get_by_test_id(control).evaluate("(element, swap) => element.setAttribute('hx-swap', swap)", swap)


@pytest.mark.parametrize("swap", ["innerHTML", "beforeend", "afterbegin", "beforebegin", "afterend"])
def test_a_swap_that_keeps_the_target_leaves_two_elements_with_the_id(page, live, desk, swap):
    open_desk(page, live)
    swap_with(page, "morph", swap)
    page.get_by_test_id("morph").click()
    finished(page, 1)
    expect(one(page, "morphed")).to_have_count(2)  # the reply's root, inside or beside the target
    assert page.console_errors == []


def test_an_inner_morph_makes_htmx_throw_and_the_reply_never_reaches_the_page(page, live, desk):
    open_desk(page, live)
    swap_with(page, "morph", "innerMorph")
    page.get_by_test_id("morph").click()
    finished(page, 1)
    assert desk.DESK["replies"]["morph"] == 1  # the server replied with 1
    [error] = page.console_errors
    assert error.startswith("htmx: htmx:error: ") and "HierarchyRequestError" in error  # the swap threw
    expect(page.locator("#morphed .replies")).to_have_text("0")  # and the reply's 1 is nowhere on the page
    expect(page.locator("#trouble")).to_be_visible()  # the layout's alert hears htmx:error


# ------------------------------------------- what an hx-select that reaches a control does (E026)


def select_from_body(page, selector):
    """An hx-select:inherited on <body>, set in the page (htmx reads it per request), so the desk's templates
    keep passing the checks."""
    page.evaluate("selector => document.body.setAttribute('hx-select:inherited', selector)", selector)


def request_types(page):
    """Each POST's HX-Request-Type, in the order the page sends them."""
    types = []
    page.on("request", lambda request: request.method == "POST" and types.append(request.headers.get("hx-request-type")))
    return types


def test_an_inherited_hx_select_sends_a_full_request_and_its_reply_empties_the_partial(page, live, desk):
    open_desk(page, live)
    types = request_types(page)
    select_from_body(page, "#elsewhere")
    page.get_by_test_id("nearest").click()
    finished(page, 1)
    assert types == ["full"] and desk.DESK["replies"]["nearest"] == 1  # the server replied with its partial
    expect(one(page, "nearest")).to_have_count(0)  # and nothing of it took #nearest's place
    expect(page.get_by_test_id("nearest")).to_have_count(0)
    assert page.console_errors == []


def test_an_inherited_hx_select_that_matches_inside_the_reply_puts_that_element_in_the_partials_place(page, live, desk):
    open_desk(page, live)
    select_from_body(page, "#nearest .replies")
    page.get_by_test_id("nearest").click()
    finished(page, 1)
    expect(one(page, "nearest")).to_have_count(0)  # the region lost its id
    expect(page.locator(".replies", has_text="1")).to_have_count(1)  # the reply's counter stands in its place
    expect(page.get_by_test_id("nearest")).to_have_count(0)
    assert page.console_errors == []


def test_an_own_empty_hx_select_stops_the_inherited_one(page, live, desk):
    open_desk(page, live)
    types = request_types(page)
    select_from_body(page, "#elsewhere")
    page.get_by_test_id("nearest").evaluate("element => element.setAttribute('hx-select', '')")
    page.get_by_test_id("nearest").click()
    finished(page, 1)
    assert types == ["partial"]
    expect(one(page, "nearest")).to_have_count(1)
    expect(page.locator("#nearest .replies")).to_have_text("1")
    assert page.console_errors == []
