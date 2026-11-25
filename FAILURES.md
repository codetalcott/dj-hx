# What is loud, in full

Every entry here is a row of [README's table](README.md#what-is-loud) with the whole story: what htmx 4 would do
silently, what dj-hx does instead, what it reads to decide, and what it cannot see. Every entry has a test in
`tests/`. Error messages name the handler and say what to change; this file says why.

## A page answers a request that targets an element

**Failure.** A page answers a request that targets an element

**What happens.** `page()` raises `HxPageIntoFragment`. The guard records it for any other 2xx `text/html`
response whose first tag, once the first `<head>` is dropped, is `<html>` or `<body>`. That is htmx 4.0.2's own
test: its swap reads such a body as a document and puts the document's body into the target, under the page already
there, and takes its `<title>` (measured in Chromium by `tests/test_interactions_browser.py`). It covers
`django.shortcuts.render`, a `TemplateResponse`, a verb given a page template, and the page a redirect leads to. A
response carrying `HX-Redirect`, `HX-Refresh: true` or `HX-Location` is not judged, because htmx obeys those before
any swap.

## A fragment answers a boosted or body-targeted request

**Failure.** A fragment answers a boosted or body-targeted request

**What happens.** `fragment()` / `text()` record `HxFragmentIntoPage`

## A 3xx answers a partial request

**Failure.** Any 3xx answers a partial request, including `APPEND_SLASH`'s 301 and `login_required`'s 302

**What happens.** `redirect()` raises. fetch follows any other 3xx with the request's headers, `HX-Request-Type`
included (measured in Chromium, 2026-11-24), so what it reaches is guarded in its turn. A page there is recorded as
`HxPageIntoFragment`, naming the view that answered. A fragment there is swapped as intended: a POST that redirects
to a list's URL is a working pattern. The guard always records `APPEND_SLASH`'s 301 (`HxRedirectIntoFragment`,
naming the cause), because a POST that follows it arrives as a GET without its body. `HX_REQUIRE_VERBS` records every
other 3xx too. `navigate()` leaves the page. What it cannot see: a redirect to a page another server answers.

## A 204 answers a partial request

**Failure.** A 204 answers a partial request

**What happens.** `HxNoSwap`: htmx 4 leaves the target untouched. A 204 carrying `HX-Redirect`, `HX-Refresh: true`
or `HX-Location` is not judged. A deliberate 204 under `hx-swap="none"` is recorded as well; `removed()` answers that
control the same way.

## A response no verb built answers a partial request

**Failure.** A response no verb built answers a partial request

**What happens.** Under `HX_REQUIRE_VERBS = True`, `HxBareResponse`: `django.shortcuts.render`, a plain
`HttpResponse` or a `TemplateResponse` skipped the verbs' checks (the request type, the partial's name, its root).
Without the setting nothing is recorded, so a project on django-htmx can install the guard and keep its views. A whole
page is recorded either way (above).

## Messages added on a fragment with no messages template

**Failure.** Messages added on a fragment with no messages template

**What happens.** `HxMessagesUnconfigured`. Not when the fragment's own template showed the messages, since iterating
them consumes them, and not when htmx will load a page instead of swapping (`navigate()`, `HX-Redirect`,
`HX-Refresh`, `HX-Location`), since that page shows them.

## A partial's root element is not its name

**Failure.** A partial used as `<hx-partial>`, or an interaction's reply, whose root is not `id="<name>"`

**What happens.** `HxPartialRootId` at the render. From the messages bridge it is recorded instead, because the bridge
runs in `HxMiddleware`, which never raises a finding: raising there would turn every fragment response that carries a
message into a 500. The fragment goes out without the messages, the middleware logs the finding, the messages wait for
the next page, and `HxTestClient` raises it. Check `dj_hx.W004` reports the same root at start-up, read from the source

## partial names a partial the template does not define

**Failure.** `partial=` names a partial the template does not define

**What happens.** `HxUnknownPartial`, listing the partials it does. When `HX_MESSAGES_TEMPLATE` names the missing
partial, the messages bridge records it as it records `HxPartialRootId`, and check `dj_hx.W004` warns at start-up

