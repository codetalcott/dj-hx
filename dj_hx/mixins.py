"""
``HxMixin``: the verbs for Django's generic views, overriding as little as possible.

::

    class ContactList(HxMixin, ListView):
        model = Contact
        template_name = "index.html"
        partial = "rows"

    class ContactCreate(HxMixin, CreateView):
        model = Contact
        fields = ["first", "last", "email"]
        template_name = "new.html"
        partial = "form"
        success_url = reverse_lazy("contacts")

Three hooks: ``render_to_response`` goes through ``render`` (so a partial
request gets ``partial``), ``form_invalid`` is a 422, and ``form_valid``
raises ``HxRedirectIntoFragment`` when Django's redirect would answer a
partial request, since fetch would follow it into the element. Put the mixin
first; check ``dj_hx.E007`` says so when it is not.
"""

from __future__ import annotations

from .errors import HxRedirectIntoFragment
from .request import wants_fragment, who
from .verbs import page, render

__all__ = ["HxMixin"]


class HxMixin:
    #: The partial of ``template_name`` a request that targets an element gets.
    #: ``None`` means the view only ever renders the page (``page()``, which is loud).
    partial: str | None = None

    def render_to_response(self, context, **response_kwargs):
        template = self.get_template_names()[0]
        status = response_kwargs.pop("status", 200)
        if self.partial:
            return render(self.request, template, self.partial, context, status=status)
        return page(self.request, template, context).with_status(status)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form), status=422)

    def form_valid(self, form):
        response = super().form_valid(form)
        if 300 <= response.status_code < 400 and wants_fragment(self.request):
            raise HxRedirectIntoFragment(
                f"{who(self.request)} redirects after a valid form, but this htmx request targets an element, "
                'not the body; fetch would follow it there. Give the control hx-target="body", or override '
                "form_valid to return a fragment (render/fragment/removed)."
            )
        return response
