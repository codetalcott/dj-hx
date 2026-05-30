from django.forms import modelform_factory
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from dj_htmx_cbv import HxResponseMixin, HxView

from .models import Note

NoteForm = modelform_factory(Note, fields=["title"])


class NoteListView(HxView, ListView):
    """Full page for normal navigation; the `notes/list_partial.html` fragment for htmx."""

    model = Note
    context_object_name = "notes"
    template_name = "notes/list.html"
    partial_template = "notes/list_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", NoteForm())  # the embedded create widget
        return context


class NoteCreateView(HxResponseMixin, CreateView):
    """Create a note. For htmx, returns the form fragment + a `formSuccess` event."""

    model = Note
    fields = ["title"]
    template_name = "notes/form.html"
    success_url = reverse_lazy("note_list")
