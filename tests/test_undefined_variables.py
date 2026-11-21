"""
HxTestClient's undefined-variable check. A project template that reads a name nobody supplies, or an
attribute an object lacks, raises HxUndefinedVariable; a lookup whose outcome depends on the request's
data does not (None in a chain, a key a mapping lacks, an index past the end, {% firstof %}, the debug
processor's names, a 500 page). The client reads Django's documented django.template DEBUG log while a
request runs, which records the lookups {% if %}, {% for %} and |default swallow too.
"""

import logging
from pathlib import Path

import django
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from dj_hx import HxUndefinedVariable
from dj_hx.templates import in_site_packages
from dj_hx.testing import HxTestClient
from tests.conftest import locmem

FORMS_TEMPLATES = Path(django.__file__).resolve().parent / "forms" / "templates"  # Django's own, in site-packages

TEMPLATES = {
    "clean.html": "<p>{{ items|length }} items</p>",
    "loose.html": (
        "<p>{{ nope }}</p>\n"
        "{% if missing %}<p>shown</p>{% endif %}\n"
        "<ul>{% for x in absent %}<li>{{ x }}</li>{% endfor %}</ul>\n"
        "<ul>{% for item in items %}<li>{{ item.nme }}</li>{% endfor %}</ul>\n"
        '<p>{{ gone|default:"-" }}</p>'
    ),
    "base.html": "<!doctype html><html><body>\n<h1>{{ heading }}</h1>\n{% block content %}{% endblock %}\n</body></html>",
    "child.html": '{% extends "base.html" %}{% block content %}\n<p>{{ in_child }}</p>{% endblock %}',
    "includer.html": '<div>\n{% include "included.html" with shown=1 only %}\n</div>',
    "included.html": "<p>{{ shown }}</p>\n<p>{{ hidden }}</p>",
    "parts.html": '<main>\n{% partialdef box inline %}<div id="box">\n{% if error %}{{ error }}{% endif %}</div>{% endpartialdef %}\n</main>',
    "installed.html": '<form>\n{% include "django/forms/widgets/input.html" %}\n<p>{{ ours }}</p>\n</form>',
    "profile.html": "<p>{{ user.profile }}</p>",
    "attributes.html": "<p>{{ holder.nmae }}</p>\n<p>{{ contact.emial }}</p>\n<p>{{ items.length }}</p>\n<p>{{ holder.name.20 }}</p>",
    "card_page.html": '<div>\n{% include "card.html" with title="T" %}\n</div>',
    "card.html": "<h2>{{ title }}</h2>{% if subtitle %}<p>{{ subtitle }}</p>{% endif %}<p>{{ holder.nmae }}</p>",
    "none_in_chain.html": "<p>{{ holder.rel.name }}</p>",
    "mapping.html": "{% if not request.GET.stage %}<p>no stage</p>{% endif %}\n<p>{{ labels.nmae }}</p>",
    "indexes.html": "{% if empty.0 %}x{% endif %}<p>{{ empty.0.name }}{{ pair.2 }}{{ nothing_yet.0.first }}</p>",
    "firstof.html": '<p>{% firstof unset also.unset "z" %}</p>',
    "debug.html": "{% if debug %}<p>{{ sql_queries|length }}</p>{% endif %}<p>ok</p>",
    "500.html": "<h1>Server error{{ nope }}</h1>",
}

LOOSE = [
    "loose.html:1: 'nope' in {{ nope }}",
    "loose.html:2: 'missing' in {% if missing %}",
    "loose.html:3: 'absent' in {% for x in absent %}",
    "loose.html:4: 'nme' in {{ item.nme }}",  # once, though the loop read it for each of three items
    """loose.html:5: 'gone' in {{ gone|default:"-" }}""",  # it renders "-", and Django logs the lookup all the same
]


@pytest.fixture(autouse=True)
def site():
    with override_settings(ROOT_URLCONF="tests.urlconfs.undefined", TEMPLATES=locmem(TEMPLATES, dirs=[FORMS_TEMPLATES])):
        yield


def found(info) -> list[str]:
    return [str(lookup) for lookup in info.value.lookups]


