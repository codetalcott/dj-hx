"""
``manage.py hx_map``: the map engine (``mapcore``) over a Django project.

Handlers come from the URLconf (``dj_hx.urlconf``); a view class contributes
one scan per HTTP method it defines, a function view is scanned whole with
``if request.method == "POST":`` branches attributed to that method. Controls
resolve through ``{% url 'name' %}`` (the name), ``{% act 'name' %}`` (the
interaction registry) or a literal path (``django.urls.resolve``). An
interaction is known by the callback ``dj_hx.urls`` routes it to: its handler is
scanned, and it replies with its partial through ``fragment()`` and announces its
``triggers=``. Only views and templates outside site-packages are scanned.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

from django.urls import Resolver404, resolve

from . import mapcore
from .mapcore import ALL_METHODS, URLFOR, Handler, Map
from .templates import ACT_MARK, in_site_packages, strip_template_syntax, template_sources
from .urlconf import RoutedView, iter_routed_views

__all__ = ["build_map", "map_with_interactions", "print_map"]

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _in_site_packages(obj) -> bool:
    """True for code outside the project: in site-packages (``templates.in_site_packages``), or with no source file."""
    try:
        file = inspect.getsourcefile(obj)
    except (TypeError, OSError):
        return True
    return not file or in_site_packages(file)


def _verb_names(module) -> dict[str, str]:
    """The names this module can call a verb by: ``from dj_hx import render as r``, ``import dj_hx as hx``."""
    names: dict[str, str] = {}
    try:
        tree = ast.parse(inspect.getsource(module))
    except (OSError, TypeError, SyntaxError):
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "dj_hx":
            for alias in node.names:
                if alias.name in mapcore.VERBS:
                    names[alias.asname or alias.name] = alias.name
                elif alias.name in ("verbs",):
                    for v in mapcore.VERBS:
                        names[f"{alias.asname or alias.name}.{v}"] = v
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "dj_hx":
                    head = alias.asname or alias.name
                    for v in mapcore.VERBS:
                        names[f"{head}.{v}"] = v
                        names[f"{head}.verbs.{v}"] = v
    return names


def _scan(handler: Handler, func, verb_names: dict[str, str], method: str = ALL_METHODS) -> None:
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(inspect.unwrap(func))))
    except (OSError, TypeError, SyntaxError):
        return
    mapcore.scan_function(handler, tree, verb_names, method=method)


def _endpoint(routed: RoutedView) -> str:
    if routed.full_name:
        return routed.full_name
    cb = routed.callback
    return f"{cb.__module__}.{getattr(cb, '__qualname__', getattr(cb, '__name__', '?'))}"


def _interactions_by_callback() -> dict:
    """Each registered interaction, by the callback ``dj_hx.urls`` routes it to."""
    from .interactions import registry, urlpatterns

    return {id(p.callback): registry[p.name] for p in urlpatterns if p.name in registry}


def _as_interaction(h: Handler, it) -> None:
    """What an interaction answers its method with: its partial, through ``fragment()``, then its ``triggers=``."""
    h.verbs.add("fragment")
    h.by_method.setdefault(it.method, set()).add("fragment")
    h.methods = {it.method}  # any other method gets a 405
    h.templates.add(f"{it.template}#{it.partial}")
    h.announces |= set(it.triggers)
    h.json_returns.clear()  # the dict a handler returns is its partial's context, not a JSON reply


def _scan_handlers(
    urlconf=None,
) -> tuple[dict[str, Handler], dict[int, Handler], dict[str, Handler | None], set[str]]:
    """
    The handlers, the same by callback, each routed interaction's handler (None: in site-packages), and the
    names of the routes whose view is outside the project, which ``{% url %}`` can name but the map does not scan.
    """
    handlers: dict[str, Handler] = {}
    by_callback: dict[int, Handler] = {}
    # Walked first: reading the URLconf imports dj_hx.urls, whose bind_routes() gives each interaction the callback
    # the resolver routes (a decorator above @interaction wraps it). manage.py hx_map runs no system checks, so
    # this can be the first read.
    routed_views = list(iter_routed_views(urlconf))
    interactions = _interactions_by_callback()
    routed_interactions: dict[str, Handler | None] = {}
    module_verbs: dict = {}  # each module's verb names, parsed once per map though many of its views are routed
    outside: set[str] = set()
    for routed in routed_views:
        it = interactions.get(id(routed.callback))
        if it is not None:
            routed_interactions.setdefault(it.name, None)
        # an interaction's handler, which a decorator above @interaction without functools.wraps would hide
        target = it.func if it is not None else routed.view_class or inspect.unwrap(routed.callback)
        if _in_site_packages(target):
            if routed.full_name:
                outside |= {routed.full_name, routed.full_name.rsplit(":", 1)[-1]}  # as `short` below reads a name
            continue
        endpoint = _endpoint(routed)
        h = handlers.get(endpoint)
        if h is None:
            h = handlers[endpoint] = Handler(endpoint, name=getattr(target, "__name__", endpoint))
            module = inspect.getmodule(target)
            if module is not None and module not in module_verbs:
                module_verbs[module] = _verb_names(module)
            verb_names = module_verbs.get(module, {}) if module is not None else {}
            if routed.view_class is not None:
                cls = routed.view_class
                for m in _HTTP_METHODS:
                    func = getattr(cls, m, None)
                    if func is None or getattr(func, "__module__", "django.").startswith("django."):
                        continue
                    _scan(h, func, verb_names, method=m.upper())
                for hook in ("form_valid", "form_invalid", "render_to_response", "get_context_data"):
                    func = getattr(cls, hook, None)
                    if func is not None and not getattr(func, "__module__", "django.").startswith(("django.", "dj_hx.")):
                        _scan(h, func, verb_names)
            elif it is not None:
                _scan(h, it.func, verb_names)
                _as_interaction(h, it)
            else:
                _scan(h, routed.callback, verb_names)
        h.rules.append("/" + routed.route)
        by_callback[id(routed.callback)] = h
        if it is not None and routed_interactions[it.name] is None:
            routed_interactions[it.name] = h
    return handlers, by_callback, routed_interactions, outside


def _act_endpoint(act, routed: dict[str, Handler | None]) -> tuple[str | None, str | None]:
    """An ``{% act %}`` control's interaction, through the registry, as ``resolve_control`` answers."""
    from .interactions import act_not_included, act_unknown, registry

    if act.name is None or act.stored_as:
        return None, "computed URL; cannot resolve statically"
    if act.name not in registry:
        return None, act_unknown(act.name)
    if act.name not in routed:
        return None, act_not_included(act.name)
    h = routed[act.name]
    return (h.endpoint, None) if h is not None else (None, None)  # None: an interaction in site-packages


