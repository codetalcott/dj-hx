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

Nothing here depends on django-htmx. The difference is a stance, not htmx 4
support, which django-htmx has had since 1.28: django-htmx and djxi hand the
view `request.htmx.target` and `.source` and a setter for every response
header, and leave it to the view to use them well. dj-hx reads one request
header, offers no way to read the others, and makes each of htmx 4's silent
outcomes loud (see [Beside the alternatives](#beside-the-alternatives)). The
same design for Flask is [hx-flask]; the sibling for Fixi.js is [dj-fixi].

**Status:** 0.2.1 (2026-11-23), alpha, installed from its git tag; not on PyPI. Django 4.2, 5.2,
6.0 and 6.1; Python 3.10 to 3.13.

## Two checks for any Django project

Nothing in these two is htmx; they live here because this package is where they
were needed first. Both need only `"dj_hx"` in `INSTALLED_APPS`; `check` then
warns `dj_hx.W001` until `HxMiddleware` is listed, which a site with no htmx can
silence (`SILENCED_SYSTEM_CHECKS = ["dj_hx.W001"]`).

- **Every `{% url %}` reverses.** `manage.py check` reads every
  `{% url 'name' … %}` in the project's templates and reverses it with the
  arguments written there, against `ROOT_URLCONF` (check `dj_hx.E022`). A
  renamed route, a dropped argument or a wrong namespace fails `check`,
  `runserver` and `migrate` instead of a 500 on the page that has it. It reads
  every template, so one that nothing renders any more fails too.
- **Every template variable exists.** `HxTestClient` raises
  `HxUndefinedVariable` when a project template reads a name nobody supplies or
  an attribute an object lacks, in `{{ }}`, `{% if %}` and `{% for %}` alike,
  naming each template:line. It checks plain `client.get()` too, so a site
  without htmx can use it. pytest-django's `--fail-on-template-vars` sees the
  `{{ }}` form only (measured under Beside the alternatives).

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

```sh
pip install "dj-hx @ git+https://github.com/codetalcott/dj-hx@v0.2.1"
pip install "dj-hx[partials] @ git+https://github.com/codetalcott/dj-hx@v0.2.1"   # Django 4.2 to 5.x
```

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
removed(request)                                  # 200, empty; the control's hx-swap="delete" acts (beside a message, only delete or swapEmpty:true swaps it)
text(request, "(3 total)")                        # an escaped text fragment

response.trigger("contacts-changed")              # HX-Trigger, always JSON, always with a target (body)
response.partial("count")                         # appends <hx-partial hx-target="#count"> from the partial
response.push_url(url) / .replace_url(url) / .with_status(code)
```

A partial name containing a dot (`rows.html`) is a separate template file;
anything else is a `{% partialdef %}` of the page template. A partial used as
an `<hx-partial>` (`.partial("count")`, the messages partial) must have a root
element whose `id` is the partial's name; the render checks it.

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
<p _="on notified from body put 'A member was notified.' into me"></p>
{% partialdef notify inline %}
<div id="notify" hx-status:40x:inherited="swap:none" hx-status:5xx:inherited="swap:none">
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

The rules, each in a line; the whole of each, with what the checks read and what was measured, is
[INTERACTIONS.md](https://github.com/codetalcott/dj-hx/blob/main/INTERACTIONS.md#the-rules).

- **The route is minted from the handler**, `x/<app label>/<handler>/<param>/…/`, one segment per
  parameter after `request`, `<int:…>` for an `int` annotation; `route=` chooses the path instead.
- **Every route is named after its handler, in the `dj_hx` namespace.** `{% act 'notify' contest=…
  member=… %}` writes it, keyword arguments only, one per parameter; a wrong one raises at render.
- **Interactions live in an app's `interactions.py`**, which dj-hx's `ready()` imports, as admin
  imports each app's `admin`; one defined elsewhere is registered when `interactions.py` imports it.
- **The reply is always the partial**, rendered from `context` with the route's parameters and the
  handler's keys laid over it; a returned key `context` does not define raises. Every reply carries
  `error`, so the page's context defines `error: None` too.
- **One return type**, a `dict` or `None`; an `HttpResponse` raises. Leave the page from a plain view
  that returns `navigate()`.
- **A declared refusal is a 422** with `error=str(exc)` and no triggers; success is a 200 with
  `.trigger(name)` for each of `triggers`; any other method a 405. Under `ATOMIC_REQUESTS` a refusal
  commits what was written before the raise: raise first, or `transaction.set_rollback(True)`.
- **View decorators go above `@interaction`**, written with `functools.wraps`; the module holds what
  they return under the handler's name, never the raw handler.
- **`manage.py check` reads every `{% act %}` in the project's templates** and checks the control
  against its interaction: the method it sends, that it targets `#<partial name>` and swaps the outer
  element, that no `hx-select` reaches it, and that every interaction has a control and a partial
  whose root carries its id (`dj_hx.E009` to `E026`; the ids are in What is loud).

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

`hx-status:40x` and `hx-status:5xx` keep the controls on a 404, a 405 or a 500 while a 422 refusal
still swaps; the alert hears every other error and a request that got no reply, and hides itself when
the next request starts. Both are hyperscript, so that layout loads `_hyperscript` after htmx. Why each
line is written as it is, what htmx's global `noSwap` would do instead, and what was measured:
[INTERACTIONS.md](https://github.com/codetalcott/dj-hx/blob/main/INTERACTIONS.md#the-status-policy).

## What is loud

Every row of the design's silent-failure catalogue has a test in `tests/`, and a full
entry in [FAILURES.md](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md).
The verbs raise where the outcome is certain at call time; everything else is
recorded on `response.hx_findings`, logged to the `dj_hx` logger, and raised
by `HxTestClient`. Nothing is gated on `DEBUG` that a test needs.

| Failure | What happens | Full entry |
|---|---|---|
| A page answers a request that targets an element | `page()` raises `HxPageIntoFragment` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-page-answers-a-request-that-targets-an-element) |
| A fragment answers a boosted or body-targeted request | `fragment()` / `text()` record `HxFragmentIntoPage` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-fragment-answers-a-boosted-or-body-targeted-request) |
| A 3xx answers a partial request | `redirect()` raises; the guard records `HxRedirectIntoFragment`, `APPEND_SLASH`'s 301 and `login_required`'s 302 included; `navigate()` leaves the page | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-3xx-answers-a-partial-request) |
| A 204 answers a partial request | `HxNoSwap`: htmx 4 leaves the target untouched | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-204-answers-a-partial-request) |
| A response no verb built answers a partial request | `HxBareResponse` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-response-no-verb-built-answers-a-partial-request) |
| Messages added on a fragment with no messages template | `HxMessagesUnconfigured` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#messages-added-on-a-fragment-with-no-messages-template) |
| A partial's root element is not its name | `HxPartialRootId` at the render | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-partials-root-element-is-not-its-name) |
| partial names a partial the template does not define | `HxUnknownPartial`, listing the partials it does | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#partial-names-a-partial-the-template-does-not-define) |
| An htmx request without HX-Request-Type | `HxProtocolError`: raised under `DEBUG`; in production answered as the page and recorded | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-htmx-request-without-hx-request-type) |
| htmx 2 idioms in the HTML | the lint: on every test-client response, in the `DEBUG` log, in `manage.py hx_lint`, as check `dj_hx.W005` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#htmx-2-idioms-in-the-html) |
| A template reads a name nobody supplies | `HxTestClient` raises `HxUndefinedVariable`, naming each variable and template:line, `{% if %}` and `{% for %}` included | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-template-reads-a-name-nobody-supplies) |
| Logging disabled, so the undefined-variable check is blind | `HxTestClient` raises `ImproperlyConfigured`, naming which | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#logging-disabled-so-the-undefined-variable-check-is-blind) |
| A control points at a view of the other kind | `manage.py hx_map` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-control-points-at-a-view-of-the-other-kind) |
| A control points at a view that calls no verb, or a view retargets | `manage.py hx_map`, as warnings | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-control-points-at-a-view-that-calls-no-verb-or-a-view-retargets) |
| A control would keep what removed() empties | `manage.py hx_map`, as a warning: beside a message, htmx 4 swaps an empty reply only with `delete` or `swapEmpty:true` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-control-would-keep-what-removed-empties) |
| Middleware or settings misconfigured | checks `dj_hx.W001`, `E002`, `W003`, `W004`, `W006` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#middleware-or-settings-misconfigured) |
| HX_EXTENSIONS names an unknown extension | check `dj_hx.W008` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#hxextensions-names-an-unknown-extension) |
| The module holds the raw handler under its name | `ImproperlyConfigured` when the URLconf is first read; `dj_hx.W018` for a decorator without `functools.wraps` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#the-module-holds-the-raw-handler-under-its-name) |
| An interaction that cannot work | `ImproperlyConfigured` at import, naming the handler | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-interaction-that-cannot-work) |
| An interaction returns a response | `ImproperlyConfigured`: leave the page from a view that returns `navigate()` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-interaction-returns-a-response) |
| A refusal whose message is empty | `HxEmptyRefusal`, recorded on the 422 | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-refusal-whose-message-is-empty) |
| A reply sets a key its context does not define | `ImproperlyConfigured`, naming the key and the context function | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-reply-sets-a-key-its-context-does-not-define) |
| act with the wrong arguments, or an unknown interaction | `TemplateSyntaxError` at render; checks `dj_hx.E009`, `E010` at start-up | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#act-with-the-wrong-arguments-or-an-unknown-interaction) |
| An act control sends the wrong method, target or swap | checks `dj_hx.E011`, `E012`, `E013` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-act-control-sends-the-wrong-method-target-or-swap) |
| An hx-select reaches an act control | check `dj_hx.E026` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-hx-select-reaches-an-act-control) |
| An interaction with no control, or a partial that fails | checks `dj_hx.E014`, `E015`, `E016` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-interaction-with-no-control-or-a-partial-that-fails) |
| An interaction registered after dj_hx.urls was read | check `dj_hx.E017` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-interaction-registered-after-djhxurls-was-read) |
| Interactions registered but dj_hx.urls not included | check `dj_hx.E020`; `{% act %}` raises `ImproperlyConfigured` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#interactions-registered-but-djhxurls-not-included) |
| A decorator without functools.wraps, or below the interaction | checks `dj_hx.W018`, `W019` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-decorator-without-functoolswraps-or-below-the-interaction) |
| An act the checks cannot tie to a control | check `dj_hx.I021`, an Info | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-act-the-checks-cannot-tie-to-a-control) |
| A url tag that does not reverse | check `dj_hx.E022`; `I023` for a route it cannot reverse with a placeholder | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-url-tag-that-does-not-reverse) |
| An event nobody listens for, or nobody announces | checks `dj_hx.W024`, `W025` | [more](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#an-event-nobody-listens-for-or-nobody-announces) |

On an existing site the first `manage.py check` is a worklist, `dj_hx.E022` above all; [FAILURES.md](https://github.com/codetalcott/dj-hx/blob/main/FAILURES.md#a-url-tag-that-does-not-reverse) says how to work through it one id at a time. Its Errors stop `migrate` too, so a container that runs `migrate` before the server does not start until they are fixed: run `check` before the first deploy. A template nothing renders any more fails `E022` like a live one; delete it.

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
silence a rule). Recorded findings raise: the first, with every other finding
on that response listed in its message, so one run shows them all;
`HxTestClient(strict=False)` turns that off. A 3xx to a full request must be chosen with `follow=`, because
htmx's fetch follows it and the browser never sees it.

A project template that reads a name nobody supplies, or an attribute an
object lacks, raises `HxUndefinedVariable`, naming each one and its
template:line, `{% if %}` and `{% for %}` included, which `string_if_invalid`
never sees. A lookup whose outcome depends on the request's data is skipped (on
None, a key a mapping such as `request.GET`, or the session, lacks, an index
past the end of a sequence, `{% firstof %}`; the "What is loud" row has the whole list), so a
misspelt dict key stays silent, as in Django, and so does any lookup on a mapping
(`forloop.countr`, `request.GET.urlencod`). The client reads Django's
documented `django.template` DEBUG log in each request's own context, so an
`async def` view is checked and a render in a thread pool or a plain thread is
not. It lowers that logger to DEBUG for the request and passes on to the other
handlers only the records they received before, then puts the level back.
Put each name in the context the view renders with, with its default, or
give it one where it is read: a name its own expression gives a `|default`
(`{{ subtitle|default:"" }}`) is not counted, because the template says what to
show. `|default_if_none` is no default for a missing name, which is not None,
so `{{ x|default_if_none:"-" }}` renders `''` and counts.
`HxTestClient(undefined=False)` turns the check off.

