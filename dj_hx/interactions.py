"""
Interactions: one handler bound to one template partial, by name.

::

    from dj_hx import interaction

    def assign_context(request, contest):
        return {"contest": Contest.get(contest), "notified": False}

    @interaction("POST", partial="contests/assign.html#notify", context=assign_context,
                 refuses=(DomainError,), triggers=("notified",))
    def notify(request, contest: str, member: int):
        Contest.get(contest).notify(member)
        return {"notified": True}

- The route is minted from the handler: ``x/<app label>/<handler>/<param>/.../``, one segment per
  parameter after ``request``, ``<int:...>`` for an ``int`` annotation and ``<str:...>`` for
  anything else. ``route="reviewers/<int:member>/notify"`` chooses the path instead; it must name
  exactly the handler's parameters. ``dj_hx.urls`` serves every route under the ``dj_hx``
  namespace, and ``{% act 'notify' contest=contest.slug member=member.id %}`` (``{% load hx %}``)
  writes one into a control.
- The reply is always the partial, rendered by ``fragment()`` from ``context(request, ...)``,
  called with the route parameters it names, plus the keys the handler returns. A parameter of
  ``context`` that the route lacks takes its default; one without a default raises at import. A
  returned key the context does not define raises, so the page and the reply render the same
  names. The handler returns a dict or ``None``; anything else raises.
- Every reply carries ``error``, which the layer owns: ``None`` on success unless ``context`` or
  the handler sets it, so the partial can read ``{% if error %}`` without ``context`` defining it.
  A page view is not a reply: a page that renders the partial puts ``error`` in its own context.
- A declared refusal, an exception in ``refuses``, re-renders the partial with
  ``error=str(exc)`` and status 422, so the handler writes no ``try``. Any other exception is a 500.
- ``triggers`` names the facts a successful reply announces, ``.trigger(name)`` for each.
- A request with any other method gets a 405.
- dj-hx's ``ready()`` imports each project app's ``views`` module, so every route exists before
  the URLconf is read.
- ``@interaction`` returns the routed view, and ``dj_hx.urls`` routes each interaction to what its
  module holds under the handler's name, as written, so a decorator written above it
  (``@login_required``) wraps the route, as on any view. Write such decorators with
  ``functools.wraps``, so dj-hx's messages and ``hx_map`` see the handler through them. The module
  must hold that view, or a decorator of it, and never the raw handler: binding the routes raises
  then, because the raw handler would skip the method guard.
"""

from __future__ import annotations

import functools
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseNotAllowed
from django.urls import NoReverseMatch, path
from django.urls.converters import IntConverter

from .verbs import HxResponse, check_root_id, fragment

__all__ = ["interaction"]

registry: dict[str, Interaction] = {}
urlpatterns: list = []  # served by dj_hx.urls; filled as each app's views module is imported, bound by bind_routes()

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
INCLUDE = 'path("", include("dj_hx.urls"))'
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


