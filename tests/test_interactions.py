"""
Interactions: ``@interaction``, the routes it mints, ``{% act %}`` and the wrapper view's guards. Each
test seeds one mistake an app could contain and asserts that it is loud, or seeds the rule and asserts
what a request gets. The rota app (tests/interactions_app) is registered by dj-hx's ready(); a test
that defines its own interactions takes ``scratch``, which puts the registry back afterwards.
"""

import functools
import inspect
import io
import itertools
import json
import re
import sys
import types

import pytest
from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.checks import WARNING
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.template import Context, Template, TemplateSyntaxError
from django.test import override_settings
from django.urls import Resolver404, clear_url_caches, resolve, reverse
from django.utils.module_loading import module_has_submodule

import dj_hx.urls  # noqa: F401  binds the routes now, after ready(), before any `scratch` snapshot of them
from dj_hx import HxFragmentIntoPage, HxPartialRootId, HxRedirectIntoFragment, HxUndefinedVariable, checks, interaction
from dj_hx.hxmap import build_map, print_map
from dj_hx.interactions import act_not_included, bind_routes, registry, urlpatterns
from dj_hx.templates import in_site_packages
from dj_hx.testing import assert_no_hx_check_issues, hx_check_messages
from tests.conftest import locmem, on_disk
from tests.interactions_app import views

ROTA = """{% extends "layout.html" %}{% load hx %}{% block content %}<h1>{{ contest }}</h1>
{% partialdef notify inline %}<div id="notify">{% for member in members %}<button hx-post="{% act 'notify' contest=contest member=member %}" hx-target="#notify" hx-swap="outerHTML">Notify {{ member }}</button>{% endfor %}{% if notified %}<p class="done">Notified {{ notified }}</p>{% endif %}{% if error %}<p class="error">{{ error }}</p>{% endif %}</div>{% endpartialdef %}
{% endblock %}"""

REVIEWERS = """{% load hx %}{% partialdef reviewer inline %}<div id="reviewer"><button hx-post="{% act 'notify_reviewer' member=member %}" hx-target="#reviewer" hx-swap="outerHTML">Notify reviewer {{ member }}</button>{% if notified %}<p class="done">Reviewer notified</p>{% endif %}</div>{% endpartialdef %}
{% partialdef signoff inline %}<div id="signoff">{% if signed %}Signed off by {{ request.user.username }}{% endif %}</div>{% endpartialdef %}
{% partialdef approval inline %}<div id="approval">{% if approved %}Approved by {{ request.user.username }}{% endif %}</div>{% endpartialdef %}"""

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


# A views module that applies @interaction as a call, not as a decorator. Its last line is the test's.
FUNCTIONAL_VIEWS = """
import functools
import sys

from dj_hx import interaction

def box_context(request):
    return {"value": "nothing yet", "error": None}

def audited(view):
    @functools.wraps(view)
    def wrapper(request, **kwargs):
        return view(request, **kwargs)
    return wrapper

def remind(request):  # kept plain, so a unit test can call it for its dict
    return {"value": "reminded"}

REMIND = dict(partial="scratch.html#box", context=box_context, route="t/remind")
"""


def functional_views(monkeypatch, last_line):
    """That module, imported as tests.functional_views: its interaction is registered, its routes not yet bound."""
    module = types.ModuleType("tests.functional_views")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(FUNCTIONAL_VIEWS + last_line, module.__dict__)
    return module


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


@pytest.mark.parametrize("method", ["FETCH", "QUERY", "", None])
def test_method_is_one_an_interaction_answers(scratch, method):
    def save(request):
        return None

    with pytest.raises(
        ImproperlyConfigured,
        match=rf"save\(\): method={re.escape(repr(method))} is not a method an interaction answers; write GET, POST, PUT, "
        r"PATCH or DELETE\.",
    ):
        interaction(method, partial="scratch.html#box", context=nothing, route="save/")(save)
    assert "save" not in registry
    interaction("post", partial="scratch.html#box", context=nothing, route="save/")(save)  # any case
    assert registry["save"].method == "POST"


@pytest.mark.parametrize(
    "refuses, holds",
    [(("DomainError",), "'DomainError'"), ("DomainError", "'DomainError'"), ((LookupError, 3), "3"), ([KeyError, str], "<class 'str'>")],
    ids=["name-in-tuple", "name", "number", "not-an-exception"],
)
def test_refuses_holds_exception_classes(scratch, refuses, holds):
    def save(request):
        return None

    with pytest.raises(
        ImproperlyConfigured,
        match=rf"save\(\): refuses={re.escape(repr(refuses))} holds {re.escape(holds)}, which is not an exception class\. "
        r"Name the classes themselves: refuses=\(DomainError,\)\.",
    ):
        interaction("POST", partial="scratch.html#box", context=nothing, refuses=refuses, route="save/")(save)
    assert "save" not in registry


def test_refuses_takes_one_exception_class_as_well_as_a_tuple(scratch, rota, client):
    @interaction("POST", partial="scratch.html#box", context=box_context, refuses=LookupError, route="t/lookup")
    def lookup(request):
        raise LookupError("not here")

    r = client.hx_post("/t/lookup")
    assert (r.status_code, r.content.decode()) == (422, '<div id="box">nothing yet not here</div>')


def star(request, *extra):
    return None


def double_star(request, **extra):
    return None


@pytest.mark.parametrize("handler, takes", [(star, r"\*extra"), (double_star, r"\*\*extra")], ids=["args", "kwargs"])
def test_a_handler_takes_named_parameters_only(scratch, monkeypatch, handler, takes):
    monkeypatch.setattr(handler, "__module__", views.__name__)  # as if written in the rota app's views.py: a minted route
    with pytest.raises(
        ImproperlyConfigured,
        match=rf"{handler.__name__}\(\) takes {takes}, which would mint a route segment like <str:extra>\. An interaction "
        r"takes named parameters only, one for each segment of its route\.",
    ):
        interaction("POST", partial="scratch.html#box", context=nothing)(handler)
    assert handler.__name__ not in registry


def test_a_context_parameter_the_route_lacks_takes_its_default(scratch, rota, client):
    def paged_context(request, page=1):
        return {"value": f"page {page}", "error": None}

    @interaction("POST", partial="scratch.html#box", context=paged_context, route="t/first")
    def first(request):
        return None

    @interaction("POST", partial="scratch.html#box", context=paged_context, route="t/paged/<int:page>")
    def paged(request, page: int):
        return None

    assert client.hx_post("/t/first").content.decode() == '<div id="box">page 1</div>'
    assert client.hx_post("/t/paged/3").content.decode() == '<div id="box">page 3</div>'


