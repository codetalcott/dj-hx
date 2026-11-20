"""
Interactions: ``@interaction``, the routes it mints, ``{% act %}`` and the wrapper view's guards. Each
test seeds one mistake an app could contain and asserts that it is loud, or seeds the rule and asserts
what a request gets. The rota app (tests/interactions_app) is registered by dj-hx's ready(); a test
that defines its own interactions takes ``scratch``, which puts the registry back afterwards.
"""

import json
import sys

import pytest
from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.template import Context, Template, TemplateSyntaxError
from django.test import override_settings
from django.urls import Resolver404, clear_url_caches, resolve, reverse
from django.utils.module_loading import module_has_submodule

import dj_hx.urls  # noqa: F401  binds the routes now, after ready(), before any `scratch` snapshot of them
from dj_hx import HxFragmentIntoPage, HxPartialRootId, HxRedirectIntoFragment, interaction
from dj_hx.interactions import registry, urlpatterns
from dj_hx.templates import in_site_packages
from tests.conftest import locmem
from tests.interactions_app import views

ROTA = """{% extends "layout.html" %}{% load hx %}{% block content %}<h1>{{ contest }}</h1>
{% partialdef notify inline %}<div id="notify">{% for member in members %}<button hx-post="{% act 'notify' contest=contest member=member %}" hx-target="#notify" hx-swap="outerHTML">Notify {{ member }}</button>{% endfor %}{% if notified %}<p class="done">Notified {{ notified }}</p>{% endif %}{% if error %}<p class="error">{{ error }}</p>{% endif %}</div>{% endpartialdef %}
{% endblock %}"""

REVIEWERS = """{% load hx %}{% partialdef reviewer inline %}<div id="reviewer"><button hx-post="{% act 'notify_reviewer' member=member %}" hx-target="#reviewer" hx-swap="outerHTML">Notify reviewer {{ member }}</button>{% if notified %}<p class="done">Reviewer notified</p>{% endif %}</div>{% endpartialdef %}
{% partialdef signoff inline %}<div id="signoff">{% if signed %}Signed off by {{ request.user.username }}{% endif %}</div>{% endpartialdef %}"""

SCRATCH = """{% partialdef box inline %}<div id="box">{{ value }}{% if error %} {{ error }}{% endif %}</div>{% endpartialdef %}
{% partialdef rootless inline %}<div class="box">{{ value }}</div>{% endpartialdef %}"""


@pytest.fixture
def rota():
    templates = locmem({"rota.html": ROTA, "reviewers.html": REVIEWERS, "scratch.html": SCRATCH})
    with override_settings(ROOT_URLCONF="tests.urlconfs.interactions", TEMPLATES=templates):
        yield


@pytest.fixture
def scratch():
    """The interactions a test defines are gone after it: the registry and the routes are put back."""
    saved_registry, saved_routes = dict(registry), list(urlpatterns)
    yield
    registry.clear()
    registry.update(saved_registry)
    urlpatterns[:] = saved_routes
    clear_url_caches()


def nothing(request):
    return {}


def box_context(request):
    return {"value": "nothing yet", "error": None}


def render_act(source, **context):
    return Template("{% load hx %}" + source).render(Context(context))


# ------------------------------------------------------------------ the routes


def test_a_minted_route_is_x_app_label_handler_then_one_segment_per_parameter(rota):
    assert reverse("dj_hx:notify", kwargs={"contest": "spring", "member": 3}) == "/x/rota/notify/spring/3/"
    assert resolve("/x/rota/notify/spring/3/").kwargs == {"contest": "spring", "member": 3}  # int: <int:member>
    assert resolve("/x/rota/notify/7/3/").kwargs["contest"] == "7"  # anything else: <str:contest>
    with pytest.raises(Resolver404):
        resolve("/x/rota/notify/spring/three/")


def test_a_postponed_int_annotation_still_mints_an_int_segment(scratch, rota):
    def tally(request, count: "int"):  # what `from __future__ import annotations` makes of `count: int`
        return None

    tally.__module__ = views.__name__  # as if written in the rota app's views.py
    interaction("POST", partial="scratch.html#box", context=nothing)(tally)
    clear_url_caches()
    assert reverse("dj_hx:tally", kwargs={"count": 4}) == "/x/rota/tally/4/"
    assert resolve("/x/rota/tally/4/").kwargs == {"count": 4}


