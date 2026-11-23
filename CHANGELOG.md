# Changelog

## Unreleased

### Changed

- **Breaking.** `ready()` discovers interactions in each project app's
  `interactions.py`, not its `views.py`: admin's `autodiscover` pattern, under
  a module that exists to be discovered, so importing it changes no other
  module's import order. An interaction left in `views.py` is registered only
  when something imports that module, which check `dj_hx.E017` or `E009`
  reports at start-up. To migrate, move the handlers, or write
  `from . import views  # noqa: F401` in the app's `interactions.py`.
- README's "What is loud" table is one line per row again; the full entries moved
  to FAILURES.md, which each row links. A new section at the top names the two
  checks that have no htmx in them, `dj_hx.E022` and `HxUndefinedVariable`, and
  the package description says so.
- README compares dj-hx with django-htmx 1.29.0 and djxi 0.1.9 from a run
  (2026-11-23, Django 6.1.3), not from memory: neither guards a 204, a 3xx
  or a whole page answering a partial request, and both offer
  `request.htmx.target`. The paragraph that said django-htmx "was written for
  htmx 2" is gone; django-htmx has read `HX-Request-Type` since 1.28. The
  0.1.0 entry below said `HX-Location` is gone or ignored in htmx 4; htmx
  4.0.2 honours it. The headers it does not read are `HX-Trigger-After-Swap`
  and `-After-Settle`. The entry is corrected in place.
- README states what pytest-django's `--fail-on-template-vars` catches and
  misses beside `HxUndefinedVariable`, from a run on pytest-django 4.14.0.
- `HxTestClient` raises the first finding with every other finding on that
  response listed in its message, so a view with three is fixed in one run.
- `X-HX-Template` has one owner, the verb that rendered the response;
  `HxMiddleware.observe` no longer sets it again.
- CI has a non-blocking canary job on Django's `main`, for the undefined-variable
  check's reliance on Django internals that are not promised.

### Added

- Check `dj_hx.E026`: an `hx-select` reaches an `{% act %}` control, its own
  or an ancestor's `hx-select:inherited`. htmx 4 then sends
  `HX-Request-Type: full`, so the interaction's reply records
  `HxFragmentIntoPage`, and it swaps in only what the selector finds in the
  reply: in Chromium on htmx 4.0.2, a selector that matches nothing removes the
  partial's region. In a private production project a page-wide
  `hx-select:inherited` emptied a reminder button's reply this way, and E011
  to E013 passed it. An own `hx-select=""` is no select to htmx 4.0.2 and
  stops an inherited one.

### Fixed

- `hx_map` read only a control's own `hx-select` when it classified the
  request: a control under an `hx-select:inherited` is now `full`
  (`hx-select:inherited from div#card`), as htmx 4.0.2 sends it, and one with
  an own `hx-select=""` is `partial`. The lint's `select-not-body` info no
  longer fires on `hx-select=""`. `mapcore.py` and `hxlint.py` are synced
  from hx-flask.
- `hx_lint` gave four htmx 2 events htmx 4.0.0's renames, which htmx 4.0.1
  corrected: `htmx:afterOnLoad` is `htmx:after:request` (it said
  `htmx:after:init`), `htmx:beforeOnLoad` is `htmx:before:response` (said
  `htmx:before:init`), `htmx:load` is `htmx:after:process` (said
  `htmx:after:init`), and `htmx:beforeProcessNode` is `htmx:before:init` (said
  `htmx:before:process`). The `htmx:load` message no longer adds "call
  htmx.onLoad(fn)": `htmx:after:process` reaches new content as `htmx:load`
  did. `hxlint.py` and `hx_vocab.py` are synced from hx-flask, whose vocabulary
  is now generated from htmx's `v4.0.2` tag.
- `hx_lint`'s `duplicate-id` no longer compares ids built in the template:
  `id="{{ form.name.id_for_label }}"` and
  `id="{{ form.collaborator_emails.id_for_label }}"` were reported as one id
  twice. Literal ids are compared as before. The lint does not follow
  `{% if %}`, so an id in two exclusive branches is still reported; llms.txt
  says so.

## 0.1.0 (2026-11-21)

