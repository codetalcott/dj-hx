# Changelog

## 0.1.0 (unreleased)

First release: the handler-first design built for Flask in hx-flask,
standalone on Django. It does not build on django-htmx, which was written
against htmx 2: django-htmx 1.27 still writes `HX-Trigger-After-Swap`/
`-After-Settle` and offers `HttpResponseLocation`, both gone or ignored in
htmx 4, and exposes `request.htmx.target` and `.trigger`, the id-sniffing this
design forbids. Two more htmx 4 facts shaped it: a 204 does not swap, and an
event fired without a target lands on `document` after a delete swap, where a
`from:body` listener never hears it.

### Added

- The verbs: `render`, `page`, `fragment`, `invalid`, `redirect`, `navigate`,
  `removed`, `text`, as functions taking `request`; `is_htmx`, `wants_page`,
  `wants_fragment` reading `HX-Request-Type` and nothing else.
- `navigate(request, to)` (from hx-flask): leave the page whatever the control
  targets, for a login check or an expired session. A plain 303 when the
  request wants a page, `HX-Redirect` when it targets an element; messages
  added before it wait for the page it loads, and the map treats it as saying
  nothing about shape.
- `HxResponse` with `.trigger()` (always JSON, always with a `target`,
  default `body`), `.partial()`, `.push_url()`, `.replace_url()`,
  `.with_status()`, and the escape hatches `.retarget()`/`.reswap()`.
- Partials as fragments: `render(request, "index.html", "rows")` renders
  `{% partialdef rows %}` on Django 6 (django-template-partials on 4.2 to 5.x);
  a name with a dot is a file. `HxUnknownPartial` lists the partials a template
  defines; `HxPartialRootId` enforces root-id-equals-name for `<hx-partial>`.
- The messages bridge: `HX_MESSAGES_TEMPLATE = "layout.html#messages"`;
  `HxMiddleware` appends pending messages to fragment responses, peeking
  before consuming. Requires the middleware after `MessageMiddleware` (E002).
- The guard: a 3xx, a 204, or a response no verb built (`HxBareResponse`:
  `django.shortcuts.render`, a plain `HttpResponse`, a `TemplateResponse`)
  answering a partial request, `APPEND_SLASH`'s
  redirect recognised whether the middleware sees the 301 or the 404 it comes
  from, an htmx request without `HX-Request-Type`. Recorded on
  `response.hx_findings`, logged, raised by `HxTestClient`.
- `HX_REQUEST_TYPE_FALLBACK = "full"` or `"partial"`: answer an htmx request
  whose `HX-Request-Type` a proxy stripped as that type instead of raising
  `HxProtocolError`. The guard records the finding either way.
- `HxTestClient`: `hx_get`/`hx_post`/`hx_put`/`hx_patch`/`hx_delete` with
  `full=`, Django's three-state `follow` for 3xx on full requests, every
  `text/html` response linted, findings raised; `assert_no_hx_check_issues()`.
- `HxMixin` for generic views: `render_to_response`, `form_invalid` (422),
  `form_valid` (guarded redirect). Check E007 for base order.
- `manage.py hx_lint` over template source, and check W005 for the same in
  the project's own templates (never site-packages, comments stripped).
- `manage.py hx_map`: controls to views to events, checked, with
  `if request.method == ...` branches attributed to their method. It also warns
  on a control reaching a view that calls no verb, and on a view that calls
  `.retarget()` or `.reswap()`, naming the controls whose templates no longer
  predict the DOM effect. `--by-template` reads the map from the other end.
  A hyperscript listener (`_="on x from body ..."`) pairs with a view's
  `.trigger("x")` like an `hx-trigger`.
  Whether or not a view calls a verb, it errors on a read of the `HX-Trigger`
  request header, which htmx 4 does not send, and on `request.POST` read on
  DELETE, which htmx 4 sends as query parameters; it warns on a read of
  `HX-Target` or `HX-Source`.
