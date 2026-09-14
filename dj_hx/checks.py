"""
dj-hx's Django system checks. Registered by ``dj_hx.apps.DjHxConfig.ready()``.

Every check here names a defect that lives in the project's settings, URLconf
or template files, which is what a boot-time check is for. Silence any with::

    SILENCED_SYSTEM_CHECKS = ["dj_hx.W005"]

=======  =======  ==========================================================
ID       Level    Fires when
=======  =======  ==========================================================
W001     Warning  HxMiddleware is not installed (no bridge, no guard outside tests)
E002     Error    HxMiddleware is listed before MessageMiddleware
W003     Warning  django.contrib.messages installed but HX_MESSAGES_TEMPLATE unset
W004     Warning  HX_MESSAGES_TEMPLATE does not resolve to a template partial
W005     Warning  A project template fails the htmx 4 lint (htmx 2 idioms, typos)
W006     Warning  Django < 6 without django-template-partials installed
E007     Error    A Django class before HxMixin in a routed view's bases shadows its hooks
W008     Warning  HX_EXTENSIONS is a string, or names an extension htmx 4 does not ship
=======  =======  ==========================================================
"""

from __future__ import annotations

import django
from django.core.checks import Error, Tags, Warning, register

HOOKS = ("render_to_response", "form_invalid", "form_valid")


def _should_run(app_configs) -> bool:
    from django.apps import apps

    if app_configs is not None and not any(c.label == "dj_hx" for c in app_configs):
        return False
    return apps.is_installed("dj_hx")


def _middleware_index(settings, dotted: str) -> int | None:
    from django.utils.module_loading import import_string

    try:
        target = import_string(dotted)
    except ImportError:
        return None
    for i, entry in enumerate(settings.MIDDLEWARE):
        try:
            candidate = import_string(entry)
        except Exception:
            continue
        if isinstance(candidate, type) and issubclass(candidate, target):
            return i
    return None


@register("dj_hx")
def check_middleware(app_configs=None, **kwargs):
    if not _should_run(app_configs):
        return []
    from django.apps import apps
    from django.conf import settings

    ours = _middleware_index(settings, "dj_hx.middleware.HxMiddleware")
    if ours is None:
        return [
            Warning(
                "dj_hx.middleware.HxMiddleware is not in MIDDLEWARE.",
                hint=(
                    "Without it, messages added on a fragment response are never bridged into an "
                    "<hx-partial>, a plain redirect or 204 answering a partial request is logged by "
                    "nothing outside HxTestClient, and responses built outside the verbs carry no "
                    "Vary header. Add 'dj_hx.middleware.HxMiddleware' after MessageMiddleware."
                ),
                id="dj_hx.W001",
            )
        ]
    messages = []
    theirs = _middleware_index(settings, "django.contrib.messages.middleware.MessageMiddleware")
    if theirs is not None and ours < theirs:
        messages.append(
            Error(
                "dj_hx.middleware.HxMiddleware is listed before MessageMiddleware.",
                hint=(
                    "Response phases run in reverse order, so HxMiddleware would bridge messages into "
                    "the fragment after MessageMiddleware has already stored them for the next page: "
                    "every message shows twice. Move HxMiddleware below MessageMiddleware."
                ),
                id="dj_hx.E002",
            )
        )
    if apps.is_installed("django.contrib.messages") and not getattr(settings, "HX_MESSAGES_TEMPLATE", None):
        messages.append(
            Warning(
                "django.contrib.messages is installed but HX_MESSAGES_TEMPLATE is not set.",
                hint=(
                    "A message added while answering a fragment request has nowhere to go and would "
                    "appear on some later page load (HxTestClient raises HxMessagesUnconfigured). Set "
                    'HX_MESSAGES_TEMPLATE = "layout.html#messages", where the partial\'s root element is '
                    'id="messages" and it iterates {{ messages }}.'
                ),
                id="dj_hx.W003",
            )
        )
    return messages


@register("dj_hx", Tags.templates)
def check_messages_template(app_configs=None, **kwargs):
    if not _should_run(app_configs):
        return []
    from django.conf import settings
    from django.template import TemplateDoesNotExist
    from django.template.loader import get_template

    value = getattr(settings, "HX_MESSAGES_TEMPLATE", None)
    if not value:
        return []
    template, _, name = str(value).partition("#")
    reference = f"{template}#{name or 'messages'}"
    try:
        get_template(reference)
    except TemplateDoesNotExist:
        return [
            Warning(
                f"HX_MESSAGES_TEMPLATE = {value!r} does not resolve to a template partial.",
                hint=(
                    f"Write {{% partialdef {name or 'messages'} inline %}}<div id=\"{name or 'messages'}\">...{{% endpartialdef %}} "
                    f"in {template!r}. Until then every message on a fragment response raises HxUnknownPartial."
                ),
                id="dj_hx.W004",
            )
        ]
    except Exception:
        return []
    return []


