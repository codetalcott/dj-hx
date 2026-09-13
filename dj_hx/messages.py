"""
The messages framework as the flash bridge.

``messages.success(request, "Deleted!")`` is stored for the next full page
render, so on a fragment response it would appear on some later page load.
The bridge, run by ``HxMiddleware``, renders pending messages through the
project's messages partial and appends them as an ``<hx-partial>``::

    HX_MESSAGES_TEMPLATE = "layout.html#messages"   # root element must be id="messages"

It peeks before it consumes, and consumes only once it knows it will append.
The middleware must be listed *after* ``MessageMiddleware`` so its response
phase runs first, before the messages are written back to the cookie or
session; check ``dj_hx.E002`` says so.
"""

from __future__ import annotations

from django.conf import settings

from .errors import HxMessagesUnconfigured
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


def pending_messages(request) -> int:
    """How many messages are waiting, without consuming them."""
    try:
        from django.contrib.messages import get_messages
    except ImportError:
        return 0
    storage = get_messages(request)
    if not storage:
        return 0
    count = len(list(storage))
    storage.used = False  # peeked, not consumed (the documented way)
    return count


def bridge_messages(request, response) -> None:
    """Append pending messages to a fragment response; records a finding if it cannot."""
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

    # Rendering iterates the storage, which consumes the messages.
    html = render_partial(template, name, {"messages": get_messages(request)}, request)
    check_root_id(html, name, f"{template}#{name}")
    response.write(wrap_partial(name, html))