The check rests on details of Django's that its documentation does not promise, which the suite
pins on Django 4.2, 5.2, 6.0 and 6.1: the DEBUG record's message and its `VariableDoesNotExist`,
the template node being rendered on the stack (for the template:line), and that exception's
`params`, `(bit, current)`. A Django release that changed the record or the node would make the
check go quiet, not fail; one that dropped `params` would make it count the lookups it now skips.
It raises by itself only when the logger is disabled.

## Tools

```
manage.py hx_lint [paths...] [--warnings-as-errors]   # template source, never site-packages
manage.py hx_map [--no-check] [--by-template]          # controls <-> views <-> events, checked
```

Neither runs Django's system checks first, so both work while `check` fails:
its `W005` hint sends you to `hx_lint` for the whole list.

`--by-template` reads the same map from the other end: every template and
partial a view names, the views that render it, and the controls that reach
them, for when you are editing a partial and need to know who serves it.

Site-packages, wherever dj-hx skips it (`hx_lint`, `hx_map`, the checks,
`ready()`), is sysconfig's `purelib` and `platlib` plus the `site-packages` and
`dist-packages` directories Python's `site` module reports, the user one that
`pip install --user` fills included.

`hx_map` classifies every control as full or partial by htmx 4's own rule
(the target is `body`, an `hx-select` reaches it, its own or an ancestor's
`hx-select:inherited`, or the element is boosted),
resolves it through `{% url %}`, `{% act %}` or the literal path, and checks it
against the verbs its view calls, with `if request.method == "DELETE":` branches
attributed to that method; a control whose view returns only JSON is an error,
since htmx swaps it in as text. A control with `hx-swap="none"` (its own or an
ancestor's `hx-swap:inherited`) is not checked for what its view answers: the
answer is put nowhere. Nor is one that reaches a view in site-packages, by
`{% url %}` or by path (allauth's `account_login`, `admin:index`): the map
lists the control and does not read that view. An `{% act %}` control resolves through the
interaction registry to its interaction, which answers its one method with its
partial (`fragment()`) and announces its `triggers=`; one naming no interaction,
or written while `dj_hx.urls` is not included, is an error. It also pairs `.trigger("x")` with
`hx-trigger="x from:body"` in both directions, and with a hyperscript listener
(`_="on x from body ..."`, or the same in an inline `<script type="text/hyperscript">`,
behaviors included); a listener for a browser event such as `click`, for a
hyperscript observer (`on intersection`, `on mutation`), or for a name with a
colon (`sse:message`, `contact:saved`) is never asked to be announced by a view,
and an event a script names (`addEventListener('x', …)`, a hyperscript `send x`)
is taken as heard and announced. Checks `dj_hx.W024` and `W025` report the same
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

## Beside the alternatives

Measured 2026-11-23: Django 6.1.3, Python 3.14.7, each library installed and
configured as its own README says (django-htmx 1.29.0: the app and
`HtmxMiddleware`; djxi 0.1.9: the app and `DjxiHeadersMiddleware`, with
`DX_HTMX_VERSION` at its default `"4"`), Django's test client sending
`HX-Request: true`, `HX-Request-Type: partial`, `HX-Target: div#rows`, and the
root logger captured at DEBUG. Only headers and bodies were inspected, not a
browser.

| A view that | django-htmx 1.29.0 | djxi 0.1.9 | dj-hx |
|---|---|---|---|
| answers a partial request with a 204 | goes out as is; nothing logged | same | `HxNoSwap` recorded, raised in tests |
| answers a partial request with a 302 | goes out as is; nothing logged | same | `redirect()` raises; the guard records any other 3xx |
| answers a partial request with `django.shortcuts.render` | the whole page goes out; nothing logged | same | `HxBareResponse` recorded |
| fires an event | `trigger_client_event(r, "x")` writes `{"x": {}}`, no target | `set_trigger("x")` writes `x`, no target | `.trigger()` always writes a target (why: measured under htmx 4 facts) |
| writes an htmx 2 header | `trigger_client_event(..., after="swap")` writes `HX-Trigger-After-Swap`, which htmx 4.0.2 does not read; the docs do not label it | no such helper | none offered |
| reads the target | `request.htmx.target`, `.source` | the same | not offered |

Neither library's docs say what htmx 4 does with a 204 or a 3xx. Both have
things dj-hx does not: django-htmx vendors htmx 2 and 4 and the htmx 4
extensions behind `{% htmx_script version=4 %}`, has `ptag`, Jinja support and
a setter for every response header, `HX-Location` included, which htmx 4.0.2
honours and which dj-hx leaves out on purpose (see what was rejected). djxi
bundles URLs, views and `<dx-section>` HTML in one class, and calls itself
pre-alpha.

Use django-htmx when you want a thin layer over the headers and will use
`HX-Location` or `HX-Retarget` deliberately, when you need Jinja, or when a
project is still on or moving from htmx 2. Use dj-hx when you want the server
to refuse, record or raise on what htmx 4 would do silently, and accept the
stance that comes with it.

For the undefined-variable check, the alternative is pytest-django's
`--fail-on-template-vars`. On pytest-django 4.14.0 with Django 6.1.3
(2026-11-23) it fails `{{ missing }}`, `{{ user.emial }}` and
`{{ missing|default:"" }}`, and passes `{% if missing %}` and
`{% for x in missing %}`: it works through `string_if_invalid`, which those
tags never consult. `HxTestClient` catches the four without a default, by
reading the `django.template` DEBUG record instead, and passes
`{{ missing|default:"" }}`, which renders what the template says.

## htmx 4 facts this depends on

All verified against `src/htmx.js` at tag v4.0.0; the line numbers are into
that file.

- `HX-Request-Type` is `full` when the target is the body or an `hx-select` reaches the element (its own or an ancestor's
  `hx-select:inherited`, read as `hx-target` is, L389), else `partial` (L578). The reply is cut down to what that selector
  finds in it before the swap (L1319).
- `hx-push-url="true"` pushes the URL after redirects (L1675), so a plain 303 updates the location bar.
- A `delete` swap runs regardless of response content (L1314) and honors `swap:1s`.
- `HX-Trigger` fires on the source element, or `document` if the swap removed it (L620, L1296); that is why `.trigger()` always sets a `target`. Measured in Chromium on 4.0.2 (`tests/test_interactions_browser.py`): after a `delete` swap, an event written without a target is dispatched on `document` and a `from body` listener never hears it; one with `target: body` is heard.
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
