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
W004     Warning  HX_MESSAGES_TEMPLATE does not resolve to a template partial, or its root is not id=<name>
W005     Warning  A project template fails the htmx 4 lint (htmx 2 idioms, typos)
W006     Warning  Django < 6 without django-template-partials installed
E007     retired  HxMixin and its order check were removed in 0.2.1; the id is not reused
W008     Warning  HX_EXTENSIONS is a string, or names an extension htmx 4 does not ship
E009     Error    {% act %} names no interaction
E010     Error    {% act %}'s keywords are not its handler's parameters
E011     Error    An {% act %} control sends another method than its interaction answers
E012     Error    An {% act %} control does not target the element with the partial's id
E013     Error    An {% act %} control's hx-swap (own or :inherited) is not an outer swap
E014     Error    An interaction has no control: no template writes its {% act %}
E015     Error    An interaction's partial does not load, or does not parse
E016     Error    An interaction's partial's root element is not id="<partial>"
E017     Error    dj_hx.urls routes an interaction to other than what its module holds
W018     Warning  The module attribute routed does not unwrap to its interaction
W019     Warning  A decorator sits below @interaction
E020     Error    Interactions are registered but dj_hx.urls is not included
I021     Info     An {% act %} the checks cannot tie to a control's attributes
E022     Error    A {% url %} with a quoted name does not reverse with its arguments
I023     Info     A {% url %} not checked: its route takes a converter with no placeholder
W024     Warning  An event a view or interaction announces that no template listens for
W025     Warning  An event a template listens for that nothing announces
E026     Error    An hx-select (own or :inherited) reaches an {% act %} control
W027     Warning  A {% url %} names a route a URLconf adds only under a condition unmet here
=======  =======  ==========================================================