## .partial() on removed() or text()

**Failure.** `removed(request).partial("count", "index.html")`: neither `removed()` nor `text()` carries a context, so
there is nothing to render `#count` from, and the region would stay as it was

**What happens.** `HxError` at the call, naming the handler. On a page, a redirect or `navigate()`, `.partial()` still does
nothing, because each ends in a full page that already contains the region. To update a region after a delete, announce
the fact: `removed(request).trigger("count-changed")`, with `hx-trigger="count-changed from:body"` on `#count`

## An htmx request without HX-Request-Type

**Failure.** An htmx request without `HX-Request-Type`

**What happens.** `HxProtocolError`: this needs htmx 4. Under `DEBUG` the verb raises, so a wrong htmx or a stripping proxy is found at the desk. In production the request is answered as `full` (the page) and the guard records the finding on the response, which `HxMiddleware` logs: a 500 there would take every htmx request on the site down with it, and the page is what a boosted link wanted anyway. `HxTestClient` raises the recorded finding whatever `DEBUG` is

## htmx 2 idioms in the HTML

**Failure.** htmx 2 idioms in the HTML: `hx-ext`, implicit inheritance, htmx 2 event names in `hx-on` or `hx-trigger`, camelCase or kebab-case (`hx-on::after-request`), `show:#x:top`

**What happens.** the lint, on every test-client response, in the middleware log under `DEBUG`, in `manage.py hx_lint`, and as check `dj_hx.W005`

## A template reads a name nobody supplies

**Failure.** A project template reads a name nobody supplies (`{{ x }}`, `{% if x %}`, `{% for i in x %}`, `{{ x|default_if_none:"" }}`, since a missing name is not None and renders '', or a name an `{% include %}` does not pass) or an attribute an object lacks (`{{ user.emial }}`, `{{ items.length }}`). Django renders each as nothing, without a word, and `string_if_invalid` never sees the ones `{% if %}` and `{% for %}` read

**What happens.** `HxTestClient` raises `HxUndefinedVariable` on the request, naming each variable and the template:line it is written in (the base of an `{% extends %}`, the included file, the file a partial is in), and for a name an included template reads, says to pass it in the include's `with` (`… subtitle=None`). It reads Django's `django.template` DEBUG log while the request runs; `strict=False` records it on `response.hx_findings`, and `undefined=False` turns it off. Skipped, because the outcome depends on the request's data: a lookup on None (`{{ obj.rel.name }}` with no `rel`), a key a mapping or the session lacks (`{% if not request.GET.stage %}`, `{% if request.session.cart %}`), an index past the end of a sequence (`items.0` on `[]`), whatever `{% firstof %}` reads, `debug` and `sql_queries` where the debug context processor is configured (it sets them only under `DEBUG`), and a response Django built from an exception (its 500 page). Also skipped, because the template says what to show: a name its own expression gives a `|default` (`{{ subtitle|default:"" }}`). The cost: a misspelt dict key or index is silent, as it is in Django today, and every lookup on a mapping counts as a key, so `{{ forloop.countr }}` (`forloop` is a dict) and `{{ request.GET.urlencod }}` (a QueryDict method) are silent too. Not seen either: a template in site-packages (Django's, admin's, any pip-installed app's), one built from a string, which has no file (Django's `DEBUG` error pages are), a lookup that raised an exception Django silences (a missing related object's `DoesNotExist`), and a render outside the request's own context: in a `ThreadPoolExecutor` or a plain thread, or a streaming response consumed after the request returns. Where new threads inherit the context that starts them (`sys.flags.thread_inherit_context`, the default in Python 3.14's free-threaded build), a thread the view starts carries the request's, and what it renders is checked. An `async def` view is checked

## Logging disabled, so the undefined-variable check is blind

**Failure.** `logging.disable()` is in force, or the `django.template` logger is disabled (a `LOGGING` dict that leaves `disable_existing_loggers` at its default, `True`, disables it), so Django writes no record for the undefined-variable check to read

**What happens.** `HxTestClient` raises `ImproperlyConfigured` on the request, naming which; `undefined=False` goes without the check

