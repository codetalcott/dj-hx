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
- A project template that reads a variable that does not exist raises
  ``HxUndefinedVariable``, naming each one and its template:line. The client
  reads Django's documented ``django.template`` DEBUG log while it runs a
  request, which records the lookups ``{% if %}`` and ``{% for %}`` swallow
  too, where ``string_if_invalid`` sees none. ``undefined=False`` turns it off.
"""

from __future__ import annotations

import inspect
import json as _json
import logging
import threading
import warnings
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.exceptions import ImproperlyConfigured
from django.test import Client

from .errors import HxLintError, HxRedirectError, HxUndefinedVariable
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
    def __init__(self, *args, strict: bool = True, lint: bool = True, lint_ignore=(), undefined: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.strict = strict
        self.lint = lint
        self.lint_ignore = tuple(lint_ignore)
        self.undefined = undefined

    def request(self, **request):
        where = f"{request.get('REQUEST_METHOD', 'GET')} {request.get('PATH_INFO', '')}"
        with _collecting_lookups() if self.undefined else nullcontext() as lookups:
            response = super().request(**request)
        wsgi_request = getattr(response, "wsgi_request", None)
        findings = guard(wsgi_request, response) if wsgi_request is not None else []
        undefined = lookups.in_project_templates() if lookups is not None else []
        if undefined:
            findings.append(HxUndefinedVariable(undefined, where))  # recorded like the guard's: response.hx_findings
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


# ------------------------------------------------------- undefined variables
#
# Django logs every lookup that fails to the django.template logger at DEBUG, in Variable._resolve_lookup,
# before any filter runs, so {% if %}, {% for %} and |default are all recorded (measured on 4.2 and 6.1).
# The record names the template the render started from (the child of an {% extends %}, the page that
# {% include %}s an admin template, only the partial's name for a partial), so the place is read from the
# template node being rendered when the record is made: its origin is the file the tag is written in, and
# its token the line.

_TEMPLATE_LOG = logging.getLogger("django.template")
_FAILED_LOOKUP = "Exception while resolving variable"  # Django's message, the same on 4.2 to 6.1


@dataclass(frozen=True)
class UndefinedLookup:
    """One lookup that failed in a project template: the name, or the attribute after a dot, and where."""

    variable: str
    template: str  # the name its loader knows it by
    line: int | None
    tag: str  # the tag or ``{{ }}`` that reads it

    def __str__(self):
        line = "" if self.line is None else f":{self.line}"
        return f"{self.template}{line}: {self.variable!r} in {self.tag}"


class _Lookups:
    """The lookups that fail while one request runs, on the thread that runs it."""

    def __init__(self):
        self.thread = threading.get_ident()
        self.failed: list[tuple] = []  # (variable, origin, token); judged once the request is over

    def take(self, record) -> None:
        node = _rendering_node()
        if node is not None:  # None: a Variable resolved outside any template
            self.failed.append((str(record.args[0]), node.origin, getattr(node, "token", None)))

    def in_project_templates(self) -> list[UndefinedLookup]:
        """
        The failed lookups written in the project's templates, each once. A template in site-packages
        (``templates.in_site_packages``, so Django's own, admin's and any pip-installed app's) is not the
        project's, and neither is one built from a string, which has no file: Django builds its debug and
        CSRF-failure pages that way.
        """
        from django.template.base import UNKNOWN_SOURCE

        from .templates import in_site_packages

        project: dict[str, bool] = {}
        found: dict[UndefinedLookup, None] = {}
        for variable, origin, token in self.failed:
            if origin.name not in project:
                project[origin.name] = origin.name != UNKNOWN_SOURCE and not in_site_packages(origin.name)
            if project[origin.name]:
                found[UndefinedLookup(variable, origin.template_name or origin.name, getattr(token, "lineno", None), _tag(token))] = None
        return list(found)


def _tag(token) -> str:
    from django.template.base import TokenType

    if token is None:
        return "a tag"
    return f"{{{{ {token.contents} }}}}" if token.token_type is TokenType.VAR else f"{{% {token.contents} %}}"


def _rendering_node():
    """The innermost template node on this thread's stack (the tag or ``{{ }}`` being rendered), or None."""
    from django.template.base import Node

    frame = inspect.currentframe()
    try:
        while frame is not None:
            node = frame.f_locals.get("self")
            if isinstance(node, Node) and getattr(node, "origin", None) is not None:
                return node
            frame = frame.f_back
        return None
    finally:
        del frame


def _is_failed_lookup(record) -> bool:
    """Django's record of a name or attribute that does not exist; not a lookup that raised an exception Django silences."""
    from django.template.base import VariableDoesNotExist

    exception = record.exc_info[1] if record.exc_info else None
    return (
        isinstance(record.msg, str)
        and record.msg.startswith(_FAILED_LOOKUP)
        and isinstance(exception, VariableDoesNotExist)
        and bool(record.args)
    )


class _Gate(logging.Filter):
    """
    On the ``django.template`` logger while any HxTestClient request runs. It hands each failed lookup to
    the innermost request running on its thread, then passes on only the records the logger delivered
    before its level was lowered to DEBUG, so no handler sees a record it would not have seen.
    """

    def filter(self, record):
        if _is_failed_lookup(record):
            thread = threading.get_ident()
            for lookups in reversed(_active):
                if lookups.thread == thread:
                    lookups.take(record)
                    break
        return record.levelno >= _saved["delivered_from"]


_GATE = _Gate()
_lock = threading.Lock()
_active: list[_Lookups] = []  # one per request running now: nested clients and threads included
_saved: dict[str, int] = {}  # the logger's own level and the level it delivered from, before the first request


@contextmanager
def _collecting_lookups():
    """
    Collect the template lookups that fail while the block runs. The first request lowers the logger's
    level and attaches the gate; the last one to finish, raising or not, takes both back.
    """
    blind = _why_blind()
    if blind:
        raise ImproperlyConfigured(blind)
    lookups = _Lookups()
    with _lock:
        if not _active:
            _saved.update(level=_TEMPLATE_LOG.level, delivered_from=_TEMPLATE_LOG.getEffectiveLevel())
            _TEMPLATE_LOG.setLevel(logging.DEBUG)
            _TEMPLATE_LOG.filters.insert(0, _GATE)  # first, so a filter of the project's cannot hide a record from it
        _active.append(lookups)
    try:
        yield lookups
    finally:
        with _lock:
            _active.remove(lookups)
            if not _active:
                _TEMPLATE_LOG.removeFilter(_GATE)
                _TEMPLATE_LOG.setLevel(_saved["level"])


def _why_blind() -> str | None:
    """Why Django would write no record for the client to read, or None."""
    head = "HxTestClient cannot see undefined template variables: "
    tail = ", or pass HxTestClient(undefined=False) to go without the check."
    disabled = logging.root.manager.disable
    if disabled >= logging.DEBUG:
        return (
            f"{head}logging.disable({logging.getLevelName(disabled)}) is in force, so Django never writes the "
            "django.template records the check reads. Lift it around the tests that use HxTestClient "
            f"(logging.disable(logging.NOTSET)){tail}"
        )
    if _TEMPLATE_LOG.disabled:
        return (
            f"{head}the django.template logger is disabled, as a LOGGING dictConfig whose "
            "disable_existing_loggers is left True disables every logger that exists when it runs. Set "
            f"disable_existing_loggers to False{tail}"
        )
    return None


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