E009 to E016, I021, E022, I023, E026 and W027 read the project's template files as hx_lint
does, never site-packages. A computed hx-swap or hx-method is not judged. A
templated id or hx-target is judged by its literal parts (``_could_equal``):
skipped only when it could equal the expected value (id="{{ name }}"), an Error
otherwise (id="row-{{ pk }}"). A block tag in an id, and the text it wraps, is
computed too (id="{% if p %}{{ p }}-{% endif %}notify" is skipped). E012 reads an
extended hx-target (closest, find, findAll, next or previous, after an optional
"global ") by its CSS part, as htmx 4.0.2's target resolver does. E014 skips
an interaction whose handler's module is in site-packages
(``templates.in_site_packages``): its controls are in that app's templates,
which the scan never reads.
E013's outer swaps, read from htmx 4.0.2's swap code: outerHTML replaces the
target, outerMorph morphs the target itself, and outerSync copies the reply
root's attributes onto it and takes the root's children, so each leaves one
element with the id. In Chromium on htmx 4.0.2 (tests/test_interactions_browser.py)
each does; innerHTML, beforeend, afterbegin, beforebegin and afterend leave two,
and on innerMorph htmx throws (HierarchyRequestError, logged as htmx:error), so
the reply never reaches the page.
E026 reads hx-select as htmx 4.0.2 does, as it reads hx-target: the control's
own, else the nearest ancestor's hx-select:inherited. An own hx-select="" is an
empty value, which selects nothing and stops an ancestor's. Any other that
reaches an {% act %} control makes the request full, so the interaction's
fragment() records HxFragmentIntoPage on each reply, and the reply is cut down
to what the selector finds in it (querySelectorAll) before the swap. In
Chromium on htmx 4.0.2 (tests/test_interactions_browser.py) a selector that
matches nothing in the reply removes the partial's region, and one that matches
inside it puts that element in the region's place.
E022 reads each {% url %} as Django's lexer does (not in a comment or {% verbatim %}),
skips a name built at run time, and reverses the name through Django's resolver
with a placeholder for each argument, chosen by the converter the pattern
declares there: int 1; str, slug and path "a"; uuid 00000000-0000-0000-0000-000000000000.
Positional and keyword arguments are counted apart; a keyword that names one of
a route's extra kwargs is passed that default. {% url ... as var %} is skipped:
it is Django's documented form for a view that may be missing. A custom
converter or a re_path group gets I023 instead. It reads .html and .htm
templates and reverses against ROOT_URLCONF only. A name no pattern or namespace
has gets W027 instead when a URLconf module the resolver loaded adds it under a
module-level if (or its elif or else) these settings do not take: a path()'s
name= there, or a name inside what an include() there includes, imported to
read it. That block left nothing in the resolver, so the module's source is
read, and only when a tag fails. A name a call builds (debug_toolbar_urls())
or a loop adds is not read, and stays E022.
W024 and W025 pair the events views announce with .trigger() or an HX-Trigger
header they write (response["HX-Trigger"] = "a, b" or HttpResponse(headers={...}),
read for its literal names as htmx 4.0.2 reads the header), or with django-htmx's
trigger_client_event() unless after= is "swap" or "settle" (as hx_map finds them) and interactions declare in triggers= with the listeners in the project's
templates (hx-trigger, hx-on, and hyperscript on in an attribute or an inline
<script type="text/hyperscript">, behaviors included), through
mapcore.unpaired_events(), the pairing hx_map warns from. A browser event,
hyperscript's on intersection, on mutation or on resize, or a name with a colon
(htmx:*, sse:message, contact:saved) is never asked to be announced, and still
pairs; a name built in the template is not read as a listener. An event a
script names (a quoted name in a <script> or hx-on, or a hyperscript send or
trigger) counts for both sides, since the scan cannot tell whether the script
listens or sends. They are Warnings because a scan cannot see every side: a
JavaScript file, a hyperscript file, a template in site-packages, or a helper
the view calls. An interaction in site-packages announces its triggers= but is
not warned about. Both skip without ROOT_URLCONF, through which the map
resolves literal paths.
"""

from __future__ import annotations

import re
from typing import Any

import django
from django.core.checks import CheckMessage, Error, Info, Tags, Warning, register

from .hxlint import SELECTOR_HEADS

_ELEMENT = re.compile(r"<[a-zA-Z]")
_ELSEWHERE = re.compile(r"\{%\s*(?:include|partial)\b")  # a tag that renders another template or partial in place
_OUTER_SWAPS = {"outerHTML", "outerMorph", "outerSync"}  # one element carries the id after the swap (htmx 4.0.2)
# htmx 4.0.2's target resolver (#be): an optional "global " prefix, then, per comma-separated part, a
# keyword whose argument is a CSS selector (closest, find, findAll, next, previous), a fixed target
# (this, document, window, body, host, bare next or previous) or plain CSS. group(1) is the CSS part.
# The prefix and the keywords are hx-flask's hxlint.SELECTOR_HEADS, which its trigger lint reads too.
_GLOBAL = "global"
_EXTENDED_SELECTOR = re.compile(
    rf"(?:{_GLOBAL} )?(?:(?:{'|'.join(sorted(SELECTOR_HEADS - {_GLOBAL}))}) )?(.*)", re.S
)
_KEEPS_THE_TARGET = {"innerHTML", "afterbegin", "beforeend", "beforebegin", "afterend"}  # reply in or beside it: two ids


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
                    'id="messages" and it iterates {{ messages }}. If your fragments show their own messages '
                    '(an {% include %} of the messages template), add "dj_hx.W003" to SILENCED_SYSTEM_CHECKS '
                    "instead: a fragment that leaves messages unshown is still recorded."
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
                    f"in {template!r}. Until then every message on a fragment response records HxUnknownPartial "
                    "and waits for the next page."
                ),
                id="dj_hx.W004",
            )
        ]
    except Exception:
        return []
    return _messages_root(template, name or "messages")


def _messages_root(template: str, name: str) -> list:
    """W004's second half: the messages partial's root carries its name, as the bridge checks at each render."""
    from django.template.loader import get_template

    from .templates import partial_sources

    source = getattr(getattr(get_template(template), "template", None), "source", None)
    region = partial_sources(source).get(name) if isinstance(source, str) else None
    found = _root_complaint(template, name, "the messages partial (HX_MESSAGES_TEMPLATE)", *region) if region else None
    if found is None:
        return []
    at, message = found
    return [
        Warning(
            message,
            hint=(
                f'Give the partial\'s root id="{name}": the bridge swaps it with hx-target="#{name}". Until then '
                "every message on a fragment response records HxPartialRootId and waits for the next page."
            ),
            obj=f"{template}:{at}",
            id="dj_hx.W004",
        )
    ]


@register("dj_hx", Tags.templates)
def check_template_lint(app_configs=None, **kwargs):
    """The htmx 4 lint over the project's own template source (never site-packages)."""
    if not _should_run(app_configs):
        return []
    from .templates import lint_templates

    errors: dict[str, list] = {}
    for f in lint_templates().findings:
        if f.severity == "error":
            errors.setdefault(str(f.file), []).append(f)
    messages = []
    for path, findings in errors.items():
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
            f"{module} before the URLconf is loaded: from the app's ready(), or from its interactions module, which dj-hx "
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
    messages: list[CheckMessage] = []
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