def build_map(urlconf=None, sources: dict[str, str] | None = None) -> Map:
    return map_with_interactions(urlconf, sources)[0]


def map_with_interactions(urlconf=None, sources: dict[str, str] | None = None) -> tuple[Map, dict[str, Handler | None]]:
    """
    The map, and the handler it holds for each interaction the URLconf routes, by name: None for one in
    site-packages, which the map does not scan. An interaction missing from the second is not routed.
    """
    handlers, by_callback, interactions, outside = _scan_handlers(urlconf)
    short: dict[str, Any] = {}
    for ep, h in handlers.items():
        short.setdefault(ep.rsplit(":", 1)[-1], h)
    acts: list = []  # one list for every template, so each __ACT<n>__ marker names one tag

    def resolve_control(url: str, method: str) -> tuple[str | None, str | None]:
        act = ACT_MARK.match(url)
        if act:
            return _act_endpoint(acts[int(act.group(1))], interactions)
        if url.startswith(URLFOR):
            written = url[len(URLFOR):].split("?", 1)[0].split("#", 1)[0]
            # The name ends where the tag did: what the attribute writes after it, as in
            # {% url 'x' %}{% if q %}?q={{ q }}{% endif %}, reaches here as a space-padded branch marker.
            first = written.split(None, 1)[0] if written.strip() else written
            for name in dict.fromkeys((written, first)):
                h = handlers.get(name) or short.get(name)
                if h is not None:
                    return h.endpoint, None
                if name in outside:
                    return None, None  # a view outside the project (allauth's account_login, admin:index), as below
            return None, f"{{% url '{first}' %}} names no URL pattern the map can see"
        path = mapcore.resolve_path(url)
        if path is None:
            return None, "computed URL; cannot resolve statically"
        try:
            match = resolve(path, urlconf)
        except Resolver404:
            from django.conf import settings

            if getattr(settings, "APPEND_SLASH", True) and not path.endswith("/"):
                try:
                    resolve(path + "/", urlconf)
                except Resolver404:
                    pass
                else:
                    return None, f"{method} {path} is a 301 from APPEND_SLASH (trailing slash?); fetch follows it silently"
            return None, f"{method} {path} matches no route (404)"
        h = by_callback.get(id(match.func))
        if h is None:
            return None, None  # a view outside the project (admin, site-packages)
        return h.endpoint, None

    raw = sources if sources is not None else template_sources()
    prepared = {name: strip_template_syntax(src, url_marker=True, acts=acts) for name, src in raw.items()}
    controls, listeners, script_names, _ = mapcore.scan_templates(prepared, resolve_control)
    return mapcore.check(handlers, controls, listeners, script_names), interactions


def print_map(
    check: bool = True, out=None, urlconf=None, sources=None, by_template: bool = False, as_json: bool = False
) -> int:
    return mapcore.print_map(build_map(urlconf, sources), check, out, by_template, as_json)
