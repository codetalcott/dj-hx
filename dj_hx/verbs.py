"""
The response verbs. A handler names the outcome; the verb speaks htmx 4.

::

    from dj_hx import render, page, fragment, invalid, redirect, removed, text

    def contacts(request):
        return render(request, "index.html", "rows", {"contacts": Contact.all()})

``render`` sends the page to a browser or a boosted link and the partial
``rows`` of the same template to a control that targets an element. On
Django 6 a partial is ``{% partialdef rows inline %}`` inside the page
template; on 4.2 to 5.x install django-template-partials. A name containing a
dot (``rows.html``) is a separate template file instead.

Nothing here changes a target or a swap from a header, and nothing here reads
``HX-Source`` or ``HX-Target``. The three rules that cause most mistakes:

1. Never ``return HttpResponseRedirect(...)``, ``HttpResponse("")`` or a 204
   to an htmx request. Say what happened: ``redirect``, ``removed``, ``text``.
2. Never read ``HX-Source`` or ``HX-Target``. The real question is whether the
   client asked for a page or a fragment: ``wants_page(request)``.
3. A partial used as an ``<hx-partial>`` (``.partial("count")``, the messages
   partial) must have a root element whose ``id`` is the partial's name.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from django.http.response import HttpResponseRedirectBase
from django.shortcuts import resolve_url
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.utils.html import escape

from .errors import (
    HxError,
    HxFragmentIntoPage,
    HxPageIntoFragment,
    HxPartialRootId,
    HxRedirectIntoFragment,
    HxUnknownPartial,
)
from .request import is_htmx, vary_on_hx, wants_fragment, wants_page, who

__all__ = [
    "HxResponse",
    "HxRedirectResponse",
    "render",
    "page",
    "fragment",
    "invalid",
    "redirect",
    "removed",
    "text",
    "render_partial",
    "wrap_partial",
    "check_root_id",
]

logger = logging.getLogger("dj_hx")


# ------------------------------------------------------------------- responses


class _HxResponseMethods:
    """The handler-side vocabulary on a response."""

    hx_kind: str = "page"  # page | fragment | text | removed | redirect
    hx_template: str | None = None  # where the body came from: "index.html" or "index.html#rows"
    hx_page_template: str | None = None  # the page template, for .partial()
    hx_context: dict[str, Any] | None = None
    hx_request = None

    def trigger(self, name: str, *, target: str = "body", **detail: Any):
        """
        Announce ``name`` to the page after the swap.

        Always the JSON form and always with a ``target``: after a ``delete``
        swap the element that made the request is gone and htmx 4 would
        dispatch on ``document``, where a ``from:body`` listener cannot hear
        it (htmx.js 4.0.0 L620-622, L865-868). ``detail`` keys are unpacked
        into the scope of ``hx-on`` handlers.
        """
        existing = self.get("HX-Trigger")
        data = json.loads(existing) if existing else {}
        data[name] = {"target": target, **detail}
        self["HX-Trigger"] = json.dumps(data)
        return self

    def partial(self, name: str, template: str | None = None):
        """
        Also update the region ``#<name>`` with the partial of the same name.

        Attached only to fragment responses; a page already contains the
        region. The partial's root element must carry ``id="<name>"``.
        """
        if self.hx_kind != "fragment":
            return self
        tpl = template or self.hx_page_template
        if tpl is None:
            raise HxError(".partial() needs a template; this response has none")
        html = render_partial(tpl, name, dict(self.hx_context or {}), self.hx_request)
        check_root_id(html, name, f"{tpl}#{name}")
        self.write(wrap_partial(name, html))
        return self

    def push_url(self, url: str):
        self["HX-Push-Url"] = url
        return self

    def replace_url(self, url: str):
        self["HX-Replace-Url"] = url
        return self

    def with_status(self, code: int):
        self.status_code = code
        return self

    # Escape hatches. Both change the DOM effect of a control from the server,
    # which the template can then no longer predict. Use with a comment.
    def retarget(self, selector: str):
        self["HX-Retarget"] = selector
        return self

    def reswap(self, spec: str):
        self["HX-Reswap"] = spec
        return self


class HxResponse(_HxResponseMethods, HttpResponse):
    """An ``HttpResponse`` with ``.trigger()``, ``.partial()``, ``.push_url()``."""


class HxRedirectResponse(_HxResponseMethods, HttpResponseRedirectBase):
    """A plain 303 (``code=`` to change it). htmx sees the followed page, never the 3xx."""

    status_code = 303
    hx_kind = "redirect"


# ------------------------------------------------------------------- partials

# Only where the first element begins; the attributes are the parser's job, because
# an attribute value may itself contain ">" (hx-on:click="if (a > b) ...").
_STARTS_WITH_ELEMENT = re.compile(r"^\s*(?:<!--.*?-->\s*)*<[a-zA-Z]", re.S)


def check_root_id(html: str, name: str, where: str) -> None:
    """The one convention: a partial swapped by name has ``id=<name>`` on its root."""
    from .hxlint import parse

    root = parse(html)[0] if _STARTS_WITH_ELEMENT.match(html) else None
    first = next(iter(root.children), None) if root is not None else None
    if first is None:
        raise HxPartialRootId(
            f'{where} is used as an <hx-partial> but does not start with an element; it must be one element with id="{name}"'
        )
    found = first.attrs.get("id") or None
    if found != name:
        have = f'id="{found}"' if found else "no id"
        raise HxPartialRootId(
            f'{where} is used as an <hx-partial>, so its root <{first.tag}> must carry id="{name}"; it has {have}'
        )


def wrap_partial(name: str, html: str) -> str:
    return f'\n<hx-partial hx-target="#{name}" hx-swap="outerHTML">{html}</hx-partial>'


def _partial_names(template_name: str) -> list[str]:
    try:
        inner = get_template(template_name).template
    except Exception:
        return []
    return sorted(getattr(inner, "extra_data", {}).get("partials", {}))


def _get_partial(template_name: str, name: str):
    reference = f"{template_name}#{name}"
    try:
        return get_template(reference)
    except TemplateDoesNotExist:
        pass
    # Say why, precisely: the page is missing, the partial is missing, or this
    # Django cannot do partials at all.
    try:
        get_template(template_name)
    except TemplateDoesNotExist:
        raise HxUnknownPartial(f"{reference}: the template {template_name!r} does not exist") from None
    import django

    if django.VERSION < (6, 0) and "template_partials" not in settings.INSTALLED_APPS:
        raise HxUnknownPartial(
            f"{reference} needs template partials, which Django {django.get_version()} does not have. "
            "Install django-template-partials and add 'template_partials' to INSTALLED_APPS, "
            "or point partial= at a separate template file (a name containing a dot)."
        ) from None
    have = ", ".join(_partial_names(template_name)) or "none"
    raise HxUnknownPartial(
        f"{template_name} defines no partial {name!r}; it defines: {have}. "
        f"Write {{% partialdef {name} inline %}}...{{% endpartialdef %}} around the region."
    ) from None


def render_partial(template_name: str, partial: str, context: dict[str, Any], request) -> str:
    """The partial ``partial`` of ``template_name``, or the file ``partial`` when it has a dot."""
    if "." in partial:
        return get_template(partial).render(context, request)
    return _get_partial(template_name, partial).render(context, request)


# ------------------------------------------------------------------- the verbs


def _response(request, body: str, *, kind: str, template: str | None, context, status: int = 200) -> HxResponse:
    response = HxResponse(body, status=status, content_type="text/html; charset=utf-8")
    response.hx_kind = kind
    response.hx_template = template
    response.hx_context = context
    response.hx_request = request
    response.hx_findings = []
    if template and settings.DEBUG:
        response["X-HX-Template"] = template
    return vary_on_hx(response)


def _page(request, template: str, context) -> HxResponse:
    body = get_template(template).render(context, request)
    return _response(request, body, kind="page", template=template, context=context)


def _fragment(request, template: str, partial: str, context) -> HxResponse:
    body = render_partial(template, partial, context, request)
    where = partial if "." in partial else f"{template}#{partial}"
    response = _response(request, body, kind="fragment", template=where, context=context)
    response.hx_page_template = template
    return response


def _record(request, response, exc: HxError) -> None:
    """A finding the test client raises and the middleware logs."""
    response.hx_findings.append(exc)
    logger.warning("hx: %s", exc)


def _guard_fragment(request, response, what: str) -> None:
    if is_htmx(request) and wants_page(request):
        _record(
            request,
            response,
            HxFragmentIntoPage(
                f"{who(request)} answers a boosted or body-targeted htmx request with a {what}; it would land "
                "in <body> with no layout. Point the control at an element, or render a page."
            ),
        )


def render(request, template: str, partial: str, context: dict[str, Any] | None = None, *, status: int = 200) -> HxResponse:
    """The page for ``wants_page``, otherwise ``partial``: a partial of ``template`` or a file."""
    context = dict(context or {})
    if wants_page(request):
        response = _page(request, template, context)
    else:
        response = _fragment(request, template, partial, context)
    return response.with_status(status)


def page(request, template: str, context: dict[str, Any] | None = None) -> HxResponse:
    """Always the page. Raises if the request wanted a fragment."""
    if wants_fragment(request):
        raise HxPageIntoFragment(
            f"{who(request)} renders the page {template} but this htmx request targets an element, not the body. "
            'Give the control hx-target="body", or use render(request, template, partial, ...).'
        )
    return _page(request, template, dict(context or {}))


def fragment(request, template: str, partial: str | None = None, context: dict[str, Any] | None = None) -> HxResponse:
    """Always a fragment: the file, or ``partial`` of it. Loud if htmx asked for a page."""
    response = _fragment(request, template, partial or template, dict(context or {}))
    _guard_fragment(request, response, f"fragment {response.hx_template}")
    return response


def invalid(request, template: str, partial: str, context: dict[str, Any] | None = None) -> HxResponse:
    """``render`` with status 422. htmx 4 swaps it; a browser shows it."""
    return render(request, template, partial, context, status=422)


def redirect(request, to, *args, code: int = 303, **kwargs) -> HxRedirectResponse:
    """
    A plain redirect; ``to`` resolves like ``django.shortcuts.redirect`` (a URL
    name, a model, or a URL). Raises if the request wanted a fragment, because
    fetch would follow it there and swap the page into the element.
    """
    url = resolve_url(to, *args, **kwargs)
    if wants_fragment(request):
        raise HxRedirectIntoFragment(
            f"{who(request)} redirects to {url}, but this htmx request targets an element, not the body; "
            'fetch would follow the redirect and swap the page into it. Give the control hx-target="body", '
            "or return a fragment."
        )
    response = HxRedirectResponse(url)
    response.status_code = code
    response.hx_request = request
    response.hx_findings = []
    return vary_on_hx(response)


def removed(request) -> HxResponse:
    """The resource is gone. The control's ``hx-swap="delete"`` removes its representation."""
    return _response(request, "", kind="removed", template=None, context=None)


def text(request, value: Any) -> HxResponse:
    """An escaped text fragment, for a span or an error slot."""
    response = _response(request, escape(str(value)), kind="text", template=None, context=None)
    _guard_fragment(request, response, "text")
    return response
