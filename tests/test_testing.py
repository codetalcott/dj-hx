"""Tests for HxTestClient: HX headers + form-encoded bodies through the middleware."""

import pytest

from dj_htmx_cbv.testing import HxTestClient


@pytest.fixture
def client():
    return HxTestClient()


def test_hx_get_sets_htmx_and_partial(client):
    data = client.hx_get("/whoami/").json()
    assert data["htmx"] is True
    assert data["request_type"] == "partial"


def test_partial_false_sends_full(client):
    data = client.hx_get("/whoami/", partial=False).json()
    assert data["request_type"] == "full"


def test_hx_get_passes_query_params(client):
    data = client.hx_get("/whoami/", {"x": "q"}).json()
    assert data["query"] == "q"


def test_hx_post_is_form_encoded(client):
    """A dict body reaches request.POST (form-encoded like htmx's FormData)."""
    data = client.hx_post("/whoami/", {"x": "1"}).json()
    assert data["htmx"] is True
    assert data["method"] == "POST"
    assert data["posted"] == "1"
