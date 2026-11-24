"""manage.py hx_map: controls to views, both directions, checked statically (hx-flask's test_hxmap.py)."""

import importlib.util
import io
import site
import sys
import sysconfig
import types
from pathlib import Path

import pytest
from django.test import override_settings
from django.urls import path
from django.utils.safestring import SafeString

from dj_hx.hxmap import build_map, print_map
from dj_hx.templates import in_site_packages
from tests.urlconfs import mapping


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
        <form><button hx-delete="{% url 'm-items' %}" hx-target="tbody" hx-swap="innerHTML swapEmpty:true">bulk</button></form>
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
def test_a_control_that_would_keep_what_removed_empties_is_warned():
    """htmx 4.0.2 skips an empty main swap beside an <hx-partial> (the messages bridge's) unless the swap is delete
    or says swapEmpty:true, as tests/test_interactions_browser.py measures on the desk's cross-off row; a control
    targeting the body gets the page, so it is not warned about."""
    page_html = """{% extends "layout.html" %}{% block content %}
        <button hx-delete="{% url 'm-items' %}" hx-target="closest li" hx-swap="delete">a</button>
        <button hx-delete="{% url 'm-items' %}" hx-target="closest li" hx-swap="outerHTML">b</button>
        <button hx-delete="{% url 'm-items' %}" hx-target="closest li" hx-swap="outerHTML swapEmpty:true">c</button>
        <button hx-delete="{% url 'm-items' %}" hx-target="closest li">d</button>
        <button hx-delete="{% url 'm-items' %}" hx-target="body">e</button>{% endblock %}"""
    m = build_map(sources={**SOURCES, "page.html": page_html})
    kept = [w for w in m.warnings if "can answer removed()" in w]
    assert [w.split(" reaches")[0] for w in kept] == ["page.html:3 <button>", "page.html:5 <button>"]
    assert 'Use hx-swap="delete", or add swapEmpty:true' in kept[0]


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
def test_a_hyperscript_listener_pairs_with_the_views_trigger():
    sources = {"p.html": '<div _="on nobody-listens from body add .flash to me">x</div>'}
    m = build_map(sources=sources)
    assert [(li.element, li.event) for li in m.listeners] == [("div", "nobody-listens")]
    assert not [w for w in m.warnings if "nobody-listens" in w], m.warnings
    # a browser event named by hyperscript is a listener too, and is not asked to be announced
    sources = {"p.html": '<div _="on click from body add .x to me">x</div><div _="on orphan from body log 1">y</div>'}
    m = build_map(sources=sources)
    warnings = "\n".join(m.warnings)
    assert "event 'orphan' is listened for" in warnings and "event 'click'" not in warnings


@override_settings(ROOT_URLCONF="tests.urlconfs.mapping")
def test_url_tag_with_as_and_unknown_names():
    sources = {"p.html": "<a hx-get=\"{% url 'nope' %}\">x</a>{% url 'm-go' as u %}<a hx-get=\"{{ u }}\">y</a>"}
    m = build_map(sources=sources)
    assert m.errors == ["p.html:1 <a> GET url:nope: {% url 'nope' %} names no URL pattern the map can see"]
    assert m.warnings[0] == "p.html:1 <a> GET {{…}}: computed URL; cannot resolve statically"  # not the __JINJA__ sentinel


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


# --------------------------------------------- site-packages, as templates.in_site_packages judges it


@pytest.fixture
def user_site(tmp_path, monkeypatch):
    """A user site-packages directory, as pip install --user fills it, which site reports."""
    directory = tmp_path / "site-packages"
    directory.mkdir()
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(directory))
    return directory


def test_in_site_packages_counts_the_directories_site_reports(user_site, tmp_path, monkeypatch):
    distro = tmp_path / "usr" / "lib" / "python3" / "dist-packages"
    # Windows lists the prefix itself first, and a project can live under it
    monkeypatch.setattr(site, "getsitepackages", lambda: [str(tmp_path / "prefix"), str(distro)])
    assert in_site_packages(user_site / "shelf" / "views.py")
    assert in_site_packages(distro / "shelf" / "views.py")
    assert not in_site_packages(tmp_path / "prefix" / "project" / "views.py")
    assert not in_site_packages(tmp_path / "project" / "views.py")


def test_in_site_packages_without_the_site_functions_an_old_virtualenv_lacks(tmp_path, monkeypatch):
    monkeypatch.delattr(site, "getsitepackages")
    monkeypatch.delattr(site, "getusersitepackages")
    assert in_site_packages(Path(sysconfig.get_paths()["purelib"]) / "django" / "__init__.py")
    assert not in_site_packages(tmp_path / "project" / "views.py")


def test_in_site_packages_takes_a_name_django_marked_safe():
    # A locmem template's origin name is its template name, a SafeString when a tag wrote it; below Python
    # 3.12 pathlib interns a one-part name and refuses a str subclass (TypeError: can't intern SafeString).
    assert not in_site_packages(SafeString("child.html"))


def test_the_map_skips_a_view_installed_in_user_site_packages(user_site):
    source = user_site / "shelf_views.py"
    source.write_text("from dj_hx import page\n\n\ndef shelf(request):\n    return page(request, 'shelf.html')\n")
    spec = importlib.util.spec_from_file_location("shelf_views", source)
    installed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installed)  # not put in sys.modules: nothing else in the suite sees it
    urlconf = types.ModuleType("user_site_urls")
    urlconf.urlpatterns = [
        path("shelf/", installed.shelf, name="shelf"),
        path("m/detail/", mapping.detail, name="m-detail"),
    ]
    assert sorted(build_map(urlconf, sources={}).handlers) == ["m-detail"]


def test_the_map_reads_each_views_module_for_its_own_verb_names(tmp_path, monkeypatch):
    # one parse of a module serves every view routed from it; a view in another module gets that module's names
    sources = {
        "aliased_views": "import dj_hx as hx\n\n\ndef one(request):\n    return hx.page(request, 'one.html')\n\n\n"
        "def two(request):\n    return hx.page(request, 'two.html')\n",
        "renamed_views": "from dj_hx import fragment as frag\n\n\ndef three(request):\n    return frag(request, 'three.html', 'part')\n",
    }
    for name, source in sources.items():
        (tmp_path / f"{name}.py").write_text(source)
        spec = importlib.util.spec_from_file_location(name, tmp_path / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)  # inspect.getmodule() finds a view's module there
        spec.loader.exec_module(module)
    aliased, renamed = sys.modules["aliased_views"], sys.modules["renamed_views"]
    urlconf = types.ModuleType("two_modules_urls")
    urlconf.urlpatterns = [
        path("1/", aliased.one, name="one"),
        path("2/", aliased.two, name="two"),
        path("3/", renamed.three, name="three"),
    ]
    m = build_map(urlconf, sources={})
    assert {endpoint: h.verbs for endpoint, h in m.handlers.items()} == {"one": {"page"}, "two": {"page"}, "three": {"fragment"}}
