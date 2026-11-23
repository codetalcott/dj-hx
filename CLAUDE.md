# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`dj-hx` is a standalone Django package for htmx 4 (no django-htmx dependency). The handler names the
outcome and the template keeps the request-side controls. README.md is the user-facing reference for the
verbs, the settings and the failure catalogue, one line per row; FAILURES.md is the catalogue in full. Read
both before changing public behavior.
`llms.txt` is the self-contained reference an agent uses to write code against the package; any change
to a verb signature, a setting, an error, a check id or a lint rule must be mirrored there.

## Commands

No virtualenv is checked in: `.venv/` is gitignored, and an old local one can point at a Python that is gone
(this one's points at a removed Homebrew 3.13). Build one outside the repo (CI instead runs
`pip install -e ".[dev,browser,partials]"` on each Python/Django pair, then `playwright install --with-deps chromium`):

```
uv venv <venv> && uv pip install -p <venv>/bin/python "django~=6.1.0" pytest pytest-django ruff "playwright==1.64.0"  # below Django 6, add django-template-partials
<venv>/bin/python -m playwright install chromium

<venv>/bin/python -m pytest -q                      # 419 tests, ~16 s
<venv>/bin/python -m pytest -q -m "not browser"     # 384, ~3 s, skipping Chromium
<venv>/bin/python -m pytest -q -m browser           # the 35 Playwright tests alone, ~14 s
<venv>/bin/python -m pytest tests/test_verbs.py::test_text_escapes
<venv>/bin/ruff check .
```

Counts and times measured 2026-11-23 on an Apple M4: Python 3.13.7, Django 6.0.5, Playwright 1.62.0.
`pytest.ini` puts the repo and `example/` on the path, so no `PYTHONPATH` is needed. On macOS 27.2 here,
Playwright 1.65.2's headless shell crash-loops ("icudtl.dat not found in bundle"); pin `playwright==1.64.0`
locally. CI installs its own and is unaffected.

The browser tests `importorskip` Playwright, so they vanish rather than fail where it is missing; with the
install above a bare `pytest` run includes them, and the count says whether they ran.

`pytest.ini` sets `DJANGO_SETTINGS_MODULE=tests.settings` and puts `example/` on the path, so the suite
runs against the example project with an in-memory database and `DEBUG` off.

The example app, from `example/`:

```
python manage.py migrate && python manage.py seed_contacts && python manage.py runserver
python manage.py hx_lint [paths...] [--warnings-as-errors]
python manage.py hx_map [--no-check]
```

CI runs `ruff check .` on 3.13 and the suite on nine Python/Django pairs, covering Django 4.2, 5.2, 6.0 and 6.1
and Python 3.10 to 3.13: the support README, llms.txt and the `pyproject.toml` classifiers state. Change the
matrix and those three together. A tenth job, `canary`, runs the suite on Django `main` with
`continue-on-error`; it is not part of the required `ci` check, and a red canary means a Django internal the
undefined-variable check rests on has moved, not that a pull request is blocked. A local run on 3.12 or 3.13 cannot show what the older pathlib of 3.10 and
3.11 does: it refuses to intern a `SafeString`, which a Django template name often is.
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

**The undefined-variable check is test-time only.** `HxTestClient` reads Django's `django.template`
DEBUG record for a failed lookup through one filter on that logger (`_Gate`), attached while any of its
requests runs. It drops what the logger's old level would not have delivered, so other handlers see
no change. A record belongs to the request whose `ContextVar` (`_COLLECTING`) it is made under, not to a
thread: asgiref carries it into an async view, and a plain thread starts without it. The record's own
template name is the template the render started from: the child of an `{% extends %}`, the page that
includes an admin template, and a partial's bare name. So the place comes from the template node being
rendered on the stack (its `origin` and `token.lineno`), and `templates.in_site_packages` judges that
origin. What counts is `_is_a_slip()`, read from Django's exception's `params == (bit, current)`: a
top-level name (`current` is the Context) or an attribute an object lacks; a lookup on None, a mapping's
or the session's key, an index past the end, `{% firstof %}` and the debug processor's names are skipped,
and so is a response built from an exception. Every view a test requests through `HxTestClient` must supply every
top-level name its templates read: `tests/urlconfs/lib.py`'s `PAGE` carries `extra` for the inline
`extra` partial of the in-memory `index.html`.