def _could_equal(value: str, literal: str) -> bool:
    """
    Whether ``value`` could render as ``literal``, an id or ``#id``. strip_template_syntax leaves one
    JINJA marker per computed part, after any newlines that part spanned, and whitespace for each
    block tag, so ``value`` is judged by its literal parts, in order, with anything between them. A
    value with no computed part could only be itself.

    An id holds no whitespace, so whitespace left in ``value`` is a block tag, and the text from the
    first such tag to the last is inside {% if %} or {% for %}, which may not render: that span is one
    computed part (id="{% if p %}{{ p }}-{% endif %}notify" renders "notify"). A selector keeps its
    real spaces safe this way: "#notify div" and ".list #notify" still cannot equal "#notify".
    """
    from .hxlint import JINJA

    value = re.sub(rf"\n+(?={re.escape(JINJA)})", "", value)  # an expression's own newlines
    tags = list(re.finditer(r"\s+", value))
    if tags:
        value = value[: tags[0].start()] + JINJA + value[tags[-1].end() :]
    parts = value.split(JINJA)
    return re.fullmatch(".*".join(map(re.escape, parts)), literal, re.S) is not None


def _shown(value: str) -> str:
    """A stripped value as a message shows it: hxlint's shown(), without the newlines the stripper keeps."""
    from .hxlint import JINJA, shown

    return shown(re.sub(rf"\n+(?={re.escape(JINJA)})", "", value))


def _shown_id(value: str) -> str:
    """A stripped id as a message shows it: {{…}} for each computed part, {%…%} for each block tag (whitespace)."""
    return re.sub(r"\s+", "{%…%}", _shown(value))


def _described(element) -> str:
    found = element.attrs.get("id")
    return f'a <{element.tag}> with id="{_shown_id(found)}"' if found else f"a <{element.tag}> with no id"


def _control_messages(it, node, attr: str, where: str) -> list:
    """E011 to E013: the control that ``{% act %}`` writes the URL of, against what its interaction replies."""
    from .hxlint import JINJA, parse_swap_spec
    from .interactions import act_form
    from .mapcore import action_method

    tag, partial, messages = f"{{% act '{it.name}' %}}", it.partial, []
    sends = action_method(node) if attr == "hx-action" else attr[len("hx-") :].upper()
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
    # htmx 4.0.2 targets the control itself when no hx-target reaches it, and the element declaring
    # hx-target="this" for "this" (its #K and #z); either is right when that element has the partial's id.
    # Otherwise the selector is right when its CSS part is #<partial>, bare or after closest, find,
    # findAll, next or previous, with or without "global " (#be): it reaches that element or nothing.
    target = node.resolved("hx-target")
    value = (target or "").strip()
    targeted = node if target is None else node.resolving("hx-target") if value == "this" else None
    if targeted is not None:
        right = _could_equal(targeted.attrs.get("id") or "", partial)
    else:
        extended = _EXTENDED_SELECTOR.fullmatch(value)
        right = extended is not None and _could_equal(extended.group(1).strip(), f"#{partial}")
    if not right:
        if target is None:
            says = (
                f"it has no hx-target, so htmx 4 targets the control itself, {_described(node)}, which would need "
                f'id="{partial}"' + _plain_on_ancestor(node, "hx-target")
            )
        elif targeted is not None:
            says = (
                f"its hx-target is 'this', so htmx 4 targets the element that declares it, {_described(targeted)}, "
                f'which would need id="{partial}"'
            )
        else:
            says = f"its hx-target is {_shown(target)!r}"
        messages.append(
            Error(
                f"{tag}: {it.name}() replies with its partial, #{partial}, but {says}.",
                hint=f'Write hx-target="#{partial}" on the control, or hx-target:inherited="#{partial}" on an ancestor, '
                f'or give the element it targets id="{partial}".',
                obj=where,
                id="dj_hx.E012",
            )
        )
    swap = node.resolved("hx-swap")
    style = parse_swap_spec(swap or "")["style"]  # htmx 4's default, innerHTML, when there is none
    if (swap is None or JINJA not in swap) and style not in _OUTER_SWAPS:
        says = (
            "it has no hx-swap, so htmx 4 swaps innerHTML by default" + _plain_on_ancestor(node, "hx-swap")
            if swap is None
            else f"its hx-swap is {swap!r}"
        )
        if style in _KEEPS_THE_TARGET:
            keeps = f' That leaves two elements with id="{partial}".'
        elif style == "innerMorph":  # measured on htmx 4.0.2: the swap throws partway through
            keeps = " With innerMorph, htmx 4.0.2 throws (HierarchyRequestError, logged as htmx:error) and the reply never reaches the page."
        else:
            keeps = ""
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
    # htmx 4.0.2 reads hx-select as it reads hx-target: the control's own, else the nearest ancestor's
    # hx-select:inherited. One that reaches the control makes the request full, and the reply is cut down to the
    # elements the selector finds in it (querySelectorAll) before the swap. An own hx-select="" is a value, empty:
    # no select, and it stops an ancestor's.
    selecting, select = node.resolving("hx-select"), node.resolved("hx-select")
    if selecting is not None and select and JINJA not in select:
        own = selecting is node
        says = (
            f"its hx-select is {select!r}"
            if own
            else f'it inherits hx-select:inherited="{select}" from {_described(selecting)}'
        )
        if _could_equal(select.strip(), f"#{partial}"):
            effect = "it picks the partial's root, so the swap itself is unchanged."
        else:
            effect = (
                f"Where none match, #{partial} is emptied away; where one inside the partial matches, it replaces "
                f"#{partial}, and the next reply has no #{partial} to target."
            )
        messages.append(
            Error(
                f"{tag}: {it.name}() replies with its partial, #{partial}, but {says}. htmx 4 then sends "
                "HX-Request-Type: full, so each reply records HxFragmentIntoPage, and swaps in only the reply's "
                f"elements that match the selector: {effect}",
                hint=(
                    "Remove hx-select from the control: its interaction already replies with its partial alone."
                    if own
                    else "Narrow the ancestor's hx-select:inherited to elements that do not hold the control (htmx 4 "
                    'has no hx-disinherit), or write hx-select="" on the control, which htmx 4.0.2 reads as no select.'
                ),
                obj=where,
                id="dj_hx.E026",
            )
        )
    return messages