def test_a_minted_route_needs_an_installed_app(scratch):
    def stray(request):
        return None

    with pytest.raises(
        ImproperlyConfigured,
        match=r"stray\(\) is in tests\.test_interactions, which is in no installed app.*views\.py, or give it route=",
    ):
        interaction("POST", partial="scratch.html#box", context=nothing)(stray)
    assert "stray" not in registry


def test_route_chooses_the_path(rota, client):
    assert reverse("dj_hx:notify_reviewer", kwargs={"member": 5}) == "/reviewers/5/notify"
    r = client.hx_post("/reviewers/5/notify")
    assert r.status_code == 200 and r.content.decode().startswith('<div id="reviewer">')
    assert '<p class="done">Reviewer notified</p>' in r.content.decode()


@pytest.mark.parametrize(
    "route, says",
    [
        ("reviewers/<int:who>/notify", r"has parameters \['who'\], but remind\(\) takes \['member'\]\. Name each"),
        ("reviewers/notify", r"has parameters \[\], but remind\(\) takes \['member'\]"),
        ("reviewers/<int:member>/<int:day>", r"has parameters \['member', 'day'\], but remind\(\) takes \['member'\]"),
        ("reviewers/<member>/notify", r"passes \['member'\] as text, but remind\(\) annotates it int\. Write <int:member>"),
    ],
    ids=["renamed", "missing", "extra", "int-as-text"],
)
def test_a_route_must_name_exactly_the_handlers_parameters(scratch, route, says):
    def remind(request, member: int):
        return None

    with pytest.raises(ImproperlyConfigured, match=says):
        interaction("POST", partial="scratch.html#box", context=nothing, route=route)(remind)
    assert "remind" not in registry


def test_two_interactions_cannot_share_a_name(scratch):
    def notify(request):
        return None

    with pytest.raises(
        ImproperlyConfigured,
        match=r"Two interactions are named notify\(\), in tests\.interactions_app\.views and tests\.test_interactions",
    ):
        interaction("POST", partial="scratch.html#box", context=nothing, route="elsewhere/")(notify)
    assert registry["notify"].view is views.notify  # @interaction returns the routed view


@pytest.mark.parametrize("partial", ["scratch.html", "scratch.html#", "#box", "scratch.html#box.html"])
def test_partial_names_a_partial_of_a_template(scratch, partial):
    def show(request):
        return None

    with pytest.raises(ImproperlyConfigured, match=r"show\(\): partial=.* must name a partial of a template, as 'page\.html#name'"):
        interaction("GET", partial=partial, context=nothing, route="show/")(show)
    assert "show" not in registry


def test_triggers_is_a_tuple_of_names_not_a_string(scratch):
    def save(request):
        return None

    with pytest.raises(ImproperlyConfigured, match=r"save\(\): triggers='saved' is a string.*Write triggers=\('saved',\)"):
        interaction("POST", partial="scratch.html#box", context=nothing, triggers="saved", route="save/")(save)


def test_ready_imports_each_project_apps_views_and_no_app_in_site_packages(scratch, monkeypatch):
    third_party = [
        f"{c.name}.views" for c in apps.get_app_configs()
        if in_site_packages(c.path) and module_has_submodule(c.module, "views")
    ]
    assert third_party  # contenttypes, messages and staticfiles each ship a views module
    for name in (views.__name__, *third_party):
        monkeypatch.delitem(sys.modules, name, raising=False)
    # The re-import rebinds the package attribute; this puts the original module back afterwards.
    monkeypatch.setattr(sys.modules["tests.interactions_app"], "views", views)
    registry.clear()
    urlpatterns.clear()

    apps.get_app_config("dj_hx").ready()

    assert {"notify", "notify_reviewer"} <= set(registry)
    assert [name for name in third_party if name in sys.modules] == []


# ------------------------------------------------------------- the wrapper view


