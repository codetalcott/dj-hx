# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`dj-hx` is a standalone Django package for htmx 4 (no django-htmx dependency). The handler names the
outcome and the template keeps the request-side controls. README.md is the user-facing reference for the
verbs, the settings and the failure catalogue; read it before changing public behavior.
`llms.txt` is the self-contained reference an agent uses to write code against the package; any change
to a verb signature, a setting, an error, a check id or a lint rule must be mirrored there.

## Commands

The checked-in `.venv` has Django 6.0, pytest, ruff and playwright.

```
.venv/bin/python -m pytest                      # 298 tests, ~5s
.venv/bin/python -m pytest -m "not browser"     # 291, skipping Chromium
.venv/bin/python -m pytest -m browser           # the 7 Playwright tests alone
.venv/bin/python -m pytest tests/test_verbs.py::test_text_escapes
.venv/bin/ruff check .
```

The browser tests `importorskip` Playwright, so they vanish rather than fail where it is missing; this
venv has it installed, so a bare `pytest` run includes them.

`pytest.ini` sets `DJANGO_SETTINGS_MODULE=tests.settings` and puts `example/` on the path, so the suite
runs against the example project with an in-memory database and `DEBUG` off.

The example app, from `example/`:

```
python manage.py migrate && python manage.py seed_contacts && python manage.py runserver
python manage.py hx_lint [paths...] [--warnings-as-errors]
python manage.py hx_map [--no-check]
```

CI runs `ruff check .` on 3.13 and the suite on eight Python/Django pairs covering Django 4.2, 5.2, 6.0 and 6.1.
Any change touching template partials, `{% url %}` handling or middleware ordering has to work on all
four Django lines; `django.VERSION < (6, 0)` branches already exist in `verbs.py`, `checks.py`,
`tests/conftest.py` and the example settings.

## Architecture

**Request side is one header.** [request.py](dj_hx/request.py) reads `HX-Request-Type` and nothing else.
`HX-Source` and `HX-Target` are deliberately never read; do not add a code path that branches on an
element id. Everything downstream asks `wants_page()` / `wants_fragment()`.

**Response side are the verbs.** [verbs.py](dj_hx/verbs.py) holds the eight verbs plus `HxResponse`.
Every response carries `hx_kind`, `hx_template`, `hx_page_template`, `hx_context`, `hx_request` and
`hx_findings`; `.partial()` and the messages bridge re-render from those attributes, so a new verb must
set them.

**Raise vs. record.** A verb raises only when the outcome is certain at call time (`page()` into a partial
request, `redirect()` into a partial request). Everything else is appended to `response.hx_findings` and
logged to the `dj_hx` logger. [guard.py](dj_hx/guard.py) records the post-hoc ones (3xx, 204, a missing
`HX-Request-Type`, `APPEND_SLASH`). [middleware.py](dj_hx/middleware.py) never raises;
[testing.py](dj_hx/testing.py) is where findings become exceptions. Keep that split: a false positive
must not be able to 500 in production.

**Ordering matters.** `HxMiddleware` must run its response phase before `MessageMiddleware` stores
messages, which means it is listed *after* it. [checks.py](dj_hx/checks.py) enforces that as `dj_hx.E002`;
the check ids W001-W025 are documented in that module's docstring.

**The lint has two surfaces over one rule set.** [hxlint.py](dj_hx/hxlint.py) works on rendered HTML
strings. [templates.py](dj_hx/templates.py) strips Django template syntax (line numbers preserved,
`{{ }}` and value tags become a sentinel the rules skip) so the same rules run over source for
`hx_lint` and check `dj_hx.W005`. Template discovery never walks site-packages, which
`templates.in_site_packages` judges for every caller (template discovery, `ready()`, `hx_map`, E014):
sysconfig's purelib/platlib plus the `site-packages`/`dist-packages` directories `site` reports, the user
one included. Keep one copy of that rule.