def _interaction_messages(it, controlled: set, sources: dict) -> list:
    """
    E014 to E016: the interaction has a control, and its partial loads and starts with its id. E014
    skips an interaction whose handler's module is in site-packages: its controls are in that app's
    templates, which the scan never reads.
    """
    from django.template import TemplateSyntaxError

    from .errors import HxUnknownPartial
    from .interactions import act_form
    from .templates import partial_sources
    from .verbs import _get_partial

    where, messages = f"{it.view.__module__}.{it.name}", []
    if it.name not in controlled and not _installed(it):
        messages.append(
            Error(
                f"{it.name}() has no control: no project template writes {{% act '{it.name}' %}}. A "
                f"{{% url 'dj_hx:{it.name}' %}} or a hand-written path is not counted, because E011 to E013 cannot "
                "check it.",
                hint=f'Write it into the control that sends the request: hx-{it.method.lower()}="{act_form(it)}" '
                f'hx-target="#{it.partial}" hx-swap="outerHTML", inside the partial, whose root carries '
                'hx-status:40x:inherited="swap:none" hx-status:5xx:inherited="swap:none" so an error reply keeps '
                "the controls (README, The status policy). Or delete the interaction.",
                obj=where,
                id="dj_hx.E014",
            )
        )
    try:
        _get_partial(it.template, it.partial)
    except (HxUnknownPartial, TemplateSyntaxError) as exc:  # Django's message names the line of a syntax error
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


def _installed(it) -> bool:
    """Whether the module that defines ``it``'s handler is in site-packages: its templates are never read."""
    import sys

    from .templates import in_site_packages

    file = getattr(sys.modules.get(it.func.__module__), "__file__", None)
    return bool(file) and in_site_packages(file)


def _root_messages(it, line: int, body: str) -> list:
    """E016, the start-up twin of HxPartialRootId for an interaction's reply."""
    found = _root_complaint(
        it.template, it.partial, f"the reply of {it.name}(), which replaces #{it.partial}", line, body
    )
    if found is None:
        return []
    at, message = found
    return [Error(message, obj=f"{it.template}:{at}", id="dj_hx.E016")]


