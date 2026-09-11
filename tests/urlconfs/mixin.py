"""Generic views with HxMixin, and one with the bases in the wrong order for E007."""

from django import forms
from django.urls import path
from django.views.generic import FormView, TemplateView

from dj_hx import HxMixin

ITEMS = ["ada", "grace", "linus"]


class ContactForm(forms.Form):
    email = forms.EmailField()


class Index(HxMixin, TemplateView):
    template_name = "index.html"
    partial = "rows"

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "items": ITEMS}


class Show(HxMixin, TemplateView):
    template_name = "index.html"  # no partial: page only

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "items": ITEMS}


class New(HxMixin, FormView):
    form_class = ContactForm
    template_name = "mform.html"
    partial = "form"
    success_url = "/mx/"


class Backwards(TemplateView, HxMixin):
    template_name = "index.html"
    partial = "rows"


urlpatterns = [
    path("mx/", Index.as_view(), name="mx-index"),
    path("mx/show/", Show.as_view(), name="mx-show"),
    path("mx/new/", New.as_view(), name="mx-new"),
]

backwards_urlpatterns = [path("mx/backwards/", Backwards.as_view(), name="mx-backwards")]
