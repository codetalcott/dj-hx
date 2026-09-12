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

It is the Django expression of the design worked out for Flask in [hx-flask],
built around three places where htmx 2 habits go wrong against htmx 4: a 204
no longer swaps, an event fired without a target lands where a `from:body`
listener cannot hear it, and django-htmx still writes headers htmx 4 removed.
The sibling for Fixi.js is [dj-fixi]. Nothing here depends on django-htmx.

**Status:** 0.1.0, unreleased. 103 tests plus 7 in Chromium, green on Django
4.2, 5.2 and 6.0 and Python 3.10 to 3.13. The name `dj-hx` was chosen because
`hx-django` is one letter from `django-htmx`, a real package with the opposite
stance.

## The three rules

1. **The handler owns every response-side decision** and says so through
   htmx 4's own protocol: `HX-Request-Type` in; `HX-Trigger`, `<hx-partial>`,
   422 and a plain 303 out.
2. **The HTML keeps the request-side controls and stays sufficient to predict
   the DOM effect.** Nothing here changes a target or a swap from a header, and
   nothing here reads `HX-Source` or `HX-Target`: the handler never learns an
   element id.
3. **One template per resource.** Fragments are `{% partialdef %}` regions of
   the page template, named in the handler, so page and fragment cannot drift.
   Django 6.0 has partials built in; on 4.2 to 5.x install
   `django-template-partials` and register its tags (see Install).

## Principles, stated so an agent can apply them

The three rules have working consequences. Each is a sentence to check code
against.

- **Never return `HttpResponseRedirect`, `HttpResponse("")` or a 204 to an
  htmx request.** Say what happened: `redirect`, `removed`, `text`.
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
- **Every control says `{% url %}`.** Then a control names the view that answers
  it, a search for the view finds every caller, and the trailing slash cannot
  drift from the route.
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
- **htmx 2 compatibility.** Without `HX-Request-Type` the page-or-fragment
  question is a guess.
- **Decorators that render a returned dict.** A view that sometimes returns a
  dict and sometimes a redirect has two return types, which is an agent trap.

`HxMixin` is here because Django's generic views are; the base-order failure
that made the Flask design refuse mixins is check `dj_hx.E007`.

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
                   render, page, fragment, invalid, redirect, removed, text)

render(request, "index.html", "rows", ctx)        # the page, or the partial, by request type
page(request, "show.html", ctx)                   # always the page; raises on a partial request
fragment(request, "archive_ui.html", context=ctx) # always a fragment; loud on a boosted request
invalid(request, "new.html", "form", ctx)         # render, status 422
redirect(request, "contacts", pk=3)               # a plain 303 (resolves like django.shortcuts.redirect); raises on a partial request
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

## What is loud

Every row of the design's silent-failure catalogue has a test in `tests/`.
The verbs raise where the outcome is certain at call time; everything else is
recorded on `response.hx_findings`, logged to the `dj_hx` logger, and raised
by `HxTestClient`. Nothing is gated on `DEBUG` that a test needs.

| Failure | What happens now |
|---|---|
| A page answers a request that targets an element | `page()` raises `HxPageIntoFragment` |
| A fragment answers a boosted or body-targeted request | `fragment()` / `text()` record `HxFragmentIntoPage` |
| Any 3xx answers a partial request, including `APPEND_SLASH`'s 301 | `redirect()` raises; the guard records `HxRedirectIntoFragment`, naming APPEND_SLASH when that is the cause |
| A 204 answers a partial request | `HxNoSwap`: htmx 4 leaves the target untouched |
| Messages added on a fragment with no messages template | `HxMessagesUnconfigured` |
| A partial used as `<hx-partial>` whose root is not `id="<name>"` | `HxPartialRootId` at the render |
| `partial=` names a partial the template does not define | `HxUnknownPartial`, listing the partials it does |
| An htmx request without `HX-Request-Type` | `HxProtocolError`: this needs htmx 4. `HX_REQUEST_TYPE_FALLBACK = "full"` answers with the page instead, for a proxy that strips the header; the guard still records it |
| htmx 2 idioms in the HTML: `hx-ext`, implicit inheritance, camelCase events, `show:#x:top` | the lint, on every test-client response, in the middleware log under `DEBUG`, in `manage.py hx_lint`, and as check `dj_hx.W005` |
| A partial control pointing at a page-only view, or a boosted link at a fragment-only one | `manage.py hx_map` |
| `HxMiddleware` missing, listed before `MessageMiddleware`, `HX_MESSAGES_TEMPLATE` unset or unresolvable, no partials on Django < 6, `HxMixin` after a Django base | checks `dj_hx.W001`, `E002`, `W003`, `W004`, `W006`, `E007` |

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

