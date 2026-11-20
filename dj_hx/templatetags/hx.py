"""
``{% load hx %}``. ``{% act 'notify' contest=contest.slug member=member.id %}`` writes the route of the
interaction ``notify()`` into a control. It takes keyword arguments only, one for each of the
handler's parameters, so the order of the arguments cannot be wrong.
"""

from django import template
from django.template import TemplateSyntaxError
from django.urls import reverse

from ..interactions import registry

register = template.Library()


@register.simple_tag
def act(interaction_name, /, *args, **kwargs):
    """
    The route of interaction ``interaction_name``, reversed from keyword arguments named like its
    parameters. Positional-only, so every keyword reaches ``kwargs``: a handler may take ``name``.
    """
    name = interaction_name
    it = registry.get(name)
    if it is None:
        known = ", ".join(sorted(registry)) or "none"
        raise TemplateSyntaxError(
            f"{{% act {name!r} %}} names no interaction; the interactions are: {known}. An interaction is registered "
            "when its module is imported, and dj-hx imports each project app's views module at start-up."
        )
    write = f"{{% act '{name}'{''.join(f' {p}=...' for p in it.params)} %}}"
    takes = ", ".join(it.params) or "no parameters"
    if args:
        raise TemplateSyntaxError(
            f"{{% act '{name}' %}} takes keyword arguments only, one for each parameter of {name}() ({takes}), and "
            f"was given {len(args)} positional. Write {write}."
        )
    problems = []
    unknown = sorted(set(kwargs) - set(it.params))
    if unknown:
        problems.append(f"{name}() takes no {', '.join(unknown)}")
    missing = [p for p in it.params if p not in kwargs]
    if missing:
        problems.append(f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing")
    if problems:
        raise TemplateSyntaxError(f"{{% act '{name}' %}}: {'; '.join(problems)}. {name}() takes {takes}; write {write}.")
    return reverse(f"dj_hx:{name}", kwargs=kwargs)
