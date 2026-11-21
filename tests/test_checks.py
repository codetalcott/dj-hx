"""
The system checks: quiet on the example project, and each one on its own defect. The example project
has no interactions, so the rota app's are set aside here; tests/test_interactions.py checks those.
"""

import pytest
from django.conf import settings
from django.core.checks import ERROR, INFO
from django.test import override_settings

from dj_hx.testing import assert_no_hx_check_issues, hx_check_messages
from tests.conftest import on_disk

pytestmark = pytest.mark.usefixtures("no_interactions")


def ids():
    return sorted(m.id for m in hx_check_messages())


def test_the_example_project_passes_every_check():
    assert_no_hx_check_issues()


def test_w001_when_the_middleware_is_absent():
    with override_settings(MIDDLEWARE=[m for m in settings.MIDDLEWARE if "dj_hx" not in m]):
        assert ids() == ["dj_hx.W001"]


def test_e002_when_listed_before_message_middleware():
    ours = "dj_hx.middleware.HxMiddleware"
    theirs = "django.contrib.messages.middleware.MessageMiddleware"
    order = [m for m in settings.MIDDLEWARE if m not in (ours, theirs)] + [ours, theirs]
    with override_settings(MIDDLEWARE=order):
        messages = hx_check_messages()
    assert [m.id for m in messages] == ["dj_hx.E002"] and "Move HxMiddleware below MessageMiddleware" in messages[0].hint


def test_w003_and_w004_for_the_messages_template():
    with override_settings(HX_MESSAGES_TEMPLATE=None):
        assert ids() == ["dj_hx.W003"]
    with override_settings(HX_MESSAGES_TEMPLATE="layout.html#flash"):
        messages = hx_check_messages()
    assert [m.id for m in messages] == ["dj_hx.W004"] and "partialdef flash" in messages[0].hint


def test_w005_names_the_template_and_the_rule(tmp_path):
    (tmp_path / "old.html").write_text('{# <div hx-ext="sse"> #}\n<div hx-ext="sse" hx-swap="outerhtml"></div>')
    (tmp_path / "fine.html").write_text('<div hx-get="{% url \'x\' %}" hx-swap="outerHTML swap:1s"></div>')
    templates = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [tmp_path], "APP_DIRS": False}]
    with override_settings(TEMPLATES=templates, HX_MESSAGES_TEMPLATE=None):
        messages = [m for m in hx_check_messages() if m.id == "dj_hx.W005"]
    assert len(messages) == 1 and messages[0].obj.endswith("old.html")
    assert "htmx2-attribute" in messages[0].msg and "swap-style-case" in messages[0].msg and "line 2" in messages[0].hint
    with override_settings(TEMPLATES=templates, HX_MESSAGES_TEMPLATE=None, HX_LINT_IGNORE=["htmx2-attribute", "swap-style-case"]):
        assert "dj_hx.W005" not in ids()


def test_w006_only_below_django_6(monkeypatch, settings):
    import django

    from dj_hx import checks

    settings.INSTALLED_APPS = [a for a in settings.INSTALLED_APPS if a != "template_partials"]
    monkeypatch.setattr(django, "VERSION", (5, 2, 0, "final", 0))
    assert [m.id for m in checks.check_partials_available()] == ["dj_hx.W006"]
    monkeypatch.setattr(django, "VERSION", (6, 0, 0, "final", 0))
    assert checks.check_partials_available() == []


def test_w008_for_an_extension_name_the_lint_does_not_know():
    # htmx registers hx-sse.js as 'sse' and hx-live.js as 'hx-live'; either spelling is the extension
    with override_settings(HX_EXTENSIONS=("sse", "hx-sse", "ws", "hx-live")):
        assert ids() == []
    with override_settings(HX_EXTENSIONS=("hx-see",)):
        messages = hx_check_messages()
    assert [m.id for m in messages] == ["dj_hx.W008"] and "did you mean 'hx-sse'?" in messages[0].msg
    with override_settings(HX_EXTENSIONS="sse, ws"):
        messages = hx_check_messages()
    assert [m.id for m in messages] == ["dj_hx.W008"] and "('sse', 'ws')" in messages[0].hint


