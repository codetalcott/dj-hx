# dj-hx

Handler-first htmx 4 for Django. The view names the outcome; the template
keeps the controls; fragments are partials of the page template.

```python
from dj_hx import render, page, invalid, redirect, removed, wants_page

def contacts(request):
    return render(request, "index.html", "rows", {"contacts": Contact.all()})

def contacts_view(request, contact_id):
    contact = Contact.find(contact_id)
    if request.method == "DELETE":
        contact.delete()
        messages.success(request, "Deleted Contact!")
        if wants_page(request):          # the edit page's button targets the body
            return redirect(request, "contacts")
        return removed(request)          # a row's link says hx-swap="delete"
    return page(request, "show.html", {"contact": contact})
```

```django
<tbody>
{% partialdef rows inline %}
  {% for contact in contacts %}<tr>...</tr>{% endfor %}
{% endpartialdef %}
</tbody>
```

Nothing here depends on django-htmx, which was written for htmx 2: a 204 no
longer swaps, an event fired without a target lands where a `from:body`
listener cannot hear it, and the headers it still writes are gone. The same
design for Flask is [hx-flask]; the sibling for Fixi.js is [dj-fixi].

**Status:** 0.1.0, unreleased. Django 4.2, 5.2, 6.0 and 6.1; Python 3.10 to 3.13.

## The three rules

1. **The handler owns every response-side decision** and says so through
   htmx 4's own protocol: `HX-Request-Type` in; `HX-Trigger`, `<hx-partial>`,
   422 and a plain 303 out.
2. **The HTML keeps the request-side controls and stays sufficient to predict
   the DOM effect.** Nothing here changes a target or a swap from a header, and
   nothing here reads `HX-Source` or `HX-Target`: the handler never reads an
   element id from the request. The only ids it names are partial names, and
   the render checks each one.
3. **One template per resource.** Fragments are `{% partialdef %}` regions of
   the page template, or a file the page includes, named in the handler; either
   way page and fragment are one source and cannot drift.
   Django 6.0 has partials built in; on 4.2 to 5.x install
   `django-template-partials` and register its tags (see Install).

## Principles, stated so an agent can apply them

The three rules have working consequences. Each is a sentence to check code
against.

- **Never return `HttpResponseRedirect`, `HttpResponse("")`, a 204 or
  `django.shortcuts.render` to an htmx request.** Say what happened:
  `redirect`, `removed`, `text`, `render(request, template, partial)`, and
  `navigate` when the answer is another page whatever the control targets (a
  login check). A response no verb built that answers a partial request is
  recorded (`HxBareResponse`).
- **Never read `HX-Source` or `HX-Target`.** The real question is whether the
  client asked for a page or a fragment: `wants_page(request)`.
- **Announce facts; do not update regions.** Prefer `.trigger("contacts-changed")`
  with `hx-trigger="contacts-changed from:body"` on the element that cares, and
  `.partial()` only when the handler already holds the data. `.trigger()` always
  names a target, so the event lands whether or not the swap removed the element
  that asked.
- **The template predicts the DOM effect; the handler predicts the resource
  effect and the representation.** `.retarget()` and `.reswap()` exist and break
  the first half; use them with a comment saying why.
- **Every control says `{% url %}`, or `{% act %}` for an interaction.** Then a
  control names the view that answers it, a search for the view finds every
  caller, and the trailing slash cannot drift from the route.
- **Every name is literal.** `render(request, "index.html", "rows")` is matched
  by `{% partialdef rows %}` in that file; nothing is derived from a naming
  scheme. The one convention, a partial's root `id` equals its name, is checked
  at the render.

Silent failure, not API surface, is the friction, for people and agents alike.
Every row of the catalogue below lands on the first tier it can: delete the
dependency (there is no `source` or `target` to read; `.trigger()` cannot omit
a target), else fail at the first deterministic moment (the verbs raise, the
guard records, `HxTestClient` raises), else check statically (the lint, the
map, the system checks), else document.

What was rejected, and why:

- **Controls declared in Python**, an `hx_attrs(get=..., target=...)` helper or
  control objects beside the view. It hides what the search box does from a
  reader of `index.html`, it is a vocabulary agents have never seen, and it does
  not enforce the agreement it seems to promise. `hx_map` does, from the HTML
  people and agents already write.
- **Server-side retargeting as a default.** `HX-Retarget`, `HX-Reswap` and
  `HX-Location` make a control's DOM effect invisible from the template.
  `HX-Redirect` is not one of them: it replaces the page instead of changing
  what the control swaps, and `navigate` sends it only where a 303 would land
  inside the target.
- **htmx 2 compatibility.** Without `HX-Request-Type` the page-or-fragment
  question is a guess.
- **Decorators that render a returned dict, as first proposed.** A view that
  sometimes returns a dict and sometimes a redirect has two return types, which
  is an agent trap. `@interaction` (below) is that decorator, made safe by
  three rules: one return type, a dict of context keys or `None`, and anything
  else, a response included, raises; the reply is always the partial it
  declares, a refusal's 422 included; and leaving the page is a plain view's
  job, through `navigate()`. What it costs: one more concept beside the verbs,
  and routes minted for interactions (`x/<app label>/<handler>/…`) instead of
  written in the app's URLconf, served by one more include.

