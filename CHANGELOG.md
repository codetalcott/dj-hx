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

- The verbs: `render`, `page`, `fragment`, `invalid`, `redirect`, `removed`,
  `text`, as functions taking `request`; `is_htmx`, `wants_page`,
  `wants_fragment` reading `HX-Request-Type` and nothing else.
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
- The guard: a 3xx or 204 answering a partial request, `APPEND_SLASH`'s
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
  `if request.method == ...` branches attributed to their method.
- Checks W001, E002, W003, W004, W005, W006, E007.
- The example: contact.app on the ORM, same routes, templates and tests as
  hx-flask; 103 tests plus 7 in Chromium, on Django 4.2, 5.2 and 6.0.
- The shared core, vendored: `hxlint.py` and `hx_vocab.py` from hx-flask
  (one import line differs), `urlconf.py` from dj-fixi; `tools/sync_shared.py`
  and a pin test. `mapcore.py` is the framework-neutral map engine.
