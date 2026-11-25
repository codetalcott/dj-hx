"""
The messages framework as the flash bridge.

``messages.success(request, "Deleted!")`` is stored for the next full page
render, so on a fragment response it would appear on some later page load.
The bridge, run by ``HxMiddleware``, renders pending messages through the
project's messages partial and appends them as an ``<hx-partial>``::

    HX_MESSAGES_TEMPLATE = "layout.html#messages"   # root element must be id="messages"

It peeks before it consumes, and consumes only once it knows it will append.
A response whose own template already showed the messages is left alone.
The middleware must be listed *after* ``MessageMiddleware`` so its response
phase runs first, before the messages are written back to the cookie or
session; check ``dj_hx.E002`` says so.

The bridge runs inside ``HxMiddleware``, which never raises a finding: a
messages partial that is missing, or whose root is not ``id="<name>"``, is
recorded on the response instead (``HxUnknownPartial``, ``HxPartialRootId``),
and its messages wait for the next page. Raising there would turn every
fragment response that carries a message into a 500.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest
from django.http.response import HttpResponseBase

from .errors import HxError, HxMessagesUnconfigured
from .guard import findings_of
from .request import who
from .verbs import check_root_id, render_partial, wrap_partial

__all__ = ["bridge_messages", "messages_template", "pending_messages"]


def messages_template() -> tuple[str, str] | None:
    """``("layout.html", "messages")`` from ``HX_MESSAGES_TEMPLATE``, or None."""
    value = getattr(settings, "HX_MESSAGES_TEMPLATE", None)
    if not value:
        return None
    template, _, name = str(value).partition("#")
    return template, name or "messages"


def pending_messages(request: HttpRequest) -> int:
    """How many messages are waiting, without consuming them."""
    try:
        from django.contrib.messages import get_messages
    except ImportError:
        return 0
    from django.contrib.messages.storage.base import BaseStorage

    storage = get_messages(request)
    if not isinstance(storage, BaseStorage) or not storage:  # a request without the middleware gets a plain list
        return 0
    if storage.used:
        # The response already showed them: its template iterated the storage, which consumes it. One added
        # after that waits for the next page, as Django keeps it.
        return 0
    count = len(list(storage))
    storage.used = False  # peeked, not consumed (the documented way)
    return count


def bridge_messages(request: HttpRequest, response: HttpResponseBase) -> None:
    """Append pending messages to a fragment response; records a finding if it cannot, and never raises one."""
    if getattr(response, "hx_kind", None) == "navigate":
        return  # htmx swaps nothing and loads a page, which shows the messages
    if not pending_messages(request):
        return
    configured = messages_template()
    if configured is None:
        findings_of(response).append(
            HxMessagesUnconfigured(
                f"{who(request)} added messages while answering a fragment request, and HX_MESSAGES_TEMPLATE is not set; "
                'they would appear on some later page load instead. Set HX_MESSAGES_TEMPLATE = "layout.html#messages".'
            )
        )
        return
    template, name = configured
    from django.contrib.messages import get_messages
    from django.contrib.messages.storage.base import BaseStorage

    storage = get_messages(request)
    if not isinstance(storage, BaseStorage):  # pending_messages() found none: no MessageMiddleware
        return
    try:
        # Rendering iterates the storage, which consumes the messages.
        html = render_partial(template, name, {"messages": storage}, request)
        check_root_id(html, name, f"{template}#{name}")
    except HxError as exc:
        storage.used = False  # not shown, so kept for the next page (the documented way, as pending_messages peeks)
        findings_of(response).append(exc)
        return
    response.write(wrap_partial(name, html))
