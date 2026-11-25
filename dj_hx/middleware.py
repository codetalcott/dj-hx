"""
``HxMiddleware``: ``Vary`` on every response, the guard, the messages bridge,
and under ``DEBUG`` the lint over every htmx response.

Nothing here raises a finding, so a false positive cannot 500 a site in
production: findings, the messages bridge's included (a messages partial that
is missing or whose root is not its name), are recorded on
``response.hx_findings`` and logged to ``dj_hx``; ``HxTestClient`` is where
they become exceptions. A project template that fails to render raises here
as it would on any page.
List it after ``MessageMiddleware`` (its response phase must run before the
messages are stored) and, like every middleware, after ``CommonMiddleware``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase

from .guard import findings_of, guard, is_html
from .messages import bridge_messages
from .request import REQUEST_TYPE_HEADER, is_htmx, vary_on_hx

logger = logging.getLogger("dj_hx")


class HxMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
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

    def observe(self, request: HttpRequest, response: HttpResponseBase) -> None:
        """Under DEBUG: the lint over every htmx response. (``X-HX-Template`` is the verb's to set: ``verbs._response``.)"""
        if not isinstance(response, HttpResponse) or not is_html(response) or response.status_code >= 500:
            return
        from . import hxlint
        from .templates import project_script_attributes

        body = response.content.decode(response.charset or "utf-8", errors="replace")
        ignore = set(getattr(settings, "HX_LINT_IGNORE", ()))
        named = project_script_attributes()
        for finding in hxlint.lint_html(body, extensions=getattr(settings, "HX_EXTENSIONS", ()), script_attributes=named):
            if finding.rule in ignore or finding.severity == "info":
                continue
            log = logger.error if finding.severity == "error" else logger.warning
            log("hx lint: %s %s: %s", request.method, request.path, finding)