@dataclass(frozen=True)
class Interaction:
    """One registered interaction: what its wrapper view runs, and the parameters ``{% act %}`` checks."""

    name: str
    method: str
    template: str
    partial: str
    context: Callable[..., dict]
    context_params: tuple[str, ...]  # the route's parameters that context= takes; any other it takes has a default
    refuses: tuple[type[BaseException], ...]
    triggers: tuple[str, ...]
    params: tuple[str, ...]
    func: Callable[..., Any]  # the handler
    route: str
    view: Callable[..., Any]  # the routed view @interaction returned, before any decorator above it

    def respond(self, request, **kwargs):
        """The wrapper view's body: the method guard, the handler, then its partial."""
        if request.method != self.method:
            return HttpResponseNotAllowed([self.method])
        try:
            reply = self.func(request, **kwargs)
        except self.refuses as exc:
            return self._render(request, kwargs, {"error": str(exc)}).with_status(422)
        if reply is not None and not isinstance(reply, dict):
            raise ImproperlyConfigured(
                f"{self.name}() returned {type(reply).__name__}; an interaction returns a dict of context keys, or "
                "None. An interaction always re-renders its partial; to leave the page, write a view that returns "
                "navigate(). Django view decorators (@login_required, @permission_required) go above "
                "@interaction, where they wrap the routed view."
            )
        response = self._render(request, kwargs, reply or {})
        for name in self.triggers:
            response.trigger(name)
        return response

    def _render(self, request, kwargs, reply: dict) -> HxResponse:
        # `error` is the layer's: a refusal writes it, and any other reply reads None unless context= or the handler sets it.
        context = {"error": None, **self.context(request, **{p: kwargs[p] for p in self.context_params})}
        undefined = sorted(key for key in reply if key not in context)
        if undefined:
            context_name = getattr(self.context, "__name__", repr(self.context))
            raise ImproperlyConfigured(
                f"{self.name}() returns {', '.join(map(repr, undefined))}, which {context_name}() does not define. Define each "
                "there with its default, so the page renders the same names as the reply."
            )
        response = fragment(request, self.template, self.partial, {**context, **reply})
        check_root_id(
            response.content.decode(response.charset),
            self.partial,
            f"{self.template}#{self.partial}",
            role=f"the reply of {self.name}(), which replaces #{self.partial}",
        )
        return response


def _is_int(parameter: inspect.Parameter) -> bool:
    # Under ``from __future__ import annotations`` the annotation is the string "int".
    return parameter.annotation is int or parameter.annotation == "int"


def _starred(parameter: inspect.Parameter) -> str:
    return ("*" if parameter.kind is inspect.Parameter.VAR_POSITIONAL else "**") + parameter.name


def _check_arguments(name: str, method, refuses, params: list[inspect.Parameter]) -> None:
    if not isinstance(method, str) or method.upper() not in METHODS:
        raise ImproperlyConfigured(
            f"{name}(): method={method!r} is not a method an interaction answers; write GET, POST, PUT, PATCH or DELETE."
        )
    bad = [r for r in _refusals(refuses) if not (isinstance(r, type) and issubclass(r, BaseException))]
    if bad:
        raise ImproperlyConfigured(
            f"{name}(): refuses={refuses!r} holds {', '.join(map(repr, bad))}, which {'is' if len(bad) == 1 else 'are'} "
            "not an exception class. Name the classes themselves: refuses=(DomainError,)."
        )
    variadic = [p for p in params if p.kind in _VARIADIC]
    if variadic:
        raise ImproperlyConfigured(
            f"{name}() takes {', '.join(map(_starred, variadic))}, which would mint a route segment like "
            f"<str:{variadic[0].name}>. An interaction takes named parameters only, one for each segment of its route."
        )


def _refusals(refuses) -> tuple:
    return tuple(refuses) if isinstance(refuses, (tuple, list)) else (refuses,)


def _context_params(name: str, context, params: list[inspect.Parameter]) -> tuple[str, ...]:
    """The route parameters ``context`` is called with; raises for one it needs that the route lacks."""
    context_name = getattr(context, "__name__", repr(context))
    takes = list(inspect.signature(context).parameters.values())
    variadic = [p for p in takes if p.kind in _VARIADIC]
    if variadic:
        raise ImproperlyConfigured(
            f"{name}(): context={context_name}() takes {', '.join(map(_starred, variadic))}; context= takes named "
            "parameters only: request, then any of the route's parameters it needs."
        )
    route = [p.name for p in params]
    missing = [p.name for p in takes[1:] if p.name not in route and p.default is inspect.Parameter.empty]
    if missing:
        raise ImproperlyConfigured(
            f"{name}(): context={context_name}() takes {', '.join(missing)}, which the route of {name}() does not have "
            f"(it has {', '.join(route) or 'none'}). Give {', '.join(missing)} a default there, or make "
            f"{'it' if len(missing) == 1 else 'them'} a parameter of {name}() too."
        )
    return tuple(p.name for p in takes[1:] if p.name in route)


