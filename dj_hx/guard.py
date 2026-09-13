"""
What htmx 4 would do silently with a response, said out loud.

``guard(request, response)`` returns the findings for one response: a 3xx, a
204, or a response no verb built answering a request that targets an element,
an htmx request that is not htmx 4, messages pending on a fragment response
with nowhere to go.
``HxMiddleware`` records and logs them; ``HxTestClient`` raises them. The
verbs record their own findings the same way, so ``response.hx_findings`` is
the one place to look.
"""

from __future__ import annotations

from django.conf import settings

from .errors import HxBareResponse, HxError, HxNoSwap, HxProtocolError, HxRedirectIntoFragment
from .request import REQUEST_TYPE_HEADER, is_htmx, who

__all__ = ["guard", "findings_of", "is_html"]


def is_html(response) -> bool:
    """A response whose body htmx would swap: not streamed, and ``text/html``."""
    return (
        not getattr(response, "streaming", False)
        and (response.get("Content-Type") or "").startswith("text/html")
    )


def findings_of(response) -> list[HxError]:
    """The findings recorded on a response so far (never raises)."""
    found = getattr(response, "hx_findings", None)
    if found is None:
        found = response.hx_findings = []
    return found


def _routing_redirect(request, response) -> bool:
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
            return CommonMiddleware(lambda r: None).should_redirect_with_slash(request)
        except Exception:
            return False
    return False


def guard(request, response) -> list[HxError]:
    """Record the findings for ``response`` and return them all."""
    found = findings_of(response)
    if getattr(response, "hx_guarded", False):
        return found
    response.hx_guarded = True

    if not is_htmx(request):
        return found
    rtype = request.headers.get(REQUEST_TYPE_HEADER)
    if rtype not in ("full", "partial"):
        found.append(
            HxProtocolError(
                f"{who(request)}: HX-Request is set but HX-Request-Type is not; this needs htmx 4. "
                "A proxy stripping headers, or an htmx 2 client, are the usual causes. "
                'HX_REQUEST_TYPE_FALLBACK = "full" answers such requests with the page instead of raising.'
            )
        )
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
    elif 300 <= status < 400:
        found.append(
            HxRedirectIntoFragment(
                f"{who(request)} answered a request that targets an element with a {status}; fetch will follow it "
                "and swap the page into that element. Use redirect() on a body-targeted control, navigate() to leave "
                "the page (a login check, an expired session), or return a fragment."
            )
        )
    elif status == 204:
        found.append(
            HxNoSwap(
                f"{who(request)} answered a request that targets an element with a 204; htmx 4 does not swap it. "
                'Use removed() with hx-swap="delete", or return a fragment.'
            )
        )
    elif status < 300 and is_html(response) and not _built_by_a_verb(response):
        found.append(
            HxBareResponse(
                f"{who(request)} answered a request that targets an element with a response no verb built "
                "(django.shortcuts.render, a plain HttpResponse, a TemplateResponse); whether it is a page or a "
                "fragment cannot be checked, and django.shortcuts.render sends the whole page into the element. "
                "Use render(request, template, partial), fragment(), text() or removed(), or HxMixin on a "
                "generic view."
            )
        )
    return found


def _built_by_a_verb(response) -> bool:
    from .verbs import HxResponse

    return isinstance(response, HxResponse)
