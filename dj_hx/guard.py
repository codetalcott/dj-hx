"""
What htmx 4 would do silently with a response, said out loud.

``guard(request, response)`` returns the findings for one response: a 204 or
a whole page answering a request that targets an element, whoever built the
response, ``APPEND_SLASH``'s redirect of such a request, and an htmx request
that is not htmx 4. A body htmx will not swap (``HX-Redirect``, ``HX-Refresh``,
``HX-Location``) is not judged. ``HX_REQUIRE_VERBS`` adds what only the verbs'
stance rules out: any other 3xx, and a response no verb built.
``HxMiddleware`` records and logs them; ``HxTestClient`` raises them. The
verbs record their own findings the same way, so ``response.hx_findings`` is
the one place to look.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase

from .errors import HxBareResponse, HxError, HxNoSwap, HxPageIntoFragment, HxProtocolError, HxRedirectIntoFragment
from .request import REQUEST_TYPE_HEADER, is_htmx, protocol_message, who

__all__ = ["guard", "findings_of", "is_html", "is_document", "navigates"]

# htmx 4.0.2's own test, from its swap (``#Ie``): drop the first <head>, then a body whose first tag is <html> or
# <body> is parsed as a document, and that document's body is what goes into the target.
_HEAD = re.compile(r"<head(\s[^>]*)?>[\s\S]*?</head>", re.IGNORECASE)
_FIRST_TAG = re.compile(r"<([a-z][^/>\x20\t\r\n\f]*)", re.IGNORECASE)


def is_html(response: HttpResponseBase) -> bool:
    """A response whose body htmx would swap: not streamed, and ``text/html``."""
    return (
        not getattr(response, "streaming", False)
        and (response.get("Content-Type") or "").startswith("text/html")
    )


def is_document(response: HttpResponseBase) -> bool:
    """A body htmx 4 would read as a whole document, so it swaps that page's body into the target."""
    if not isinstance(response, HttpResponse):
        return False
    body = response.content.decode(response.charset or "utf-8", errors="replace")
    first = _FIRST_TAG.search(_HEAD.sub("", body, count=1))
    return first is not None and first.group(1).lower() in ("html", "body")


def navigates(response: HttpResponseBase) -> bool:
    """``HX-Refresh: true``, ``HX-Redirect`` or ``HX-Location``: htmx 4 obeys it before any swap, so it swaps none of the body."""
    return response.get("HX-Refresh") == "true" or bool(response.get("HX-Redirect")) or bool(response.get("HX-Location"))


def findings_of(response: HttpResponseBase) -> list[HxError]:
    """The findings recorded on a response so far (never raises)."""
    found = getattr(response, "hx_findings", None)
    if found is None:
        found = []
        response.hx_findings = found  # type: ignore[attr-defined]  # any response can carry findings
    return found


def _routing_redirect(request: HttpRequest, response: HttpResponseBase) -> bool:
    """
    True when the 3xx (or the 404 CommonMiddleware will turn into one) is
    ``APPEND_SLASH``'s fix-up rather than a handler's decision.

    CommonMiddleware issues that redirect in ``process_response`` from a 404,
    so a middleware listed after it sees the 404 and one listed before it sees
    the 301. Both are recognised here.
    """
    location = response.get("Location", "")
    if 300 <= response.status_code < 400:
        return location.split("?", 1)[0] == request.path + "/"
    if response.status_code == 404 and getattr(settings, "APPEND_SLASH", True):
        from django.middleware.common import CommonMiddleware

        try:
            return CommonMiddleware(lambda request: HttpResponse()).should_redirect_with_slash(request)  # never called
        except Exception:
            return False
    return False


def guard(request: HttpRequest, response: HttpResponseBase) -> list[HxError]:
    """Record the findings for ``response`` and return them all."""
    found = findings_of(response)
    if getattr(response, "hx_guarded", False):
        return found
    response.hx_guarded = True  # type: ignore[attr-defined]

    if not is_htmx(request):
        return found
    rtype = request.headers.get(REQUEST_TYPE_HEADER)
    if rtype not in ("full", "partial"):
        found.append(HxProtocolError(protocol_message(request)))
        return found
    if rtype != "partial":
        return found

    status = response.status_code
    if _routing_redirect(request, response):
        found.append(
            HxRedirectIntoFragment(
                f"{who(request)} got a redirect from APPEND_SLASH: the control's URL {request.path!r} is missing its "
                "trailing slash, and fetch will follow the 301 into an element that is not the body. Match the route "
                "exactly ({% url %} does)."
            )
        )
        return found
    if 300 <= status < 400:
        # fetch follows it with the same headers, so the request it makes is guarded in its turn: a page at the
        # other end is recorded there. Only HX_REQUIRE_VERBS records the redirect itself.
        if _verbs_required():
            found.append(
                HxRedirectIntoFragment(
                    f"{who(request)} answered a request that targets an element with a {status} (HX_REQUIRE_VERBS is "
                    "set); fetch follows it with the same headers and swaps whatever that URL answers into the element. "
                    "Use redirect() on a body-targeted control, navigate() to leave the page (a login check, an expired "
                    "session), or return a fragment."
                )
            )
        return found
    if navigates(response):
        return found
    if status == 204:
        found.append(
            HxNoSwap(
                f"{who(request)} answered a request that targets an element with a 204; htmx 4 does not swap it. "
                'Use removed() with hx-swap="delete", or return a fragment.'
            )
        )
    elif status < 300 and is_html(response) and is_document(response):
        found.append(
            HxPageIntoFragment(
                f"{who(request)} answered a request that targets an element with a whole page (its first tag is "
                "<html> or <body>); htmx 4 swaps that page's body into the element, inside the page already there. "
                "Return a fragment (render(request, template, partial), fragment()), or give the control "
                'hx-target="body". If a redirect led here, fetch followed it with the same headers: change the view '
                "that redirected (navigate() leaves the page)."
            )
        )
    elif status < 300 and is_html(response) and not _built_by_a_verb(response) and _verbs_required():
        found.append(
            HxBareResponse(
                f"{who(request)} answered a request that targets an element with a response no verb built "
                "(django.shortcuts.render, a plain HttpResponse, a TemplateResponse), so the verbs' checks did not "
                "run on it (HX_REQUIRE_VERBS is set). Use render(request, template, partial), fragment(), text() "
                "or removed()."
            )
        )
    return found


def _verbs_required() -> bool:
    return bool(getattr(settings, "HX_REQUIRE_VERBS", False))


def _built_by_a_verb(response: HttpResponseBase) -> bool:
    from .verbs import HxResponse

    return isinstance(response, HxResponse)