def _check_route(name: str, route: str, pattern, params: list[inspect.Parameter]) -> None:
    converters = pattern.pattern.converters
    takes = [p.name for p in params]
    if set(converters) != set(takes):
        raise ImproperlyConfigured(
            f"{name}(route={route!r}) has parameters {list(converters)}, but {name}() takes {takes}. Name each of the "
            f"handler's parameters in the route, and nothing else, so {{% act '{name}' %}} can reverse it."
        )
    as_text = [p.name for p in params if _is_int(p) and not isinstance(converters[p.name], IntConverter)]
    if as_text:
        raise ImproperlyConfigured(
            f"{name}(route={route!r}) passes {as_text} as text, but {name}() annotates {'it' if len(as_text) == 1 else 'them'} "
            f"int. Write <int:{as_text[0]}> in the route."
        )


def interaction(method: str, *, partial: str, context: Callable[..., dict], refuses=(), triggers=(), route=None):
    """Register the decorated function as an interaction (see the module docstring) and return its routed view."""

    def decorate(func):
        name = func.__name__
        if name in registry:
            other = registry[name].func
            raise ImproperlyConfigured(
                f"Two interactions are named {name}(), in {other.__module__} and {func.__module__}; "
                f"{{% act '{name}' %}} and the route name need one. Rename one of them."
            )
        template, _, part = partial.partition("#")
        if not template or not part or "." in part:
            raise ImproperlyConfigured(
                f"{name}(): partial={partial!r} must name a partial of a template, as 'page.html#name'. The reply is "
                'that {% partialdef %}, and its root element carries id="name".'
            )
        if isinstance(triggers, str):
            raise ImproperlyConfigured(
                f"{name}(): triggers={triggers!r} is a string, which would announce each of its letters. "
                f"Write triggers=({triggers!r},)."
            )
        signature = list(inspect.signature(func).parameters.values())
        _check_arguments(name, method, refuses, signature)
        params = signature[1:]

        def view(request, **kwargs):
            return it.respond(request, **kwargs)

        functools.update_wrapper(view, func)  # who(request) and hx_map name the handler, not "view"

        if route is None:
            config = apps.get_containing_app_config(func.__module__)
            if config is None:
                raise ImproperlyConfigured(
                    f"{name}() is in {func.__module__}, which is in no installed app, so its route has no app label "
                    "to be minted from. Define it in an installed app's views.py, or give it route=."
                )
            segments = "".join(f"<{'int' if _is_int(p) else 'str'}:{p.name}>/" for p in params)
            pattern = path(f"x/{config.label}/{name}/{segments}", view, name=name)
        else:
            pattern = path(route, view, name=name)
            _check_route(name, route, pattern, params)
        context_params = _context_params(name, context, params)  # params are the route's, now that it is checked
        it = Interaction(
            name=name,
            method=method.upper(),
            template=template,
            partial=part,
            context=context,
            context_params=context_params,
            refuses=_refusals(refuses),
            triggers=tuple(triggers),
            params=tuple(p.name for p in params),
            func=func,
            route=str(pattern.pattern),
            view=view,
        )
        registry[name] = it
        urlpatterns.append(pattern)  # routed to the view until bind_routes() runs
        return view

    return decorate


def act_form(it: Interaction) -> str:
    """``{% act 'notify' contest=... member=... %}``: how a template writes the route of ``it``."""
    return f"{{% act '{it.name}'{''.join(f' {p}=...' for p in it.params)} %}}"


def act_unknown(name) -> str:
    """What ``{% act %}`` and check E009 say of a name no interaction has."""
    known = ", ".join(sorted(registry)) or "none"
    return (
        f"{{% act {name!r} %}} names no interaction; the interactions are: {known}. An interaction is registered "
        "when its module is imported, and dj-hx imports each project app's views module at start-up."
    )


