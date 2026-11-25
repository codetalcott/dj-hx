"""HxMiddleware: records and logs, never raises; under DEBUG it also lints and names the template."""

import pytest
from django.test import override_settings

from dj_hx.testing import HxTestClient

pytestmark = pytest.mark.usefixtures("lib")


def test_findings_are_recorded_on_the_response_and_logged(caplog):
    client = HxTestClient(strict=False, lint=False)
    with caplog.at_level("WARNING", logger="dj_hx"):
        r = client.hx_delete("/lib/b/")
    assert r.status_code == 204
    assert [type(f).__name__ for f in r.hx_findings] == ["HxNoSwap"]
    assert any("with a 204" in m for m in caplog.messages)


def test_a_fragment_answering_a_full_request_is_recorded_by_the_verb(caplog):
    client = HxTestClient(strict=False, lint=False)
    with caplog.at_level("WARNING", logger="dj_hx"):
        r = client.hx_get("/lib/rows/", full=True)
    assert r.status_code == 200 and [type(f).__name__ for f in r.hx_findings] == ["HxFragmentIntoPage"]
    assert sum("answers a boosted" in m for m in caplog.messages) == 1


def test_debug_lint_logs_and_the_template_header(caplog):
    client = HxTestClient(strict=False, lint=False)
    with override_settings(DEBUG=True), caplog.at_level("WARNING", logger="dj_hx"):
        r = client.hx_get("/lib/lint-bad/")
        assert r["X-HX-Template"] == "bad.html"
        assert client.get("/lib/lint-bad/").status_code == 200  # not htmx: not observed
    assert sum("hx lint: GET /lib/lint-bad/" in m and "swap-style-case" in m for m in caplog.messages) == 1


def test_nothing_is_gated_on_debug_that_a_test_needs(client):
    """The bridge, the guard and the client's lint all run with DEBUG off (pytest-django's default)."""
    from django.conf import settings

    assert settings.DEBUG is False
    assert "<hx-partial" in client.hx_delete("/lib/flash-removed/").content.decode()


def test_a_whole_page_into_an_element_is_recorded_whoever_built_it(caplog):
    """django.shortcuts.render, a TemplateResponse (what a generic view returns) and a verb given a page."""
    client = HxTestClient(strict=False, lint=False)
    with caplog.at_level("WARNING", logger="dj_hx"):
        for url in ("/lib/bare-page/", "/lib/bare-template-response/", "/lib/fragment-of-page/"):
            r = client.hx_get(url)
            assert r.status_code == 200
            assert [type(f).__name__ for f in r.hx_findings] == ["HxPageIntoFragment"], url
    for url in ("/lib/bare-page/", "/lib/bare-template-response/"):
        assert client.hx_get(url, full=True).hx_findings == [], url  # a boosted link wants the page
    assert sum("with a whole page (its first tag is <html> or <body>)" in m for m in caplog.messages) == 3


@pytest.mark.parametrize(
    ("body", "document"),
    [
        ("<!doctype html><html><body><p>x</p></body></html>", True),
        ("\n  <!-- a comment --><HTML lang=en>", True),
        ("<body><p>x</p></body>", True),
        ("<!doctype html><head><title>t</title></head><body><p>x</p></body>", True),  # <html> may be left out
        ("<head><title>New</title></head>\n<div>x</div>", False),  # htmx takes the title and swaps the div
        ("<header><p>x</p></header>", False),
        ("<tr><td>x</td></tr><html>", False),  # the first tag decides
        ('<hx-partial hx-target="#m"><div id="m"></div></hx-partial>', False),
        ("plain text", False),
        ("", False),
    ],
)
def test_a_document_is_what_htmx_reads_as_one(body, document):
    """htmx 4.0.2's test, from its swap: drop the first <head>, then the first tag is <html> or <body>."""
    from django.http import HttpResponse

    from dj_hx.guard import is_document

    assert is_document(HttpResponse(body)) is document


def test_a_response_no_verb_built_is_recorded_only_under_hx_require_verbs(caplog):
    """Without the setting, a project on django-htmx installs the guard and keeps its views."""
    client = HxTestClient(strict=False, lint=False)
    assert client.hx_get("/lib/plain/").hx_findings == []
    with override_settings(HX_REQUIRE_VERBS=True), caplog.at_level("WARNING", logger="dj_hx"):
        r = client.hx_get("/lib/plain/")
        assert [type(f).__name__ for f in r.hx_findings] == ["HxBareResponse"]
        # A whole page is the one finding that says what goes wrong, so it is the one recorded.
        assert [type(f).__name__ for f in client.hx_get("/lib/bare-page/").hx_findings] == ["HxPageIntoFragment"]
    assert sum("no verb built" in m and "HX_REQUIRE_VERBS is set" in m for m in caplog.messages) == 1


def test_a_response_no_verb_built_is_fine_for_a_page_and_for_what_htmx_never_swaps():
    """A boosted link wants a page, whoever built it; JSON, a download and a stream are not swapped."""
    client = HxTestClient(lint=False)  # strict: a finding would raise
    assert client.hx_get("/lib/bare-page/", full=True).status_code == 200
    assert client.get("/lib/bare-page/").status_code == 200
    assert client.hx_get("/lib/json/").status_code == 200
    assert client.hx_get("/lib/echo/").status_code == 200
    assert client.hx_get("/lib/flash-stream/").status_code == 200