def _root_complaint(template: str, partial: str, role: str, line: int, body: str) -> tuple[int, str] | None:
    """
    What check_root_id would say of the partial ``partial`` of ``template`` at render, and the line, read
    from its source (``line`` is where ``body`` starts); None when it would say nothing. Judged only where
    the source shows the root: not when computed output or another template or partial comes first, nor
    for a templated id that could be the name. E016 and W004 both ask this.
    """
    from .errors import HxPartialRootId
    from .hxlint import JINJA, parse
    from .templates import strip_template_syntax
    from .verbs import check_root_id

    html = strip_template_syntax(body)
    content = html.lstrip()
    first_element = _ELEMENT.search(body)
    if content.startswith(JINJA) or _ELSEWHERE.search(body[: first_element.start()] if first_element else body):
        return None  # computed output, or another template or partial, comes first
    root = next(iter(parse(html)[0].children), None)
    root_id = (root.attrs.get("id") or "") if root is not None else ""
    if content.startswith("<") and _could_equal(root_id, partial):
        return None  # the partial's id, or a templated one that could be it
    try:
        check_root_id(html, partial, f"{template}#{partial}", role=role)
    except HxPartialRootId as exc:
        at = line + html.count("\n", 0, len(html) - len(content))
        message = str(exc).replace(f'id="{root_id}"', f'id="{_shown_id(root_id)}"') if root_id else str(exc)
        return at, _shown(message)
    return None


@register("dj_hx", Tags.templates, Tags.urls)
def check_url_tags(app_configs=None, **kwargs):
    """
    Every ``{% url %}`` with a quoted name in the project's templates reverses with the arguments it
    passes (E022), or names the converter that keeps it from being checked (I023). ``{% url ... as var %}``
    is skipped: it is Django's documented form for a view that may be missing, and stores "" then.
    """
    if not _should_run(app_configs):
        return []
    from django.conf import settings
    from django.urls import get_resolver

    from .templates import template_sources, url_tags

    if not getattr(settings, "ROOT_URLCONF", None):
        return []
    try:
        get_resolver().reverse_dict  # imports the URLconf; Django's own checks report one that does not load
    except Exception:
        return []
    messages = []
    gated = {}  # a name, as a tag writes it -> (where, condition): _gated_routes()
    read = []

    def gate(name: str) -> tuple[str, str] | None:
        if not read:  # read the URLconf modules' source once, and only when a tag has failed
            gated.update(_gated_routes())
            read.append(True)
        return gated.get(name)

    for template, source in template_sources().items():
        for tag in url_tags(source):
            if tag.name is not None and tag.stored_as is None:  # a name built at run time, or `as var`
                messages += _url_messages(tag, f"{template}:{tag.line}", gate)
    return messages


def _placeholder(converter):
    """What one of Django's own converters is reversed with; None for any other, or a re_path group (None)."""
    from django.urls import converters as c

    return {
        c.IntConverter: 1,
        c.StringConverter: "a",
        c.SlugConverter: "a",
        c.PathConverter: "a",
        c.UUIDConverter: "00000000-0000-0000-0000-000000000000",
    }.get(type(converter))


def _url_patterns(name: str):
    """
    ``(patterns, None)``: what ``reverse(name)`` chooses among, as ``(route, params, converters,
    defaults)``, read from the resolver through the namespaces as ``reverse()`` walks them; ``defaults``
    are the route's extra kwargs, which a keyword may name. ``(None, (namespace, inside, known))`` when a
    namespace on the way is not installed.
    """
    from django.urls import get_resolver
    from django.urls.resolvers import get_ns_resolver

    from .hxmap import namespace_walk

    resolver = get_resolver()
    *path, view = name.split(":")
    steps, missing = namespace_walk(path, resolver)
    inside = [step[0] for step in steps]
    if steps:
        resolver = steps[-1][2]
    if missing is not None:
        return None, (missing, inside, sorted({*resolver.namespace_dict, *resolver.app_dict}))
    ns_pattern, ns_converters = "".join(step[1] for step in steps), {}
    for step in steps:
        ns_converters.update(step[2].pattern.converters)
    if ns_pattern:
        resolver = get_ns_resolver(ns_pattern, resolver, tuple(ns_converters.items()))
    patterns = [
        (route, params, converters, defaults)
        for possibilities, _, defaults, converters in resolver.reverse_dict.getlist(view)
        for route, params in possibilities
    ]
    return patterns, None