def test_a_required_context_parameter_the_route_lacks_raises_at_import(scratch):
    def contest_context(request, contest, page=1):
        return {}

    def tally(request, member: int):
        return None

    with pytest.raises(
        ImproperlyConfigured,
        match=r"tally\(\): context=contest_context\(\) takes contest, which the route of tally\(\) does not have \(it has "
        r"member\)\. Give contest a default there, or make it a parameter of tally\(\) too\.",
    ):
        interaction("POST", partial="scratch.html#box", context=contest_context, route="t/<int:member>")(tally)
    assert "tally" not in registry


def spread_context(request, *args):
    return {}


def keyed_context(request, **kwargs):
    return {}


@pytest.mark.parametrize("context, takes", [(spread_context, r"\*args"), (keyed_context, r"\*\*kwargs")], ids=["args", "kwargs"])
def test_context_takes_named_parameters_only(scratch, context, takes):
    def show(request):
        return None

    with pytest.raises(
        ImproperlyConfigured,
        match=rf"show\(\): context={context.__name__}\(\) takes {takes}; context= takes named parameters only: request, "
        r"then any of the route's parameters it needs\.",
    ):
        interaction("GET", partial="scratch.html#box", context=context, route="show/")(show)
    assert "show" not in registry


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


def test_a_page_that_renders_the_partial_without_error_fails_the_test(rota, client):
    # Every reply carries `error`, but the page view is not a reply: its own context has to define it.
    with pytest.raises(HxUndefinedVariable) as info:
        client.get("/rota/spring/without-error/")
    assert [str(lookup) for lookup in info.value.lookups] == ["rota.html:2: 'error' in {% if error %}"]
    assert str(info.value).startswith("GET /rota/spring/without-error/ read 1 undefined template variable,")
    assert views.rota_context(None, "spring")["error"] is None
    assert client.get("/rota/spring/").status_code == 200  # the same page, from that context


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


def test_every_reply_carries_error_so_its_partial_can_read_it(scratch, rota, client):
    def bare_context(request):  # defines no `error`: the layer owns it
        return {"value": "nothing yet"}

    @interaction("POST", partial="scratch.html#box", context=bare_context, refuses=(LookupError,), route="t/vanish")
    def vanish(request):
        if request.POST.get("gone"):
            raise LookupError("gone")
        if request.POST.get("warn"):
            return {"value": "kept", "error": "careful"}  # the handler may set it too
        return {"value": "kept"}

    # The strict client raises HxUndefinedVariable on a reply whose {% if error %} reads a missing name.
    r = client.hx_post("/t/vanish")
    assert (r.status_code, r.content.decode()) == (200, '<div id="box">kept</div>')
    r = client.hx_post("/t/vanish", {"warn": "1"})
    assert (r.status_code, r.content.decode()) == (200, '<div id="box">kept careful</div>')
    r = client.hx_post("/t/vanish", {"gone": "1"})
    assert (r.status_code, r.content.decode()) == (422, '<div id="box">nothing yet gone</div>')


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


def test_a_decorator_above_interaction_without_wraps_is_routed_as_written(rota, client, db, django_user_model):
    url = reverse("dj_hx:approve", kwargs={"member": 5})  # views.staff_only sets no __wrapped__
    client.force_login(django_user_model.objects.create_user("bob"))
    r = client.hx_post(url)
    assert (r.status_code, r.content.decode()) == (403, "Staff only.")
    client.force_login(django_user_model.objects.create_user("ada", is_staff=True))
    r = client.hx_post(url)
    assert (r.status_code, r.content.decode()) == (200, '<div id="approval">Approved by ada</div>')


@pytest.mark.parametrize("held", [None, "not callable"], ids=["missing", "not-callable"])
def test_bind_routes_routes_the_view_when_the_module_holds_nothing_callable(scratch, rota, client, monkeypatch, held):
    def deny(view):
        def check(request, **kwargs):
            return HttpResponse("denied", status=403)

        return check

    @deny  # applied, but the module holds no callable `ghost`, so the route gets the bare view without it
    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/ghost")
    def ghost(request):  # a local function: the module holds no `ghost` unless the test puts one there
        return {"value": "the view itself"}

    if held is not None:
        monkeypatch.setattr(sys.modules[__name__], "ghost", held, raising=False)
    bind_routes()
    assert client.hx_post("/t/ghost").content.decode() == '<div id="box">the view itself</div>'


def test_a_module_holding_the_raw_handler_raises_when_the_routes_are_bound(scratch, monkeypatch):
    functional_views(monkeypatch, 'remind_view = interaction("POST", **REMIND)(remind)\n')
    bound = list(urlpatterns)
    with pytest.raises(
        ImproperlyConfigured,
        match=r"tests\.functional_views\.remind holds remind\(\) itself, not the view @interaction returned, so its route "
        r"would skip the method guard, the declared refusals and the return-type guard\. Apply @interaction as a "
        r"decorator, or bind its result to the handler's own name in the module that defines it, tests\.functional_views: "
        r"remind = interaction\(\.\.\.\)\(remind\)\. The handler stays reachable as inspect\.unwrap\(remind\)\.",
    ):
        bind_routes()
    assert urlpatterns == bound  # nothing was rebound


def test_a_decorator_that_skips_the_view_raises_when_the_routes_are_bound(scratch, monkeypatch):
    functional_views(monkeypatch, 'remind_view = interaction("POST", **REMIND)(remind)\nremind = audited(remind)\n')
    with pytest.raises(
        ImproperlyConfigured, match=r"tests\.functional_views\.remind holds a decorator of remind\(\) itself, not the view"
    ):
        bind_routes()


def test_the_call_form_in_another_module_says_to_bind_it_in_the_handlers_own(scratch, monkeypatch):
    handlers = types.ModuleType("tests.functional_handlers")
    monkeypatch.setitem(sys.modules, handlers.__name__, handlers)
    exec("def nudge(request):\n    return {'value': 'nudged'}\n", handlers.__dict__)
    functional_views(monkeypatch, 'nudge = interaction("POST", **REMIND)(sys.modules["tests.functional_handlers"].nudge)\n')
    with pytest.raises(
        ImproperlyConfigured,
        match=r"tests\.functional_handlers\.nudge holds nudge\(\) itself, .* bind its result to the handler's own name in "
        r"the module that defines it, tests\.functional_handlers: nudge = interaction\(\.\.\.\)\(nudge\)\.",
    ):
        bind_routes()