First release: the handler-first design built for Flask in hx-flask,
standalone on Django. It does not build on django-htmx, whose
`trigger_client_event(after="swap")` still writes `HX-Trigger-After-Swap`/
`-After-Settle`, which htmx 4 does not read, and which exposes
`request.htmx.target` and `.trigger`, the id-sniffing this design forbids.
(This entry said `HttpResponseLocation`'s `HX-Location` was gone too; htmx
4.0.2 honours it. Corrected 2026-11-23.) Two more htmx 4 facts shaped it: a 204 does not swap, and an
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
- `HxTestClient` raises `HxUndefinedVariable` when a project template reads a
  name nobody supplies or an attribute an object lacks, naming each and the
  template:line it is written in, and for a name an included template reads,
  the include's `with` to pass it in. It reads Django's documented
  `django.template` DEBUG log in each request's own context, which records the
  lookups `{% if %}`, `{% for %}` and `|default` swallow (`string_if_invalid`
  sees none of the first two), lowering that logger's level for the request
  alone and passing on to other handlers only what they got before. Skipped,
  because the outcome depends on the data: a lookup on None, a key a mapping
  or the session lacks (`request.GET`, `request.session`), an index past the
  end of a sequence, what `{% firstof %}`
  reads, the debug context processor's `debug` and `sql_queries`, and a
  response built from an exception; so a misspelt dict key or index stays
  silent, as in Django, and so does any lookup on a mapping (`forloop.countr`,
  `forloop` being a dict; a misspelt QueryDict method, `request.GET.urlencod`). Not seen: templates in site-packages or built from a
  string, lookups that raise an exception Django silences, and a render outside
  the request's context (a thread pool, a plain thread, a streaming body read
  after the request); an `async def` view is checked. `undefined=False` turns
  it off and `strict=False` records it; a `logging.disable()` or a disabled
  `django.template` logger, which would leave it blind, raises
  `ImproperlyConfigured`.
- `HxMixin` for generic views: `render_to_response`, `form_invalid` (422),
  `form_valid` (guarded redirect). Check E007 for base order.
- `manage.py hx_lint` over template source, and check W005 for the same in
  the project's own templates (never site-packages, comments stripped).
- `manage.py hx_map`: controls to views to events, checked, with
  `if request.method == ...` branches attributed to their method. It also warns
  on a control reaching a view that calls no verb, and on a view that calls
  `.retarget()` or `.reswap()`, naming the controls whose templates no longer
  predict the DOM effect. `--by-template` reads the map from the other end.
  A hyperscript listener (`_="on x from body ..."`, or in a
  `<script type="text/hyperscript">` written inline, behaviors included) pairs with a view's
  `.trigger("x")` like an `hx-trigger`, and an event a script names counts
  for both sides. An `{% act %}` control resolves
  through the interaction registry, as a `{% url %}` control resolves through
  the URLconf: the interaction answers its method with its partial and
  announces its `triggers=`, and an `{% act %}` naming no interaction, or
  without `dj_hx.urls` included, is an error.
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
- Checks W001, E002, W003, W004, W005, W006, E007, W008, the interaction
  checks E009 to I021, and the template-wide checks from E022, below.