def _gated_routes() -> dict[str, tuple[str, str]]:
    """
    ``{"set_language": ("proj/urls.py:51", "settings.LANGUAGE_SWITCHER")}``: each URL name, as a tag writes it,
    that a URLconf module the resolver loaded adds only under a module-level ``if``, ``elif`` or ``else``, with
    where and on what condition. The branch not taken left nothing in the resolver, so the module's source is
    read: a ``path()``'s ``name=`` in the block, and the names inside what an ``include()`` there includes (a
    dotted path, imported; a name the module holds; either in an ``(urls, app_name)`` pair). Nothing here raises.
    """
    import ast
    import importlib
    import inspect
    import os
    import types

    from django.urls import get_resolver
    from django.urls.resolvers import RegexPattern, URLResolver

    found: dict[str, tuple[str, str]] = {}
    scanned: set[tuple[str, tuple[str, ...]]] = set()

    def names_in(urlconf) -> list[str]:
        try:
            return _url_names(URLResolver(RegexPattern(r"^"), urlconf))
        except Exception:  # an include that does not load: Django's own checks say why when it is taken
            return []

    def included(call, module) -> list[str]:
        target = call.args[0]
        namespace = call.args[1].value if len(call.args) > 1 and isinstance(call.args[1], ast.Constant) else None
        namespace = next((k.value.value for k in call.keywords if k.arg == "namespace" and isinstance(k.value, ast.Constant)), namespace)
        app_name = None
        if isinstance(target, ast.Tuple) and len(target.elts) == 2:
            if isinstance(target.elts[1], ast.Constant):
                app_name = target.elts[1].value
            target = target.elts[0]
        urlconf: Any = None
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            try:
                urlconf = importlib.import_module(target.value)
            except Exception:
                return []
        elif isinstance(target, (ast.Name, ast.Attribute)):
            dotted = ast.unparse(target).split(".")
            urlconf = getattr(module, dotted[0], None)
            for attr in dotted[1:]:
                urlconf = getattr(urlconf, attr, None)
        if isinstance(urlconf, tuple) and len(urlconf) == 2:  # include(shop), shop = (urlpatterns, "shop")
            urlconf, app_name = urlconf[0], app_name or urlconf[1]
        if urlconf is None:
            return []
        if isinstance(urlconf, types.ModuleType):
            app_name = app_name or getattr(urlconf, "app_name", None)
        prefixes = [f"{n}:" for n in dict.fromkeys((namespace, app_name)) if isinstance(n, str) and n] or [""]
        return [p + name for name in names_in(urlconf) for p in prefixes]

    def branches(stmt, earlier: list):
        """Each branch of an if/elif/else chain, with the whole condition it is taken on."""
        test = ast.BoolOp(ast.And(), [*earlier, stmt.test]) if earlier else stmt.test
        yield stmt.body, test
        earlier = [*earlier, ast.UnaryOp(ast.Not(), stmt.test)]
        if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
            yield from branches(stmt.orelse[0], earlier)
        elif stmt.orelse:
            yield stmt.orelse, ast.BoolOp(ast.And(), earlier) if len(earlier) > 1 else earlier[0]

    def scan(module, prefixes: list[str]) -> None:
        if (module.__name__, tuple(prefixes)) in scanned:
            return
        scanned.add((module.__name__, tuple(prefixes)))
        try:
            source, file = inspect.getsource(module), inspect.getsourcefile(module) or module.__name__
            tree = ast.parse(source)
        except (OSError, TypeError, SyntaxError):
            return
        try:
            file = os.path.relpath(file)
        except ValueError:  # another drive, on Windows
            pass
        for stmt in tree.body:
            if not isinstance(stmt, ast.If):
                continue
            for body, test in branches(stmt, []):
                at = (f"{file}:{body[0].lineno}" if body else f"{file}:{stmt.lineno}", ast.unparse(test))
                for node in (n for b in body for n in ast.walk(b) if isinstance(n, ast.Call)):
                    func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    names: list[str] = []
                    if func in ("path", "re_path", "url"):
                        names = [k.value.value for k in node.keywords if k.arg == "name" and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)]
                    elif func == "include" and node.args:
                        names = included(node, module)
                    for name in names:
                        for p in prefixes:
                            found.setdefault(p + name, at)

    def visit(resolver, prefixes: list[str], depth: int) -> None:
        if depth > 10:  # a URLconf that includes itself
            return
        try:
            module, patterns = resolver.urlconf_module, list(resolver.url_patterns)
        except Exception:
            return
        if isinstance(module, types.ModuleType):
            scan(module, prefixes)
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                names = [n for n in dict.fromkeys((pattern.namespace, pattern.app_name)) if n]
                visit(pattern, [f"{p}{n}:" for p in prefixes for n in names] if names else prefixes, depth + 1)

    try:
        visit(get_resolver(), [""], 0)
    except Exception:
        return found
    return found


