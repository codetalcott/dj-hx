"""Tests for HxView: partial detection and fragment/full-page template negotiation."""

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.views.generic import ListView

from dj_htmx_cbv.views import HxView, is_partial_request

from .conftest import make_request

# --------------------------------------------------------------------------- #
# is_partial detection
# --------------------------------------------------------------------------- #


def test_non_htmx_request_is_not_partial(rf):
    assert is_partial_request(make_request(rf)) is False


def test_htmx_request_is_partial(rf):
    assert is_partial_request(make_request(rf, htmx=True)) is True


def test_boosted_htmx_request_is_not_partial(rf):
    """A boosted navigation wants a full document, not a fragment."""
    assert is_partial_request(make_request(rf, htmx=True, boosted=True)) is False


def test_request_type_header_takes_precedence(rf):
    """HTMX 4's HX-Request-Type overrides the boosted heuristic."""
    req = make_request(rf, htmx=True, boosted=True, request_type="partial")
    assert is_partial_request(req) is True
    req = make_request(rf, htmx=True, request_type="full")
    assert is_partial_request(req) is False


# --------------------------------------------------------------------------- #
# get_template_names
# --------------------------------------------------------------------------- #


def test_partial_template_first_for_htmx(rf):
    class V(HxView):
        template_name = "notes/list.html"
        partial_template = "notes/_list.html"

    view = V()
    view.setup(make_request(rf, htmx=True))
    names = view.get_template_names()

    assert names[0] == "notes/_list.html"
    assert names.index("notes/_list.html") < names.index("notes/list.html")


def test_suffix_variant_when_no_partial_template(rf):
    class V(HxView):
        template_name = "notes/list.html"

    view = V()
    view.setup(make_request(rf, htmx=True))
    names = view.get_template_names()

    assert "notes/list_partial.html" in names
    assert "notes/list.html" in names


def test_full_page_only_for_non_htmx(rf):
    class V(HxView):
        template_name = "notes/list.html"
        partial_template = "notes/_list.html"

    view = V()
    view.setup(make_request(rf))  # not htmx
    names = view.get_template_names()

    assert names == ["notes/list.html"]


def test_unconfigured_view_raises(rf):
    class V(HxView):
        pass

    view = V()
    view.setup(make_request(rf))
    with pytest.raises(ImproperlyConfigured) as exc:
        view.get_template_names()
    assert "V" in str(exc.value)


# --------------------------------------------------------------------------- #
# MRO cooperation with generic views
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_listview_context_and_template_survive_hxview(rf):
    class V(HxView, ListView):
        model = Group
        ordering = ["id"]
        context_object_name = "groups"
        template_name = "notes/list.html"

    Group.objects.create(name="a")

    view = V()
    view.setup(make_request(rf, htmx=True))
    view.object_list = view.get_queryset()
    ctx = view.get_context_data(object_list=view.object_list)

    # ListView context preserved through HxView
    assert list(ctx["groups"]) == list(ctx["object_list"])
    assert "page_obj" in ctx and "paginator" in ctx
    # HxView metadata layered on top
    assert ctx["is_partial"] is True
    # Model-derived template name appended after the explicit/partial ones
    names = view.get_template_names()
    assert names[0] == "notes/list_partial.html"
    assert "auth/group_list.html" in names