def template_logger() -> tuple:
    log = logging.getLogger("django.template")
    return log.level, list(log.filters), list(log.handlers), log.propagate, log.getEffectiveLevel()


def test_an_undefined_variable_raises_naming_each_one_and_its_template_line(client):
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/loose.html")
    assert found(info) == LOOSE
    assert str(info.value) == (
        "GET /u/show/loose.html read 5 undefined template variables, which Django renders as '', as false in "
        "{% if %} and as nothing to loop over in {% for %}, without a word:\n  "
        + "\n  ".join(LOOSE)
        + "\nPut each in the context the view renders with (an interaction's: its context=), with its default, or "
        "correct the name. HxTestClient(undefined=False) turns this check off."
    )
    assert client.get("/u/show/clean.html").content == b"<p>3 items</p>"


def test_the_template_named_is_the_one_the_tag_is_written_in(client):
    # Django's own record names the template the render started from: child.html for both of these,
    # includer.html for the included one, and only "box" for the partial.
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/child.html")
    assert found(info) == ["base.html:2: 'heading' in {{ heading }}", "child.html:2: 'in_child' in {{ in_child }}"]
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/includer.html")  # `only`: the included template sees `shown` and nothing else
    assert found(info) == [
        "included.html:2: 'hidden' in {{ hidden }} (an included template: pass it in the include's with, ... hidden=None)"
    ]
    with pytest.raises(HxUndefinedVariable) as info:
        client.hx_get("/u/box/")
    assert found(info) == ["parts.html:3: 'error' in {% if error %}"]


def test_an_attribute_an_object_lacks_raises_and_so_does_a_strings_index(client):
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/attributes.html")
    assert found(info) == [
        "attributes.html:1: 'nmae' in {{ holder.nmae }}",  # a plain object
        "attributes.html:2: 'emial' in {{ contact.emial }}",  # a model instance
        "attributes.html:3: 'length' in {{ items.length }}",  # a name, not an index, on a list
        "attributes.html:4: '20' in {{ holder.name.20 }}",  # a string is not a sequence the index rule skips
    ]


def test_an_optional_include_parameter_raises_and_says_to_pass_it_in_the_with(client):
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/card_page.html")
    assert found(info) == [
        "card.html:1: 'subtitle' in {% if subtitle %} (an included template: pass it in the include's with, "
        "... subtitle=None)",
        "card.html:1: 'nmae' in {{ holder.nmae }}",  # an attribute: the include's with is not the fix
    ]


def test_a_lookup_on_none_is_not_counted(client):
    assert client.get("/u/show/none_in_chain.html").content == b"<p></p>"  # holder.rel is None


def test_a_key_a_mapping_lacks_is_not_counted_so_a_misspelt_key_is_silent(client):
    # request.GET is a QueryDict; labels a dict, whose misspelt key is silent: the accepted cost.
    assert client.get("/u/show/mapping.html").content == b"<p>no stage</p>\n<p></p>"


def test_an_index_past_the_end_of_a_sequence_is_not_counted(client):
    assert client.get("/u/show/indexes.html").content == b"<p></p>"  # a list, a tuple and a queryset


def test_a_lookup_firstof_makes_is_not_counted(client):
    assert client.get("/u/show/firstof.html").content == b"<p>z</p>"


def test_the_debug_processors_names_are_not_counted_where_it_is_configured(client):
    processors = ["django.template.context_processors.debug", "django.template.context_processors.request"]
    with override_settings(TEMPLATES=locmem(TEMPLATES, context_processors=processors)):
        assert client.get("/u/show/debug.html").content == b"<p>ok</p>"  # it sets debug only under DEBUG
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/debug.html")  # without the processor, nobody supplies debug
    assert found(info) == ["debug.html:1: 'debug' in {% if debug %}"]


def test_a_response_built_from_an_exception_is_not_judged():
    # Django renders 500.html from an empty Context on purpose.
    r = HxTestClient(raise_request_exception=False).get("/u/broken/")
    assert (r.status_code, r.content, r.hx_findings) == (500, b"<h1>Server error</h1>", [])