def _url_names(resolver, prefix: str = "") -> list[str]:
    """Every name ``{% url %}`` can reverse under ``resolver``, namespaced as a tag writes it."""
    names = [prefix + key for key in resolver.reverse_dict if isinstance(key, str)]
    for namespace, (_, inner) in resolver.namespace_dict.items():
        names += _url_names(inner, f"{prefix}{namespace}:")
    return names


def _route_shown(route: str, params, converters) -> str:
    """``/contacts/<int:contact_id>/edit/``: a pattern as path() writes it."""
    from django.urls.converters import get_converters

    names = {type(c): n for n, c in get_converters().items()}
    return "/" + route % {
        p: f"<{names[type(converters[p])]}:{p}>" if type(converters.get(p)) in names else f"<{p}>" for p in params
    }


def _url_messages(tag, where: str, gate=lambda name: None) -> list:
    """
    E022 or I023 for one ``{% url %}``: reversed with a placeholder for each argument it passes. W027 instead of
    E022 for a name ``gate(name)`` says a URLconf adds only under a condition these settings do not take.
    """
    import difflib

    from django.urls import NoReverseMatch, get_resolver, reverse

    shown = f"{{% url '{tag.name}' %}}"
    fails = "so the page raises NoReverseMatch at render"

    def error(msg, hint):
        # The check reads every template, rendered or not, so one a removed view left behind fails too.
        hint += " A template nothing renders any more fails this check too; delete it."
        return [Error(msg, hint=hint, obj=where, id="dj_hx.E022")]

    if tag.positional and tag.keywords:
        return error(
            f"{shown} passes {tag.positional} positional and {len(tag.keywords)} keyword "
            f"argument{'s' if len(tag.keywords) > 1 else ''}; reverse() refuses the mix, so the page raises "
            "ValueError at render.",
            "Pass every argument by keyword, or every one by position.",
        )
    patterns, missing = _url_patterns(tag.name)
    gated = gate(tag.name) if missing or not patterns else None
    if gated:
        line, condition = gated
        return [
            Warning(
                f"{shown} names a URL pattern that {line} adds only when {condition}, which these settings do not "
                "meet, so the page raises NoReverseMatch if it renders this tag.",
                hint=f"Render the tag only under the same condition, or write {{% url '{tag.name}' as url %}}, "
                "Django's form for a view that may be missing, which stores \"\" then. This is a Warning, not E022, "
                "because the check cannot see the condition each page renders the tag under; silence dj_hx.W027 "
                "where every one holds it.",
                obj=where,
                id="dj_hx.W027",
            )
        ]
    if missing:
        namespace, inside, known = missing
        close = difflib.get_close_matches(namespace, known, n=3, cutoff=0.6)
        return error(
            f"{shown} names the namespace {namespace!r}"
            + (f" inside {':'.join(inside)!r}" if inside else "")
            + ", which no URLconf installs"
            + (f" (did you mean {' or '.join(map(repr, close))}?)" if close else "")
            + f", {fails}.",
            f"Include the URLconf whose app_name is {namespace!r} (path('...', include('<app>.urls'))), or give "
            f"include() namespace={namespace!r}; or correct the namespace in the tag.",
        )
    if not patterns:
        close = difflib.get_close_matches(tag.name, _url_names(get_resolver()), n=3, cutoff=0.6)
        return error(
            f"{shown} names no URL pattern"
            + (f" (did you mean {' or '.join(map(repr, close))}?)" if close else "")
            + f", {fails}.",
            f"Correct the name in the tag, or name the pattern: path(..., name={tag.name.rsplit(':', 1)[-1]!r}).",
        )
    unchecked = []
    for route, params, converters, defaults in patterns:
        passed = params[: tag.positional] if tag.positional else [k for k in tag.keywords if k in params]
        values = {p: _placeholder(converters.get(p)) for p in passed}
        if None in values.values():
            unchecked.append((route, params, converters, next(p for p, v in values.items() if v is None)))
            continue
        args = [values.get(p, "a") for p in params[: tag.positional]] + ["a"] * (tag.positional - len(params))
        # a keyword naming one of the route's extra kwargs reverses only with its value: pass that, so a
        # literal that differs is missed rather than a correct tag called wrong
        kwargs = {k: values[k] if k in values else defaults.get(k, "a") for k in tag.keywords}
        try:
            reverse(tag.name, args=args, kwargs=kwargs)
        except NoReverseMatch:
            continue
        return []
    if unchecked:
        route, params, converters, param = unchecked[0]
        converter = converters.get(param)
        what = (
            f"the converter of {param}, {type(converter).__name__}"
            if converter is not None
            else f"{param}, a regular-expression group (re_path)"
        )
        return [
            Info(
                f"{shown} is not checked: {tag.name!r} is {_route_shown(route, params, converters)}, and dj-hx has no "
                f"placeholder value for {what}.",
                hint="Only int, str, slug, path and uuid parameters are reversed with a placeholder. Silence "
                "dj_hx.I023 in SILENCED_SYSTEM_CHECKS where a route takes another.",
                obj=where,
                id="dj_hx.I023",
            )
        ]
    if tag.positional:
        passes = f"{tag.positional} positional argument{'s' if tag.positional > 1 else ''}"
    elif tag.keywords:
        passes = f"the keyword{'s' if len(tag.keywords) > 1 else ''} {', '.join(tag.keywords)}"
    else:
        passes = "no arguments"
    routes = [(_route_shown(route, params, conv), ", ".join(params) or "nothing") for route, params, conv, _ in patterns]
    if len(routes) == 1:
        takes = f"{routes[0][0]}, which takes {routes[0][1]}"
    else:
        takes = "any of " + "; ".join(f"{shown_route} (takes {params})" for shown_route, params in routes)
    first = patterns[0][1]
    return error(
        f"{shown} passes {passes}, but {tag.name!r} is {takes}, {fails}.",
        "Pass one value for each parameter of the route, all by position or all by keyword: "
        f"{{% url '{tag.name}'{''.join(f' {p}=...' for p in first)} %}}.",
    )


