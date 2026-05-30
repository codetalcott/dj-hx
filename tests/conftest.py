"""Shared test helpers for dj-htmx-cbv."""

import pytest
from django.test import RequestFactory
from django_htmx.middleware import HtmxDetails


@pytest.fixture
def rf():
    return RequestFactory()


def make_request(
    rf, method="get", path="/", *, htmx=False, request_type=None, boosted=False, data=None
):
    """Build a request, optionally carrying django-htmx's ``request.htmx``.

    Mirrors what HtmxMiddleware does: attaches an ``HtmxDetails`` that reads the HX-*
    headers we set here (HX-Request / HX-Request-Type / HX-Boosted).
    """
    headers = {}
    if htmx:
        headers["HTTP_HX_REQUEST"] = "true"
    if request_type:
        headers["HTTP_HX_REQUEST_TYPE"] = request_type
    if boosted:
        headers["HTTP_HX_BOOSTED"] = "true"

    factory = getattr(rf, method)
    request = factory(path, data or {}, **headers) if method == "post" else factory(path, **headers)
    request.htmx = HtmxDetails(request)
    return request
