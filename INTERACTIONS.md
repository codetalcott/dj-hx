# Interactions, in full

README's [Interactions](README.md#interactions) section shows one interaction and states each rule in a line. This
file is the whole of each rule: what the layer does, what `manage.py check` reads to judge a control, and which
of it was measured in Chromium on htmx 4.0.2 (`tests/test_interactions_browser.py`, against `tests/desk`).

## The rules

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
- **Interactions live in an app's `interactions.py`.** dj-hx's `ready()` imports the `interactions`
  module of every installed app outside site-packages, as admin imports each app's `admin`, so every
  route exists before the URLconf is read and no other module's import order changes. An interaction
  defined anywhere else is registered when its module is imported: import it from `interactions.py`.
  One in a pip-installed app is not registered until something imports its module. One registered after the URLconf was read
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
    an element, fetch follows it with the same headers, and the login page it reaches is recorded
    (`HxPageIntoFragment`), as for any view. `HX_REQUIRE_VERBS` records the 302 itself.
  - Every interaction is routed by the root `include("dj_hx.urls")`, not under its app's own
    include, so protection attached to that include, such as `decorator_include` or a middleware
    that checks the app's URL prefix, never reaches it. A decorator above `@interaction` does, and
    so does middleware that sees every request, such as Django 5.1's `LoginRequiredMiddleware`.
- **`manage.py check` reads every `{% act %}` in the project's `.html` and `.htm` templates**, as
  `hx_lint` does, never site-packages, and checks the control it writes the URL of against its
  interaction, as htmx 4.0.2 resolves each attribute:
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
  loads and starts with its id. The scan reads the source, so an `{% act %}` inside `{% verbatim %}`,
  which Django renders as text, still counts: E009 judges its name, and it is a control for E014. A
  computed `hx-swap` or `hx-method` is not judged. A templated id or
  `hx-target` is judged by its literal parts, and skipped only when it could equal the expected
  value: `id="{{ name }}"` and `hx-target="#{{ name }}"` are skipped, while `id="row-{{ pk }}"` and
  `hx-target="#row-{{ pk }}"` cannot be `notify` and are Errors. A block tag in an id, and what
  it wraps, is computed too, since it may not render: `id="{% if p %}{{ p }}-{% endif %}notify"` is
  skipped, `id="{% if p %}{{ p }}-{% endif %}row"` is an Error. An `{% act %}` it cannot tie to
  one element's verb attribute gets an Info (`dj_hx.I021`) saying so. The ids are in README's ["What is loud"](README.md#what-is-loud) and in [FAILURES.md](FAILURES.md).

  "Measured" means in Chromium, on htmx 4.0.2, by `tests/test_interactions_browser.py`, against a
  page whose controls pass every check (`tests/desk`).

## The status policy


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

