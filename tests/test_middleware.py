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
