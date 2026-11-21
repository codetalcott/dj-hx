"""
``{% load hx %}``. ``{% act 'notify' contest=contest.slug member=member.id %}`` writes the route of the
interaction ``notify()`` into a control. It takes keyword arguments only, one for each of the
handler's parameters, so the order of the arguments cannot be wrong.
"""

from django import template
from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateSyntaxError
from django.urls import NoReverseMatch, reverse

from ..interactions import act_mismatch, act_not_included, act_unknown, namespace_missing, registry

register = template.Library()


@register.simple_tag
def act(interaction_name, /, *args, **kwargs):
    """
    The route of interaction ``interaction_name``, reversed from keyword arguments named like its
    parameters. Positional-only, so every keyword reaches ``kwargs``: a handler may take ``name``.
    The start-up checks E009 and E010 say the same of the tags they can read.
    """
    name = interaction_name
    it = registry.get(name)
    if it is None:
        raise TemplateSyntaxError(act_unknown(name))
    problem = act_mismatch(it, len(args), kwargs)
    if problem:
        raise TemplateSyntaxError(problem)
    try:
        return reverse(f"dj_hx:{name}", kwargs=kwargs)
    except NoReverseMatch as exc:
        if not namespace_missing(exc):
            raise
        raise ImproperlyConfigured(act_not_included(name)) from exc