def test_the_functional_form_bound_to_the_handlers_name_routes_the_view(scratch, rota, client, monkeypatch):
    module = functional_views(monkeypatch, 'remind = interaction("POST", **REMIND)(remind)\n')
    bind_routes()
    assert client.hx_get("/t/remind").status_code == 405  # the method guard is on the route
    assert client.hx_post("/t/remind").content.decode() == '<div id="box">reminded</div>'
    assert inspect.unwrap(module.remind)(None) == {"value": "reminded"}  # the handler, as the message says


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
        match=r"\{% act 'notfy' %\} names no interaction; the interactions are: approve, notify, notify_reviewer, sign_off\.",
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


def test_act_names_the_include_when_dj_hx_urls_is_not_included():
    # tests/settings.py routes the example project's URLconf, which does not include dj_hx.urls
    with pytest.raises(
        ImproperlyConfigured,
        match=r"\{% act 'notify' %\} reverses notify\(\)'s route in the dj_hx namespace, which no URLconf registers: "
        r"dj_hx\.urls is not included\. Include it once, at the site root: path\(\"\", include\(\"dj_hx\.urls\"\)\)\.",
    ):
        render_act("{% act 'notify' contest='spring' member=3 %}")


# ------------------------------------------------------------------- hx_map

MAPPED = {
    "rota.html": '{% load hx %}<div id="notify"><button hx-post="{% act \'notify\' contest=c member=m %}" '
    'hx-target="#notify" hx-swap="outerHTML">Notify</button></div>',
    "reviewers.html": '{% load hx %}<div id="approval"><button hx-post="{% act \'approve\' member=m %}" '
    'hx-target="#approval" hx-swap="outerHTML">Approve</button></div>',
}


def test_hx_map_pairs_an_act_control_with_its_interaction(rota):
    # through the registry, as {% url %} pairs a control with its view: no longer a "computed URL"
    m = build_map(sources=MAPPED)
    assert [(c.file, c.endpoint, c.scope) for c in m.controls] == [
        ("rota.html", "dj_hx:notify", "partial"),
        ("reviewers.html", "dj_hx:approve", "partial"),
    ]
    assert m.errors == [] and not [w for w in m.warnings if "computed URL" in w]
    notify = m.handlers["dj_hx:notify"]
    assert (notify.verbs, notify.templates, notify.announces) == ({"fragment"}, {"rota.html#notify"}, {"notified", "rota-changed"})
    # approve() is routed through views.staff_only, which has no functools.wraps: the map still scans the handler
    assert m.handlers["dj_hx:approve"].label == "approve()"


@pytest.mark.parametrize(
    "template, says",
    [
        ('<div hx-post="{% act \'notify\' contest=c member=m %}" hx-target="body">x</div>', "[error] x.html:1 <div> wants a page (hx-target=body) but notify() only calls fragment"),
        ("<div hx-post=\"{% act 'notfy' %}\" hx-target=\"#notify\">x</div>", "[error] x.html:1 <div> POST __ACT0__: {% act 'notfy' %} names no interaction"),
        ('<div hx-post="{% act which %}" hx-target="#notify">x</div>', "[warning] x.html:1 <div> POST __ACT0__: computed URL"),
    ],
    ids=["full-control", "no-such-interaction", "variable-name"],
)
def test_hx_map_checks_an_act_control_against_its_interaction(rota, template, says):
    out = io.StringIO()
    print_map(out=out, sources={"x.html": "{% load hx %}" + template})
    assert says in out.getvalue()


def test_hx_map_says_an_act_control_has_no_route_when_dj_hx_urls_is_not_included():
    # tests/settings.py routes the example project's URLconf, which does not include dj_hx.urls
    m = build_map(sources=MAPPED)
    assert m.errors[0] == f"rota.html:1 <button> POST __ACT0__: {act_not_included('notify')}"


def test_hx_map_reads_an_interactions_one_method(scratch, rota):
    def purge(request):
        request.POST.get("all")  # htmx 4 sends DELETE values as query parameters
        return {"value": "purged"}

    interaction("DELETE", partial="scratch.html#box", context=box_context, route="t/purge")(purge)
    m = build_map(sources={})
    assert m.handlers["dj_hx:purge"].methods == {"DELETE"}
    assert [e for e in m.errors if e.startswith("purge() reads request.POST on DELETE")]
    # a GET control reaching it gets a 405, and the dict it returns is its context: no JSON error
    m = build_map(sources={"x.html": '{% load hx %}<p hx-get="{% act \'purge\' %}" hx-target="#box">x</p>'})
    assert [(c.method, c.endpoint) for c in m.controls] == [("GET", "dj_hx:purge")]
    assert not [e for e in m.errors if "JSON" in e]


# ------------------------------------------------------------ the start-up checks

# The rota app's templates on disk, which the template checks read. Every interaction has a control;
# approve()'s takes its target and swap from an ancestor's :inherited ones. The layout hears notify()'s triggers.
CHECKED = {
    "layout.html": '{% partialdef messages inline %}<div id="messages">{% for m in messages %}<p>{{ m }}</p>{% endfor %}</div>{% endpartialdef %}\n'
    '<p id="rota-status" _="on notified from body put \'Notified\' into me end on rota-changed from body add .stale to me"></p>',
    "rota.html": ROTA,
    "reviewers.html": """{% load hx %}{% partialdef reviewer inline %}<div id="reviewer"><button hx-post="{% act 'notify_reviewer' member=member %}" hx-target="#reviewer" hx-swap="outerHTML">Notify</button></div>{% endpartialdef %}
{% partialdef signoff inline %}<div id="signoff"><button hx-post="{% act 'sign_off' member=member %}" hx-target="#signoff" hx-swap="outerHTML">Sign off</button></div>{% endpartialdef %}
{% partialdef approval inline %}<div id="approval" hx-target:inherited="#approval" hx-swap:inherited="outerHTML"><button hx-post="{% act 'approve' member=member %}">Approve</button></div>{% endpartialdef %}""",
}
# views.staff_only wraps approve() without functools.wraps, on purpose, so W018 cannot see the interaction through it.
APPROVE_UNVERIFIED = ("dj_hx.W018", "tests.interactions_app.views.approve")
NOTIFY = "{% act 'notify' contest='spring' member=3 %}"
NOTIFY_BODY = ROTA.split("{% partialdef notify inline %}")[1].split("{% endpartialdef %}")[0]


@pytest.fixture
def startup(tmp_path):
    """dj-hx's check messages for the rota app, its templates on disk: CHECKED, with the test's laid over it."""
    runs = itertools.count()

    def run(**templates):
        directory = tmp_path / str(next(runs))
        directory.mkdir()
        with checked_on_disk(directory, templates):
            return hx_check_messages()

    return run