## A control points at a view of the other kind

**Failure.** A partial control pointing at a page-only view, or a boosted link at a fragment-only one (an interaction is fragment-only)

**What happens.** `manage.py hx_map`

## A control points at a view that calls no verb, or a view retargets

**Failure.** A control pointing at a view that calls no verb; a view that calls `.retarget()` or `.reswap()`

**What happens.** `manage.py hx_map`, as warnings

## A control would keep what removed() empties

**Failure.** A control targeting an element, with a swap that is neither `delete` nor `swapEmpty:true`, reaching a view that can answer `removed()`. htmx 4 skips an empty main swap when the reply carries an `<hx-partial>`, and the messages bridge appends one whenever the view adds a message, so the element stays on the page. Measured in Chromium by the desk's cross-off row (`tests/test_interactions_browser.py`); with no message, the same `outerHTML` swap removes the row.

**What happens.** `manage.py hx_map`, as a warning. Use `hx-swap="delete"`. When the view can also answer with content (a refused delete that sends the row back with the reason), use `hx-swap="outerHTML swapEmpty:true"`.

## Middleware or settings misconfigured

**Failure.** `HxMiddleware` missing, listed before `MessageMiddleware`, `HX_MESSAGES_TEMPLATE` unset or unresolvable or naming a partial whose root is not `id="<name>"`, no partials on Django < 6

**What happens.** checks `dj_hx.W001`, `E002`, `W003`, `W004`, `W006`

## HX_EXTENSIONS names an unknown extension

**Failure.** `HX_EXTENSIONS` names an extension htmx 4 does not ship, or is a string

**What happens.** check `dj_hx.W008`; htmx's registered name (`sse`) and the file name (`hx-sse`) both count

## The module holds the raw handler under its name

**Failure.** The module that defines the handler holds the raw handler under its name (`remind_view = interaction(...)(remind)`, or `remind = interaction(...)(handlers.remind)` in another module), or a decorator of it written with `functools.wraps`, so its route would skip the method guard

**What happens.** `ImproperlyConfigured` when the URLconf is first read (the first request, or `manage.py check`), naming the module attribute and the fix. A decorator of the raw handler written without `functools.wraps` is routed as it is, past the method guard: only check `dj_hx.W018` warns

## An interaction that cannot work

**Failure.** An `@interaction` that cannot work: two with one name, a minted route for a handler in no installed app, `route=` parameters that are not the handler's (or `<str:...>` for one annotated `int`), a `partial=` that is not `page.html#name`, `triggers=` given as a string, a `method` that is not GET, POST, PUT, PATCH or DELETE, a `refuses` holding anything but exception classes (`refuses=("DomainError",)`), a handler or a `context=` taking `*args` or `**kwargs`, a `context=` parameter without a default that the route does not have

**What happens.** `ImproperlyConfigured` when the views module is imported, so at start-up, naming the handler

## An interaction returns a response

**Failure.** An interaction returns anything but a `dict` or `None`, an `HttpResponse` included, or a view decorator below `@interaction` answers with one

**What happens.** `ImproperlyConfigured`: an interaction always re-renders its partial; leave the page from a view that returns `navigate()`, and put Django view decorators above `@interaction`

## A refusal whose message is empty

**Failure.** A declared refusal whose message is empty or blank (`raise NotOnRota()`), so the 422 reply's `{% if error %}` shows nothing and the click seems to do nothing

**What happens.** `HxEmptyRefusal`, recorded on the 422, which still goes out: logged, and raised by `HxTestClient`, naming the handler and the exception to give a message

## A reply sets a key its context does not define

**Failure.** An interaction's reply sets a key its context does not define

**What happens.** `ImproperlyConfigured`, naming the key and the context function: define each there with its default. `error` is always defined, because every reply carries it

## act with the wrong arguments, or an unknown interaction

**Failure.** `{% act %}` with a positional argument, a keyword the handler does not take, a missing one, or a name no interaction has

**What happens.** `TemplateSyntaxError` at render, naming the handler's parameters, or listing the interactions there are; at start-up, checks `dj_hx.E009` (no such interaction) and `E010` (the arguments), naming template:line

