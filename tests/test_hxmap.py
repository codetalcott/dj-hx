"""manage.py hx_map: controls to views, both directions, checked statically (hx-flask's test_hxmap.py)."""

import io

import pytest
from django.test import override_settings

from dj_hx.hxmap import build_map, print_map


def by(controls, **match):
    return [c for c in controls if all(getattr(c, k) == v for k, v in match.items())]


def test_every_control_in_the_contact_app_resolves_and_agrees_with_its_view():
    m = build_map()
    assert m.errors == [] and m.warnings == []
    assert all(c.endpoint for c in m.controls), [c for c in m.controls if not c.endpoint]
    # htmx 4's own full/partial rule, applied statically
    search = by(m.controls, element="input#search")[0]
    assert (search.endpoint, search.scope, search.why) == ("contacts", "partial", "hx-target=tbody")
    row_delete = by(m.controls, method="DELETE", endpoint="contacts_view", scope="partial")
    assert row_delete and row_delete[0].why == "hx-target=closest tr"
    page_delete = by(m.controls, method="DELETE", endpoint="contacts_view", scope="full")
    assert page_delete and page_delete[0].why == "hx-target=body"
    new_form = by(m.controls, endpoint="contacts_new", method="POST")[0]
    assert new_form.boosted and new_form.scope == "full"
    bulk = by(m.controls, endpoint="contacts", method="DELETE")[0]
    assert bulk.include and bulk.scope == "partial"


def test_the_contact_app_events_pair_up_and_method_branches_are_attributed():
    m = build_map()
    assert m.handlers["contacts"].announces == {"contacts-changed"}
    assert [li.element for li in m.listeners if li.event == "contacts-changed"] == ["span#count"]
    assert m.handlers["contacts"].templates == {"index.html#rows"}
    view = m.handlers["contacts_view"]
    assert view.verbs == {"page", "redirect", "removed"}
    assert view.verbs_for("DELETE") == {"redirect", "removed"} and view.verbs_for("GET") == {"page"}
    assert m.handlers["contacts"].reads_values and m.handlers["contacts"].flashes


def test_map_prints_and_exits_clean_for_the_contact_app():
    out = io.StringIO()
    assert print_map(out=out) == 0
    text = out.getvalue()
    assert "contacts()  /contacts/" in text
    assert "announces contacts-changed -> index.html:" in text
    assert "0 errors, 0 warnings" in text


SOURCES = {
    "layout.html": '<html><body hx-boost:inherited="true">{% block content %}{% endblock %}</body></html>',
    "page.html": """{% extends "layout.html" %}{% block content %}
        <button hx-get="{% url 'm-detail' %}" hx-target="#panel">open</button>
        <a href="/m/rows/">rows as a page</a>
        <span hx-get="/nowhere" hx-trigger="load"></span>
        <span hx-get="/m/rows" hx-trigger="load" hx-target="#panel"></span>
        <div hx-trigger="orphan from:body" hx-get="{% url 'm-rows' %}" hx-target="#panel"></div>
        <form><button hx-delete="{% url 'm-items' %}" hx-target="tbody">bulk</button></form>
        <a href="{% url 'm-items' %}">items page</a>
        <div id="panel"></div>{% endblock %}""",
    "detail.html": "<html><body>detail</body></html>",
}


@override_settings(ROOT_URLCONF="tests.urlconfs.mapping")
def test_map_reports_the_mismatches_a_dsl_could_not():
    m = build_map(sources=SOURCES)
    errors = "\n".join(m.errors)
    warnings = "\n".join(m.warnings)
    assert "<button> targets an element (hx-target=#panel) but detail() only calls page" in errors
    assert "<a> wants a page (boosted) but rows() only calls fragment" in errors
    assert "GET /nowhere matches no route (404)" in errors
    assert "GET /m/rows is a 301 from APPEND_SLASH" in errors
    assert "event 'orphan' is listened for (page.html:" in warnings
    assert "event 'nobody-listens' is announced by rows() but nothing in the templates listens" in warnings
    assert "<button> sends no form values on DELETE, but items() reads request values" in warnings
    assert len(m.errors) == 4 and len(m.warnings) == 3
    # the GET branch of items() is a page, so the boosted link to it is fine
    assert m.handlers["m-items"].verbs_for("GET") == {"page"} and m.handlers["m-items"].verbs_for("DELETE") == {"removed"}


