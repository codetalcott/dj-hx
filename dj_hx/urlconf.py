"""
A defensive walk over a project's URLconf.

Copied from dj-fixi (``dj_fixi/urlconf.py``), whose public API this is; the
system checks and ``manage.py hx_map`` are built on it. ``tools/sync_shared.py``
keeps the body identical.

The contract that matters: **nothing here raises.** A URLconf that cannot be
imported, a pattern object from a third-party router, or a URLconf that includes
itself yields *fewer* results, never an exception. Django's own ``urls.E00x``
checks are what should report a broken URLconf.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

__all__ = ["RoutedView", "iter_routed_views", "routed_view_classes"]

_EMPTY: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class RoutedView:
    """One URLconf entry, resolved as far as can be done safely."""

    callback: Callable[..., Any]
    view_class: type | None
    """None for function-based views. Every check filters on this."""

    initkwargs: Mapping[str, Any]
    """What ``as_view(**kwargs)`` was called with. Empty for function views."""

    route: str
    url_name: str | None
    namespace: str

    @property
    def full_name(self) -> str | None:
        """``'shop:product-edit'``, or None when the pattern is unnamed."""
        if self.url_name is None:
            return None
        return f"{self.namespace}:{self.url_name}" if self.namespace else self.url_name

    def attr(self, name: str, default: Any = None) -> Any:
        """
        The view attribute actually in effect, initkwargs winning.

        Load-bearing: ``as_view(template_name="x.html")`` stores that in
        ``view_initkwargs``, never on the class. A caller that reads
        ``view_class.template_name`` directly will report a view configured at
        the URLconf as having no template at all.
        """
        if name in self.initkwargs:
            return self.initkwargs[name]
        return getattr(self.view_class, name, default)


def _describe(pattern: Any) -> str:
    try:
        return str(pattern.pattern)
    except Exception:
        return ""


def _walk(node, namespaces, prefix, depth, max_depth, seen) -> Iterator[RoutedView]:
    if depth > max_depth or id(node) in seen:
        return
    seen.add(id(node))

    try:
        # A cached_property that imports the included module, so this is where a
        # broken or circular URLconf blows up. Swallow it and report nothing.
        patterns = list(node.url_patterns)
    except Exception:
        return

    for pattern in patterns:
        route = prefix + _describe(pattern)

        # Duck-typed rather than isinstance: third-party routers subclass freely.
        if hasattr(pattern, "url_patterns"):
            namespace = getattr(pattern, "namespace", None)
            yield from _walk(
                pattern,
                namespaces + (namespace,) if namespace else namespaces,
                route,
                depth + 1,
                max_depth,
                seen,
            )
            continue

        callback = getattr(pattern, "callback", None)
        if callback is None:
            continue

        # as_view() puts these in the function's __dict__, so functools.wraps
        # decorators (login_required, csrf_exempt, method_decorator) preserve
        # them. A decorator that does not use @wraps loses them, and the view
        # then reads as a function view -- which keeps every check quiet, the
        # correct direction to fail.
        initkwargs = getattr(callback, "view_initkwargs", None)

        yield RoutedView(
            callback=callback,
            view_class=getattr(callback, "view_class", None),
            initkwargs=MappingProxyType(dict(initkwargs)) if initkwargs else _EMPTY,
            route=route,
            url_name=getattr(pattern, "name", None),
            namespace=":".join(namespaces),
        )


def iter_routed_views(
    urlconf: str | object | None = None,
    *,
    max_depth: int = 25,
) -> Iterator[RoutedView]:
    """
    Yield every routed view under ``urlconf`` (default: ``settings.ROOT_URLCONF``).

    Order follows the URLconf. ``max_depth`` bounds a self-including URLconf.
    """
    try:
        from django.urls import get_resolver

        resolver = get_resolver(urlconf)
    except Exception:
        return

    yield from _walk(resolver, (), "", 0, max_depth, set())


def routed_view_classes(
    base: type | tuple[type, ...],
    urlconf: str | object | None = None,
) -> dict[type, RoutedView]:
    """
    Map each routed subclass of ``base`` to its first route, in URLconf order.

    Deduplicated by class: a view routed at several paths (dj-fixi-tables routes
    one ``FxTableView`` five times) should not produce five copies of the same
    class-level finding.
    """
    found: dict[type, RoutedView] = {}
    for routed in iter_routed_views(urlconf):
        view_class = routed.view_class
        if view_class is None or view_class in found:
            continue
        try:
            if issubclass(view_class, base):
                found[view_class] = routed
        except TypeError:  # not a class after all
            continue
    return found