**Interactions are one handler bound to one partial.** [interactions.py](dj_hx/interactions.py) holds
`@interaction`, the registry (by handler name) and the wrapper view (method guard, refusals as 422,
the return-type and reply-key guards). Its 200 and 422 are built by `fragment()` and checked by
`check_root_id()`, and its facts go out through `.trigger()`; only the 405 is a plain Django
`HttpResponseNotAllowed`, which the guard does not judge (it reads 2xx, 3xx and 204). Each decorator appends its
route to the module's `urlpatterns`, which [urls.py](dj_hx/urls.py) serves (`include("dj_hx.urls")`,
namespace `dj_hx`); [templatetags/hx.py](dj_hx/templatetags/hx.py) is `{% act %}`, which reverses
from keyword arguments only. [apps.py](dj_hx/apps.py)'s `ready()` imports every project app's `views`
module (`templates.in_site_packages` decides what is the project's), so every route is registered
before the URLconf is read. The decorator returns the routed view; when `dj_hx/urls.py` is first
imported, `bind_routes()` points each route at whatever the module that defines the handler holds under
its name, as written, whenever it is callable, so any decorator written above `@interaction` wraps the route, with or
without `functools.wraps` (falling back to the bare view would drop an access check). Only a missing or
non-callable attribute routes the bare view. The raw handler, or a decorator that unwraps to it before
the view (the call form `remind_view = interaction(...)(remind)`), raises `ImproperlyConfigured` from
`bind_routes()`, so from the first URLconf read (first request, `manage.py check`): routing it would
skip the method guard. It rebuilds the list in place: `interactions.urlpatterns` and
`dj_hx.urls.urlpatterns` are one list object, and `include("dj_hx.urls")` imports the module at once
but its resolver reads `urlpatterns` only on its first resolve or reverse, then caches that same list.
An interaction registered after `dj_hx/urls.py` was imported keeps a route to its bare view, which
check `dj_hx.E017` reports.

**The interaction checks reuse the runtime's own pieces.** `{% act %}` and checks E009/E010 take their
messages from `act_unknown()` and `act_mismatch()` in interactions.py, and E015/E016 from
`_get_partial()` and `check_root_id()`, so the start-up and render-time wording cannot drift. E011
reads `hx-action`'s method through `mapcore.action_method()`, as `hx_map` does, and E012 finds the
element `hx-target="this"` names through `Node.resolving()`; both are hx-flask's, so change them there. The
template checks read each `{% act %}` through `strip_template_syntax(source, acts=[...])`, which marks
the n-th tag `__ACT<n>__` so its holding element is found in hxlint's tree, and `partial_sources()`
for `{% partialdef %}` bodies. E022 reads `{% url %}` through `url_tags()`, which is Django's own lexer:
a tag in `{% verbatim %}` or across lines is text to Django, and `strip_template_syntax` would read both.
It reverses through `django.urls.reverse()`, taking each placeholder from the converter the resolver holds
for that parameter (the namespace walk mirrors `reverse()`'s), never from the route string. W024 and W025
take `hxmap.map_with_interactions()` and call `mapcore.unpaired_events()` on it, the pairing `hx_map` warns
from: there is no second trigger or listener collector. An interaction the map has no handler for (not
routed, or in site-packages) is added from the registry, so its `triggers=` still count.

**The map is split by framework.** [mapcore.py](dj_hx/mapcore.py) is framework-neutral: template scan,
the AST visitor that finds verb calls, the control-vs-handler checks. [hxmap.py](dj_hx/hxmap.py) is the
Django adapter: URLconf walk, `{% url %}` and `resolve()`, and `{% act %}` through the registry: an
interaction is found by the callback `dj_hx.urls.urlpatterns` routes it to (identity, not name), its handler
is scanned rather than a decorator's closure, and `_as_interaction()` records its partial and `triggers=`.
The `__ACT<n>__` markers index one `acts` list shared by every template. New map logic belongs in `mapcore` unless it
is genuinely Django-specific; the core is vendored from hx-flask (see below).

## Vendored files: do not edit in place

`dj_hx/hxlint.py`, `dj_hx/hx_vocab.py` and `dj_hx/mapcore.py` are hx-flask's byte for byte apart from one or two import lines, and
`dj_hx/urlconf.py` is dj-fixi's body under a local docstring. Fix them upstream and run
`python tools/sync_shared.py` (`HX_FLASK` / `DJ_FIXI` env vars point at the checkouts).
`tests/test_shared_core.py` pins the copies and fails when the neighbours are checked out and differ.
`hx_vocab.py` is generated from the htmx 4.0.0 source tree by hx-flask's `tools/gen_vocab.py`.

## Conventions

- A partial name containing a dot is a separate template file; anything else is a `{% partialdef %}` of
  the page template. A partial delivered as `<hx-partial>` must have a root element with `id` equal to
  the partial name, checked at render by `check_root_id`.
- `.trigger()` always emits the JSON form and always sets a target, because after a delete swap htmx 4
  dispatches on `document` where a `from:body` listener cannot hear it.
- Error messages name the handler (`who(request)`) and say what to change. Match that tone; the messages
  are the documentation for the failure catalogue in README.md.
- Ruff: line length 120 but `E501` ignored, `N818` ignored (exception names mirror hx-flask, except `HxUnknownPartial` for its `HxUnknownBlock` and `HxMessagesUnconfigured` for its `HxFlashUnconfigured`), vendored
  files excluded.
- Every row of the README's "What is loud" table has a test. Adding a failure mode means adding a row and
  a test.

## Test layout

- `tests/conftest.py` serves in-memory templates through a locmem loader (`lib` fixture, with the
  django-template-partials loader added below Django 6) and loads the contact fixtures (`contacts`).
  `on_disk(directory)` is the same setting over a directory, for the template checks, which read
  files and so see nothing through locmem. `no_interactions` empties the registry for a test of the
  example project or a per-area URLconf, which have none; without it the rota app's four trip the
  interaction checks.
- `tests/urlconfs/` holds small URLconfs, one per area, that exercise the library directly.
- `tests/interactions_app/` is an installed app (label `rota`, from its `apps.py`; installed by `tests/settings.py`), because a
  minted route needs an app label; dj-hx's `ready()` imports its views. A test that defines its own
  interactions takes the `scratch` fixture in `tests/test_interactions.py`, which restores the registry.
  Its `startup` fixture writes the rota app's templates to disk and returns the check messages; the
  W018 on `approve()` is there on purpose (`views.staff_only` has no `functools.wraps`).
  `tests/settings.py` also adds `django.contrib.auth` and `AuthenticationMiddleware` (the example has
  neither) for the `@login_required` test.
- `tests/test_contact_app.py` and `tests/test_browser.py` run against `example/`, mirroring hx-flask's
  suite for a like-for-like comparison.
- pytest does not run system checks, so check coverage goes through `assert_no_hx_check_issues()`.