- Lint rule `boost-not-inherited` (error, from hx-flask): a plain `hx-boost` on
  anything but `<a>`/`<form>`, including a layout's `<body>` whose links live in
  child templates.
- Lint rule `htmx2-event-name` (from hx-flask) catches kebab-case event names
  (`hx-on::after-request`), htmx 2's documented form, which htmx 4 never fires,
  and checks the events in `hx-trigger` as well as `hx-on`.
- `HX_EXTENSIONS` takes the name htmx registers an extension under (`sse`,
  `ws`, `upsert`) or its file name (`hx-sse`); check W008 names one that is
  neither, and a string where a tuple belongs.
- Checks W001, E002, W003, W004, W005, W006, E007, W008, and the interaction
  checks E009 to I021 below.
- Interactions: `@interaction(method, partial=, context=, refuses=, triggers=,
  route=)` binds a handler to one partial, and the reply is always that
  partial, through `fragment()`, from the context function the page uses too.
  The route is minted as `x/<app label>/<handler>/<param>/.../` (`<int:...>`
  for an `int` annotation), or chosen with `route=`, which must name the
  handler's parameters. `dj_hx.urls` serves every route under the `dj_hx`
  namespace, and `{% act 'notify' contest=... member=... %}` (`{% load hx %}`)
  writes one into a control, from keyword arguments only. A declared refusal
  is a 422 with `error`; success a 200 with the declared triggers; another
  method a 405. A handler returns a dict or `None`, and every key it returns
  must already be in the context. dj-hx's `ready()` imports each project
  app's `views` module, so every route exists before the URLconf is read.
  `@interaction` returns the routed view, and `dj_hx.urls` routes each
  interaction to what its module holds under the handler's name, as written,
  so a decorator written above it (`@login_required`, or a hand-written check)
  wraps the route. A module that holds the raw handler under that name, as
  `remind_view = interaction(...)(remind)` leaves it, raises
  `ImproperlyConfigured` when the URLconf is read, instead of routing a
  handler past the method guard; the message says the binding belongs in the
  module that defines the handler. A wrapper of the raw handler written
  without `functools.wraps` is still routed as it is (W018 warns).
- `@interaction` refuses at import a `method` other than GET, POST, PUT, PATCH
  or DELETE, a `refuses` holding anything but exception classes (one class is
  taken as well as a tuple), and `*args` or `**kwargs` on the handler or on
  `context=`. A `context=` parameter the route lacks takes its default; one
  without a default raises at import. `{% act %}` without `dj_hx.urls`
  included raises `ImproperlyConfigured`, naming the include.
- Interaction checks, from `manage.py check`: every `{% act %}` in the
  project's templates names an interaction (E009) with its handler's
  parameters (E010), and its control sends the interaction's method (E011,
  with `hx-action`'s method resolved as htmx 4.0.2 does), targets the element
  with the partial's id (E012: `#<partial>`, or no `hx-target` or
  `hx-target="this"` on that element) and uses an outer swap, `outerHTML`,
  `outerMorph` or `outerSync` as read in htmx 4.0.2's swap code (E013), reading
  htmx 4's `:inherited` on ancestors; every interaction has an `{% act %}` control (E014;
  a `{% url %}` or hand-written path is not counted), a partial
  that loads (E015) and whose root carries its id (E016); `dj_hx.urls` routes
  each interaction to what its module holds (E017) and is included (E020).
  Warnings for a decorator above `@interaction` without `functools.wraps`
  (W018) and for one below it (W019); an Info for an `{% act %}` no element's
  verb attribute holds (I021), which `assert_no_hx_check_issues()` counts.
- The example: contact.app on the ORM, same routes, templates and tests as
  hx-flask; 156 tests plus 7 in Chromium, on Django 4.2, 5.2, 6.0 and 6.1.
- The shared core, vendored: `hxlint.py`, `hx_vocab.py` and `mapcore.py`, the
  framework-neutral map engine, from hx-flask (one or two import lines differ),
  `urlconf.py` from dj-fixi; `tools/sync_shared.py` and a pin test.