@override_settings(ROOT_URLCONF="tests.urlconfs.mapping")
def test_navigate_says_nothing_about_the_shape_a_view_answers_with():
    sources = {
        "layout.html": '<html><body hx-boost:inherited="true">{% block content %}{% endblock %}</body></html>',
        "page.html": """{% extends "layout.html" %}{% block content %}
            <button hx-get="{% url 'm-guarded' %}" hx-target="#panel">guarded</button>
            <button hx-get="{% url 'm-gone' %}" hx-target="#panel">gone</button>
            <a href="{% url 'm-gone' %}">gone, boosted</a>
            <div id="panel"></div>{% endblock %}""",
    }
    m = build_map(sources=sources)
    assert m.handlers["m-gone"].verbs == {"navigate"}
    assert m.errors == [
        "page.html:2 <button> targets an element (hx-target=#panel) but guarded() only calls page; the page would "
        "land inside it. Target body, or give the handler a partial."
    ]
    assert [w for w in m.warnings if "nobody-listens" not in w] == []  # rows() in this urlconf announces one


@override_settings(ROOT_URLCONF="tests.urlconfs.book")
def test_map_reports_header_reads_and_a_body_read_on_delete_without_a_verb():
    sources = {
        "index.html": """<form><button hx-delete="{% url 'b-delete' %}" hx-include="closest form" hx-target="body">bulk</button></form>""",
    }
    m = build_map(sources=sources)
    assert m.errors == [
        "contacts() reads the HX-Trigger request header, which htmx 4 does not send (the requesting element is "
        "HX-Source), so the test is always false. To choose a page or a fragment, ask HX-Request-Type (wants_page).",
        "delete_all() reads request.POST on DELETE, but htmx 4 sends DELETE values as query parameters, so it is "
        'always empty; read the query string (request.args / request.GET), with hx-include="closest form" on the '
        "control if the values are in a form.",
    ]
    assert [w for w in m.warnings if "request header" in w] == [
        "panel() reads the HX-Target request header, so it depends on an element id the template can change. "
        "To choose a page or a fragment, ask HX-Request-Type (wants_page)."
    ]
    assert m.handlers["b-delete"].body_reads_for("POST") == {"request.POST"}


@override_settings(ROOT_URLCONF="tests.urlconfs.mapping")
def test_map_treats_script_dispatched_events_as_announced():
    sources = {
        "layout.html": '<html><body>{% block content %}{% endblock %}<script>btn.dispatchEvent(new Event("confirmed"))</script></body></html>',
        "page.html": '{% extends "layout.html" %}{% block content %}<button hx-delete="{% url \'m-go\' %}" hx-target="body" hx-trigger="confirmed">x</button>{% endblock %}',
    }
    m = build_map(sources=sources)
    assert m.errors == [] and not [w for w in m.warnings if "confirmed" in w]


@override_settings(ROOT_URLCONF="tests.urlconfs.mapping")
def test_url_tag_with_as_and_unknown_names():
    sources = {"p.html": "<a hx-get=\"{% url 'nope' %}\">x</a>{% url 'm-go' as u %}<a hx-get=\"{{ u }}\">y</a>"}
    m = build_map(sources=sources)
    assert m.errors == ["p.html:1 <a> GET url:nope: {% url 'nope' %} names no URL pattern the map can see"]
    assert m.warnings[0] == "p.html:1 <a> GET __JINJA__: computed URL; cannot resolve statically"


def test_the_management_command(tmp_path):
    from django.core.management import CommandError, call_command

    out = io.StringIO()
    call_command("hx_map", stdout=out)
    assert "0 errors, 0 warnings" in out.getvalue()
    (tmp_path / "p.html").write_text('<button hx-get="{% url \'m-detail\' %}" hx-target="#x">x</button>')
    templates = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [tmp_path], "APP_DIRS": False}]
    out = io.StringIO()
    with override_settings(ROOT_URLCONF="tests.urlconfs.mapping", TEMPLATES=templates):
        with pytest.raises(CommandError, match="hx_map found errors"):
            call_command("hx_map", stdout=out)
    assert "detail() only calls page" in out.getvalue()


def test_by_template_says_who_renders_each_partial():
    from django.core.management import call_command

    out = io.StringIO()
    call_command("hx_map", "--by-template", stdout=out)
    text = out.getvalue()
    # The page and its partial are one template, and hx_map says which view renders each
    rows = text.split("index.html#rows\n", 1)[1].split("\nnew.html", 1)[0]
    assert rows.splitlines()[0].strip() == "contacts()  /contacts/"
    assert "    <- index.html:10 <input#search> GET partial (hx-target=tbody)" in rows
    assert "edit.html\n  contacts_edit()" in text and "edit.html#form\n  contacts_edit()" in text
    assert text.rstrip().endswith("hx map: 7 templates, 9 handlers")
    assert "0 errors, 0 warnings" not in text  # not the by-view report as well
