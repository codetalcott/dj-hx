"""
dj-hx's Django system checks. Registered by ``dj_hx.apps.DjHxConfig.ready()``.

Every check here names a defect that lives in the project's settings, URLconf,
views or template files, which is what a boot-time check is for. Silence any with::

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
E009     Error    {% act %} names no interaction
E010     Error    {% act %}'s keywords are not its handler's parameters
E011     Error    An {% act %} control sends another method than its interaction answers
E012     Error    An {% act %} control's hx-target (own or :inherited) is not #<partial>
E013     Error    An {% act %} control's hx-swap (own or :inherited) is not an outer swap
E014     Error    An interaction has no control: no template writes its {% act %}
E015     Error    An interaction's partial does not load
E016     Error    An interaction's partial's root element is not id="<partial>"
E017     Error    dj_hx.urls routes an interaction to other than what its module holds
W018     Warning  The module attribute routed does not unwrap to its interaction
W019     Warning  A decorator sits below @interaction
E020     Error    Interactions are registered but dj_hx.urls is not included
I021     Info     An {% act %} the checks cannot tie to a control's attributes
=======  =======  ==========================================================

E009 to E016 and I021 read the project's template files as hx_lint does, never
site-packages; a computed hx-target, hx-swap, hx-method or root id is not judged.
E013's outer swaps, read from htmx 4.0.2's swap code: outerHTML replaces the
target, outerMorph morphs the target itself, and outerSync copies the reply
root's attributes onto it and takes the root's children, so each leaves one
element with the id. innerMorph morphs the reply, root and all, into the target.
"""

from __future__ import annotations

import re

import django
from django.core.checks import Error, Info, Tags, Warning, register

HOOKS = ("render_to_response", "form_invalid", "form_valid")
_ELEMENT = re.compile(r"<[a-zA-Z]")
_ELSEWHERE = re.compile(r"\{%\s*(?:include|partial)\b")  # a tag that renders another template or partial in place
_OUTER_SWAPS = {"outerHTML", "outerMorph", "outerSync"}  # one element carries the id after the swap (htmx 4.0.2)
_KEEPS_THE_TARGET = {"innerHTML", "innerMorph", "afterbegin", "beforeend", "beforebegin", "afterend"}  # reply in or beside it


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


@register("dj_hx", Tags.urls)
def check_interaction_routes(app_configs=None, **kwargs):
    """Each interaction routed, through dj_hx.urls, to what its module holds (W018, W019, E020, E017)."""
    if not _should_run(app_configs):
        return []
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
    from django.urls import NoReverseMatch, reverse

    from .interactions import (
        INCLUDE,
        _routed_view,
        module_attribute,
        namespace_missing,
        registry,
        unwraps_to,
        urlpatterns,
    )

    messages = []
    for it in registry.values():
        where = f"{it.view.__module__}.{it.name}"
        held = module_attribute(it)
        if callable(held) and unwraps_to(it, held) not in (it.view, it.func):  # the raw handler is bind_routes()' to refuse
            messages.append(
                Warning(
                    f"{it.name}() is routed to {where}, which does not unwrap to the view @interaction returned, so "
                    "dj-hx cannot tell that it wraps the interaction.",
                    hint="Use functools.wraps in decorators above @interaction, as Django's own do. A wrapper of the raw "
                    "handler written without it is routed as it is, past the method guard.",
                    obj=where,
                    id="dj_hx.W018",
                )
            )
        if hasattr(it.func, "__wrapped__"):
            messages.append(
                Warning(
                    f"{it.name}() is wrapped by a decorator below @interaction, which runs inside the interaction.",
                    hint="View decorators belong above @interaction, where they wrap the routed view; below it, one "
                    "that answers with a response is the return-type error. One that returns the handler's dict, such as "
                    "transaction.atomic, belongs there: silence dj_hx.W019.",
                    obj=where,
                    id="dj_hx.W019",
                )
            )
    if not registry or not getattr(settings, "ROOT_URLCONF", None):
        return messages
    try:
        reverse(f"dj_hx:{next(iter(registry))}")  # reads the URLconf, so dj_hx.urls has bound the routes it includes
    except NoReverseMatch as exc:
        if namespace_missing(exc):
            messages.append(
                Error(
                    f"Interactions are registered ({', '.join(sorted(registry))}), but dj_hx.urls is not included, so "
                    "none of them has a route and every {% act %} raises.",
                    hint=f"Include it once, at the site root of ROOT_URLCONF: {INCLUDE}.",
                    id="dj_hx.E020",
                )
            )
            return messages
    routed = {}
    for pattern in urlpatterns:  # dj_hx.urls.urlpatterns, which the include reads
        routed.setdefault(pattern.name, pattern.callback)
    for it in registry.values():
        module, where = it.view.__module__, f"{it.view.__module__}.{it.name}"
        late = (
            f"{it.name}() was registered after dj_hx.urls was first read, or {module} rebound {it.name} since. Import "
            f"{module} before the URLconf is loaded: from the app's ready(), or from its views module, which dj-hx "
            "imports at start-up."
        )
        try:
            expected = _routed_view(it)
        except ImproperlyConfigured as exc:  # the module holds the raw handler: binding the routes now would raise
            messages.append(Error(str(exc), hint=late, obj=where, id="dj_hx.E017"))
            continue
        callback = routed.get(it.name)
        if callback is expected:
            continue
        to = "the view @interaction returned" if callback is it.view else "another object"
        messages.append(
            Error(
                f"dj_hx.urls routes {it.name}() to {to}, not to what {module} holds under its name, so the decorators "
                "written above @interaction do not apply to the route.",
                hint=late,
                obj=where,
                id="dj_hx.E017",
            )
        )
    return messages


