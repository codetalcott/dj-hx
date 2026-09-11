"""
The request side, read from headers and nothing else.

htmx 4 says what it can do with the answer in one header: ``HX-Request-Type``
is ``full`` when the control targets ``<body>`` (or is boosted, or sets
``hx-select``) and ``partial`` otherwise. That is the only client-side fact a
handler needs. ``HX-Source`` and ``HX-Target`` are also sent; nothing here
reads them, on purpose: a handler that branches on an element id is dead code
the moment the template is edited.
"""

from django.utils.cache import patch_vary_headers

from .errors import HxProtocolError

REQUEST_HEADER = "HX-Request"
REQUEST_TYPE_HEADER = "HX-Request-Type"
VARY_HEADERS = ("HX-Request", "HX-Request-Type")

__all__ = [
    "REQUEST_HEADER",
    "REQUEST_TYPE_HEADER",
    "VARY_HEADERS",
    "is_htmx",
    "request_type",
    "wants_page",
    "wants_fragment",
    "current_url",
    "vary_on_hx",
    "who",
]


def is_htmx(request) -> bool:
    """``HX-Request: true``."""
    return request.headers.get(REQUEST_HEADER) == "true"


def request_type(request) -> str | None:
    """``"full"``, ``"partial"``, or ``None`` for a browser. Raises on htmx without htmx 4."""
    if not is_htmx(request):
        return None
    rtype = request.headers.get(REQUEST_TYPE_HEADER)
    if rtype not in ("full", "partial"):
        raise HxProtocolError(
            f"{who(request)}: HX-Request is set but HX-Request-Type is not; this needs htmx 4. "
            "A proxy stripping headers, or an htmx 2 client, are the usual causes."
        )
    return rtype


def wants_page(request) -> bool:
    """A browser, a boosted link, or a control that targets the body."""
    return request_type(request) != "partial"


def wants_fragment(request) -> bool:
    """A control that targets an element."""
    return request_type(request) == "partial"


def current_url(request) -> str | None:
    return request.headers.get("HX-Current-URL")


def vary_on_hx(response):
    """Every URL that answers differently by request type must say so to caches."""
    patch_vary_headers(response, VARY_HEADERS)
    return response


def who(request) -> str:
    """``contacts_view()`` for messages: the routed view, else method and path."""
    match = getattr(request, "resolver_match", None)
    func = getattr(match, "func", None)
    if func is not None:
        cls = getattr(func, "view_class", None)
        name = cls.__name__ if cls is not None else getattr(func, "__name__", None)
        if name:
            return f"{name}()"
    return f"{request.method} {request.path}"
