"""
Interactions: one handler bound to one template partial, by name.

::

    from dj_hx import interaction

    def assign_context(request, contest):
        return {"contest": Contest.get(contest), "notified": False, "error": None}

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
  called with the route parameters it names, plus the keys the handler returns. A returned key the
  context does not define raises, so the page and the reply render the same names. The handler
  returns a dict or ``None``; anything else raises.
- A declared refusal, an exception in ``refuses``, re-renders the partial with
  ``error=str(exc)`` and status 422, so the handler writes no ``try``. Any other exception is a 500.
- ``triggers`` names the facts a successful reply announces, ``.trigger(name)`` for each.
- A request with any other method gets a 405.
- dj-hx's ``ready()`` imports each project app's ``views`` module, so every route exists before
  the URLconf is read.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseNotAllowed
from django.urls import path
from django.urls.converters import IntConverter

from .verbs import HxResponse, check_root_id, fragment

__all__ = ["interaction"]

registry: dict[str, Interaction] = {}
urlpatterns: list = []  # served by dj_hx.urls; filled as each app's views module is imported


@dataclass(frozen=True)
class Interaction:
    """One registered interaction: what its wrapper view runs, and the parameters ``{% act %}`` checks."""

    name: str
    method: str
    template: str
    partial: str
    context: Callable[..., dict]
    context_params: tuple[str, ...]
    refuses: tuple[type[BaseException], ...]
    triggers: tuple[str, ...]
    params: tuple[str, ...]
    func: Callable[..., Any]

    def respond(self, request, **kwargs):
        """The wrapper view's body: the method guard, the handler, then its partial."""
        if request.method != self.method:
            return HttpResponseNotAllowed([self.method])
        try:
            reply = self.func(request, **kwargs)
        except self.refuses as exc:
            why = f"{self.name}() refused with {type(exc).__name__}, and the refusal's reply sets"
            return self._render(request, kwargs, {"error": str(exc)}, why).with_status(422)
        if reply is not None and not isinstance(reply, dict):
            raise ImproperlyConfigured(
                f"{self.name}() returned {type(reply).__name__}; an interaction returns a dict of context keys, or "
                "None. An interaction always re-renders its partial; to leave the page, write a view that returns "
                "navigate()."
            )
        response = self._render(request, kwargs, reply or {}, f"{self.name}() returns")
        for name in self.triggers:
            response.trigger(name)
        return response

    def _render(self, request, kwargs, reply: dict, why: str) -> HxResponse:
        context = self.context(request, **{p: kwargs[p] for p in self.context_params})
        undefined = sorted(key for key in reply if key not in context)
        if undefined:
            context_name = getattr(self.context, "__name__", repr(self.context))
            raise ImproperlyConfigured(
                f"{why} {', '.join(map(repr, undefined))}, which {context_name}() does not define. Define each "
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
    """Register the decorated function as an interaction; see the module docstring. Returns it unchanged."""

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
        params = list(inspect.signature(func).parameters.values())[1:]
        it = Interaction(
            name=name,
            method=method.upper(),
            template=template,
            partial=part,
            context=context,
            context_params=tuple(list(inspect.signature(context).parameters)[1:]),
            refuses=tuple(refuses),
            triggers=tuple(triggers),
            params=tuple(p.name for p in params),
            func=func,
        )

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
        registry[name] = it
        urlpatterns.append(pattern)
        return func

    return decorate


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
