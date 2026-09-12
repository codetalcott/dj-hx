"""
``HxMiddleware``: ``Vary`` on every response, the guard, the messages bridge,
and under ``DEBUG`` the lint and the template each fragment came from.

Nothing here raises. Findings are recorded on ``response.hx_findings`` and
logged to ``dj_hx``; ``HxTestClient`` is where they become exceptions.
List it after ``MessageMiddleware`` (its response phase must run before the
messages are stored) and, like every middleware, after ``CommonMiddleware``.
"""

from __future__ import annotations

import logging

from django.conf import settings

from .guard import findings_of, guard, is_html
from .messages import bridge_messages
from .request import REQUEST_TYPE_HEADER, is_htmx, vary_on_hx

logger = logging.getLogger("dj_hx")


class HxMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        vary_on_hx(response)
        findings = findings_of(response)
        already_logged = len(findings)  # the verbs log what they record
        guard(request, response)
        partial = is_htmx(request) and request.headers.get(REQUEST_TYPE_HEADER) == "partial"
        if partial and response.status_code < 300 and response.status_code != 204 and is_html(response):
            bridge_messages(request, response)
        for finding in findings[already_logged:]:
            logger.warning("hx: %s", finding)
        if settings.DEBUG and is_htmx(request):
            self.observe(request, response)
        return response

    def observe(self, request, response) -> None:
        """Under DEBUG: the lint over every htmx response, and where it came from."""
        template = getattr(response, "hx_template", None)
        if template:
            response["X-HX-Template"] = template
        if not is_html(response) or response.status_code >= 500:
            return
        from . import hxlint

        body = response.content.decode(response.charset or "utf-8", errors="replace")
        ignore = set(getattr(settings, "HX_LINT_IGNORE", ()))
        for finding in hxlint.lint_html(body, extensions=getattr(settings, "HX_EXTENSIONS", ())):
            if finding.rule in ignore or finding.severity == "info":
                continue
            log = logger.error if finding.severity == "error" else logger.warning
            log("hx lint: %s %s: %s", request.method, request.path, finding)