@register("dj_hx", Tags.templates)
def check_interaction_controls(app_configs=None, **kwargs):
    """
    Every ``{% act %}`` in the project's templates against the registry and the control holding it, and
    each interaction's control and partial (E009 to E016, I021).
    """
    if not _should_run(app_configs):
        return []
    from .hxlint import parse
    from .interactions import registry
    from .templates import ACT_MARK, strip_template_syntax, template_sources

    sources = template_sources()
    messages, controlled = [], set()
    for template, source in sources.items():
        acts = []
        html = strip_template_syntax(source, acts=acts)
        if not acts:
            continue
        holders = {}
        for node in parse(html)[0].descendants():
            for attr, value in node.attrs.items():
                for index in ACT_MARK.findall(value or ""):
                    holders.setdefault(int(index), (node, attr))
        for index, act in enumerate(acts):
            if act.name is not None:
                controlled.add(act.name)
            messages += _act_messages(act, f"{template}:{act.line}", *holders.get(index, (None, None)))
    for it in registry.values():
        messages += _interaction_messages(it, controlled, sources)
    return messages


_UNTIED = (
    "Write the {% act %}, with the interaction's name quoted, into the verb attribute (hx-post, hx-get, ...) of the "
    "control that sends it to have that control checked, or silence dj_hx.I021 in SILENCED_SYSTEM_CHECKS."
)


def _act_messages(act, where: str, node, attr: str | None) -> list:
    from .hx_vocab import REQUEST_ATTRIBUTES
    from .interactions import act_mismatch, act_unknown, registry

    if act.name is None:
        return [
            Info(
                "{% act %} names its interaction with a variable, so the checks cannot tell which interaction it is.",
                hint=_UNTIED,
                obj=where,
                id="dj_hx.I021",
            )
        ]
    it = registry.get(act.name)
    if it is None:
        return [Error(act_unknown(act.name), obj=where, id="dj_hx.E009")]
    messages = []
    problem = act_mismatch(it, act.positional, act.keywords)
    if problem:
        messages.append(Error(problem, obj=where, id="dj_hx.E010"))
    if act.stored_as:
        untied = f"stores its URL in {act.stored_as}"
    elif node is None:
        untied = "is outside an attribute value"
    elif attr not in REQUEST_ATTRIBUTES:
        untied = f"is in {attr}, which is not a verb attribute"
    else:
        return messages + _control_messages(it, node, attr, where)
    messages.append(
        Info(
            f"{{% act '{it.name}' %}} {untied}, so the checks cannot tie it to a control: no method, hx-target or "
            "hx-swap is checked for it.",
            hint=_UNTIED,
            obj=where,
            id="dj_hx.I021",
        )
    )
    return messages


def _plain_on_ancestor(node, attr: str) -> str:
    plain = next((a for a in node.ancestors() if a.attrs.get(attr) is not None), None)
    return f"; the plain {attr} on <{plain.tag}> above it does not reach it in htmx 4" if plain is not None else ""