def test_the_reply_is_the_partial_with_the_handlers_keys_and_its_triggers(rota, client):
    r = client.hx_post("/x/rota/notify/spring/3/")
    body = r.content.decode()
    assert r.status_code == 200 and body.startswith('<div id="notify">') and "<html>" not in body
    assert '<p class="done">Notified 3</p>' in body
    # rota_context() takes only `contest`, and is called with only that: its members are rendered.
    assert 'hx-post="/x/rota/notify/spring/3/"' in body and 'hx-post="/x/rota/notify/spring/7/"' in body
    assert json.loads(r["HX-Trigger"]) == {"notified": {"target": "body"}, "rota-changed": {"target": "body"}}


def test_the_page_renders_the_region_from_the_same_context(rota, client):
    body = client.get("/rota/spring/").content.decode()
    assert "<html>" in body and '<div id="notify">' in body and "Notified" not in body
    assert 'hx-post="/x/rota/notify/spring/3/"' in body and 'hx-post="/x/rota/notify/spring/7/"' in body


def test_another_method_gets_a_405_that_the_guard_records_nothing_for(rota, client):
    for send in (client.hx_get, client.hx_put, client.hx_delete):
        r = send("/x/rota/notify/spring/3/")  # the strict client would raise any recorded finding
        assert (r.status_code, r["Allow"], r.hx_findings) == (405, "POST", [])


def test_a_declared_refusal_re_renders_the_partial_with_error_and_422(rota, client):
    r = client.hx_post("/x/rota/notify/spring/9/")
    body = r.content.decode()
    assert r.status_code == 422 and body.startswith('<div id="notify">')
    assert '<p class="error">Member 9 is not on the spring rota.</p>' in body
    assert "Notified" not in body and "HX-Trigger" not in r  # a refusal announces nothing


def test_only_a_declared_exception_is_a_refusal(scratch, rota, client):
    @interaction("POST", partial="scratch.html#box", context=box_context, refuses=(LookupError,), route="t/broken")
    def broken(request):
        raise ValueError("a bug, not a refusal")

    with pytest.raises(ValueError, match="a bug"):
        client.hx_post("/t/broken")


def test_a_reply_key_the_context_does_not_define_raises(scratch, rota, client):
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/boast")
    def boast(request):
        return {"value": "done", "surprise": True}

    with pytest.raises(
        ImproperlyConfigured,
        match=r"boast\(\) returns 'surprise', which box_context\(\) does not define\. Define each there with its default",
    ):
        client.hx_post("/t/boast")


def test_a_refusal_needs_error_in_the_context(scratch, rota, client):
    def bare_context(request):
        return {"value": ""}

    @interaction("POST", partial="scratch.html#box", context=bare_context, refuses=(LookupError,), route="t/vanish")
    def vanish(request):
        raise LookupError("gone")

    with pytest.raises(
        ImproperlyConfigured,
        match=r"vanish\(\) refused with LookupError, and the refusal's reply sets 'error', which bare_context\(\) does not define",
    ):
        client.hx_post("/t/vanish")


@pytest.mark.parametrize("reply", [HttpResponse("left"), ["value"], "value"], ids=["HttpResponse", "list", "str"])
def test_an_interaction_returns_a_dict_or_none(scratch, rota, client, reply):
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/leave")
    def leave(request):
        return reply

    with pytest.raises(
        ImproperlyConfigured,
        match=rf"leave\(\) returned {type(reply).__name__}; .*An interaction always re-renders its partial; to leave "
        r"the page, write a view that returns navigate\(\)\.",
    ):
        client.hx_post("/t/leave")


def test_none_replies_with_the_context_alone(scratch, rota, client):
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/idle")
    def idle(request):
        return None

    r = client.hx_post("/t/idle")
    assert (r.status_code, r.content.decode()) == (200, '<div id="box">nothing yet</div>')


def test_the_reply_root_carries_the_partial_name(scratch, rota, client):
    @interaction("POST", partial="scratch.html#rootless", context=box_context, route="t/rootless")
    def rootless(request):
        return None

    with pytest.raises(
        HxPartialRootId,
        match=r'scratch\.html#rootless is the reply of rootless\(\), which replaces #rootless, so its root <div> must '
        r'carry id="rootless"; it has no id',
    ):
        client.hx_post("/t/rootless")