# ------------------------------------------------------------------ {% url %}: E022, I023


def url_messages(directory, source):
    """E022 and I023 for one template, page.html, under tests/urlconfs/reversing.py."""
    (directory / "page.html").write_text(source)
    with override_settings(ROOT_URLCONF="tests.urlconfs.reversing", TEMPLATES=on_disk(directory)):
        return [m for m in hx_check_messages() if m.id in ("dj_hx.E022", "dj_hx.I023")]


REVERSES = """<a href="{% url 'home' %}">home</a>
<a href="{% url 'contacts_edit' contact.id %}">int</a> <a href="{% url "contacts_edit" contact_id=contact.id %}">by keyword</a>
<a href="{% url 'page' page.title %}">str</a> <a href="{% url 'tag' tag=t.slug %}">slug</a>
<a href="{% url 'file' f.path %}">path</a> <a href="{% url 'token' token=t.uuid %}">uuid</a>
<a href="{% url 'shop:cart' store=s.id %}">a namespace whose prefix takes one</a> <a href="{% url 'shop:item' s.id i.slug %}">item</a>
{% url 'contacts_edit' contact.id as edit %}<a href="{{ edit }}">as</a>"""


def test_e022_is_quiet_when_every_url_reverses_with_its_converters_placeholders(tmp_path):
    # int -> 1; str, slug and path -> "a"; uuid -> 00000000-...; read from the resolver, through the namespace
    assert url_messages(tmp_path, REVERSES) == []


@pytest.mark.parametrize(
    "tag, says",
    [
        (
            "{% url 'contacts_edit' %}",
            "{% url 'contacts_edit' %} passes no arguments, but 'contacts_edit' is /contacts/<int:contact_id>/edit/, "
            "which takes contact_id, so the page raises NoReverseMatch at render.",
        ),
        ("{% url 'contacts_edit' contact.id 2 %}", "passes 2 positional arguments, but 'contacts_edit' is"),
        ("{% url 'contacts_edit' pk=contact.id %}", "passes the keyword pk, but 'contacts_edit' is"),
        ("{% url 'shop:cart' %}", "passes no arguments, but 'shop:cart' is /stores/<int:store>/cart/, which takes store"),
        (
            "{% url 'contacts_edit' contact.id page=2 %}",
            "{% url 'contacts_edit' %} passes 1 positional and 1 keyword argument; reverse() refuses the mix, so the "
            "page raises ValueError at render.",
        ),
        (
            "{% url 'contact_edit' contact.id %}",
            "{% url 'contact_edit' %} names no URL pattern (did you mean 'contacts_edit'?), so the page raises "
            "NoReverseMatch at render.",
        ),
        ("{% url 'shop:crat' store=s.id %}", "{% url 'shop:crat' %} names no URL pattern (did you mean 'shop:cart'"),
        (
            "{% url 'shops:cart' store=s.id %}",
            "{% url 'shops:cart' %} names the namespace 'shops', which no URLconf installs (did you mean 'shop'?), so "
            "the page raises NoReverseMatch at render.",
        ),
        (
            "{% url 'contacts_edit' as edit %}",
            "so {% url ... as edit %} stores an empty string in edit instead of raising, and whatever reads it gets no URL.",
        ),
        ("{% url 'archive' %}", "passes no arguments, but 'archive' is /archive/<yyyy:year>/, which takes year"),
        ("{% comment %}{% url 'home' 1 %}{% endcomment %}{% url 'home' 1 %}", "passes 1 positional argument, but 'home'"),
    ],
    ids=[
        "missing", "extra", "wrong-keyword", "namespaced", "mixed", "no-such-name", "no-such-name-in-namespace",
        "no-such-namespace", "as", "custom-converter-missing", "after-a-comment",
    ],
)
def test_e022_a_url_that_does_not_reverse(tmp_path, tag, says):
    messages = url_messages(tmp_path, f'<p>a link</p>\n<a href="{tag}">x</a>')
    assert [(m.id, m.level, m.obj) for m in messages] == [("dj_hx.E022", ERROR, "page.html:2")]
    assert says in messages[0].msg