## Install

```python
INSTALLED_APPS = [..., "django.contrib.messages", "dj_hx", ...]

MIDDLEWARE = [
    ...,
    "django.contrib.messages.middleware.MessageMiddleware",
    "dj_hx.middleware.HxMiddleware",        # after MessageMiddleware
]

HX_MESSAGES_TEMPLATE = "layout.html#messages"   # optional; see the messages bridge
```

On Django 4.2 to 5.x, `{% partialdef %}` comes from django-template-partials,
which registers nothing globally. Install it, add it to `INSTALLED_APPS`, and
name its tag library as a builtin, or every template has to `{% load partials %}`:

```python
INSTALLED_APPS = ["template_partials", ..., "dj_hx", ...]

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "OPTIONS": {"builtins": ["template_partials.templatetags.partials"], ...},
}]
```

Django 6.0 needs none of that; `{% partialdef %}` is built in.

The layout loads htmx 4 and, because attributes reach descendants only with
`:inherited` in htmx 4, boosts and sends the CSRF header like this:

```django
<body hx-boost:inherited="true" hx-headers:inherited='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

## The vocabulary

```python
from dj_hx import (is_htmx, wants_page, wants_fragment,                 # HX-Request-Type, nothing else
                   render, page, fragment, invalid, redirect, navigate, removed, text)

render(request, "index.html", "rows", ctx)        # the page, or the partial, by request type
page(request, "show.html", ctx)                   # always the page; raises on a partial request
fragment(request, "archive_ui.html", context=ctx) # always a fragment; loud on a boosted request
invalid(request, "new.html", "form", ctx)         # render, status 422
redirect(request, "contacts", pk=3)               # a plain 303 (resolves like django.shortcuts.redirect); raises on a partial request
navigate(request, "login")                        # leave the page: a 303, or HX-Redirect on a partial request
removed(request)                                  # 200, empty; the control's hx-swap="delete" acts
text(request, "(3 total)")                        # an escaped text fragment

response.trigger("contacts-changed")              # HX-Trigger, always JSON, always with a target (body)
response.partial("count")                         # appends <hx-partial hx-target="#count"> from the partial
response.push_url(url) / .replace_url(url) / .with_status(code)
```

A partial name containing a dot (`rows.html`) is a separate template file;
anything else is a `{% partialdef %}` of the page template. A partial used as
an `<hx-partial>` (`.partial("count")`, the messages partial) must have a root
element whose `id` is the partial's name; the render checks it.

**Generic views.** `HxMixin` puts the verbs under Django's generic views,
overriding three hooks: `render_to_response` (negotiates on `partial`),
`form_invalid` (422) and `form_valid` (raises when Django's redirect would
answer a partial request). Put it first; check `dj_hx.E007` says so when it is
not.

```python
class ContactList(HxMixin, ListView):
    model = Contact
    template_name = "index.html"
    partial = "rows"
```

## The messages bridge

`messages.success(request, ...)` is stored for the next full page render, so
on a fragment response it would appear on some later page load. With
`HX_MESSAGES_TEMPLATE = "layout.html#messages"`, `HxMiddleware` renders pending
messages through that partial and appends them to fragment responses as
`<hx-partial hx-target="#messages" hx-swap="outerHTML">`. It peeks before it
consumes. The partial's root is `id="messages"` and it iterates `messages`:

```django
{% partialdef messages inline %}
<div id="messages">{% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}</div>
{% endpartialdef %}
```

## Interactions

An interaction is a handler bound to one partial. It returns the context keys it changed, and the
reply is always that partial, rendered from the same context function the page uses.

```python
from dj_hx import interaction, page

def assign_context(request, contest):            # the page's context, and every reply's
    return {"contest": Contest.get(contest), "notified": False, "error": None}

def assign(request, contest):                    # the page is a plain view
    return page(request, "contests/assign.html", assign_context(request, contest))

@interaction("POST", partial="contests/assign.html#notify", context=assign_context,
             refuses=(DomainError,), triggers=("notified",))
def notify(request, contest: str, member: int):
    Contest.get(contest).notify(member)          # a DomainError raised here becomes the reply's error
    return {"notified": True}
