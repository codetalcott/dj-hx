"""
HxTestClient — a Django test client that issues HTMX-shaped requests (the analog of
dj-fixi's corrected FxTestClient).

htmx submits form-encoded bodies (not JSON) and identifies itself with ``HX-Request:
true`` plus, in HTMX 4, ``HX-Request-Type`` (partial vs full). These helpers set those
headers and otherwise behave like Django's test client (so dict bodies are form-encoded,
matching htmx's FormData). Because requests go through the middleware stack,
``request.htmx`` is populated as in production.

    client = HxTestClient()
    resp = client.hx_post("/notes/create/", {"title": "hi"})
    assert resp["HX-Trigger"]
"""

import json as _json
from urllib.parse import urlencode

from django.test import Client


def _hx_headers(partial: bool | None) -> dict[str, str]:
    headers = {"HTTP_HX_REQUEST": "true"}
    if partial is not None:
        headers["HTTP_HX_REQUEST_TYPE"] = "partial" if partial else "full"
    return headers


class HxTestClient(Client):
    """Test client with htmx request helpers (form-encoded, ``HX-Request: true``)."""

    def hx_get(self, url, data=None, *, partial=True, **kwargs):
        """GET with HX headers (``data`` -> query string)."""
        return self.get(url, data=data, **_hx_headers(partial), **kwargs)

    def hx_post(self, url, data=None, *, partial=True, json=None, **kwargs):
        """POST with HX headers. ``data`` is form-encoded like htmx's FormData; pass
        ``json=`` to send a JSON body instead."""
        if json is not None:
            data = _json.dumps(json)
            kwargs.setdefault("content_type", "application/json")
        return self.post(url, data=data, **_hx_headers(partial), **kwargs)

    def hx_patch(self, url, data=None, *, partial=True, json=None, **kwargs):
        """PATCH with HX headers (form-encoded body by default)."""
        if json is not None:
            return self.patch(
                url,
                data=_json.dumps(json),
                content_type="application/json",
                **_hx_headers(partial),
                **kwargs,
            )
        if isinstance(data, dict):
            data = urlencode(data)
        return self.patch(
            url,
            data=data or "",
            content_type="application/x-www-form-urlencoded",
            **_hx_headers(partial),
            **kwargs,
        )

    def hx_delete(self, url, data=None, *, partial=True, json=None, **kwargs):
        """DELETE with HX headers. htmx sends DELETE parameters in the query string, so
        pass them via ``url``; ``json=`` is available if needed."""
        if json is not None:
            data = _json.dumps(json)
            kwargs.setdefault("content_type", "application/json")
        return self.delete(url, data=data, **_hx_headers(partial), **kwargs)