def test_e022_says_how_to_write_the_tag(tmp_path):
    [message] = url_messages(tmp_path, "{% url 'shop:item' %}")
    assert message.hint == (
        "Pass one value for each parameter of the route, all by position or all by keyword: "
        "{% url 'shop:item' store=... item=... %}."
    )


@pytest.mark.parametrize(
    "source",
    [
        "{% url view_name %}",
        "{% url 'nowher'|add:'e' %}",
        "{# {% url 'nowhere' %} #}",
        "{% comment 'old' %}{% url 'nowhere' %}{% endcomment %}",
        "{% verbatim %}{% url 'nowhere' %}{% endverbatim %}",
        "{% verbatim js %}{% url 'nowhere' %}{% endverbatim js %}",
        "{% url 'nowhere'\n %}",
    ],
    ids=["variable", "filter", "comment", "comment-tag", "verbatim", "named-verbatim", "across-lines"],
)
def test_e022_skips_a_name_built_at_run_time_and_what_django_does_not_read_as_a_tag(tmp_path, source):
    assert url_messages(tmp_path, source) == []


@pytest.mark.parametrize(
    "tag, says",
    [
        (
            "{% url 'archive' 2024 %}",
            "{% url 'archive' %} is not checked: 'archive' is /archive/<yyyy:year>/, and dj-hx has no placeholder "
            "value for the converter of year, FourDigitYear.",
        ),
        (
            "{% url 'legacy' code='ABC' %}",
            "{% url 'legacy' %} is not checked: 'legacy' is /legacy/<code>/, and dj-hx has no placeholder value for "
            "code, a regular-expression group (re_path).",
        ),
    ],
    ids=["custom-converter", "re_path"],
)
def test_i023_a_url_whose_route_takes_a_converter_without_a_placeholder(tmp_path, tag, says):
    messages = url_messages(tmp_path, f'<p>a link</p>\n<a href="{tag}">x</a>')
    assert [(m.id, m.level, m.obj) for m in messages] == [("dj_hx.I023", INFO, "page.html:2")]  # not checked, not wrong
    assert messages[0].msg == says and "SILENCED_SYSTEM_CHECKS" in messages[0].hint


def test_w024_a_views_trigger_no_template_listens_for(tmp_path):
    # contacts() announces contacts-changed with .trigger(), as hx_map finds it; index.html is not here to listen
    (tmp_path / "page.html").write_text("<p>no listener</p>")
    with override_settings(TEMPLATES=on_disk(tmp_path)):
        messages = [m for m in hx_check_messages() if m.id == "dj_hx.W024"]
    assert [(m.obj, m.msg) for m in messages] == [
        (
            "contacts",
            "contacts() announces 'contacts-changed' with .trigger(), but no project template listens for it "
            "(hx-trigger, hx-on or a hyperscript 'on contacts-changed').",
        )
    ]


def test_checks_stay_quiet_when_dj_hx_is_not_installed():
    with override_settings(INSTALLED_APPS=[a for a in settings.INSTALLED_APPS if a != "dj_hx"], HX_MESSAGES_TEMPLATE=None):
        assert ids() == []


@pytest.mark.parametrize("silenced", [["dj_hx.W003"]])
def test_silenced_system_checks_is_honored(silenced):
    with override_settings(HX_MESSAGES_TEMPLATE=None, SILENCED_SYSTEM_CHECKS=silenced):
        assert_no_hx_check_issues()