```

```django
{% load hx %}
{% partialdef notify inline %}
<div id="notify">
  {% for member in contest.members %}
    <button hx-post="{% act 'notify' contest=contest.slug member=member.id %}"
            hx-target="#notify" hx-swap="outerHTML">Notify {{ member }}</button>
  {% endfor %}
  {% if notified %}<p>Notified.</p>{% endif %}
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
</div>
{% endpartialdef %}
```

One URLconf serves every interaction. Include it once, at the site root:

```python
urlpatterns = [
    ...,
    path("", include("dj_hx.urls")),
]
```

The rules:

- **The route is minted from the handler:** `x/<app label>/<handler>/<param>/.../`, one segment
  per parameter after `request`. An `int` annotation gives `<int:member>`; anything else gives
  `<str:contest>`. In an app labelled `contests`, `notify` above is
  `/x/contests/notify/<str:contest>/<int:member>/`. The app label comes from the installed app that
  contains the handler's module.
- **`route="reviewers/<int:member>/notify"` chooses the path instead.** It is used as given, so it
  is relative to where `dj_hx.urls` is included. It must name exactly the handler's parameters, with
  `<int:...>` for each one annotated `int`.
- **Every route is named after its handler, in the `dj_hx` namespace**, so two interactions cannot
  share a name.
- **`{% act %}` takes keyword arguments only**, one for each parameter of the handler
  (`{% load hx %}`). A positional argument, a name the handler does not take, or a missing one
  raises `TemplateSyntaxError` at render, naming the parameters. Without `dj_hx.urls` included it
  raises `ImproperlyConfigured`, naming the include.
- **Interactions live in an app's `views.py`.** dj-hx's `ready()` imports the `views` module of
  every installed app outside site-packages, so every route exists before the URLconf is read. An
  interaction defined anywhere else has to be imported before then, and one in a pip-installed app
  is not registered until something imports its views. One registered after the URLconf was read
  is routed to its view alone, without the view decorators above it; check `dj_hx.E017` says so.
- **The reply is always the partial**, through `fragment()`. `context` is called on every reply
  with the route parameters it names, and the handler's keys are laid over it. A parameter of
  `context` that the route lacks takes its default; one without a default, or `*args` or
  `**kwargs`, raises at import. A key the handler returns must already be in the context: define
  each there with its default (`notified: False`), so the page renders the same names as the reply.
- **Every reply carries `error`:** `str(exc)` on a refusal, and `None` on success unless `context`
  or the handler sets it, so the partial can read `{% if error %}` whatever `context` defines. The
  page is a plain view, not a reply, so a page that renders the partial needs `error` in its own
  context, as `assign_context` above has it; otherwise `HxTestClient` raises
  `HxUndefinedVariable` on the page.
- **One return type:** a `dict` or `None`. Anything else, an `HttpResponse` included, raises. An
  interaction always re-renders its partial; to leave the page, write a view that returns
  `navigate()`. A view decorator written below `@interaction` that answers with a response, such
  as `@login_required` redirecting, raises the same way.
- **A declared refusal is a 422.** An exception listed in `refuses` re-renders the partial with
  `error=str(exc)` and status 422, which htmx 4 swaps, and sends no triggers. The handler writes no
  `try`. Any other exception is a 500.
  - The message is what the user reads. One that is empty or blank (`raise NotOnRota()`) leaves
    `{% if error %}` nothing to show, so the click seems to do nothing; the reply still goes out, and
    `HxEmptyRefusal` is recorded on it, which `HxTestClient` raises.
  - A refusal is a response, not an exception Django sees, so under `ATOMIC_REQUESTS` the writes the
    handler made before raising are committed. Raise before writing; or call
    `transaction.set_rollback(True)` before the raise, which rolls the request's block back as the
    422 goes out; or write inside `with transaction.atomic():` and raise inside it, which rolls that
    block back with or without `ATOMIC_REQUESTS`.
- **Success is a 200**, with `.trigger(name)` for each name in `triggers`.
- **Any other method gets a 405** with `Allow`. The guard records nothing for it.
- **The partial's root element carries `id="<partial name>"`**, checked on every reply, so the
  element `hx-swap="outerHTML"` puts back keeps the id the next request targets.
- **View decorators go above `@interaction`, and the module holds what it returned.**
  `@interaction` returns the routed view, and `dj_hx.urls` routes each interaction to whatever the
  module that defines the handler holds under the handler's name, as written:
  - `@login_required` above it wraps the route, as on any Django view, and so does a hand-written
    check. Write your own with `functools.wraps`, as Django's are, so dj-hx's messages and `hx_map`
    name the handler rather than the decorator's inner function. Check `dj_hx.W018` warns on one
    written without it, because nothing can then see that it wraps the interaction. A decorator
    below `@interaction` gets `dj_hx.W019`.
  - That name must hold the view `@interaction` returned, or a decorator of it, and never the raw
    handler. The call form `remind_view = interaction(...)(remind)` leaves `remind` itself there,
    which would skip the method guard, so reading the URLconf raises `ImproperlyConfigured`. Write
    `remind = interaction(...)(remind)`, in the module that defines `remind`; the handler stays
    reachable as `inspect.unwrap(remind)`. A decorator of the raw handler raises the same way only
    when it is written with `functools.wraps`; one written without it is routed as it is, past the
    method guard, and only `dj_hx.W018` warns.
  - An interaction its module does not hold under its name, or holds as something not callable,
    such as one defined inside a function, is routed to the bare view, and any decorator applied to
    it is dropped.
  - A signed-out request to a `@login_required` interaction gets its 302. On a control that targets
    an element the guard records that 302 (`HxRedirectIntoFragment`), as it does for any view,
    because fetch would follow it into the target.
  - Every interaction is routed by the root `include("dj_hx.urls")`, not under its app's own
    include, so protection attached to that include, such as `decorator_include` or a middleware
    that checks the app's URL prefix, never reaches it. A decorator above `@interaction` does, and
    so does middleware that sees every request, such as Django 5.1's `LoginRequiredMiddleware`.
- **`manage.py check` reads every `{% act %}` in the project's templates**, as `hx_lint` does,
  never site-packages, and checks the control it writes the URL of against its interaction, as
  htmx 4.0.2 resolves each attribute:
  - The control sends the interaction's method. `hx-post` and its siblings name it; `hx-action`
    sends its own `hx-method`, else an ancestor's `hx-method:inherited`, else its `method`
    attribute (`<form method="post">`, measured), else GET. A submit button's `formmethod` is
    chosen at click time and is not read.
  - It targets the element with the partial's id: `hx-target="#<partial name>"`, or no
    `hx-target` on a control that carries the id itself, or `hx-target="this"` on the element
    that carries it (htmx 4 resolves `this` to the element declaring it; both measured, the second
    as click-to-edit's `hx-target:inherited="this"` on the partial's root). An extended selector
    whose CSS part is `#<partial name>` counts too: `closest`, `find`, `findAll`, `next` or
    `previous #<partial name>`, with or without `global `, as htmx 4.0.2's target resolver reads
    them, each reaching that element or nothing (`closest` measured). A comma list, a bare `next`
    or `previous`, `document`, `window`, `body`, `host` and any other CSS stay Errors.
  - Its `hx-swap` is an outer swap (`outerHTML`, `outerMorph` or `outerSync`, which each leave one
    element with the id, as read in htmx 4.0.2's swap code and measured). Without `hx-swap`, htmx 4
    swaps `innerHTML` and nests a second element with the partial's id inside the first, as
    `beforeend`, `afterbegin`, `beforebegin` and `afterend` leave a second one beside it or inside
    it; on `innerMorph` htmx 4.0.2 throws (`HierarchyRequestError`, logged as `htmx:error`) and the
    reply never reaches the page.
  - Each attribute is the control's own or an ancestor's `:inherited` one; a plain attribute on an
    ancestor does not reach it in htmx 4.

  It also checks that every interaction has an `{% act %}` control (a `{% url 'dj_hx:…' %}` or
  hand-written path is not counted, because its control cannot be checked), and that its partial
  loads and starts with its id. A computed `hx-swap` or `hx-method` is not judged. A templated id or
  `hx-target` is judged by its literal parts, and skipped only when it could equal the expected
  value: `id="{{ name }}"` and `hx-target="#{{ name }}"` are skipped, while `id="row-{{ pk }}"` and
  `hx-target="#row-{{ pk }}"` cannot be `notify` and are Errors. A block tag in an id, and what
  it wraps, is computed too, since it may not render: `id="{% if p %}{{ p }}-{% endif %}notify"` is
  skipped, `id="{% if p %}{{ p }}-{% endif %}row"` is an Error. An `{% act %}` it cannot tie to
  one element's verb attribute gets an Info (`dj_hx.I021`) saying so. The ids are in "What is loud" below.

  "Measured" means in Chromium, on htmx 4.0.2, by `tests/test_interactions_browser.py`, against a
  page whose controls pass every check (`tests/desk`).

### The status policy

htmx 4 swaps every status but 204 and 304. A 405 from a control that sends the wrong method, a 404
for an object removed since the page was drawn, or a 500 replaces the region with the error's body,
and the controls are gone (measured for each). So the root element of each interaction's partial
says not to swap those, and the layout carries one alert:

```django
{% partialdef notify inline %}
<div id="notify" hx-status:40x:inherited="swap:none" hx-status:5xx:inherited="swap:none">
  ...
```

```django
<body hx-boost:inherited="true" hx-headers:inherited='{"X-CSRFToken": "{{ csrf_token }}"}'>
  <p id="trouble" role="alert" style="display: none"
     _="on htmx:before:request from body hide me end
        on htmx:error from body show me end
        on htmx:response:error from body if event.detail.ctx.response.status is not 422 show me">Something went wrong. Please try again.</p>
```

- **`hx-status:40x` and `hx-status:5xx`** keep the controls on a 404, a 405 or a 500, while a 422
  refusal still swaps (each measured). htmx 4.0.2 tries the status, then its first two digits and
  `x`, then its first digit and `xx`, and takes the first `hx-status:<code>` the control has or
  inherits, so `40x` covers 400 to 409 and `5xx` every 5xx; a 410, 413 or 429 still swaps (read from
  that code, not measured). `swap:none` is what htmx's own `noSwap` sets.
- **On the partial's root, with `:inherited`,** the pair reaches every control inside the partial
  (measured), and the root itself where the root is the control (read from htmx 4.0.2's attribute
  reader, not measured). It is part of the partial, so every reply carries it back. A control
  outside the partial that targets it does not inherit it: write the pair on that control,
  `hx-status:40x="swap:none" hx-status:5xx="swap:none"` (read from the same code, not measured).
- **Not htmx's global `noSwap`.** `<meta name="htmx-config" content='{"noSwap": [204, 304, "40x",
  "5xx"]}'>` keeps the controls too, but htmx 4.0.2 applies it to every htmx request on the page,
  boosted links and forms included, and checks it before any `hx-status`, so no element can opt
  back in (read from that code). A boosted link to a page that answers 404 then leaves the old page
  in place under the new URL (measured); under the scoped pair the same link shows the 404 page
  (measured).
- **One generic listener**, written once in the layout, says something went wrong.
  `htmx:response:error` fires for every status of 400 or above, a refusal's 422 included, so it
  leaves 422 to the partial's own `{% if error %}`. A request that gets no reply (the server down, a
  timeout) has no status: htmx 4.0.2 fires `htmx:error` instead, as it does when a swap throws, so
  the alert hears that too (measured with a request failed at the network, and with `innerMorph`'s throw). It
  hides itself again when the next request starts.
- **Hidden with `style="display: none"`, never the `hidden` attribute.** Hyperscript's `show`
  clears only an inline `display`, so an alert hidden with `hidden` never appears (measured).
- **A fact an interaction announces in `triggers=`** reaches the regions that care through a
  listener, `_="on notified from body ..."` in hyperscript or `hx-trigger="notified from:body"`,
  and the listener runs after the reply, never while it is pending (measured, holding the request
  for 1.2 s).

The alert and the `_=` listener are hyperscript, so that layout loads `_hyperscript` after htmx.

## What is loud

Every row of the design's silent-failure catalogue has a test in `tests/`.
The verbs raise where the outcome is certain at call time; everything else is
recorded on `response.hx_findings`, logged to the `dj_hx` logger, and raised
by `HxTestClient`. Nothing is gated on `DEBUG` that a test needs.

| Failure | What happens now |
|---|---|
| A page answers a request that targets an element | `page()` raises `HxPageIntoFragment` |
| A fragment answers a boosted or body-targeted request | `fragment()` / `text()` record `HxFragmentIntoPage` |
| Any 3xx answers a partial request, including `APPEND_SLASH`'s 301 and `login_required`'s 302 | `redirect()` raises; the guard records `HxRedirectIntoFragment`, naming APPEND_SLASH when that is the cause, and `navigate()` for leaving the page |
| A 204 answers a partial request | `HxNoSwap`: htmx 4 leaves the target untouched |
| A response no verb built answers a partial request | `HxBareResponse`: `django.shortcuts.render`, a plain `HttpResponse` or a `TemplateResponse` cannot be checked, and Django's `render` sends the whole page |
| Messages added on a fragment with no messages template | `HxMessagesUnconfigured` |
| A partial used as `<hx-partial>`, or an interaction's reply, whose root is not `id="<name>"` | `HxPartialRootId` at the render |
| `partial=` names a partial the template does not define | `HxUnknownPartial`, listing the partials it does |
| An htmx request without `HX-Request-Type` | `HxProtocolError`: this needs htmx 4. `HX_REQUEST_TYPE_FALLBACK = "full"` answers with the page instead, for a proxy that strips the header; the guard still records it |
| htmx 2 idioms in the HTML: `hx-ext`, implicit inheritance, htmx 2 event names in `hx-on` or `hx-trigger`, camelCase or kebab-case (`hx-on::after-request`), `show:#x:top` | the lint, on every test-client response, in the middleware log under `DEBUG`, in `manage.py hx_lint`, and as check `dj_hx.W005` |
| A project template reads a name nobody supplies (`{{ x }}`, `{% if x %}`, `{% for i in x %}`, `{{ x\|default:"" }}`, since Django logs the lookup before the filter runs, or a name an `{% include %}` does not pass) or an attribute an object lacks (`{{ user.emial }}`, `{{ items.length }}`). Django renders each as nothing, without a word, and `string_if_invalid` never sees the ones `{% if %}` and `{% for %}` read | `HxTestClient` raises `HxUndefinedVariable` on the request, naming each variable and the template:line it is written in (the base of an `{% extends %}`, the included file, the file a partial is in), and for a name an included template reads, says to pass it in the include's `with` (`… subtitle=None`). It reads Django's `django.template` DEBUG log while the request runs; `strict=False` records it on `response.hx_findings`, and `undefined=False` turns it off. Skipped, because the outcome depends on the request's data: a lookup on None (`{{ obj.rel.name }}` with no `rel`), a key a mapping or the session lacks (`{% if not request.GET.stage %}`, `{% if request.session.cart %}`), an index past the end of a sequence (`items.0` on `[]`), whatever `{% firstof %}` reads, `debug` and `sql_queries` where the debug context processor is configured (it sets them only under `DEBUG`), and a response Django built from an exception (its 500 page). The cost: a misspelt dict key or index is silent, as it is in Django today. Not seen either: a template in site-packages (Django's, admin's, any pip-installed app's), one built from a string, which has no file (Django's `DEBUG` error pages are), a lookup that raised an exception Django silences (a missing related object's `DoesNotExist`), and a render outside the request's own context: in a `ThreadPoolExecutor` or a plain thread, or a streaming response consumed after the request returns. An `async def` view is checked |
| `logging.disable()` is in force, or the `django.template` logger is disabled (a `LOGGING` dict that leaves `disable_existing_loggers` at its default, `True`, disables it), so Django writes no record for the undefined-variable check to read | `HxTestClient` raises `ImproperlyConfigured` on the request, naming which; `undefined=False` goes without the check |
| A partial control pointing at a page-only view, or a boosted link at a fragment-only one (an interaction is fragment-only) | `manage.py hx_map` |
| A control pointing at a view that calls no verb; a view that calls `.retarget()` or `.reswap()` | `manage.py hx_map`, as warnings |
| `HxMiddleware` missing, listed before `MessageMiddleware`, `HX_MESSAGES_TEMPLATE` unset or unresolvable, no partials on Django < 6, `HxMixin` after a Django base | checks `dj_hx.W001`, `E002`, `W003`, `W004`, `W006`, `E007` |
| `HX_EXTENSIONS` names an extension htmx 4 does not ship, or is a string | check `dj_hx.W008`; htmx's registered name (`sse`) and the file name (`hx-sse`) both count |
| The module that defines the handler holds the raw handler under its name (`remind_view = interaction(...)(remind)`, or `remind = interaction(...)(handlers.remind)` in another module), or a decorator of it written with `functools.wraps`, so its route would skip the method guard | `ImproperlyConfigured` when the URLconf is first read (the first request, or `manage.py check`), naming the module attribute and the fix. A decorator of the raw handler written without `functools.wraps` is routed as it is, past the method guard: only check `dj_hx.W018` warns |
| An `@interaction` that cannot work: two with one name, a minted route for a handler in no installed app, `route=` parameters that are not the handler's (or `<str:...>` for one annotated `int`), a `partial=` that is not `page.html#name`, `triggers=` given as a string, a `method` that is not GET, POST, PUT, PATCH or DELETE, a `refuses` holding anything but exception classes (`refuses=("DomainError",)`), a handler or a `context=` taking `*args` or `**kwargs`, a `context=` parameter without a default that the route does not have | `ImproperlyConfigured` when the views module is imported, so at start-up, naming the handler |
| An interaction returns anything but a `dict` or `None`, an `HttpResponse` included, or a view decorator below `@interaction` answers with one | `ImproperlyConfigured`: an interaction always re-renders its partial; leave the page from a view that returns `navigate()`, and put Django view decorators above `@interaction` |
| A declared refusal whose message is empty or blank (`raise NotOnRota()`), so the 422 reply's `{% if error %}` shows nothing and the click seems to do nothing | `HxEmptyRefusal`, recorded on the 422, which still goes out: logged, and raised by `HxTestClient`, naming the handler and the exception to give a message |
| An interaction's reply sets a key its context does not define | `ImproperlyConfigured`, naming the key and the context function: define each there with its default. `error` is always defined, because every reply carries it |
| `{% act %}` with a positional argument, a keyword the handler does not take, a missing one, or a name no interaction has | `TemplateSyntaxError` at render, naming the handler's parameters, or listing the interactions there are; at start-up, checks `dj_hx.E009` (no such interaction) and `E010` (the arguments), naming template:line |
| An `{% act %}` control that sends another method than its interaction answers (for `hx-action`: its `hx-method`, an ancestor's `hx-method:inherited`, its `method` attribute, else GET; a submit button's `formmethod` is not read), that does not target the element with id `<partial name>` (`hx-target="#<partial name>"`, its own or an ancestor's `hx-target:inherited`, or an htmx 4.0.2 extended selector whose CSS part is that, such as `closest #<partial name>`; or no `hx-target`, or `hx-target="this"`, on the element with that id), or whose `hx-swap` (its own or inherited) is not an outer swap (`outerHTML`, `outerMorph` or `outerSync`, read from htmx 4.0.2's swap code and measured in Chromium) | checks `dj_hx.E011`, `E012` and `E013`, naming template:line and the attribute to write; a plain `hx-target` or `hx-swap` on an ancestor is named as not reaching the control. E013 says what the swap does instead: two elements with the id (`innerHTML`, `beforeend`, `afterbegin`, `beforebegin`, `afterend`), or, for `innerMorph`, an htmx 4.0.2 `HierarchyRequestError` (logged as `htmx:error`), so the reply never reaches the page |
| An interaction no project template writes an `{% act %}` for (a `{% url 'dj_hx:…' %}` or hand-written path is not counted: E011 to E013 cannot check it), whose partial does not load, or whose partial's root element is not `id="<partial name>"` | checks `dj_hx.E014`, `E015` (with `HxUnknownPartial`'s reason) and `E016` (the start-up twin of `HxPartialRootId`, judged where the source shows the root). E014 skips an interaction whose handler's module is in site-packages: its controls are in that app's templates, which are never read |
| An interaction registered after `dj_hx.urls` was first read, so its route is the bare view and the decorators above it do not apply | check `dj_hx.E017`, naming the module to import before the URLconf is loaded |
| Interactions registered, but `dj_hx.urls` not included | check `dj_hx.E020`; `{% act %}` raises `ImproperlyConfigured`; both name `path("", include("dj_hx.urls"))` |
| A decorator above `@interaction` written without `functools.wraps`, so nothing can see that it wraps the interaction; a decorator below `@interaction` (the handler has `__wrapped__`) | checks `dj_hx.W018` (use `functools.wraps`) and `W019` (view decorators belong above `@interaction`) |
| An `{% act %}` the checks cannot tie to one element's verb attribute: in a `<script>` or text, in another attribute, stored with `as`, or naming its interaction with a variable | check `dj_hx.I021`, an Info naming template:line; a quoted name and its keywords are still checked. `assert_no_hx_check_issues()` counts it, so silence it by id where it is deliberate |
| A `{% url 'name' … %}` in a project's `.html` or `.htm` template that does not reverse: a name no pattern has (close names are listed), a namespace no URLconf installs, positional arguments or keywords the route does not take, or both kinds mixed | check `dj_hx.E022`, naming template:line and the route the name has. Each argument is reversed with a placeholder for the converter its route declares (`int` 1; `str`, `slug` and `path` "a"; `uuid` all zeros), and a keyword that names one of a route's extra kwargs (`path("feed.atom", view, {"fmt": "atom"})`) with that default, so a route with a custom converter or a `re_path` group is not checked: Info `dj_hx.I023` names it. `{% url … as var %}` is skipped, as Django's documented form for a view that may be missing (admin's own templates use it), and so are a name built at run time (a variable, a filter on it) and a tag in a comment or `{% verbatim %}`. It reverses against `ROOT_URLCONF` only: a site that sets `request.urlconf` per request silences it |
| An event a view announces with `.trigger()` (as `hx_map` finds it) or an interaction declares in `triggers=` that no project template listens for (`hx-trigger`, `hx-on`, a hyperscript `on` in an `_`, `script` or `data-script` attribute or in a `<script type="text/hyperscript">`, behaviors included); an event a template listens for that nothing announces. A listener for a browser event, or for one of hyperscript's observers (`on intersection`, `on mutation`, `on resize`), is never asked to be announced; a name with a colon (htmx's own `htmx:*`, an extension's `sse:message`) or one built in the template (`on {{ name }}`) is not read as a listener, so a view that announces a colon name gets W024. An event a script in the templates names (a quoted name in a `<script>` or `hx-on`, such as `addEventListener('x', …)`, or a hyperscript `send` or `trigger`, even one inside a quoted string) counts for both sides, since the scan cannot tell whether the script listens or sends | checks `dj_hx.W024` (naming the view or the handler) and `W025` (naming template:line), through the pairing `hx_map` uses. Warnings, not Errors: a JavaScript file, a template in site-packages or a helper the view calls can be the other side, which a scan cannot see |

