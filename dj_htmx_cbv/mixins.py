"""
CBV mixins for HTMX 4. The HTMX-4 analogs of dj-fixi's mixins — but here the
client-event and server-driven-targeting features actually work, because HTMX
reads response headers.

``HxResponseMixin`` is htmx-specific. ``ContextPersistenceMixin`` and
``OptimizedQueryMixin`` are protocol-agnostic (no HX/FX specifics) and are ported
~verbatim from dj-fixi; they work with any Django ``ListView``.
"""

import logging
from typing import Any
from urllib.parse import urlencode

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.http import HttpResponse
from django_htmx.http import trigger_client_event

from .views import is_htmx_request, is_partial_request

logger = logging.getLogger(__name__)


class HxResponseMixin:
    """Render fragments and fire client events for htmx form submissions.

    Mix in front of CreateView/UpdateView/DeleteView::

        class NoteCreateView(HxResponseMixin, CreateView):
            model = Note
            fields = ["title"]
            template_name = "notes/form.html"     # _partial variant served to htmx
            success_url = "/notes/"

    On success the fragment is swapped in and a ``formSuccess`` event fires (via the
    ``HX-Trigger`` header). On validation failure the fragment is re-rendered with a
    ``formError`` event.
    """

    hx_template_suffix: str = "_partial"
    hx_success_event: str = "formSuccess"
    hx_error_event: str = "formError"

    #: Status returned for an invalid htmx form. 422 is the correct, increasingly
    #: conventional choice — but htmx only swaps error responses when
    #: ``htmx.config.responseHandling`` allows the status (the default config does NOT
    #: swap 4xx). Either add a responseHandling rule for 422 (see the example/README)
    #: or set this to ``200`` to swap with no client config.
    hx_invalid_status: int = 422

    def get_template_names(self) -> list[str]:
        """Fragment-first template names for htmx requests.

        For an htmx request, try the ``_partial`` suffix and a ``fragments/`` sibling of
        each name the generic view would use, then fall back to the originals.
        """
        if is_partial_request(self.request):
            original = super().get_template_names()
            fragments: list[str] = []
            for template in original:
                name_parts = template.rsplit(".", 1)
                if len(name_parts) == 2:
                    fragments.append(f"{name_parts[0]}{self.hx_template_suffix}.{name_parts[1]}")
                path_parts = template.rsplit("/", 1)
                if len(path_parts) == 2:
                    fragments.append(f"{path_parts[0]}/fragments/{path_parts[1]}")
            return fragments + original
        return super().get_template_names()

    def form_valid(self, form) -> HttpResponse:
        """Save via super(), then for htmx swap in a fragment + fire the success event.

        Create/update (object keeps a pk) -> render the fragment and attach the success
        event with the object id. Delete (or no renderable object) -> ``204 No Content``
        with the event (the deleted id is preserved so the client can drop its row).
        Non-htmx requests get Django's normal redirect.
        """
        # Capture pk before delegating: DeletionMixin clears it on delete.
        existing = getattr(self, "object", None)
        pk_before = getattr(existing, "pk", None)

        response = super().form_valid(form)

        if not is_htmx_request(self.request):
            return response

        detail = {"message": self.get_success_message()}
        obj = getattr(self, "object", None)
        obj_pk = getattr(obj, "pk", None)

        if obj_pk is not None:
            detail["object_id"] = str(obj_pk)
            hx_response = self.render_to_response(self.get_context_data(form=form))
        else:
            if pk_before is not None:
                detail["object_id"] = str(pk_before)
            hx_response = HttpResponse(status=204)

        return trigger_client_event(hx_response, self.hx_success_event, detail)

    def form_invalid(self, form) -> HttpResponse:
        """For htmx, re-render the fragment with errors and fire the error event.

        Returns ``hx_invalid_status`` (default 422). See that attribute's note on
        htmx's ``responseHandling`` config if errors do not appear to swap.
        """
        if not is_htmx_request(self.request):
            return super().form_invalid(form)

        response = self.render_to_response(self.get_context_data(form=form))
        response.status_code = self.hx_invalid_status
        return trigger_client_event(
            response, self.hx_error_event, {"errors": form.errors.get_json_data()}
        )

    def get_success_message(self) -> str:
        """Human-readable success message for the success event."""
        return f"{self.model._meta.verbose_name.title()} saved successfully"


class ContextPersistenceMixin:
    """
    Preserves user context (filters, sorting, pagination) across navigation.

    Protocol-agnostic — works with any Django ListView, htmx or not. Ported from
    dj-fixi unchanged.

    Input:
        - request.GET holds filter params, ``sort`` and ``page``
        - ``filterset_class`` or ``filterset_fields`` (django-filter) is optional
    Output:
        - adds ``query_string``, ``preserved_params``, ``current_sort`` (and ``filter``)
          to context; filters/sorts the queryset from URL params
    """

    filterset_class: type | None = None
    filterset_fields: list[str] | None = None
    preserved_params: list[str] = ["sort", "page", "q"]

    def get_queryset(self) -> models.QuerySet:
        """Apply filtering and sorting from URL parameters."""
        queryset = super().get_queryset()

        if self.filterset_class or self.filterset_fields:
            filterset = self.get_filterset(queryset)
            if filterset is not None:
                queryset = filterset.qs
                self.filterset = filterset

        sort_param = self.request.GET.get("sort", "")
        if sort_param:
            field_name = sort_param.lstrip("-")
            try:
                queryset.model._meta.get_field(field_name)
                queryset = queryset.order_by(sort_param)
            except FieldDoesNotExist:
                logger.warning("Invalid sort field: %s", field_name)

        return queryset

    def get_filterset(self, queryset: models.QuerySet) -> Any | None:
        """Initialize filterset with the current queryset and request."""
        if self.filterset_class:
            return self.filterset_class(self.request.GET, queryset=queryset, request=self.request)
        return None

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """Add preserved parameters to context."""
        context = super().get_context_data(**kwargs)

        params = {}
        for key in set(self.preserved_params + list(self.request.GET.keys())):
            value = self.request.GET.get(key)
            if value:
                params[key] = value

        context["query_string"] = urlencode(params)
        context["preserved_params"] = params
        context["current_sort"] = self.request.GET.get("sort", "")

        if hasattr(self, "filterset"):
            context["filter"] = self.filterset

        return context


class OptimizedQueryMixin:
    """
    Optimizes querysets with ``select_related`` / ``prefetch_related``.

    Protocol-agnostic; ported from dj-fixi unchanged.
    """

    select_related_fields: list[str] = []
    prefetch_related_fields: list[str] = []

    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()

        if self.select_related_fields:
            queryset = queryset.select_related(*self.select_related_fields)

        if self.prefetch_related_fields:
            queryset = queryset.prefetch_related(*self.prefetch_related_fields)

        return queryset