## An act control sends the wrong method, target or swap

**Failure.** An `{% act %}` control that sends another method than its interaction answers (for `hx-action`: its `hx-method`, an ancestor's `hx-method:inherited`, its `method` attribute, else GET; a submit button's `formmethod` is not read), that does not target the element with id `<partial name>` (`hx-target="#<partial name>"`, its own or an ancestor's `hx-target:inherited`, or an htmx 4.0.2 extended selector whose CSS part is that, such as `closest #<partial name>`; or no `hx-target`, or `hx-target="this"`, on the element with that id), or whose `hx-swap` (its own or inherited) is not an outer swap (`outerHTML`, `outerMorph` or `outerSync`, read from htmx 4.0.2's swap code and measured in Chromium)

**What happens.** checks `dj_hx.E011`, `E012` and `E013`, naming template:line and the attribute to write; a plain `hx-target` or `hx-swap` on an ancestor is named as not reaching the control. E013 says what the swap does instead: two elements with the id (`innerHTML`, `beforeend`, `afterbegin`, `beforebegin`, `afterend`), or, for `innerMorph`, an htmx 4.0.2 `HierarchyRequestError` (logged as `htmx:error`), so the reply never reaches the page. E013 does not read a page's `htmx.config.defaultSwap`: a control without `hx-swap` is judged as htmx 4's default, `innerHTML`, because the design is that each control writes its swap

## An hx-select reaches an act control

**Failure.** An `hx-select` that reaches an `{% act %}` control: its own, or the nearest ancestor's `hx-select:inherited` (an own `hx-select=""` is an empty value to htmx 4.0.2: no select, and it stops an ancestor's). htmx 4 then sends `HX-Request-Type: full`, so each reply records `HxFragmentIntoPage`, and swaps in only what the selector finds in the reply

**What happens.** check `dj_hx.E026`, naming template:line and the element the select comes from. In Chromium on htmx 4.0.2 a selector that matches nothing in the reply removes the partial's region, and one that matches inside it puts that element in the region's place, so the next reply has no target; a selector naming the partial's root leaves the swap as it was. A computed `hx-select` is not judged

## An interaction with no control, or a partial that fails

**Failure.** An interaction no project `.html` or `.htm` template writes an `{% act %}` for (a `{% url 'dj_hx:…' %}` or hand-written path is not counted: E011 to E013 cannot check it), whose partial does not load or does not parse, or whose partial's root element is not `id="<partial name>"`

**What happens.** checks `dj_hx.E014`, `E015` (with `HxUnknownPartial`'s reason, or Django's `TemplateSyntaxError` message, so a typo in the partial is a message, not a traceback that stops `manage.py check`) and `E016` (the start-up twin of `HxPartialRootId`, judged where the source shows the root). E014 skips an interaction whose handler's module is in site-packages: its controls are in that app's templates, which are never read

## An interaction registered after dj_hx.urls was read

**Failure.** An interaction registered after `dj_hx.urls` was first read, so its route is the bare view and the decorators above it do not apply

**What happens.** check `dj_hx.E017`, naming the module to import before the URLconf is loaded

## Interactions registered but dj_hx.urls not included

**Failure.** Interactions registered, but `dj_hx.urls` not included

**What happens.** check `dj_hx.E020`; `{% act %}` raises `ImproperlyConfigured`; both name `path("", include("dj_hx.urls"))`

## A decorator without functools.wraps, or below the interaction

**Failure.** A decorator above `@interaction` written without `functools.wraps`, so nothing can see that it wraps the interaction; a decorator below `@interaction` (the handler has `__wrapped__`)

**What happens.** checks `dj_hx.W018` (use `functools.wraps`) and `W019` (view decorators belong above `@interaction`)

## An act the checks cannot tie to a control

**Failure.** An `{% act %}` the checks cannot tie to one element's verb attribute: in a `<script>` or text, in another attribute, stored with `as`, or naming its interaction with a variable

**What happens.** check `dj_hx.I021`, an Info naming template:line; a quoted name and its keywords are still checked. `assert_no_hx_check_issues()` counts it, so silence it by id where it is deliberate