On an existing site the first `manage.py check` is a worklist, `dj_hx.E022` above all, since it
reads every `{% url %}` in the project's `.html` and `.htm` templates. An Error fails `manage.py
check`, keeps `runserver` from starting, and aborts `migrate`, `makemigrations`, `createsuperuser` and
`manage.py test`, which all run the checks. While you work through the list,
`SILENCED_SYSTEM_CHECKS = ["dj_hx.E022"]` silences one id, Errors included; take it out again to check
the rest. E022 reverses against `ROOT_URLCONF` only, so a site that routes some requests through
another URLconf (`request.urlconf`, as django-hosts sets it) silences it.

## Testing

```python
from dj_hx.testing import HxTestClient, assert_no_hx_check_issues

client = HxTestClient()
client.hx_get("/contacts/")                    # HX-Request: true, HX-Request-Type: partial
client.hx_delete("/contacts/3/", full=True, follow=False)   # a body-targeted control; 303 stays a 303
client.hx_post("/contacts/new/", form, full=True, follow=True)  # what the browser shows after the 303

def test_dj_hx_is_configured():
    assert_no_hx_check_issues()               # pytest does not run system checks
```

`assert_no_hx_check_issues()` fails on any dj-hx check message, Infos included (`dj_hx.I021`, a
control the checks could not tie to its interaction; `dj_hx.I023`, a `{% url %}` they could not
reverse with a placeholder); `include_warnings=False` keeps Errors only, and `SILENCED_SYSTEM_CHECKS`
silences one id.

Every `text/html` response is linted (`HxLintError` on an error-level
finding, a warning otherwise; `lint_ignore=(...)` or `HX_LINT_IGNORE`
silence a rule). Recorded findings raise; `HxTestClient(strict=False)` turns
that off. A 3xx to a full request must be chosen with `follow=`, because
htmx's fetch follows it and the browser never sees it.

A project template that reads a name nobody supplies, or an attribute an
object lacks, raises `HxUndefinedVariable`, naming each one and its
template:line, `{% if %}` and `{% for %}` included, which `string_if_invalid`
never sees. A lookup whose outcome depends on the request's data is skipped (on
None, a key a mapping such as `request.GET`, or the session, lacks, an index
past the end of a sequence, `{% firstof %}`; the "What is loud" row has the whole list), so a
misspelt dict key stays silent, as in Django. The client reads Django's
documented `django.template` DEBUG log in each request's own context, so an
`async def` view is checked and a render in a thread pool or a plain thread is
not. It lowers that logger to DEBUG for the request and passes on to the other
handlers only the records they received before, then puts the level back.
Put each name in the context the view renders with, with its default; a
`|default` filter does not count, because Django logs the lookup before the
filter runs. `HxTestClient(undefined=False)` turns the check off.

## Tools

```
manage.py hx_lint [paths...] [--warnings-as-errors]   # template source, never site-packages
manage.py hx_map [--no-check] [--by-template]          # controls <-> views <-> events, checked
```

`--by-template` reads the same map from the other end: every template and
partial a view names, the views that render it, and the controls that reach
them, for when you are editing a partial and need to know who serves it.

Site-packages, wherever dj-hx skips it (`hx_lint`, `hx_map`, the checks,
`ready()`), is sysconfig's `purelib` and `platlib` plus the `site-packages` and
`dist-packages` directories Python's `site` module reports, the user one that
`pip install --user` fills included.

`hx_map` classifies every control as full or partial by htmx 4's own rule
(the target is `body`, `hx-select` is present, or the element is boosted),
resolves it through `{% url %}`, `{% act %}` or the literal path, and checks it
against the verbs its view calls, with `if request.method == "DELETE":` branches
attributed to that method. An `{% act %}` control resolves through the
interaction registry to its interaction, which answers its one method with its
partial (`fragment()`) and announces its `triggers=`; one naming no interaction,
or written while `dj_hx.urls` is not included, is an error. It also pairs `.trigger("x")` with
`hx-trigger="x from:body"` in both directions, and with a hyperscript listener
(`_="on x from body ..."`, or the same in a `<script type="text/hyperscript">`,
behaviors included); a listener for a browser event such as `click`, or for a
hyperscript observer (`on intersection`, `on mutation`), is never asked to be
announced by a view, a name with a colon (`sse:message`) is not read as a
listener, and an event a script names (`addEventListener('x', …)`, a hyperscript
`send x`) is taken as heard and announced. Checks `dj_hx.W024` and `W025` report the same
pairing at start-up.

## The example

`example/` is *Hypermedia Systems*' contact.app on the ORM, with the book's
routes and templates.

```
cd example
python manage.py migrate && python manage.py seed_contacts
python manage.py runserver
```

```
python -m pytest                 # the suite
python -m pytest -m browser      # in Chromium (pip install playwright; playwright install chromium)
```

The browser tests also drive `tests/desk`, one page of interactions on htmx
4.0.2 and _hyperscript 0.9.94 (vendored, with their npm sources and sha256
beside them), which passes every check. The status policy is measured there,
and so are six of the forms checks E011 to E013 accept: `outerMorph`,
`outerSync`, a self-replacing control, click-to-edit's inherited `this`,
`closest #<partial>` and `<form method="post" hx-action>`. The others they
accept (`find`, `findAll`, `next`, `previous` and `global` selectors, an
ancestor's `hx-target:inherited="#x"`, `hx-method` and `hx-method:inherited`,
swap modifiers) are accepted from htmx 4.0.2's source, not measured.

