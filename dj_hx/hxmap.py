"""
``manage.py hx_map``: the map engine (``mapcore``) over a Django project.

Handlers come from the URLconf (``dj_hx.urlconf``); a view class contributes
one scan per HTTP method it defines, a function view is scanned whole with
``if request.method == "POST":`` branches attributed to that method. Controls
resolve through ``{% url 'name' %}`` (the name) or a literal path
(``django.urls.resolve``). Only views and templates outside site-packages are
scanned.
"""

from __future__ import annotations

import ast
import inspect
import sysconfig
import textwrap
from pathlib import Path

from django.urls import Resolver404, resolve

from . import mapcore
from .mapcore import ALL_METHODS, URLFOR, Handler, Map
from .templates import strip_template_syntax, template_sources
from .urlconf import RoutedView, iter_routed_views

__all__ = ["build_map", "print_map"]

_SITE = {Path(sysconfig.get_paths()[k]).resolve() for k in ("purelib", "platlib")}
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _in_site_packages(obj) -> bool:
    try:
        file = inspect.getsourcefile(obj)
    except (TypeError, OSError):
        return True
    if not file:
        return True
    path = Path(file).resolve()
    return any(path.is_relative_to(s) for s in _SITE)


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


def _scan_handlers(urlconf=None) -> tuple[dict[str, Handler], dict[int, Handler]]:
    handlers: dict[str, Handler] = {}
    by_callback: dict[int, Handler] = {}
    for routed in iter_routed_views(urlconf):
        target = routed.view_class or inspect.unwrap(routed.callback)
        if _in_site_packages(target):
            continue
        endpoint = _endpoint(routed)
        h = handlers.get(endpoint)
        if h is None:
            h = handlers[endpoint] = Handler(endpoint, name=getattr(target, "__name__", endpoint))
            module = inspect.getmodule(target)
            verb_names = _verb_names(module) if module else {}
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
                from .mixins import HxMixin

                if issubclass(cls, HxMixin):
                    partial = routed.attr("partial")
                    template = routed.attr("template_name")
                    h.verbs.add("render" if partial else "page")
                    h.by_method.setdefault(ALL_METHODS, set()).add("render" if partial else "page")
                    if template:
                        h.templates.add(f"{template}#{partial}" if partial and "." not in partial else (partial or template))
            else:
                _scan(h, routed.callback, verb_names)
        h.rules.append("/" + routed.route)
        by_callback[id(routed.callback)] = h
    return handlers, by_callback


def build_map(urlconf=None, sources: dict[str, str] | None = None) -> Map:
    handlers, by_callback = _scan_handlers(urlconf)
    short = {}
    for ep, h in handlers.items():
        short.setdefault(ep.rsplit(":", 1)[-1], h)

    def resolve_control(url: str, method: str) -> tuple[str | None, str | None]:
        if url.startswith(URLFOR):
            name = url[len(URLFOR):].split("?", 1)[0].split("#", 1)[0]
            h = handlers.get(name) or short.get(name)
            if h is None:
                return None, f"{{% url '{name}' %}} names no URL pattern the map can see"
            return h.endpoint, None
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
    prepared = {name: strip_template_syntax(src, url_marker=True) for name, src in raw.items()}
    controls, listeners, script_names, _ = mapcore.scan_templates(prepared, resolve_control)
    return mapcore.check(handlers, controls, listeners, script_names)


def print_map(check: bool = True, out=None, urlconf=None, sources=None) -> int:
    return mapcore.print_map(build_map(urlconf, sources), check, out)