**Ordering matters.** `HxMiddleware` must run its response phase before `MessageMiddleware` stores
messages, which means it is listed *after* it. [checks.py](dj_hx/checks.py) enforces that as `dj_hx.E002`;
the check ids are documented in that module's docstring: W001 to W008 for settings, middleware, the lint and `HxMixin`,
E009 to E017, W018, W019, E020, I021 and E026 for interactions, E022 and I023 for `{% url %}`, and W024 and W025
for events.

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
`HttpResponseNotAllowed`, which the guard does not judge (it reads 2xx, 3xx and 204). A refusal whose message
is empty or blank is recorded on its 422 as `HxEmptyRefusal` (through `verbs._record`, so it is logged and
`HxTestClient` raises it; never raised in production). Each decorator appends its
route to the module's `urlpatterns`, which [urls.py](dj_hx/urls.py) serves (`include("dj_hx.urls")`,
namespace `dj_hx`); [templatetags/hx.py](dj_hx/templatetags/hx.py) is `{% act %}`, which reverses
from keyword arguments only. [apps.py](dj_hx/apps.py)'s `ready()` imports every project app's `interactions`
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
for that parameter (the namespace walk mirrors `reverse()`'s), never from the route string; a keyword naming
a route's extra kwarg is passed that default. It skips `{% url ... as var %}`: Django's documented form for a
view that may be missing, which admin's own templates use, so an Error there would stop `migrate`. W024 and W025
take `hxmap.map_with_interactions()` and call `mapcore.unpaired_events()` on it, the pairing `hx_map` warns
from: there is no second trigger or listener collector. An interaction the map has no handler for (not
routed, or in site-packages) is added from the registry, so its `triggers=` still count.

**The map is split by framework.** [mapcore.py](dj_hx/mapcore.py) is framework-neutral: template scan,
the AST visitor that finds verb calls, the control-vs-handler checks. [hxmap.py](dj_hx/hxmap.py) is the
Django adapter: URLconf walk, `{% url %}` and `resolve()`, and `{% act %}` through the registry: an
interaction is found by the callback `dj_hx.urls.urlpatterns` routes it to (identity, not name), its handler
is scanned rather than a decorator's closure, and `_as_interaction()` records its partial and `triggers=`.
The `__ACT<n>__` markers index one `acts` list shared by every template. The checks build this map at every
`runserver` start, so `_scan_handlers` parses each views module once per map (`module_verbs`), not once per
view, and `templates.in_site_packages` resolves the site roots once per set of directories. On a private
378-template production project the checks took 3.6 s before those two, and after them three runs had
medians of 553, 639 and 659 ms (2026-11-20, Apple M4, Python 3.13.6, Django 6.1.2). New map logic belongs in `mapcore` unless it
is genuinely Django-specific; the core is vendored from hx-flask (see below).

## Vendored files: do not edit in place

`dj_hx/hxlint.py`, `dj_hx/hx_vocab.py` and `dj_hx/mapcore.py` are hx-flask's byte for byte apart from one or two import lines, and
`dj_hx/urlconf.py` is dj-fixi's body under a local docstring. Fix them upstream and run
`python tools/sync_shared.py` (`HX_FLASK` / `DJ_FIXI` env vars point at the checkouts).
`tests/test_shared_core.py` pins the copies and fails when the neighbours are checked out and differ.
`hx_vocab.py` is generated from htmx's repository at the `v4.0.2` tag by hx-flask's `tools/gen_vocab.py`.

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
- Every row of the README's "What is loud" table has a test and an entry in FAILURES.md, in the same order.
  Adding a failure mode means adding all three.

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
  Its layout listens for `notify()`'s two `triggers=`, so W024 stays quiet; a test that drops one expects it.
  `tests/settings.py` also adds `django.contrib.auth` and `AuthenticationMiddleware` (the example has
  neither) for the `@login_required` test.
- `tests/test_contact_app.py` and `tests/test_browser.py` run against `example/`, mirroring hx-flask's
  suite for a like-for-like comparison.
- `tests/desk/` is the app `tests/test_interactions_browser.py` drives in Chromium. It is installed (label
  `desk`) for its label and its static files: htmx 4.0.2 and _hyperscript 0.9.94, vendored with their npm
  sources and sha256 in `static/desk/README.md`, while `example/` stays on htmx 4.0.0. Its interactions
  are in `handlers.py`, not `interactions.py`, so `ready()` never registers them: the `desk` fixture (conftest)
  imports it afresh with the rota app's interactions set aside, routes them, serves `pages/` from disk with
  `tests.desk.urls` as the root, and puts the rota app back after. `test_interactions.py` asserts the
  desk passes every check, so each control the browser measures is one the checks accept; a swap the checks
  reject is set on the control from the test, in the page. Its layout boosts the body as README's Install
  recommends, and each partial's root carries the status policy's `hx-status` pair; `tests/test_docs.py`
  compares README's and llms.txt's status-policy blocks with those files, so editing one means editing the
  others. The browser tests wait for htmx with
  `finished(page, n)`, which counts `htmx:finally:request` on `document` (htmx dispatches there when the
  swap removed the control), and hold a write in the browser until the test releases it (`hold_writes`).
- `browser` (one Chromium per module, with `DJANGO_ALLOW_ASYNC_UNSAFE` set while it runs) and `page` are
  conftest's, shared by both browser modules.
- `tests/test_undefined_variables.py` covers the client's undefined-variable check, through the views in
  `tests/urlconfs/undefined.py`. `locmem(templates, dirs=[...])` adds a filesystem loader over `dirs`,
  so a test can include one of Django's own templates from site-packages.
- pytest does not run system checks, so check coverage goes through `assert_no_hx_check_issues()`.