## htmx 4 facts this depends on

All verified against `src/htmx.js` at tag v4.0.0; the line numbers are into
that file.

- `HX-Request-Type` is `full` when the target is the body or `hx-select` is set, else `partial` (L578).
- `hx-push-url="true"` pushes the URL after redirects (L1675), so a plain 303 updates the location bar.
- A `delete` swap runs regardless of response content (L1314) and honors `swap:1s`.
- `HX-Trigger` fires on the source element, or `document` if the swap removed it (L620, L1296); that is why `.trigger()` always sets a `target`.
- Attributes reach descendants only with `:inherited`; `<body hx-boost="true">` boosts nothing (L285).
- `hx-delete` sends query parameters and excludes the enclosing form unless asked with `hx-include` (L476).
- Only 204 and 304 skip the swap (L202). A 422 body swaps with no client configuration, and so do a
  404, a 405 and a 5xx, which is why interactions want the status policy.

The interaction layer's status policy is measured on htmx 4.0.2 in Chromium
instead, by `tests/test_interactions_browser.py`, and so are the six control
forms named under The example; the other forms checks E011 to E013 accept are
read from htmx 4.0.2's source.

## License

MIT

[hx-flask]: https://github.com/codetalcott/hx-flask
[dj-fixi]: https://github.com/codetalcott/dj-fixi
