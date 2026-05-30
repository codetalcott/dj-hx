"""
dj-htmx-cbv: class-based-view ergonomics for Django + HTMX 4.

This is the HTMX-4 sibling of dj-fixi. It deliberately does NOT reimplement the
HTMX wire protocol — django-htmx already provides ``request.htmx``,
``trigger_client_event()``, and ``reswap``/``retarget``/``reselect`` helpers, all of
which map onto HTMX 4's (unchanged) ``HX-*`` header contract. This package ports only
dj-fixi's genuinely useful, protocol-agnostic ergonomics on top:

  * HxView           — fragment vs full-page template negotiation
  * HxResponseMixin  — form_valid/form_invalid that render fragments and fire
                       client events via django-htmx (a real capability Fixi lacked)
  * HxTestClient     — a test client that sends HTMX-shaped requests

Unlike Fixi (default swap ``outerHTML``, reads no response headers), HTMX defaults to
``innerHTML`` and consumes server response headers — so the features that are inert in
dj-fixi (FX-Trigger events, server-driven retarget/reswap) work natively here.

Status: Phase B (lean) — HxView, HxResponseMixin (configurable 422), the protocol-agnostic
ContextPersistence/OptimizedQuery mixins, and a thin HxTestClient are implemented. Out of
scope by design: form-rendering helpers.
"""

from .mixins import ContextPersistenceMixin, HxResponseMixin, OptimizedQueryMixin
from .testing import HxTestClient
from .views import HxTemplateView, HxView, is_htmx_request, is_partial_request

__version__ = "0.1.0"

__all__ = [
    "HxView",
    "HxTemplateView",
    "HxResponseMixin",
    "ContextPersistenceMixin",
    "OptimizedQueryMixin",
    "HxTestClient",
    "is_htmx_request",
    "is_partial_request",
]
