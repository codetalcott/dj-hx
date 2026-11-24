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
- A project template that reads a name nobody supplies, or an attribute an
  object lacks, raises ``HxUndefinedVariable``, naming each one and its
  template:line; a lookup the request's data decides is skipped
  (``_is_a_slip``). The client reads Django's documented ``django.template``
  DEBUG log in each request's own context, which records the lookups
  ``{% if %}`` and ``{% for %}`` swallow too, where ``string_if_invalid`` sees
  none. ``undefined=False`` turns it off.
"""

from __future__ import annotations

import inspect
import json as _json
import logging
import sys
import threading
import warnings
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

from django.core.exceptions import ImproperlyConfigured
from django.test import Client

from .errors import HxError, HxLintError, HxRedirectError, HxUndefinedVariable
from .guard import guard

if TYPE_CHECKING:
    from django.core.checks import CheckMessage
    from django.test.client import _MonkeyPatchedWSGIResponse  # django-stubs' name for what the test client returns

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
    def __init__(
        self,
        *args: Any,
        strict: bool = True,
        lint: bool = True,
        lint_ignore: Iterable[str] = (),
        undefined: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.strict = strict
        self.lint = lint
        self.lint_ignore = tuple(lint_ignore)
        self.undefined = undefined

    def request(self, **request: Any) -> _MonkeyPatchedWSGIResponse:
        where = f"{request.get('REQUEST_METHOD', 'GET')} {request.get('PATH_INFO', '')}"
        with _collecting_lookups() if self.undefined else nullcontext() as lookups:
            response = super().request(**request)
        wsgi_request = getattr(response, "wsgi_request", None)
        findings = guard(wsgi_request, response) if wsgi_request is not None else []
        # A response Django built from an exception (the 500 page renders 500.html from an empty Context on
        # purpose) is not the templates' doing; the test client sets exc_info on it.
        built_from_an_exception = bool(getattr(response, "exc_info", None))
        undefined = lookups.in_project_templates() if lookups is not None and not built_from_an_exception else []
        if undefined:
            findings.append(HxUndefinedVariable(undefined, where))  # recorded like the guard's: response.hx_findings
        if self.strict and findings:
            raise _with_the_rest(findings)
        if self.lint:
            response.hx_lint = self._lint(response, where)  # type: ignore[attr-defined]
        return response

    def _lint(self, response: _MonkeyPatchedWSGIResponse, where: str) -> list[Any]:
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

    def _hx(
        self,
        send: Callable[..., _MonkeyPatchedWSGIResponse],
        url: str,
        full: bool,
        follow: bool | None,
        kwargs: dict[str, Any],
    ) -> _MonkeyPatchedWSGIResponse:
        response = send(url, follow=bool(follow), **hx_headers(full=full), **kwargs)
        if full and follow is None and 300 <= response.status_code < 400:
            raise HxRedirectError(
                f"{send.__name__.upper()} {url.split('?', 1)[0]} answered a full htmx request with a "
                f"{response.status_code} to {response.get('Location', '')!r}. htmx's fetch follows it and swaps the "
                "followed page into <body>. Pass follow=True to get what the browser would show, or follow=False "
                "to assert on the redirect itself."
            )
        return response

    def hx_get(
        self, url: str, data: Any = None, *, full: bool = False, follow: bool | None = None, **kwargs: Any
    ) -> _MonkeyPatchedWSGIResponse:
        """GET as htmx (``data`` -> query string)."""
        return self._hx(self.get, url, full, follow, {"data": data, **kwargs})

    def hx_post(
        self,
        url: str,
        data: Any = None,
        *,
        full: bool = False,
        follow: bool | None = None,
        json: Any = None,
        **kwargs: Any,
    ) -> _MonkeyPatchedWSGIResponse:
        """POST as htmx; ``data`` is form-encoded like FormData, ``json=`` sends JSON."""
        if json is not None:
            data = _json.dumps(json)
            kwargs.setdefault("content_type", "application/json")
        return self._hx(self.post, url, full, follow, {"data": data, **kwargs})

    def hx_put(
        self,
        url: str,
        data: Any = None,
        *,
        full: bool = False,
        follow: bool | None = None,
        json: Any = None,
        **kwargs: Any,
    ) -> _MonkeyPatchedWSGIResponse:
        return self._hx(self.put, url, full, follow, self._body(data, json, kwargs))

    def hx_patch(
        self,
        url: str,
        data: Any = None,
        *,
        full: bool = False,
        follow: bool | None = None,
        json: Any = None,
        **kwargs: Any,
    ) -> _MonkeyPatchedWSGIResponse:
        return self._hx(self.patch, url, full, follow, self._body(data, json, kwargs))

    def hx_delete(
        self,
        url: str,
        data: Any = None,
        *,
        full: bool = False,
        follow: bool | None = None,
        json: Any = None,
        **kwargs: Any,
    ) -> _MonkeyPatchedWSGIResponse:
        """DELETE as htmx. htmx 4 sends DELETE parameters in the query string: pass them in ``url``."""
        if json is not None:
            data = _json.dumps(json)
            kwargs.setdefault("content_type", "application/json")
        return self._hx(self.delete, url, full, follow, {"data": data, **kwargs})

    @staticmethod
    def _body(data: Any, json: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        if json is not None:
            return {"data": _json.dumps(json), "content_type": "application/json", **kwargs}
        if isinstance(data, dict):
            data = urlencode(data)
        return {"data": data or "", "content_type": "application/x-www-form-urlencoded", **kwargs}


def _with_the_rest(findings: list[HxError]) -> HxError:
    """
    The first finding, to raise, carrying the others in its message: a response with three findings
    is fixed in one run, not three. The type stays the first's, so ``pytest.raises(HxNoSwap)`` holds.
    """
    first, *rest = findings
    if rest:
        first.args = (
            f"{first}\n\nAlso recorded on this response, {len(rest)} more:\n  "
            + "\n  ".join(f"{type(f).__name__}: {f}" for f in rest),
        )
    return first


# ------------------------------------------------------- undefined variables
#
# Django logs every lookup that fails to the django.template logger at DEBUG, in Variable._resolve_lookup,
# before any filter runs, so {% if %}, {% for %} and |default are all recorded (measured on 4.2 and 6.1).
# A name its own expression gives a |default is dropped here (_defaulted()): the template says what to show.
# The record names the template the render started from (the child of an {% extends %}, the page that
# {% include %}s an admin template, only the partial's name for a partial), so the place is read from the
# template node being rendered when the record is made: its origin is the file the tag is written in, and
# its token the line.
#
# What counts is what the template's author controls and could misspell: a top-level name nobody supplies,
# and an attribute an object lacks. A lookup whose outcome depends on the request's data does not: see
# _is_a_slip(). Django's exception carries params == (bit, current), the object the bit was looked up on
# (the Context for a top-level name), on 4.2 to 6.1.

_TEMPLATE_LOG = logging.getLogger("django.template")
_FAILED_LOOKUP = "Exception while resolving variable"  # Django's message, the same on 4.2 to 6.1


@dataclass(frozen=True)
class UndefinedLookup:
    """One lookup that failed in a project template: the name, or the attribute after a dot, and where."""

    variable: str
    template: str  # the name its loader knows it by
    line: int | None
    tag: str  # the tag or ``{{ }}`` that reads it
    included: bool = False  # a top-level name read by a template an {% include %} renders

    def __str__(self) -> str:
        line = "" if self.line is None else f":{self.line}"
        where = f"{self.template}{line}: {self.variable!r} in {self.tag}"
        if self.included:
            return f"{where} (an included template: pass it in the include's with, ... {self.variable}=None)"
        return where


class _Lookups:
    """The lookups that fail while one request runs, in its context (``_COLLECTING``)."""

    def __init__(self) -> None:
        self.failed: list[tuple] = []  # (variable, origin, token, included); judged once the request is over
        self.debug_names = _debug_processor_names()

    def take(self, record: logging.LogRecord) -> None:
        # _is_failed_lookup() has passed: the record carries the exception and a tuple of args.
        params: tuple[Any, ...] = getattr(record.exc_info[1] if record.exc_info else None, "params", ())
        current = params[1] if len(params) == 2 else _UNKNOWN
        variable = str(cast(tuple[Any, ...], record.args)[0])
        if _defaulted():
            return
        nodes = _nodes_being_rendered()
        try:
            node = next(nodes, None)
            if node is None or not _is_a_slip(variable, current, node, self.debug_names):
                return  # no node: a Variable resolved outside any template; or a lookup the data decides
            from django.template.context import BaseContext
            from django.template.loader_tags import IncludeNode

            included = isinstance(current, BaseContext) and any(isinstance(outer, IncludeNode) for outer in nodes)
            self.failed.append((variable, node.origin, getattr(node, "token", None), included))
        finally:
            nodes.close()

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
        for variable, origin, token, included in self.failed:
            if origin.name not in project:
                project[origin.name] = origin.name != UNKNOWN_SOURCE and not in_site_packages(origin.name)
            if project[origin.name]:
                template, line = origin.template_name or origin.name, getattr(token, "lineno", None)
                found[UndefinedLookup(variable, template, line, _tag(token), included)] = None
        return list(found)


_UNKNOWN = object()  # the looked-up object, when a VariableDoesNotExist does not carry Django's (bit, current)
_DEBUG_PROCESSOR = "django.template.context_processors.debug"


def _debug_processor_names() -> frozenset[str]:
    """``debug`` and ``sql_queries``, which the debug context processor sets only under DEBUG with INTERNAL_IPS."""
    from django.conf import settings

    configured = any(
        _DEBUG_PROCESSOR in ((backend.get("OPTIONS") or {}).get("context_processors") or ())
        for backend in settings.TEMPLATES
    )
    return frozenset({"debug", "sql_queries"}) if configured else frozenset()


def _is_session(current: object) -> bool:
    """A Django session, which is request data but not a Mapping; never imported here, so no app is needed."""
    sessions = sys.modules.get("django.contrib.sessions.backends.base")  # a session exists only once it is imported
    return sessions is not None and isinstance(current, sessions.SessionBase)


def _is_index(bit: str) -> bool:
    try:
        int(bit)
    except ValueError:
        return False
    return True


def _is_a_slip(variable: str, current: object, node: Any, debug_names: frozenset[str]) -> bool:
    """
    Whether a failed lookup is the template author's to fix: a top-level name nobody supplies, or an
    attribute an object lacks (``{{ user.emial }}``, ``{{ items.length }}``). Not counted, because the
    outcome depends on the request's data: a lookup on None (``{{ obj.rel.name }}`` with no ``rel``), a key a
    mapping or the session lacks (``{% if not request.GET.stage %}``, ``request.session.cart``, so a misspelt
    dict key is silent too), an index past the end of a sequence (``items.0`` on ``[]``; a string's index
    still counts), whatever ``{% firstof %}`` reads, and the names the debug context processor sets only
    under DEBUG.
    """
    from django.template.context import BaseContext
    from django.template.defaulttags import FirstOfNode

    if isinstance(node, FirstOfNode):
        return False
    if isinstance(current, BaseContext):
        return variable not in debug_names
    if current is None or isinstance(current, Mapping) or _is_session(current):
        return False
    if _is_index(variable) and hasattr(current, "__getitem__") and not isinstance(current, (str, bytes)):
        return False
    return True


def _defaulted() -> bool:
    """
    Whether the lookup failing now is the variable of an expression that applies ``|default``
    (``{{ x|default:"-" }}``, ``{% if x|lower|default:y %}``), which renders the fallback. A missing argument,
    the ``y`` of ``{{ x|default:y }}``, is not this: Django raises VariableDoesNotExist for it. Nor is
    ``|default_if_none``: a missing name is not None, so ``{{ x|default_if_none:"-" }}`` renders '' (both
    measured on Django 6.0.5). Read from the stack, where ``FilterExpression.resolve`` calls the ``Variable``
    whose lookup Django is logging.
    """
    from django.template.base import FilterExpression, Variable
    from django.template.defaultfilters import default

    frame = inspect.currentframe()
    variable = None
    try:
        while frame is not None:
            owner = frame.f_locals.get("self")
            if variable is None and isinstance(owner, Variable):
                variable = owner
            elif isinstance(owner, FilterExpression):
                return owner.var is variable and any(func is default for func, _ in owner.filters)
            frame = frame.f_back
        return False
    finally:
        del frame


def _tag(token: Any) -> str:
    from django.template.base import TokenType

    if token is None:
        return "a tag"
    return f"{{{{ {token.contents} }}}}" if token.token_type is TokenType.VAR else f"{{% {token.contents} %}}"


def _nodes_being_rendered() -> Generator[Any, None, None]:
    """The template nodes on this thread's stack, innermost (the tag or ``{{ }}`` being rendered) first."""
    from django.template.base import Node

    frame = inspect.currentframe()
    try:
        while frame is not None:
            node = frame.f_locals.get("self")
            if isinstance(node, Node) and getattr(node, "origin", None) is not None:
                yield node
            frame = frame.f_back
    finally:
        del frame