def checked_on_disk(directory, templates, **settings):
    """The rota app's settings, CHECKED with ``templates`` laid over it written to ``directory``."""
    for name, source in {**CHECKED, **templates}.items():
        (directory / name).write_text(source)
    return override_settings(ROOT_URLCONF="tests.urlconfs.interactions", TEMPLATES=on_disk(directory), **settings)


def found(messages):
    """(id, where) for each message but the W018 the rota app carries on purpose."""
    return [(m.id, m.obj) for m in messages if (m.id, m.obj) != APPROVE_UNVERIFIED]


def the(messages, check_id):
    [message] = [m for m in messages if m.id == check_id]
    return message


def control(act, verb="hx-post", rest='hx-target="#notify" hx-swap="outerHTML"'):
    """A template whose one control, on line 2, takes its URL from ``act``."""
    return f'{{% load hx %}}\n<button {verb}="{act}" {rest}>Go</button>'


def routing_messages():
    """The routing checks alone, which need no templates."""
    return [m for m in checks.check_interaction_routes() if (m.id, m.obj) != APPROVE_UNVERIFIED]


def test_the_rota_app_passes_every_check_but_the_warning_it_carries_on_purpose(startup):
    assert [(m.id, m.obj) for m in startup()] == [APPROVE_UNVERIFIED]


def test_e009_an_act_that_names_no_interaction(startup):
    messages = startup(**{"extra.html": control("{% act 'notfy' contest='spring' member=3 %}")})
    assert found(messages) == [("dj_hx.E009", "extra.html:2")]
    assert the(messages, "dj_hx.E009").msg.startswith(
        "{% act 'notfy' %} names no interaction; the interactions are: approve, notify, notify_reviewer, sign_off."
    )


@pytest.mark.parametrize(
    "act, says",
    [
        (
            "{% act 'notify' contest='spring' who=3 %}",
            "{% act 'notify' %}: notify() takes no who; member is missing. notify() takes contest, member; write "
            "{% act 'notify' contest=... member=... %}.",
        ),
        (
            "{% act 'notify' 'spring' 3 %}",
            "{% act 'notify' %} takes keyword arguments only, one for each parameter of notify() (contest, member), and "
            "was given 2 positional.",
        ),
    ],
    ids=["keywords", "positional"],
)
def test_e010_act_arguments_that_are_not_the_handlers_parameters(startup, act, says):
    messages = startup(**{"extra.html": control(act)})
    assert found(messages) == [("dj_hx.E010", "extra.html:2")] and says in the(messages, "dj_hx.E010").msg


@pytest.mark.parametrize(
    "verb, rest, sends",
    [
        ("hx-get", 'hx-target="#notify" hx-swap="outerHTML"', "GET"),
        ("hx-put", 'hx-target="#notify" hx-swap="outerHTML"', "PUT"),
        ("hx-action", 'hx-method="get" hx-target="#notify" hx-swap="outerHTML"', "GET"),
        ("hx-action", 'hx-target="#notify" hx-swap="outerHTML"', "GET"),  # hx-method defaults to GET
    ],
    ids=["hx-get", "hx-put", "hx-action-get", "hx-action-default"],
)
def test_e011_a_control_that_sends_another_method(startup, verb, rest, sends):
    messages = startup(**{"extra.html": control(NOTIFY, verb, rest)})
    assert found(messages) == [("dj_hx.E011", "extra.html:2")]
    message = the(messages, "dj_hx.E011")
    assert f"{{% act 'notify' %}} is in {verb}, so its control sends {sends}, but notify() answers POST" in message.msg
    assert f"a {sends} gets a 405" in message.msg and "hx-post=" in message.hint


@pytest.mark.parametrize(
    "template",
    [
        control(NOTIFY, "hx-action", 'hx-method="post" hx-target="#notify" hx-swap="outerHTML"'),
        '{% load hx %}\n<form method="post" hx-action="' + NOTIFY + '" hx-target="#notify" hx-swap="outerHTML"><button>Go</button></form>',
        '{% load hx %}\n<div hx-method:inherited="post"><button hx-action="' + NOTIFY + '" hx-target="#notify" hx-swap="outerHTML">Go</button></div>',
    ],
    ids=["own-hx-method", "form-method", "inherited-hx-method"],
)
def test_e011_reads_hx_actions_method_as_htmx_4_does(startup, template):
    # mapcore.action_method: its hx-method, else an ancestor's hx-method:inherited, else its method attribute, else GET
    assert found(startup(**{"extra.html": template})) == []


def test_e011_a_plain_hx_method_on_an_ancestor_does_not_reach_the_control(startup):
    template = '{% load hx %}\n<div hx-method="post"><button hx-action="' + NOTIFY + '" hx-target="#notify" hx-swap="outerHTML">Go</button></div>'
    messages = startup(**{"extra.html": template})
    assert found(messages) == [("dj_hx.E011", "extra.html:2")]
    assert "{% act 'notify' %} is in hx-action, so its control sends GET" in the(messages, "dj_hx.E011").msg


@pytest.mark.parametrize(
    "template, says",
    [
        (control(NOTIFY, rest='hx-target="#rota" hx-swap="outerHTML"'), "its hx-target is '#rota'"),
        (
            control(NOTIFY, rest='hx-swap="outerHTML"'),
            'it has no hx-target, so htmx 4 targets the control itself, a <button> with no id, which would need id="notify"',
        ),
        (
            '{% load hx %}\n<div hx-target="#notify"><button hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</button></div>',
            'it has no hx-target, so htmx 4 targets the control itself, a <button> with no id, which would need id="notify"; '
            "the plain hx-target on <div> above it does not reach it in htmx 4",
        ),
        (
            '{% load hx %}\n<div id="box" hx-post="' + NOTIFY + '" hx-target="this" hx-swap="outerHTML">Go</div>',
            "its hx-target is 'this', so htmx 4 targets the element that declares it, a <div> with id=\"box\", which "
            'would need id="notify"',
        ),
        (
            '{% load hx %}\n<div class="box" hx-target:inherited="this" hx-swap:inherited="outerHTML"><button hx-post="'
            + NOTIFY + '">Go</button></div>',
            "its hx-target is 'this', so htmx 4 targets the element that declares it, a <div> with no id, which would need "
            'id="notify"',
        ),
    ],
    ids=["another", "none", "plain-ancestor", "this-wrong-id", "inherited-this-no-id"],
)
def test_e012_a_control_whose_target_is_not_the_partial(startup, template, says):
    messages = startup(**{"extra.html": template})
    assert found(messages) == [("dj_hx.E012", "extra.html:2")]
    message = the(messages, "dj_hx.E012")
    assert "notify() replies with its partial, #notify" in message.msg and says in message.msg
    assert 'hx-target="#notify"' in message.hint and 'hx-target:inherited="#notify"' in message.hint


