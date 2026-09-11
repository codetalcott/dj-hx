"""HxMixin: the verbs for generic views, and the E007 order check."""

import pytest
from django.test import override_settings

from dj_hx import HxPageIntoFragment, HxRedirectIntoFragment
from dj_hx.hxmap import build_map
from dj_hx.testing import hx_check_messages
from tests.conftest import locmem

MFORM = """{% extends "layout.html" %}{% block content %}
{% partialdef form inline %}<form id="form" method="post">{{ form.errors.email }}</form>{% endpartialdef %}
{% endblock %}"""


@pytest.fixture(autouse=True)
def _mixin_settings():
    with override_settings(ROOT_URLCONF="tests.urlconfs.mixin", TEMPLATES=locmem({"mform.html": MFORM})):
        yield


def test_render_to_response_negotiates(client):
    assert b"<html>" in client.get("/mx/").content
    body = client.hx_get("/mx/").content
    assert b"<html>" not in body and body.count(b"<tr>") == 3
    assert client.hx_get("/mx/show/", full=True).status_code == 200
    with pytest.raises(HxPageIntoFragment, match=r"Show\(\) renders the page"):
        client.hx_get("/mx/show/")


def test_form_invalid_is_422_and_form_valid_guards_the_redirect(client):
    r = client.hx_post("/mx/new/", {"email": "nope"})
    assert r.status_code == 422 and r.content.strip().startswith(b'<form id="form"') and b"valid email" in r.content
    r = client.hx_post("/mx/new/", {"email": "a@b.co"}, full=True, follow=False)
    assert (r.status_code, r["Location"]) == (302, "/mx/")
    with pytest.raises(HxRedirectIntoFragment, match=r"New\(\) redirects after a valid form"):
        client.hx_post("/mx/new/", {"email": "a@b.co"})


def test_the_map_knows_a_mixin_view_renders_or_pages():
    m = build_map(sources={"p.html": "<a hx-get=\"{% url 'mx-show' %}\" hx-target=\"#x\">x</a><b hx-get=\"{% url 'mx-index' %}\" hx-target=\"#x\">y</b>"})
    assert m.handlers["mx-index"].verbs == {"render"} and m.handlers["mx-index"].templates == {"index.html#rows"}
    assert m.handlers["mx-show"].verbs == {"page"}
    assert len(m.errors) == 1 and "Show() only calls page" in m.errors[0]


def test_e007_names_the_backwards_view():
    assert [m.id for m in hx_check_messages() if m.id.startswith("dj_hx.E")] == []
    with override_settings(ROOT_URLCONF="tests.urlconfs.backwards"):
        errors = [m for m in hx_check_messages() if m.id == "dj_hx.E007"]
    assert len(errors) == 1 and "Backwards lists TemplateResponseMixin before HxMixin, so HxMixin.render_to_response() never runs" in errors[0].msg