def _is_failed_lookup(record: logging.LogRecord) -> bool:
    """Django's record of a name or attribute that does not exist; not a lookup that raised an exception Django silences."""
    from django.template.base import VariableDoesNotExist

    exception = record.exc_info[1] if record.exc_info else None
    return (
        isinstance(record.msg, str)
        and record.msg.startswith(_FAILED_LOOKUP)
        and isinstance(exception, VariableDoesNotExist)
        and isinstance(record.args, tuple)
        and bool(record.args)
    )


class _Gate(logging.Filter):
    """
    On the ``django.template`` logger while any HxTestClient request runs. It hands each failed lookup to
    the request whose context it is made in (``_COLLECTING``), then passes on only the records the logger
    delivered before its level was lowered to DEBUG, so no handler sees a record it would not have seen.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _is_failed_lookup(record):
            lookups = _COLLECTING.get()
            if lookups is not None:
                lookups.take(record)
        return record.levelno >= _saved["delivered_from"]


# The request a lookup belongs to. A context variable, not the thread: asgiref carries it into the thread
# an async view runs on and through sync_to_async, while a plain thread or a ThreadPoolExecutor worker
# starts without it, so a render there is no request's.
_COLLECTING: ContextVar[_Lookups | None] = ContextVar("dj_hx_collecting_lookups", default=None)
_GATE = _Gate()
_lock = threading.Lock()
_active: list[_Lookups] = []  # one per request running now, nested clients included: the gate stays while any runs
_saved: dict[str, int] = {}  # the logger's own level and the level it delivered from, before the first request


@contextmanager
def _collecting_lookups() -> Iterator[_Lookups]:
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
    token = _COLLECTING.set(lookups)
    try:
        yield lookups
    finally:
        _COLLECTING.reset(token)
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


def hx_check_messages(*, include_warnings: bool = True) -> list[CheckMessage]:
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