_UNSEEN = (
    "This is a Warning because a scan of the project's templates and views cannot see every side: a JavaScript "
    'file, a hyperscript file (<script type="text/hyperscript" src=...>), a template in site-packages, or a '
    "helper the view calls can {}. If one does, silence dj_hx.{}."
)


@register("dj_hx", Tags.templates)
def check_events(app_configs=None, **kwargs):
    """
    The events views and interactions announce against the listeners in the project's templates, both
    ways, through mapcore.unpaired_events(), the pairing hx_map warns from (W024, W025).
    """
    if not _should_run(app_configs):
        return []
    from django.conf import settings

    from .hxmap import map_with_interactions
    from .interactions import registry
    from .mapcore import Handler, unpaired_events

    if not getattr(settings, "ROOT_URLCONF", None):
        return []  # the map resolves literal-path controls through it, as check_url_tags reverses through it

    m, routed = map_with_interactions()
    handlers, owner = dict(m.handlers), {}
    for it in registry.values():
        h = routed.get(it.name)
        if h is None:  # not routed (E020), or in site-packages: its triggers= are announced all the same
            h = handlers[f"interaction:{it.name}"] = Handler(it.name, name=it.name, announces=set(it.triggers))
        owner[id(h)] = it
    unannounced, unheard = unpaired_events(handlers, m.listeners, m.script_names)
    messages = []
    for event, by in unheard.items():
        for h in by:
            it = owner.get(id(h))
            if it is not None and _installed(it):
                continue  # its listeners are in that app's templates, which are never read
            who, how = (f"{it.name}()", "in its triggers=") if it else (h.label, "with .trigger() or an HX-Trigger header")
            messages.append(
                Warning(
                    f"{who} announces '{event}' {how}, but no project template listens for it (hx-trigger, hx-on, or "
                    f"a hyperscript 'on {event}' in an attribute or an inline <script type=\"text/hyperscript\">), "
                    "and no script there names it.",
                    hint=f'Listen where the change should show: hx-trigger="{event} from:body", or '
                    f'_="on {event} from body ..."; or stop announcing it. ' + _UNSEEN.format("listen", "W024"),
                    obj=f"{it.view.__module__}.{it.name}" if it else h.endpoint,
                    id="dj_hx.W024",
                )
            )
    for event, heard in unannounced.items():
        where = ", ".join(f"{li.file}:{li.line}" for li in heard)
        messages.append(
            Warning(
                f"'{event}' is listened for ({where}), but no view announces it with .trigger() or an HX-Trigger "
                "header it sets, no interaction declares it in triggers=, and no script in the templates names it (a "
                "quoted name in a <script> or hx-on, or a hyperscript send or trigger).",
                hint=f"Announce it, with triggers=({event!r},) on the interaction or .trigger({event!r}) on the "
                "view's response, or correct the name. " + _UNSEEN.format("send it", "W025"),
                obj=f"{heard[0].file}:{heard[0].line}",
                id="dj_hx.W025",
            )
        )
    return messages