def act_mismatch(it: Interaction, positional: int, keywords) -> str | None:
    """What ``{% act %}`` and check E010 say of arguments that are not ``it``'s parameters; None when they are."""
    name, takes = it.name, ", ".join(it.params) or "no parameters"
    if positional:
        return (
            f"{{% act '{name}' %}} takes keyword arguments only, one for each parameter of {name}() ({takes}), and "
            f"was given {positional} positional. Write {act_form(it)}."
        )
    problems = []
    unknown = sorted(set(keywords) - set(it.params))
    if unknown:
        problems.append(f"{name}() takes no {', '.join(unknown)}")
    missing = [p for p in it.params if p not in keywords]
    if missing:
        problems.append(f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing")
    if problems:
        return f"{{% act '{name}' %}}: {'; '.join(problems)}. {name}() takes {takes}; write {act_form(it)}."
    return None


def act_not_included(name) -> str:
    """What ``{% act %}`` raises, and ``hx_map`` reports, when no URLconf includes ``dj_hx.urls``."""
    return (
        f"{{% act '{name}' %}} reverses {name}()'s route in the dj_hx namespace, which no URLconf registers: "
        f"dj_hx.urls is not included. Include it once, at the site root: {INCLUDE}."
    )


def namespace_missing(exc: NoReverseMatch) -> bool:
    """True when ``exc`` says no URLconf registers the ``dj_hx`` namespace: ``dj_hx.urls`` is not included."""
    return "'dj_hx' is not a registered namespace" in str(exc)


def module_attribute(it: Interaction):
    """What the module that defines the handler holds under the handler's name, or None."""
    return getattr(sys.modules.get(it.view.__module__), it.name, None)


def unwraps_to(it: Interaction, held):
    """Where ``inspect.unwrap`` from ``held`` stops: the view, the raw handler, or the last object it can see."""
    return inspect.unwrap(held, stop=lambda link: link is it.view or link is it.func)


def _routed_view(it: Interaction):
    """
    What the handler's module holds under its name, routed as written when it is callable: the view
    ``@interaction`` returned, or a decorator of it, with or without ``functools.wraps`` (dropping one
    could drop an access check). The bare view when the module holds nothing callable there.

    The raw handler, or a decorator that reaches the raw handler before the view, raises instead:
    routing it would skip the method guard, the refusals and the return-type guard.
    """
    module = it.view.__module__
    held = module_attribute(it)
    if not callable(held):
        return it.view
    if unwraps_to(it, held) is it.func:
        what = f"{it.name}() itself" if held is it.func else f"a decorator of {it.name}() itself"
        raise ImproperlyConfigured(
            f"{module}.{it.name} holds {what}, not the view @interaction returned, so its route would skip the "
            "method guard, the declared refusals and the return-type guard. Apply @interaction as a decorator, "
            f"or bind its result to the handler's own name in the module that defines it, {module}: "
            f"{it.name} = interaction(...)({it.name}). The handler stays reachable as inspect.unwrap({it.name})."
        )
    return held


def bind_routes() -> None:
    """
    Route each interaction to what its module holds under the handler's name, as written: the view
    ``@interaction`` returned, inside any decorators written above it (see ``_routed_view``, which
    raises ``ImproperlyConfigured`` when the module holds the raw handler). ``dj_hx.urls`` calls this
    when it is first imported, after ``ready()`` has imported every views module. The list is rebuilt
    in place because ``dj_hx.urls.urlpatterns`` is this same list object, and the resolver for
    ``include("dj_hx.urls")`` reads it lazily and caches it, so a new list would never be seen.
    """
    urlpatterns[:] = [path(it.route, _routed_view(it), name=it.name) for it in registry.values()]


def import_views() -> None:
    """
    Import every project app's ``views`` module, so each interaction is registered before the URLconf
    is read. Apps in site-packages are skipped, as template discovery skips them.
    """
    from django.utils.module_loading import module_has_submodule

    from .templates import in_site_packages

    for config in apps.get_app_configs():
        if in_site_packages(config.path) or not module_has_submodule(config.module, "views"):
            continue
        import_module(f"{config.name}.views")