def test_a_view_decorator_above_interaction_wraps_the_route(rota, client, db, django_user_model):
    url = reverse("dj_hx:sign_off", kwargs={"member": 5})
    r = client.post(url)  # a browser, signed out: @login_required answers
    assert (r.status_code, r["Location"]) == (302, f"/accounts/login/?next={url}")
    with pytest.raises(HxRedirectIntoFragment, match=r"sign_off\(\) answered a request that targets an element with a 302"):
        client.hx_post(url)  # its 302 to a control that targets an element, which the guard records
    client.force_login(django_user_model.objects.create_user("ada"))
    r = client.hx_post(url)
    assert (r.status_code, r.content.decode()) == (200, '<div id="signoff">Signed off by ada</div>')


def test_a_view_decorator_below_interaction_is_a_return_type_error(scratch, rota, client, db):
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/below")
    @login_required
    def below(request):
        return {"value": "signed in"}

    with pytest.raises(
        ImproperlyConfigured,
        match=r"below\(\) returned HttpResponseRedirect; .*write a view that returns navigate\(\)\. Django view "
        r"decorators \(@login_required, @permission_required\) go above @interaction, where they wrap the routed view\.",
    ):
        client.hx_post("/t/below")  # signed out


def test_an_interaction_registered_after_the_urlconf_was_read_is_routed_to_its_view_alone(scratch, rota, client, db):
    # The `scratch` interactions are all registered late; README says a decorator above one is not bound.
    @login_required
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/late")
    def late(request):
        return {"value": "routed undecorated"}

    assert client.hx_post("/t/late").content.decode() == '<div id="box">routed undecorated</div>'  # signed out


def test_findings_name_the_handler(rota, client):
    with pytest.raises(HxFragmentIntoPage, match=r"notify\(\) answers a boosted or body-targeted htmx request"):
        client.hx_post("/x/rota/notify/spring/3/", full=True)


# ---------------------------------------------------------------------- {% act %}


def test_act_reverses_the_route_from_keywords_in_any_order(rota):
    assert render_act("{% act 'notify' member=m contest=c %}", c="spring", m=3) == "/x/rota/notify/spring/3/"
    assert render_act("{% act 'notify_reviewer' member=5 %}") == "/reviewers/5/notify"


def test_act_refuses_a_positional_argument_naming_the_parameters(rota):
    with pytest.raises(
        TemplateSyntaxError,
        match=r"\{% act 'notify' %\} takes keyword arguments only, one for each parameter of notify\(\) "
        r"\(contest, member\), and was given 2 positional\. Write \{% act 'notify' contest=\.\.\. member=\.\.\. %\}",
    ):
        render_act("{% act 'notify' 'spring' 3 %}")


def test_act_refuses_an_unknown_or_a_missing_keyword(rota):
    with pytest.raises(
        TemplateSyntaxError,
        match=r"\{% act 'notify' %\}: notify\(\) takes no who; member is missing\. notify\(\) takes contest, member; "
        r"write \{% act 'notify' contest=\.\.\. member=\.\.\. %\}",
    ):
        render_act("{% act 'notify' contest='spring' who=3 %}")
    with pytest.raises(TemplateSyntaxError, match=r"\{% act 'notify' %\}: member is missing\."):
        render_act("{% act 'notify' contest='spring' %}")


def test_act_lists_the_interactions_when_it_names_none(rota):
    with pytest.raises(
        TemplateSyntaxError,
        match=r"\{% act 'notfy' %\} names no interaction; the interactions are: notify, notify_reviewer, sign_off\.",
    ):
        render_act("{% act 'notfy' %}")


def test_act_reverses_a_handler_parameter_called_name(scratch, rota):
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/rename/<str:name>")
    def rename(request, name: str):
        return None

    clear_url_caches()
    assert render_act("{% act 'rename' name='ada' %}") == "/t/rename/ada"


def test_act_refuses_an_unknown_keyword_called_name(rota):
    with pytest.raises(TemplateSyntaxError, match=r"\{% act 'notify' %\}: notify\(\) takes no name\. notify\(\) takes contest, member"):
        render_act("{% act 'notify' contest='spring' member=3 name='x' %}")