def test_an_async_view_is_checked_as_a_sync_one_is(client):
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/async/")
    assert found(info) == LOOSE


def test_a_template_in_site_packages_is_not_the_projects(client):
    assert in_site_packages(FORMS_TEMPLATES)
    # Django's input.html reads widget.type and widget.name with no widget, and its record names
    # installed.html, the template the render started from; only the project's own lookup counts.
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/u/show/installed.html")
    assert found(info) == ["installed.html:3: 'ours' in {{ ours }}"]


def test_a_template_built_from_a_string_is_not_judged(client):
    # It has no file to judge by, and Django builds its DEBUG error pages and CSRF-failure page this way.
    assert client.get("/u/from-string/").content == b"ok"


def test_a_lookup_made_outside_any_template_is_not_counted(client):
    # Django's record names the template "unknown", and no template node is being rendered.
    assert client.get("/u/outside/").content == b"<p>3 items</p>"


def test_a_lookup_that_raises_an_exception_django_silences_is_not_undefined(client):
    # user.profile exists and raised ObjectDoesNotExist, as a missing related object does.
    assert client.get("/u/show/profile.html").content == b"<p></p>"


def test_undefined_false_turns_it_off_and_strict_false_records_it():
    assert HxTestClient(undefined=False).get("/u/show/loose.html").hx_findings == []
    [finding] = HxTestClient(strict=False).get("/u/show/loose.html").hx_findings
    assert isinstance(finding, HxUndefinedVariable) and [str(lookup) for lookup in finding.lookups] == LOOSE


def test_one_requests_lookups_are_not_the_next_ones():
    client = HxTestClient(strict=False)
    assert len(client.get("/u/show/loose.html").hx_findings) == 1
    assert client.get("/u/show/clean.html").hx_findings == []


def test_the_template_logger_is_put_back_after_every_request(client):
    before = template_logger()
    assert before[0] != logging.DEBUG  # else a level left at DEBUG would not show
    client.get("/u/show/clean.html")
    assert template_logger() == before
    with pytest.raises(HxUndefinedVariable):
        client.get("/u/show/loose.html")
    assert template_logger() == before
    with pytest.raises(ValueError, match="boom"):
        client.get("/u/boom/")  # the view raises in the middle of the request
    assert template_logger() == before
    # A client inside a request: the inner request's five lookups are its own, not the outer one's.
    assert client.get("/u/nested/").content == b"<p>5 items</p>"
    assert template_logger() == before
    HxTestClient().get("/u/show/clean.html")
    HxTestClient(strict=False).get("/u/show/loose.html")  # one client after another
    assert template_logger() == before


def test_a_render_on_another_thread_is_not_this_requests(client):
    assert client.get("/u/elsewhere/").content == b"<p>3 items</p>"


def test_no_other_handler_sees_a_record_it_would_not_have(client, caplog):
    # caplog's handler takes every record that reaches the root logger, at any level.
    with pytest.raises(HxUndefinedVariable):
        client.get("/u/show/loose.html")
    assert [r for r in caplog.records if r.name == "django.template"] == []
    with caplog.at_level(logging.DEBUG, logger="django.template"), pytest.raises(HxUndefinedVariable):
        client.get("/u/show/loose.html")  # a project that logs them at DEBUG still gets every one
    assert len([r for r in caplog.records if r.name == "django.template"]) == 7  # the loop's three included


def test_a_check_that_cannot_see_says_so(client, monkeypatch):
    logging.disable(logging.CRITICAL)
    try:
        with pytest.raises(
            ImproperlyConfigured,
            match=r"HxTestClient cannot see undefined template variables: logging\.disable\(CRITICAL\) is in force",
        ):
            client.get("/u/show/clean.html")
        assert HxTestClient(undefined=False).get("/u/show/clean.html").status_code == 200
    finally:
        logging.disable(logging.NOTSET)
    monkeypatch.setattr(logging.getLogger("django.template"), "disabled", True)
    with pytest.raises(ImproperlyConfigured, match=r"the django\.template logger is disabled, as a LOGGING dictConfig"):
        client.get("/u/show/clean.html")
