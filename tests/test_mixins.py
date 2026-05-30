"""Tests for HxResponseMixin: form_valid/form_invalid render fragments and fire events."""

import json

import pytest
from django import forms
from django.contrib.auth.models import Group
from django.test import override_settings
from django.views.generic import CreateView, DeleteView, ListView

from dj_htmx_cbv.mixins import ContextPersistenceMixin, HxResponseMixin, OptimizedQueryMixin

from .conftest import make_request

# locmem templates so fragment rendering works without app template dirs.
LOCMEM_TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.locmem.Loader",
                    {
                        "g/form.html": "FULL {{ object.name }}",
                        "g/form_partial.html": "PARTIAL {{ object.name }}",
                    },
                )
            ],
            "context_processors": ["django.template.context_processors.request"],
        },
    }
]


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name"]


@override_settings(TEMPLATES=LOCMEM_TEMPLATES)
@pytest.mark.django_db
def test_form_valid_create_renders_fragment_and_triggers_event(rf):
    class V(HxResponseMixin, CreateView):
        model = Group
        form_class = GroupForm
        template_name = "g/form.html"
        success_url = "/done/"

    view = V()
    view.setup(make_request(rf, "post", htmx=True, data={"name": "new"}))
    view.object = None
    form = view.get_form()
    assert form.is_valid()

    response = view.form_valid(form)
    response.render()

    assert response.status_code == 200
    assert b"PARTIAL new" in response.content  # fragment, not the FULL template
    assert Group.objects.filter(name="new").exists()
    payload = json.loads(response["HX-Trigger"])
    assert "formSuccess" in payload
    assert payload["formSuccess"]["object_id"]


@override_settings(TEMPLATES=LOCMEM_TEMPLATES)
@pytest.mark.django_db
def test_form_valid_delete_returns_204_with_event(rf):
    grp = Group.objects.create(name="gone")
    pk = grp.pk

    class V(HxResponseMixin, DeleteView):
        model = Group
        template_name = "g/confirm.html"
        success_url = "/done/"

    view = V()
    view.setup(make_request(rf, "post", htmx=True), pk=pk)
    view.object = view.get_object()
    form = view.get_form()
    assert form.is_valid()

    response = view.form_valid(form)

    assert response.status_code == 204
    assert not Group.objects.filter(pk=pk).exists()
    payload = json.loads(response["HX-Trigger"])
    assert payload["formSuccess"]["object_id"] == str(pk)


@override_settings(TEMPLATES=LOCMEM_TEMPLATES)
@pytest.mark.django_db
def test_form_invalid_returns_422_with_error_event(rf):
    class V(HxResponseMixin, CreateView):
        model = Group
        form_class = GroupForm
        template_name = "g/form.html"
        success_url = "/done/"

    view = V()
    view.setup(make_request(rf, "post", htmx=True, data={}))  # missing required name
    view.object = None
    form = view.get_form()
    assert not form.is_valid()

    response = view.form_invalid(form)
    response.render()

    assert response.status_code == 422  # default; needs a responseHandling rule client-side
    assert b"PARTIAL" in response.content
    payload = json.loads(response["HX-Trigger"])
    assert "formError" in payload


@override_settings(TEMPLATES=LOCMEM_TEMPLATES)
@pytest.mark.django_db
def test_hx_invalid_status_is_configurable(rf):
    """Teams that don't want to touch responseHandling can opt into 200."""

    class V(HxResponseMixin, CreateView):
        model = Group
        form_class = GroupForm
        template_name = "g/form.html"
        success_url = "/done/"
        hx_invalid_status = 200

    view = V()
    view.setup(make_request(rf, "post", htmx=True, data={}))
    view.object = None
    form = view.get_form()
    assert not form.is_valid()

    response = view.form_invalid(form)
    assert response.status_code == 200


@override_settings(TEMPLATES=LOCMEM_TEMPLATES)
@pytest.mark.django_db
def test_non_htmx_request_redirects(rf):
    class V(HxResponseMixin, CreateView):
        model = Group
        form_class = GroupForm
        template_name = "g/form.html"
        success_url = "/done/"

    view = V()
    view.setup(make_request(rf, "post", data={"name": "plain"}))  # not htmx
    view.object = None
    form = view.get_form()
    assert form.is_valid()

    response = view.form_valid(form)

    assert response.status_code == 302
    assert response["Location"] == "/done/"
    assert "HX-Trigger" not in response


# --------------------------------------------------------------------------- #
# ContextPersistenceMixin / OptimizedQueryMixin (protocol-agnostic)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_context_persistence_invalid_sort_ignored(rf):
    class V(ContextPersistenceMixin, ListView):
        model = Group
        ordering = ["id"]

    view = V()
    view.setup(rf.get("/?sort=bogus"))
    qs = view.get_queryset()  # must not raise

    assert qs.query.order_by == ("id",)  # bogus sort not applied


@pytest.mark.django_db
def test_context_persistence_valid_sort_applied(rf):
    class V(ContextPersistenceMixin, ListView):
        model = Group

    view = V()
    view.setup(rf.get("/?sort=name"))
    qs = view.get_queryset()

    assert qs.query.order_by == ("name",)


@pytest.mark.django_db
def test_context_persistence_query_string(rf):
    class V(ContextPersistenceMixin, ListView):
        model = Group

    view = V()
    view.setup(rf.get("/?q=test&page=2&extra=1"))
    view.object_list = Group.objects.none()
    ctx = view.get_context_data(object_list=view.object_list)

    assert "q=test" in ctx["query_string"]
    assert ctx["preserved_params"]["q"] == "test"
    assert ctx["current_sort"] == ""


@pytest.mark.django_db
def test_optimized_query_applies_prefetch(rf):
    class V(OptimizedQueryMixin, ListView):
        model = Group
        prefetch_related_fields = ["permissions"]

    view = V()
    view.setup(rf.get("/"))
    qs = view.get_queryset()

    assert qs._prefetch_related_lookups == ("permissions",)