def _control_messages(it, node, attr: str, where: str) -> list:
    """E011 to E013: the control that ``{% act %}`` writes the URL of, against what its interaction replies."""
    from .hxlint import JINJA, parse_swap_spec
    from .interactions import act_form

    tag, partial, messages = f"{{% act '{it.name}' %}}", it.partial, []
    sends = (node.own("hx-method") or "GET").upper() if attr == "hx-action" else attr[len("hx-") :].upper()
    if JINJA not in sends and sends != it.method:
        messages.append(
            Error(
                f"{tag} is in {attr}, so its control sends {sends}, but {it.name}() answers {it.method}: a {sends} gets "
                "a 405.",
                hint=f'Write hx-{it.method.lower()}="{act_form(it)}" on the control, or give {it.name}() the method '
                "the control sends.",
                obj=where,
                id="dj_hx.E011",
            )
        )
    target = node.resolved("hx-target")
    if (target is None or JINJA not in target) and (target or "").strip() != f"#{partial}":
        says = (
            "it has no hx-target, so htmx 4 swaps the reply into the control itself" + _plain_on_ancestor(node, "hx-target")
            if target is None
            else f"its hx-target is {target!r}"
        )
        messages.append(
            Error(
                f"{tag}: {it.name}() replies with its partial, #{partial}, but {says}.",
                hint=f'Write hx-target="#{partial}" on the control, or hx-target:inherited="#{partial}" on an ancestor.',
                obj=where,
                id="dj_hx.E012",
            )
        )
    swap = node.resolved("hx-swap")
    style = parse_swap_spec(swap or "")["style"]  # htmx 4's default, innerHTML, when there is none
    if (swap is None or JINJA not in swap) and style not in _OUTER_SWAPS:
        says = (
            "it has no hx-swap, so htmx 4 swaps innerHTML" + _plain_on_ancestor(node, "hx-swap")
            if swap is None
            else f"its hx-swap is {swap!r}"
        )
        keeps = f' That leaves two elements with id="{partial}".' if style in _KEEPS_THE_TARGET else ""
        messages.append(
            Error(
                f"{tag}: {it.name}() replies with its whole partial, root and all, so the control must use an outer "
                f"swap (outerHTML, outerMorph or outerSync), but {says}.{keeps}",
                hint='Write hx-swap="outerHTML" on the control, or hx-swap:inherited="outerHTML" on an ancestor; '
                "outerMorph and outerSync are outer swaps too.",
                obj=where,
                id="dj_hx.E013",
            )
        )
    return messages


def _interaction_messages(it, controlled: set, sources: dict) -> list:
    """E014 to E016: the interaction has a control, and its partial loads and starts with its id."""
    from .errors import HxUnknownPartial
    from .interactions import act_form
    from .templates import partial_sources
    from .verbs import _get_partial

    where, messages = f"{it.view.__module__}.{it.name}", []
    if it.name not in controlled:
        messages.append(
            Error(
                f"{it.name}() has no control: no project template writes {{% act '{it.name}' %}}. A "
                f"{{% url 'dj_hx:{it.name}' %}} or a hand-written path is not counted, because E011 to E013 cannot "
                "check it.",
                hint=f'Write it into the control that sends the request: hx-{it.method.lower()}="{act_form(it)}" '
                f'hx-target="#{it.partial}" hx-swap="outerHTML". Or delete the interaction.',
                obj=where,
                id="dj_hx.E014",
            )
        )
    try:
        _get_partial(it.template, it.partial)
    except HxUnknownPartial as exc:
        messages.append(
            Error(
                f"{it.name}() replies with {it.template}#{it.partial}, which does not load: {exc}",
                obj=where,
                id="dj_hx.E015",
            )
        )
        return messages
    region = partial_sources(sources[it.template]).get(it.partial) if it.template in sources else None
    if region is not None:
        messages += _root_messages(it, *region)
    return messages


def _root_messages(it, line: int, body: str) -> list:
    """E016, the start-up twin of HxPartialRootId: judged only where the source shows the root."""
    from .errors import HxPartialRootId
    from .hxlint import JINJA, parse
    from .templates import strip_template_syntax
    from .verbs import check_root_id

    html = strip_template_syntax(body)
    content = html.lstrip()
    first_element = _ELEMENT.search(body)
    if content.startswith(JINJA) or _ELSEWHERE.search(body[: first_element.start()] if first_element else body):
        return []  # computed output, or another template or partial, comes first
    root = next(iter(parse(html)[0].children), None)
    if content.startswith("<") and root is not None and JINJA in (root.attrs.get("id") or ""):
        return []  # a computed id
    try:
        check_root_id(
            html, it.partial, f"{it.template}#{it.partial}", role=f"the reply of {it.name}(), which replaces #{it.partial}"
        )
    except HxPartialRootId as exc:
        at = line + html.count("\n", 0, len(html) - len(content))
        return [Error(str(exc), obj=f"{it.template}:{at}", id="dj_hx.E016")]
    return []