@register("dj_hx", Tags.templates)
def check_template_lint(app_configs=None, **kwargs):
    """The htmx 4 lint over the project's own template source (never site-packages)."""
    if not _should_run(app_configs):
        return []
    from django.conf import settings

    from .templates import iter_template_files, lint_template_source, template_directories

    ignore = set(getattr(settings, "HX_LINT_IGNORE", ()))
    messages = []
    for path in iter_template_files(template_directories()):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings = [
            f for f in lint_template_source(source, file=str(path), extensions=getattr(settings, "HX_EXTENSIONS", ()))
            if f.severity == "error" and f.rule not in ignore
        ]
        if not findings:
            continue
        shown = findings[:4]
        more = f" (+{len(findings) - 4} more)" if len(findings) > 4 else ""
        messages.append(
            Warning(
                f"{path} fails the htmx 4 lint ({', '.join(sorted({f.rule for f in shown}))}{more}).",
                hint="; ".join(f"line {f.line}: {f.message}" for f in shown)
                + ". Run manage.py hx_lint for the full list; silence a rule with HX_LINT_IGNORE.",
                obj=str(path),
                id="dj_hx.W005",
            )
        )
    return messages


@register("dj_hx", Tags.templates)
def check_extensions(app_configs=None, **kwargs):
    """``HX_EXTENSIONS`` names the lint does not know match nothing, so every extension attribute warns."""
    if not _should_run(app_configs):
        return []
    import difflib

    from django.conf import settings

    from .hx_vocab import EXTENSION_NAMES

    configured = getattr(settings, "HX_EXTENSIONS", ())
    if isinstance(configured, str):
        return [
            Warning(
                f"HX_EXTENSIONS is the string {configured!r}, so the lint reads each character as an extension name.",
                hint=f"Make it a tuple: HX_EXTENSIONS = {tuple(e.strip() for e in configured.split(',') if e.strip())!r}.",
                id="dj_hx.W008",
            )
        ]
    messages = []
    for name in configured:
        if name in EXTENSION_NAMES:
            continue
        close = difflib.get_close_matches(str(name), list(EXTENSION_NAMES), n=1, cutoff=0.6)
        messages.append(
            Warning(
                f"HX_EXTENSIONS names {name!r}, which is not an htmx 4 extension, so it tells the lint nothing"
                + (f" (did you mean {close[0]!r}?)." if close else "."),
                hint="Use the file name (hx-sse) or the name htmx registers it under (sse). An extension of "
                "your own has attributes the lint cannot know; leave it out of HX_EXTENSIONS.",
                id="dj_hx.W008",
            )
        )
    return messages


@register("dj_hx", Tags.templates)
def check_partials_available(app_configs=None, **kwargs):
    if not _should_run(app_configs) or django.VERSION >= (6, 0):
        return []
    from django.apps import apps

    if apps.is_installed("template_partials"):
        return []
    return [
        Warning(
            f"Django {django.get_version()} has no template partials and django-template-partials is not installed.",
            hint=(
                "render(request, 'index.html', 'rows') needs {% partialdef rows %}. Install "
                "django-template-partials, add 'template_partials' to INSTALLED_APPS, and add "
                "'template_partials.templatetags.partials' to the TEMPLATES OPTIONS 'builtins' "
                "(it registers no tags globally, so without that every template must {% load partials %}). "
                "Or name a separate file ('rows.html') as the partial."
            ),
            id="dj_hx.W006",
        )
    ]


@register("dj_hx", Tags.urls)
def check_mixin_order(app_configs=None, **kwargs):
    """``class V(ListView, HxMixin)`` renders, returns 200, and never negotiates."""
    if not _should_run(app_configs):
        return []
    from .mixins import HxMixin
    from .urlconf import routed_view_classes

    messages = []
    for view_class, routed in routed_view_classes(HxMixin).items():
        mro = view_class.__mro__
        index = mro.index(HxMixin)
        for hook in HOOKS:
            for earlier in mro[:index]:
                if hook in vars(earlier) and earlier.__module__.startswith("django."):
                    messages.append(
                        Error(
                            f"{view_class.__name__} lists {earlier.__name__} before HxMixin, so "
                            f"HxMixin.{hook}() never runs (routed at {routed.route!r}).",
                            hint=f"Put HxMixin first: class {view_class.__name__}(HxMixin, ...).",
                            obj=view_class,
                            id="dj_hx.E007",
                        )
                    )
                    break
    return messages