def swapping(swap):
    return control(NOTIFY, rest=f'hx-target="#notify" hx-swap="{swap}"')


@pytest.mark.parametrize(
    "template, says, two_ids",
    [
        (control(NOTIFY, rest='hx-target="#notify"'), "it has no hx-swap, so htmx 4 swaps innerHTML", True),
        (swapping("innerHTML"), "its hx-swap is 'innerHTML'", True),
        (swapping("innerMorph"), "its hx-swap is 'innerMorph'", True),  # morphs the reply, root and all, into the target
        (
            '{% load hx %}\n<div hx-swap="outerHTML"><button hx-post="' + NOTIFY + '" hx-target="#notify">Go</button></div>',
            "the plain hx-swap on <div> above it does not reach it in htmx 4",
            True,
        ),
        (swapping("none"), "its hx-swap is 'none'", False),
        (swapping("delete"), "its hx-swap is 'delete'", False),
        (swapping("textContent"), "its hx-swap is 'textContent'", False),
    ],
    ids=["none", "innerHTML", "innerMorph", "plain-ancestor", "style-none", "delete", "textContent"],
)
def test_e013_a_control_that_does_not_swap_outer(startup, template, says, two_ids):
    messages = startup(**{"extra.html": template})
    assert found(messages) == [("dj_hx.E013", "extra.html:2")]
    message = the(messages, "dj_hx.E013")
    assert "so the control must use an outer swap (outerHTML, outerMorph or outerSync)" in message.msg
    assert says in message.msg and ('two elements with id="notify"' in message.msg) == two_ids
    assert 'hx-swap="outerHTML"' in message.hint


@pytest.mark.parametrize(
    "swap", ["outerHTML", "outerMorph", "outerSync", "outerMorph transition:true", "outerHTML swap:100ms"]
)
def test_e013_takes_each_outer_swap_whatever_its_modifiers(startup, swap):
    # htmx 4.0.2's swap code: outerMorph morphs the target itself; outerSync copies the reply root's attributes onto
    # the target and replaces its children with the root's. Each leaves one element with the id, as outerHTML does.
    assert found(startup(**{"extra.html": swapping(swap)})) == []


@pytest.mark.parametrize(
    "template",
    [
        '{% load hx %}\n<div id="notify" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</div>',
        '{% load hx %}\n<div id="notify" hx-post="' + NOTIFY + '" hx-target="this" hx-swap="outerHTML">Go</div>',
        '{% load hx %}\n<div id="notify" hx-target:inherited="this" hx-swap:inherited="outerHTML"><button hx-post="'
        + NOTIFY + '">Go</button></div>',
    ],
    ids=["no-target", "this", "inherited-this"],
)
def test_e012_takes_a_control_that_targets_the_element_with_the_partials_id(startup, template):
    # htmx 4.0.2: no hx-target targets the control itself; "this" is the element that declares it (#K, #z)
    assert found(startup(**{"extra.html": template})) == []


@pytest.mark.parametrize(
    "selector",
    [
        "closest #notify",
        "find #notify",
        "findAll #notify",
        "next #notify",
        "previous #notify",
        "global #notify",
        "global closest #notify",
        "closest #{{ name }}",
    ],
)
def test_e012_takes_an_extended_selector_whose_css_part_is_the_partials_id(startup, selector):
    # htmx 4.0.2's target resolver (#be) strips "global ", then reads closest/find/findAll/next/previous X as a
    # search for the CSS selector X: with X #notify it reaches the element with the partial's id, or nothing
    assert found(startup(**{"extra.html": control(NOTIFY, rest=f'hx-target="{selector}" hx-swap="outerHTML"')})) == []


@pytest.mark.parametrize(
    "selector",
    ["closest #other", "closest .card", "closest #row-{{ pk }}", "#notify, #other", "next", "previous", "document"],
)
def test_e012_an_extended_selector_that_does_not_name_the_partial(startup, selector):
    # another id or a class; a comma list, whose first match is whichever comes first; bare next or previous,
    # the sibling whatever its id; a fixed target
    messages = startup(**{"extra.html": control(NOTIFY, rest=f'hx-target="{selector}" hx-swap="outerHTML"')})
    assert found(messages) == [("dj_hx.E012", "extra.html:2")]
    assert f"its hx-target is '{selector}'".replace("{{ pk }}", "{{…}}") in the(messages, "dj_hx.E012").msg


def test_e012_and_e013_read_an_ancestors_inherited_target_and_swap(startup):
    template = '{% load hx %}\n<div hx-target:inherited="#notify" hx-swap:inherited="outerHTML swap:100ms"><button hx-post="' + NOTIFY + '">Go</button></div>'
    assert found(startup(**{"extra.html": template})) == []


@pytest.mark.parametrize(
    "verb, rest",
    [
        ("hx-post", 'hx-target="#{{ region }}" hx-swap="outerHTML"'),
        ("hx-post", 'hx-target="#notify" hx-swap="{{ swap }}"'),
        ("hx-action", 'hx-method="{{ method }}" hx-target="#notify" hx-swap="outerHTML"'),
    ],
    ids=["hx-target", "hx-swap", "hx-method"],
)
def test_e011_to_e013_do_not_judge_a_computed_value(startup, verb, rest):
    assert found(startup(**{"extra.html": control(NOTIFY, verb, rest)})) == []


