"""
``HxTestClient``: a Django test client that behaves the way htmx 4 does, and
is strict about what htmx would do silently.

- ``hx_get``/``hx_post``/``hx_put``/``hx_patch``/``hx_delete`` send
  ``HX-Request: true`` and ``HX-Request-Type: partial`` (``full=True`` for a
  boosted link or a body-targeted control), form-encoded like htmx's FormData.
- Every response's recorded findings (the verbs' and the middleware's) are
  raised: ``HxRedirectIntoFragment``, ``HxNoSwap``, ``HxFragmentIntoPage``,
  ``HxMessagesUnconfigured``, ``HxProtocolError``. Without ``HxMiddleware``
  the client runs the guard itself.
- Every ``text/html`` response is linted for the htmx 4 vocabulary and an
  error-level finding raises ``HxLintError``; ``lint=False`` or
  ``lint_ignore=("rule",)`` switch that off (``HX_LINT_IGNORE`` too).
- A 3xx answering a *full* request raises ``HxRedirectError`` unless the test
  says ``follow=True`` (the page the browser shows) or ``follow=False`` (the
  redirect itself), because htmx's fetch follows redirects and the browser
  never sees them. A 3xx answering a partial request is the guard's finding.
"""

from __future__ import annotations

import json as _json
import warnings
from urllib.parse import urlencode

from django.test import Client

from .errors import HxLintError, HxRedirectError
from .guard import guard

__all__ = ["HxTestClient", "HxLintWarning", "hx_check_messages", "assert_no_hx_check_issues"]


class HxLintWarning(UserWarning):
    """A warning-level lint finding, surfaced through ``warnings.warn``."""


def hx_headers(*, full: bool = False) -> dict[str, str]:
    return {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_REQUEST_TYPE": "full" if full else "partial",
        "HTTP_ACCEPT": "text/html",
    }


class HxTestClient(Client):
    def __init__(self, *args, strict: bool = True, lint: bool = True, lint_ignore=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.strict = strict
        self.lint = lint
        self.lint_ignore = tuple(lint_ignore)

    def request(self, **request):
        response = super().request(**request)
        where = f"{request.get('REQUEST_METHOD', 'GET')} {request.get('PATH_INFO', '')}"
        wsgi_request = getattr(response, "wsgi_request", None)
        findings = guard(wsgi_request, response) if wsgi_request is not None else []
        if self.strict and findings:
            raise findings[0]
        if self.lint:
            response.hx_lint = self._lint(response, where)
        return response

    def _lint(self, response, where):
        from django.conf import settings

        from . import hxlint

        if getattr(response, "streaming", False) or response.status_code >= 500:
            return []
        if not (response.get("Content-Type") or "").startswith("text/html"):
            return []
        body = response.content.decode(response.charset or "utf-8", errors="replace")
        if not body.strip():
            return []
        ignore = set(self.lint_ignore) | set(getattr(settings, "HX_LINT_IGNORE", ()))
        findings = [
            f for f in hxlint.lint_html(body, extensions=getattr(settings, "HX_EXTENSIONS", ()))
            if f.rule not in ignore
        ]
        errors = [f for f in findings if f.severity == "error"]
        if errors and self.strict:
            raise HxLintError(errors, where)
        for f in findings:
            if f.severity == "warning":
                warnings.warn(str(f), HxLintWarning, stacklevel=4)
        return findings

    # ---------------------------------------------------------------- helpers

    def _hx(self, send, url, full, follow, kwargs):
        response = send(url, follow=bool(follow), **hx_headers(full=full), **kwargs)
        if full and follow is None and 300 <= response.status_code < 400:
            raise HxRedirectError(
                f"{send.__name__.upper()} {url.split('?', 1)[0]} answered a full htmx request with a "
                f"{response.status_code} to {response.get('Location', '')!r}. htmx's fetch follows it and swaps the "
                "followed page into <body>. Pass follow=True to get what the browser would show, or follow=False "
                "to assert on the redirect itself."
            )
        return response

    def hx_get(self, url, data=None, *, full=False, follow=None, **kwargs):
        """GET as htmx (``data`` -> query string)."""
        return self._hx(self.get, url, full, follow, {"data": data, **kwargs})

    def hx_post(self, url, data=None, *, full=False, follow=None, json=None, **kwargs):
        """POST as htmx; ``data`` is form-encoded like FormData, ``json=`` sends JSON."""
        if json is not None:
            data = _json.dumps(json)
            kwargs.setdefault("content_type", "application/json")
        return self._hx(self.post, url, full, follow, {"data": data, **kwargs})

    def hx_put(self, url, data=None, *, full=False, follow=None, json=None, **kwargs):
        return self._hx(self.put, url, full, follow, self._body(data, json, kwargs))

    def hx_patch(self, url, data=None, *, full=False, follow=None, json=None, **kwargs):
        return self._hx(self.patch, url, full, follow, self._body(data, json, kwargs))

    def hx_delete(self, url, data=None, *, full=False, follow=None, json=None, **kwargs):
        """DELETE as htmx. htmx 4 sends DELETE parameters in the query string: pass them in ``url``."""
        if json is not None:
            data = _json.dumps(json)
            kwargs.setdefault("content_type", "application/json")
        return self._hx(self.delete, url, full, follow, {"data": data, **kwargs})

    @staticmethod
    def _body(data, json, kwargs):
        if json is not None:
            return {"data": _json.dumps(json), "content_type": "application/json", **kwargs}
        if isinstance(data, dict):
            data = urlencode(data)
        return {"data": data or "", "content_type": "application/x-www-form-urlencoded", **kwargs}


def hx_check_messages(*, include_warnings: bool = True) -> list:
    """dj-hx's system-check messages; pytest does not run checks, so call this from a test."""
    from django.conf import settings
    from django.core.checks import ERROR, run_checks

    silenced = set(getattr(settings, "SILENCED_SYSTEM_CHECKS", []))
    messages = [m for m in run_checks(tags=["dj_hx"]) if m.id not in silenced]
    if not include_warnings:
        messages = [m for m in messages if m.is_serious(ERROR)]
    return messages


def assert_no_hx_check_issues(*, include_warnings: bool = True) -> None:
    """Fail with the full check output if dj-hx has anything to report."""
    messages = hx_check_messages(include_warnings=include_warnings)
    if not messages:
        return
    lines = [f"dj-hx reported {len(messages)} system check issue(s):", ""]
    for message in messages:
        obj = f"{message.obj}: " if message.obj is not None else ""
        lines.append(f"({message.id}) {obj}{message.msg}")
        if message.hint:
            lines.append(f"    HINT: {message.hint}")
        lines.append("")
    raise AssertionError("\n".join(lines))