## A url tag that does not reverse

**Failure.** A `{% url 'name' … %}` in a project's `.html` or `.htm` template that does not reverse: a name no pattern has (close names are listed), a namespace no URLconf installs, positional arguments or keywords the route does not take, or both kinds mixed

**What happens.** check `dj_hx.E022`, naming template:line and the route the name has. Each argument is reversed with a placeholder for the converter its route declares (`int` 1; `str`, `slug` and `path` "a"; `uuid` all zeros), and a keyword that names one of a route's extra kwargs (`path("feed.atom", view, {"fmt": "atom"})`) with that default. A route with a custom converter or a `re_path` group has no placeholder, so it is not checked: Info `dj_hx.I023` names it. The usual one is a third-party `re_path` route in a template the project overrides: admin's breadcrumb `{% url 'admin:app_list' app_label=… %}`, or allauth's `{% url 'account_confirm_email' … %}` (the only I023 in a 378-template production project). `assert_no_hx_check_issues()` counts an Info, so silence `dj_hx.I023` by id there. `{% url … as var %}` is skipped, as Django's documented form for a view that may be missing (admin's own templates use it), and so are a name built at run time (a variable, a filter on it) and a tag in a comment or `{% verbatim %}`. A tag written across lines is read where Django reads it: a tag from Django 6.2, text before (`templates.tags_span_lines()` asks the lexer). It reverses against `ROOT_URLCONF` only: a site that sets `request.urlconf` per request silences it

On an existing site the first `manage.py check` is a worklist, `dj_hx.E022` above all, since it
reads every `{% url %}` in the project's `.html` and `.htm` templates, rendered or not. A template that
nothing renders any more fails too; each hint says to delete it, and on one app it did not build beside
all five of dj-hx's first E022s were that (2026-11-23). An Error fails `manage.py
check`, keeps `runserver` from starting, and aborts `migrate`, `makemigrations`, `createsuperuser` and
`manage.py test`, which all run the checks. While you work through the list,
`SILENCED_SYSTEM_CHECKS = ["dj_hx.E022"]` silences one id, Errors included; take it out again to check
the rest. E022 reverses against `ROOT_URLCONF` only, so a site that routes some requests through
another URLconf (`request.urlconf`, as django-hosts sets it) silences it.

E022's result depends on the settings it runs under. A route included only under `DEBUG` or a
feature flag does not exist under other settings, so a template that links it, even behind
`{% if %}`, is an E022 there, and a deploy's `migrate` runs the checks under production settings.
Write such a link as `{% url 'name' as link %}{% if link %}…{% endif %}`: Django stores `""` for a
route that does not reverse, and E022 skips the `as` form.

## An event nobody listens for, or nobody announces

**Failure.** An event a view announces with `.trigger()` (as `hx_map` finds it) or an interaction declares in `triggers=` that no project template listens for (`hx-trigger`, `hx-on`, a hyperscript `on` in an `_`, `script` or `data-script` attribute or in an inline `<script type="text/hyperscript">`, behaviors included); an event a template listens for that nothing announces. A listener for a browser event, for one of hyperscript's observers (`on intersection`, `on mutation`, `on resize`), or for a name with a colon (htmx's own `htmx:*`, an extension's `sse:message`, a namespaced `contact:saved`) is never asked to be announced, and still pairs with a `.trigger()` or `triggers=` of that name; a name built in the template (`on {{ name }}`) is not read as a listener. An event a script in the templates names (a quoted name in a `<script>` or `hx-on`, such as `addEventListener('x', …)`, or a hyperscript `send` or `trigger`, even one inside a quoted string) counts for both sides, since the scan cannot tell whether the script listens or sends

**What happens.** checks `dj_hx.W024` (naming the view or the handler) and `W025` (naming template:line), through the pairing `hx_map` uses. Warnings, not Errors: a JavaScript file, a hyperscript file (`<script type="text/hyperscript" src=…>`), an Alpine listener (`@refreshed.window`, `x-on:refreshed.window`), a template in site-packages or a helper the view calls can be the other side, which a scan cannot see. Both skip when `ROOT_URLCONF` is unset