@pytest.mark.parametrize(
    "template, says",
    [
        (
            '{% load hx %}\n<button id="row-{{ pk }}" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</button>',
            'it has no hx-target, so htmx 4 targets the control itself, a <button> with id="row-{{…}}", which would need '
            'id="notify"',
        ),
        (
            '{% load hx %}\n<li id="item-{{ pk }}" hx-target:inherited="this" hx-swap:inherited="outerHTML"><button hx-post="'
            + NOTIFY + '">Go</button></li>',
            "its hx-target is 'this', so htmx 4 targets the element that declares it, a <li> with id=\"item-{{…}}\", which "
            'would need id="notify"',
        ),
        (control(NOTIFY, rest='hx-target="#row-{{ pk }}" hx-swap="outerHTML"'), "its hx-target is '#row-{{…}}'"),
        (
            '{% load hx %}\n<button id="{% if p %}{{ p }}-{% endif %}row" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</button>',
            'it has no hx-target, so htmx 4 targets the control itself, a <button> with id="{%…%}{{…}}-{%…%}row", '
            'which would need id="notify"',
        ),
        (control(NOTIFY, rest='hx-target="#notify div" hx-swap="outerHTML"'), "its hx-target is '#notify div'"),
    ],
    ids=["row-id-no-target", "item-id-click-to-edit", "row-selector", "if-built-id", "descendant-selector"],
)
def test_e012_judges_a_templated_id_or_selector_by_its_literal_parts(startup, template, says):
    messages = startup(**{"extra.html": template})
    assert found(messages) == [("dj_hx.E012", "extra.html:2")] and says in the(messages, "dj_hx.E012").msg


@pytest.mark.parametrize(
    "template",
    [
        '{% load hx %}\n<div id="{{ region }}" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</div>',
        '{% load hx %}\n<li id="{{ region }}" hx-target:inherited="this" hx-swap:inherited="outerHTML"><button hx-post="'
        + NOTIFY + '">Go</button></li>',
        control(NOTIFY, rest='hx-target="#{{ name }}" hx-swap="outerHTML"'),
        '{% load hx %}\n<div id="{{ prefix }}notify" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</div>',
        '{% load hx %}\n<div id="{{\n region }}" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</div>',
        # a block tag strips to whitespace, which an id cannot hold: what it wraps may not render
        '{% load hx %}\n<div id="{% if p %}{{ p }}-{% endif %}notify" hx-post="' + NOTIFY + '" hx-swap="outerHTML">Go</div>',
        '{% load hx %}\n<li id="{% if wide %}wide-{% endif %}notify" hx-target:inherited="this" hx-swap:inherited="outerHTML">'
        '<button hx-post="' + NOTIFY + '">Go</button></li>',
    ],
    ids=["id", "click-to-edit-id", "selector", "literal-suffix", "expression-across-lines", "if-built-id", "if-built-literal-prefix"],
)
def test_e012_skips_a_templated_value_that_could_be_the_partials_id(startup, template):
    assert found(startup(**{"extra.html": template})) == []



@pytest.mark.parametrize("url", ["{% url 'dj_hx:sign_off' member=member %}", "/reviewers/{{ member }}/sign-off"], ids=["url-tag", "path"])
def test_e014_an_interaction_no_template_writes_an_act_for(startup, url):
    # a control that reaches sign_off() by {% url %} or a hand-written path is not counted: E011-E013 cannot check it
    reviewers = CHECKED["reviewers.html"].replace("{% act 'sign_off' member=member %}", url)
    messages = startup(**{"reviewers.html": reviewers})
    assert found(messages) == [("dj_hx.E014", "tests.interactions_app.views.sign_off")]
    message = the(messages, "dj_hx.E014")
    assert message.msg == (
        "sign_off() has no control: no project template writes {% act 'sign_off' %}. A {% url 'dj_hx:sign_off' %} or a "
        "hand-written path is not counted, because E011 to E013 cannot check it."
    )
    assert """hx-post="{% act 'sign_off' member=... %}" hx-target="#signoff" hx-swap="outerHTML\"""" in message.hint


@pytest.mark.parametrize("installed", [True, False], ids=["site-packages", "project"])
def test_e014_skips_an_interaction_whose_handler_is_in_site_packages(scratch, startup, tmp_path, monkeypatch, installed):
    # Its controls are in that app's own templates, which the checks never read. pip install --user puts it here:
    import site

    user_site = tmp_path / "site-packages"
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(user_site))
    module = types.ModuleType("shelf.views")
    module.__file__ = str((user_site if installed else tmp_path / "project") / "shelf" / "views.py")
    monkeypatch.setitem(sys.modules, module.__name__, module)

    def shelve(request):
        return None

    shelve.__module__ = module.__name__
    interaction("POST", partial="rota.html#notify", context=nothing, route="t/shelve")(shelve)
    assert found(startup()) == ([] if installed else [("dj_hx.E014", "shelf.views.shelve")])


@pytest.mark.parametrize(
    "partial, says",
    [
        ("rota.html#gone", "rota.html defines no partial 'gone'; it defines: notify."),
        ("nowhere.html#gone", "nowhere.html#gone: the template 'nowhere.html' does not exist"),
    ],
    ids=["partial", "template"],
)
def test_e015_an_interaction_whose_partial_does_not_exist(scratch, startup, partial, says):
    def gone(request):
        return None

    interaction("POST", partial=partial, context=nothing, route="t/gone")(gone)
    messages = startup(**{"extra.html": control("{% act 'gone' %}", rest='hx-target="#gone" hx-swap="outerHTML"')})
    assert found(messages) == [("dj_hx.E015", "tests.test_interactions.gone")]
    assert the(messages, "dj_hx.E015").msg.startswith(f"gone() replies with {partial}, which does not load: {says}")


@pytest.mark.parametrize(
    "root, says",
    [
        ('<div class="notify">', ', so its root <div> must carry id="notify"; it has no id'),
        ('<div id="notice">', ', so its root <div> must carry id="notify"; it has id="notice"'),
        ('Notify: <div id="notify">', ' but does not start with an element; it must be one element with id="notify"'),
        ('<div id="item-{{ pk }}">', ', so its root <div> must carry id="notify"; it has id="item-{{…}}"'),
        (
            '<div id="{% if p %}{{ p }}-{% endif %}notice">',
            ', so its root <div> must carry id="notify"; it has id="{%…%}{{…}}-{%…%}notice"',
        ),
    ],
    ids=["no-id", "another-id", "text-first", "templated-id", "if-built-id"],
)
def test_e016_a_partial_whose_root_is_not_its_name(startup, root, says):
    messages = startup(**{"rota.html": ROTA.replace('<div id="notify">', root)})
    assert found(messages) == [("dj_hx.E016", "rota.html:2")]
    assert the(messages, "dj_hx.E016").msg == f"rota.html#notify is the reply of notify(), which replaces #notify{says}"


