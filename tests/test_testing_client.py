"""HxTestClient: htmx-shaped requests, every response linted, redirects made explicit."""

import pytest
from django.test import override_settings

from dj_hx import HxLintError, HxRedirectError
from dj_hx.testing import HxLintWarning, HxTestClient

pytestmark = pytest.mark.usefixtures("lib")


def test_helpers_send_the_headers_and_htmx_shaped_bodies(client):
    assert client.hx_get("/lib/echo/", {"a": "1"}).content == b"GET hx=true type=partial ct= a=1"
    assert client.hx_get("/lib/echo/", full=True).content.startswith(b"GET hx=true type=full")
    assert client.hx_post("/lib/echo/", {"a": "2"}).content.startswith(b"POST hx=true type=partial ct=multipart/form-data a=2")
    assert client.hx_put("/lib/echo/", {"a": "3"}).content == b"PUT hx=true type=partial ct=application/x-www-form-urlencoded a="
    assert client.hx_patch("/lib/echo/", {"a": "5"}).content.startswith(b"PATCH hx=true")
    assert client.hx_delete("/lib/echo/?a=4").content.endswith(b"a=4")
    assert b"ct=application/json" in client.hx_post("/lib/echo/", json={"a": 1}).content
    assert client.get("/lib/echo/").content == b"GET hx=None type=None ct= a="


def test_a_redirect_to_a_full_request_must_be_chosen(client):
    with pytest.raises(HxRedirectError, match="303.*follow=True"):
        client.hx_post("/lib/save/", full=True)
    assert client.hx_post("/lib/save/", full=True, follow=False).status_code == 303
    followed = client.hx_post("/lib/save/", full=True, follow=True)
    assert followed.status_code == 200 and followed.redirect_chain == [("/lib/", 303)]


def test_plain_get_never_raises_on_redirects(client):
    assert client.get("/lib/save/").status_code == 303


def test_lint_raises_warns_and_can_be_silenced(client):
    with pytest.raises(HxLintError, match=r"(?s)GET /lib/lint-bad/.*swap-style-case") as info:
        client.hx_get("/lib/lint-bad/")
    assert info.value.findings[0].rule == "swap-style-case"
    with pytest.warns(HxLintWarning, match="implicit-inheritance"):
        r = client.hx_get("/lib/lint-warn/")
    assert [f.rule for f in r.hx_lint] == ["implicit-inheritance"]
    assert HxTestClient(lint=False).hx_get("/lib/lint-bad/").status_code == 200
    assert HxTestClient(lint_ignore=("swap-style-case",)).hx_get("/lib/lint-bad/").hx_lint == []
    with override_settings(HX_LINT_IGNORE=["swap-style-case"]):
        assert client.hx_get("/lib/lint-bad/").hx_lint == []


def test_non_html_and_empty_responses_are_skipped(client):
    assert client.hx_get("/lib/json/").hx_lint == []
    assert client.hx_delete("/lib/a/").hx_lint == []


def test_the_client_guards_without_the_middleware(client):
    from dj_hx import HxRedirectIntoFragment

    middleware = [m for m in __import__("django.conf").conf.settings.MIDDLEWARE if "dj_hx" not in m]
    with override_settings(MIDDLEWARE=middleware):
        with pytest.raises(HxRedirectIntoFragment):
            client.hx_post("/lib/plain-redirect/")
        assert "HX-Request" in client.hx_get("/lib/")["Vary"]  # the verbs set it themselves