Every `text/html` response is linted (`HxLintError` on an error-level
finding, a warning otherwise; `lint_ignore=(...)` or `HX_LINT_IGNORE`
silence a rule). Recorded findings raise; `HxTestClient(strict=False)` turns
that off. A 3xx to a full request must be chosen with `follow=`, because
htmx's fetch follows it and the browser never sees it.

## Tools

```
manage.py hx_lint [paths...] [--warnings-as-errors]   # template source, never site-packages
manage.py hx_map [--no-check]                          # controls <-> views <-> events, checked
```

`hx_map` classifies every control as full or partial by htmx 4's own rule
(the target is `body`, `hx-select` is present, or the element is boosted),
resolves it through `{% url %}` or the literal path, and checks it against the
verbs its view calls, with `if request.method == "DELETE":` branches
attributed to that method. It also pairs `.trigger("x")` with
`hx-trigger="x from:body"` in both directions.

## The shared core

`dj_hx/hxlint.py` and `dj_hx/hx_vocab.py` are [hx-flask]'s, byte for byte
apart from one import line; the vocabulary is generated there from the htmx
4.0.0 source tree. `dj_hx/urlconf.py` is [dj-fixi]'s URLconf walk.
`tools/sync_shared.py` refreshes them and `tests/test_shared_core.py` pins
them. The map is split into `dj_hx/mapcore.py` (framework-neutral: template
scanning, the handler visitor, the checks) and `dj_hx/hxmap.py` (Django:
URLconf, `{% url %}`, `resolve()`), so hx-flask and a future `fixi_map` can
share the core with their own vocabulary and resolver.

## The example

`example/` is *Hypermedia Systems*' contact.app on the ORM: the same routes,
the same templates modulo `{% url %}` and `{% partialdef %}`, and the same
tests as hx-flask, for a like-for-like comparison.

```
cd example
python manage.py migrate && python manage.py seed_contacts
python manage.py runserver
```

```
.venv/bin/python -m pytest                 # 103 tests
.venv/bin/python -m pytest -m browser      # 7 more, in Chromium (pip install playwright; playwright install chromium)
python tools/sync_shared.py                # refresh the vendored core from hx-flask and dj-fixi
```

## htmx 4 facts this depends on

All verified against `src/htmx.js` at tag v4.0.0; the line numbers are into
that file.

- `HX-Request-Type` is `full` when the target is the body or `hx-select` is set, else `partial` (L578).
- `hx-push-url="true"` pushes the URL after redirects (L1675), so a plain 303 updates the location bar.
- A `delete` swap runs regardless of response content (L1314) and honors `swap:1s`.
- `HX-Trigger` fires on the source element, or `document` if the swap removed it (L620, L1296); that is why `.trigger()` always sets a `target`.
- Attributes reach descendants only with `:inherited`; `<body hx-boost="true">` boosts nothing (L285).
- `hx-delete` sends query parameters and excludes the enclosing form unless asked with `hx-include` (L476).
- Only 204 and 304 skip the swap (L202). A 422 body swaps with no client configuration.

## License

MIT

[hx-flask]: https://github.com/codetalcott/hx-flask
[dj-fixi]: https://github.com/codetalcott/dj-fixi