@pytest.mark.parametrize(
    "templates",
    [
        {"rota.html": ROTA.replace('<div id="notify">', '<div id="{{ region }}">')},
        {"rota.html": ROTA.replace('<div id="notify">', '<div id="{{ prefix }}notify">')},
        {"rota.html": ROTA.replace('<div id="notify">', '{{ banner }}<div id="notify">')},
        {"rota.html": ROTA.replace(NOTIFY_BODY, '{% include "region.html" %}'), "region.html": "{% load hx %}" + NOTIFY_BODY},
        {"rota.html": ROTA.replace("{% partialdef notify inline %}", "{# {% partialdef notify inline %}<p>{% endpartialdef %} #}{% partialdef notify inline %}")},
        {"rota.html": ROTA.replace(NOTIFY_BODY, "{% if members %}" + NOTIFY_BODY + "{% endif %}")},
        {"rota.html": ROTA.replace('<div id="notify">', '<div id="notify"{% if notified %} class="done"{% endif %}>')},
        {"rota.html": ROTA.replace('<div id="notify">', '<div id="{% if p %}{{ p }}-{% endif %}notify">')},
        {"rota.html": ROTA.replace('<div id="notify">', '<div id="{% if wide %}wide-{% endif %}notify">')},
    ],
    ids=[
        "computed-id", "id-with-literal-suffix", "computed-first", "include", "commented-out", "block-tag-first",
        "tag-in-start-tag", "if-built-id", "if-built-literal-prefix",
    ],
)
def test_e016_judges_only_a_root_the_source_shows(startup, templates):
    assert found(startup(**templates)) == []


LATE_LOGIN = 'from django.contrib.auth.decorators import login_required\nremind = login_required(interaction("POST", **REMIND)(remind))\n'


def test_e017_an_interaction_registered_after_the_urlconf_was_read(scratch, rota, client, db, monkeypatch):
    # dj_hx.urls bound the routes when this test module imported it. This views module comes later, as one
    # imported by a URLconf listed below the include would, so its route is the bare view, without the login check.
    functional_views(monkeypatch, LATE_LOGIN)
    error = the(routing_messages(), "dj_hx.E017")
    assert error.obj == "tests.functional_views.remind"
    assert error.msg == (
        "dj_hx.urls routes remind() to the view @interaction returned, not to what tests.functional_views holds under "
        "its name, so the decorators written above @interaction do not apply to the route."
    )
    assert error.hint == (
        "remind() was registered after dj_hx.urls was first read, or tests.functional_views rebound remind since. Import "
        "tests.functional_views before the URLconf is loaded: from the app's ready(), or from its views module, which "
        "dj-hx imports at start-up."
    )
    assert client.hx_post("/t/remind").content.decode() == '<div id="box">reminded</div>'  # signed out, and answered
    bind_routes()  # the binding a URLconf read after the import makes
    assert [m.id for m in routing_messages()] == []
    assert client.post("/t/remind").status_code == 302  # now @login_required answers


def test_e017_a_module_that_rebinds_the_name_after_the_urlconf_was_read(rota, monkeypatch):
    def audited(view):
        @functools.wraps(view)
        def wrapper(request, **kwargs):
            return view(request, **kwargs)

        return wrapper

    monkeypatch.setattr(views, "sign_off", audited(views.sign_off))  # the route keeps the object it was bound to
    error = the(routing_messages(), "dj_hx.E017")
    assert error.obj == "tests.interactions_app.views.sign_off"
    assert error.msg.startswith("dj_hx.urls routes sign_off() to another object, not to what tests.interactions_app.views holds")
    assert "or tests.interactions_app.views rebound sign_off since" in error.hint


def test_e017_names_a_late_module_that_holds_the_raw_handler(scratch, rota, monkeypatch):
    functional_views(monkeypatch, 'remind_view = interaction("POST", **REMIND)(remind)\n')
    error = the(routing_messages(), "dj_hx.E017")
    assert error.obj == "tests.functional_views.remind"
    assert error.msg.startswith("tests.functional_views.remind holds remind() itself, not the view @interaction returned")


def test_w018_a_routed_attribute_that_does_not_unwrap_to_its_interaction(rota):
    [warning] = [m for m in checks.check_interaction_routes() if m.id == "dj_hx.W018"]
    assert warning.obj == "tests.interactions_app.views.approve"
    assert warning.msg == (
        "approve() is routed to tests.interactions_app.views.approve, which does not unwrap to the view @interaction "
        "returned, so dj-hx cannot tell that it wraps the interaction."
    )
    assert "Use functools.wraps in decorators above @interaction" in warning.hint


PLAIN_CHECK = """
CALLS = []

def nudge(request):  # answers POST only
    CALLS.append(request.method)
    return {"value": "nudged"}

def plain_check(view):  # a decorator without functools.wraps
    def check(request, **kwargs):
        return view(request, **kwargs)
    return check

nudge_view = interaction("POST", **REMIND)(nudge)
nudge = plain_check(nudge)
"""


def test_w018_warns_on_a_decorator_of_the_raw_handler_written_without_wraps(scratch, rota, client, monkeypatch):
    module = functional_views(monkeypatch, PLAIN_CHECK)
    bind_routes()  # nothing it can see says the wrapper holds the raw handler, so it routes it
    with pytest.raises(AttributeError, match="'dict' object has no attribute"):
        client.hx_get("/t/remind")  # the handler's dict is no response
    assert module.CALLS == ["GET"]  # a GET ran the POST-only handler: the route skips the method guard
    assert [m.obj for m in routing_messages() if m.id == "dj_hx.W018"] == ["tests.functional_views.nudge"]


def test_w019_a_handler_wrapped_below_interaction(scratch, rota):
    def audited(view):
        @functools.wraps(view)
        def wrapper(request, **kwargs):
            return view(request, **kwargs)

        return wrapper

    @interaction("POST", partial="scratch.html#box", context=box_context, route="t/logged")
    @audited
    def logged(request):
        return None

    warning = the(routing_messages(), "dj_hx.W019")
    assert warning.obj == "tests.test_interactions.logged"
    assert warning.msg == "logged() is wrapped by a decorator below @interaction, which runs inside the interaction."
    assert warning.hint.startswith("View decorators belong above @interaction")


def test_e020_when_dj_hx_urls_is_not_included():
    # tests/settings.py routes the example project's URLconf, which does not include dj_hx.urls
    messages = routing_messages()
    assert [m.id for m in messages] == ["dj_hx.E020"]
    assert messages[0].msg == (
        "Interactions are registered (approve, notify, notify_reviewer, sign_off), but dj_hx.urls is not included, "
        "so none of them has a route and every {% act %} raises."
    )
    assert messages[0].hint == 'Include it once, at the site root of ROOT_URLCONF: path("", include("dj_hx.urls")).'