- Interactions: `@interaction(method, partial=, context=, refuses=, triggers=,
  route=)` binds a handler to one partial, and the reply is always that
  partial, through `fragment()`, from the context function the page uses too.
  The route is minted as `x/<app label>/<handler>/<param>/.../` (`<int:...>`
  for an `int` annotation), or chosen with `route=`, which must name the
  handler's parameters. `dj_hx.urls` serves every route under the `dj_hx`
  namespace, and `{% act 'notify' contest=... member=... %}` (`{% load hx %}`)
  writes one into a control, from keyword arguments only. A declared refusal
  is a 422 with `error`; success a 200 with the declared triggers; another
  method a 405. A refusal whose message is empty or blank is recorded as
  `HxEmptyRefusal` (its reply shows nothing to read), which `HxTestClient`
  raises. Every reply carries `error`: `None` on success unless the
  handler or the context sets it. A handler returns a dict or `None`, and every
  key it returns must already be in the context (`error` always is). dj-hx's
  `ready()` imports each project app's `views` module, so every route exists
  before the URLconf is read.
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
  project's `.html` and `.htm` templates (one in `{% verbatim %}` included)
  names an interaction (E009) with its handler's
  parameters (E010), and its control sends the interaction's method (E011,
  with `hx-action`'s method resolved as htmx 4.0.2 does), targets the element
  with the partial's id (E012: `#<partial>`, or an extended selector whose
  CSS part is that, `closest #<partial>` and its siblings as htmx 4.0.2's
  target resolver reads them, or no `hx-target` or `hx-target="this"` on that
  element) and uses an outer swap, `outerHTML`,
  `outerMorph` or `outerSync` as read in htmx 4.0.2's swap code (E013, whose
  message says what the swap does instead: a second element with the id, or
  for `innerMorph` an htmx `HierarchyRequestError`, so the reply never reaches
  the page; a page's `htmx.config.defaultSwap` is not read), reading
  htmx 4's `:inherited` on ancestors, and judging a templated id or `hx-target`
  by its literal parts (`id="row-{{ pk }}"` cannot be `#notify`;
  `id="{{ name }}"` is skipped, and so is
  `id="{% if p %}{{ p }}-{% endif %}notify"`: a block tag in an id, and what it
  wraps, is computed); every interaction has an `{% act %}` control (E014;
  a `{% url %}` or hand-written path is not counted, and an interaction whose
  handler is in site-packages is skipped), a partial
  that loads and parses (E015, with Django's message for a syntax error) and
  whose root carries its id (E016); `dj_hx.urls` routes
  each interaction to what its module holds (E017) and is included (E020).
  Warnings for a decorator above `@interaction` without `functools.wraps`
  (W018) and for one below it (W019); an Info for an `{% act %}` no element's
  verb attribute holds (I021), which `assert_no_hx_check_issues()` counts.
- `{% url %}` checks, from `manage.py check`: every `{% url %}` with a quoted
  name in the project's `.html` and `.htm` templates reverses, against
  `ROOT_URLCONF`, with the arguments it passes (E022), through Django's
  resolver with a placeholder for the converter each argument's route
  declares, positional and keyword arguments counted apart, and a keyword
  that names a route's extra kwarg passed that default. The message names
  template:line and the route, and lists close names for one that does not
  exist or a namespace no URLconf installs. A route with a custom converter or
  a `re_path` group gets an Info instead (I023). Skipped: `{% url ... as var %}`,
  Django's documented form for a view that may be missing; a name built at
  run time; a tag in a comment or `{% verbatim %}`.
- Event checks, from `manage.py check`: an event a view announces with
  `.trigger()` (as `hx_map` finds it) or an interaction declares in
  `triggers=` that no project template listens for (W024), and an event a
  template listens for that nothing announces (W025), browser events,
  hyperscript's observers (`on intersection`, `on mutation`, `on resize`)
  and names with a colon (`htmx:*`, an extension's `sse:message`, a
  namespaced `contact:saved`) left out; they still pair with a `.trigger()`
  of that name. A name built in the template (`on {{ name }}`) is not read as
  a listener.
  A hyperscript `on` counts in an attribute or an inline `<script type="text/hyperscript">`,
  behaviors included, and an event a script names (a quoted name in a
  `<script>` or `hx-on`, a hyperscript `send`) counts for both sides. They call
  the pairing `hx_map` warns from
  (hx-flask's `mapcore.unpaired_events`), and they are Warnings, because a
  JavaScript file, a hyperscript file, a template in site-packages or a
  helper the view calls can be the other side. They skip without
  `ROOT_URLCONF`.
- README's status policy for interactions: `hx-status:40x:inherited="swap:none"`
  and `hx-status:5xx:inherited="swap:none"` on the root of each interaction's
  partial, so a 404, a 405 or a 5xx keeps the controls while a 422 still
  swaps, and one hyperscript alert in the layout. Not `htmx-config`'s global
  `noSwap`: htmx 4.0.2 applies it to every request on the page, so under it a
  boosted link to a page that answers 404 keeps the old page under the new
  URL. The alert shows on any
  error status but 422 and on `htmx:error` (a request that gets no reply, a
  swap that throws), hides itself when the next request starts, and is hidden
  with `style="display: none"`, since `show` never clears the `hidden`
  attribute.
  It also says that a refusal is a response, so `ATOMIC_REQUESTS` commits the
  writes made before it (raise first, or `transaction.set_rollback(True)`),
  and that protection on an app's own include never reaches its interactions.
- `tests/desk`, a page of interactions that passes every check, driven in
  Chromium on htmx 4.0.2 and _hyperscript 0.9.94 (vendored with their npm
  sha256): feedback only after the reply, a refusal that keeps the controls,
  the status policy against a 405, a 404, a 500 and a request that gets no
  reply, a boosted link to a missing page that still shows the 404 page, and
  six of the forms checks E011 to E013 accept, each measured once:
  `outerMorph`, `outerSync`, a self-replacing control, inherited `this`,
  `closest #<partial>` and `<form method="post" hx-action>`. The other forms
  they accept are read from htmx 4.0.2's source.
- The example: contact.app on the ORM, same routes, templates and tests as
  hx-flask, in Chromium too, on Django 4.2, 5.2, 6.0 and 6.1.
- Site-packages, which the lint, the map, the checks and `ready()` all skip,
  is one rule (`templates.in_site_packages`): sysconfig's `purelib` and
  `platlib` plus the `site-packages` and `dist-packages` directories `site`
  reports, the user one included.
- The shared core, vendored: `hxlint.py`, `hx_vocab.py` and `mapcore.py`, the
  framework-neutral map engine, from hx-flask (one or two import lines differ),
  `urlconf.py` from dj-fixi; `tools/sync_shared.py` and a pin test.
