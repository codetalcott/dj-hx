"""
HxView — fragment/full-page template negotiation for HTMX (the HTMX-4 analog of
dj-fixi's FxView, and the one piece django-htmx itself does not provide).

Detection is layered on django-htmx (``request.htmx``) and HTMX 4's ``HX-Request-Type``
header:

* ``HX-Request-Type: partial|full`` (HTMX 4) takes precedence when present.
* Otherwise we treat any non-boosted HTMX request as wanting a fragment, since a boosted
  navigation expects a full document.

HTMX's default swap is ``innerHTML`` (unlike Fixi's ``outerHTML``); that is a client-side
concern, so HxView does not emit swap — it only chooses the template.
"""

from django.core.exceptions import ImproperlyConfigured
from django.template.response import TemplateResponse
from django.views import View


def is_htmx_request(request) -> bool:
    """True if this request came from htmx (django-htmx's ``request.htmx`` is truthy)."""
    return bool(getattr(request, "htmx", False))


def is_partial_request(request) -> bool:
    """True if htmx wants a fragment rather than a full page.

    Honors HTMX 4's ``HX-Request-Type`` header when present; otherwise any non-boosted
    htmx request is treated as a fragment request.
    """
    request_type = request.headers.get("HX-Request-Type")
    if request_type:
        return request_type == "partial"
    htmx = getattr(request, "htmx", None)
    return bool(htmx) and not getattr(htmx, "boosted", False)


class HxView(View):
    """
    Base HTMX view with automatic fragment/full-page template selection.

    Serves ``partial_template`` (or a ``_partial`` variant of ``template_name``) to htmx
    fragment requests, and the full ``template_name`` to normal navigations. Cooperates
    with the generic-view MRO so it can sit in front of ListView/DetailView/etc.

    Example::

        class NoteListView(HxView, ListView):
            template_name = "notes/list.html"
            partial_template = "notes/_list.html"
    """

    template_name: str | None = None
    partial_template: str | None = None

    @property
    def is_partial(self) -> bool:
        """Whether the current request wants a fragment."""
        return is_partial_request(self.request)

    def get_template_names(self) -> list[str]:
        """Template candidates, fragment-first for htmx requests.

        Mirrors dj-fixi's FxView: explicit ``partial_template`` / ``_partial`` suffix
        first for fragment requests, then ``template_name``, then any names a cooperating
        generic view supplies (e.g. the model-derived ``<app>/<model>_list.html``).
        """
        template_names: list[str] = []

        if self.is_partial and self.partial_template:
            template_names.append(self.partial_template)

        if self.is_partial and self.template_name and self.template_name.endswith(".html"):
            template_names.append(self.template_name.replace(".html", "_partial.html"))

        if self.template_name:
            template_names.append(self.template_name)

        parent = getattr(super(), "get_template_names", None)
        if callable(parent):
            try:
                for name in parent():
                    if name not in template_names:
                        template_names.append(name)
            except ImproperlyConfigured:
                # Generic mixin couldn't derive a name; rely on ours instead.
                pass

        if not template_names:
            raise ImproperlyConfigured(
                f"{type(self).__name__} requires a 'template_name' or "
                "'partial_template' attribute, or an implementation of "
                "'get_template_names()'."
            )

        return template_names

    def get_context_data(self, **kwargs) -> dict:
        """Add ``is_partial`` to context, cooperating with the generic-view MRO."""
        parent = getattr(super(), "get_context_data", None)
        if callable(parent):
            context = parent(**kwargs)
        else:
            context = {**kwargs}
            context.setdefault("view", self)
        context["is_partial"] = self.is_partial
        return context

    def render_to_response(self, context=None, **response_kwargs) -> TemplateResponse:
        """Render the negotiated template(s).

        Self-contained (like dj-fixi's FxView) rather than delegating to
        TemplateResponseMixin, whose signature differs and which would re-run
        ``get_template_names``.
        """
        if context is None:
            context = self.get_context_data()
        return TemplateResponse(
            request=self.request,
            template=self.get_template_names(),
            context=context,
            **response_kwargs,
        )


class HxTemplateView(HxView):
    """HTMX-aware TemplateView analog: renders the negotiated template on GET."""

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)