@pytest.mark.parametrize(
    "template, says",
    [
        ("{% load hx %}\n<script>htmx.ajax('POST', '" + NOTIFY + "', '#notify')</script>", "is outside an attribute value"),
        ("{% load hx %}\n<p>" + NOTIFY + "</p>", "is outside an attribute value"),
        ('{% load hx %}\n<div data-url="' + NOTIFY + '"></div>', "is in data-url, which is not a verb attribute"),
        (
            "{% load hx %}\n{% act 'notify' contest='spring' member=3 as url %}"
            '<button hx-post="{{ url }}" hx-target="#notify" hx-swap="outerHTML">Go</button>',
            "stores its URL in url",
        ),
        (control("{% act which contest='spring' member=3 %}"), "names its interaction with a variable"),
    ],
    ids=["script", "text", "other-attribute", "as", "variable"],
)
def test_i021_an_act_the_checks_cannot_tie_to_a_control(startup, template, says):
    messages = startup(**{"extra.html": template})
    assert found(messages) == [("dj_hx.I021", "extra.html:2")]
    assert says in the(messages, "dj_hx.I021").msg and "SILENCED_SYSTEM_CHECKS" in the(messages, "dj_hx.I021").hint


# notify() declares triggers=("notified", "rota-changed"); CHECKED's layout listens for both.
HEARS_NOTIFIED = "<p _=\"on notified from body put 'Notified' into me\"></p>"


def test_w024_an_interactions_trigger_no_template_listens_for(startup):
    messages = startup(**{"layout.html": CHECKED["layout.html"].split("\n")[0] + "\n" + HEARS_NOTIFIED})
    assert found(messages) == [("dj_hx.W024", "tests.interactions_app.views.notify")]
    warning = the(messages, "dj_hx.W024")
    assert warning.level == WARNING
    assert warning.msg == (
        "notify() announces 'rota-changed' in its triggers=, but no project template listens for it (hx-trigger, "
        "hx-on, or a hyperscript 'on rota-changed' in an attribute or a <script type=\"text/hyperscript\">), and no "
        "script there names it."
    )
    assert 'hx-trigger="rota-changed from:body"' in warning.hint and "a JavaScript file" in warning.hint


@pytest.mark.parametrize(
    "template, says",
    [
        ('<p _="on rota-changd from body add .stale to me"></p>', "'rota-changd' is listened for (extra.html:2)"),
        (control(NOTIFY, rest='hx-trigger="rota-reset from:body" hx-target="#notify" hx-swap="outerHTML"'), "'rota-reset'"),
        ('<p hx-on:rota-cleared="this.remove()"></p>', "'rota-cleared'"),
    ],
    ids=["hyperscript", "hx-trigger", "hx-on"],
)
def test_w025_a_listener_nothing_announces(startup, template, says):
    messages = startup(**{"extra.html": "{% load hx %}\n" + template.removeprefix("{% load hx %}\n")})
    assert found(messages) == [("dj_hx.W025", "extra.html:2")]
    warning = the(messages, "dj_hx.W025")
    assert warning.level == WARNING and warning.msg.startswith(says)
    assert warning.msg.endswith(
        "but no view announces it with .trigger(), no interaction declares it in triggers=, and no script in the "
        "templates names it (a quoted name in a <script> or hx-on, or a hyperscript send or trigger)."
    )
    assert "cannot see every side" in warning.hint


@pytest.mark.parametrize(
    "template",
    [
        '<p _="on click add .x to me end on mouseover add .y to me"></p>',
        '<p hx-on:close="this.remove()"></p>',
        '<button _="on click send refreshed to me end on refreshed add .x to me">x</button>',
        '<p _="on refreshed from body add .x to me"></p><script>document.body.dispatchEvent(new Event("refreshed"))</script>',
    ],
    ids=["browser-events", "browser-event-hx-on", "hyperscript-send", "script-dispatch"],
)
def test_w025_leaves_out_browser_events_and_the_names_scripts_send(startup, template):
    assert found(startup(**{"extra.html": template})) == []


def test_w024_and_w025_count_triggers_of_an_interaction_dj_hx_urls_does_not_route(tmp_path):
    # The example project's URLconf: E020, and notify()'s triggers= still pair with the layout's listeners. The one
    # pairing Warning is the example's own contacts(), whose listener is in index.html, not among these templates.
    with checked_on_disk(tmp_path, {}), override_settings(ROOT_URLCONF="contactapp.urls"):
        messages = hx_check_messages()
    assert [(m.id, m.obj) for m in messages if m.id in ("dj_hx.W024", "dj_hx.W025")] == [("dj_hx.W024", "contacts")]
    assert "dj_hx.E020" in [m.id for m in messages]


@pytest.mark.parametrize("installed", [True, False], ids=["site-packages", "project"])
def test_w024_skips_an_interaction_whose_handler_is_in_site_packages(scratch, startup, tmp_path, monkeypatch, installed):
    import site

    user_site = tmp_path / "site-packages"
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(user_site))
    module = types.ModuleType("shelf.views")
    module.__file__ = str((user_site if installed else tmp_path / "project") / "shelf" / "views.py")
    monkeypatch.setitem(sys.modules, module.__name__, module)

    def shelve(request):
        return None

    shelve.__module__ = module.__name__
    interaction("POST", partial="rota.html#notify", context=nothing, route="t/shelve", triggers=("shelved",))(shelve)
    messages = startup(**{"extra.html": control("{% act 'shelve' %}")})
    assert [m for m in found(messages) if m[0] == "dj_hx.W024"] == ([] if installed else [("dj_hx.W024", "shelf.views.shelve")])


def test_assert_no_hx_check_issues_counts_an_info(tmp_path):
    with checked_on_disk(tmp_path, {"extra.html": "{% load hx %}\n<p>" + NOTIFY + "</p>"}, SILENCED_SYSTEM_CHECKS=["dj_hx.W018"]):
        with pytest.raises(AssertionError, match=r"\(dj_hx\.I021\) extra\.html:2: \{% act 'notify' %\} is outside an attribute"):
            assert_no_hx_check_issues()
        assert_no_hx_check_issues(include_warnings=False)  # Errors only


@pytest.mark.parametrize(
    "act, ids",
    [("{% act 'notify' who=3 %}", ["dj_hx.E010", "dj_hx.I021"]), ("{% act 'notfy' %}", ["dj_hx.E009"])],
    ids=["keywords", "name"],
)
def test_an_act_the_checks_cannot_tie_still_has_its_name_and_arguments_checked(startup, act, ids):
    messages = startup(**{"extra.html": f"{{% load hx %}}\n<script>htmx.ajax('POST', \"{act}\", '#notify')</script>"})
    assert sorted(found(messages)) == [(check_id, "extra.html:2") for check_id in ids]
