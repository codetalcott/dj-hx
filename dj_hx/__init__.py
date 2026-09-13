"""
dj-hx: handler-first htmx 4 for Django.

The handler owns every response-side decision and says so through htmx 4's
own protocol; the template keeps the request-side controls; fragments are
partials of the page template. See README.md.
"""

__version__ = "0.1.0"

from .errors import (
    HxBareResponse,
    HxError,
    HxFragmentIntoPage,
    HxLintError,
    HxMessagesUnconfigured,
    HxNoSwap,
    HxPageIntoFragment,
    HxPartialRootId,
    HxProtocolError,
    HxRedirectError,
    HxRedirectIntoFragment,
    HxUnknownPartial,
)
from .mixins import HxMixin
from .request import current_url, is_htmx, request_type, vary_on_hx, wants_fragment, wants_page
from .verbs import HxRedirectResponse, HxResponse, fragment, invalid, navigate, page, redirect, removed, render, text

__all__ = [
    "render", "page", "fragment", "invalid", "redirect", "navigate", "removed", "text",
    "is_htmx", "request_type", "wants_page", "wants_fragment", "current_url", "vary_on_hx",
    "HxResponse", "HxRedirectResponse", "HxMixin",
    "HxError", "HxProtocolError", "HxPageIntoFragment", "HxFragmentIntoPage", "HxRedirectIntoFragment",
    "HxNoSwap", "HxBareResponse", "HxUnknownPartial", "HxPartialRootId", "HxMessagesUnconfigured", "HxLintError", "HxRedirectError",
]
