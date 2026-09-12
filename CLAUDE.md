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
.venv/bin/python -m pytest                      # 110 tests, ~5s
.venv/bin/python -m pytest -m "not browser"     # 103, skipping Chromium
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

CI runs `ruff check .` on 3.13 and the suite on six Python/Django pairs covering Django 4.2, 5.2 and 6.0.
Any change touching template partials, `{% url %}` handling or middleware ordering has to work on all
three Django lines; `django.VERSION < (6, 0)` branches already exist in `verbs.py`, `checks.py`,
`tests/conftest.py` and the example settings.

## Architecture

**Request side is one header.** [request.py](dj_hx/request.py) reads `HX-Request-Type` and nothing else.
`HX-Source` and `HX-Target` are deliberately never read; do not add a code path that branches on an
element id. Everything downstream asks `wants_page()` / `wants_fragment()`.

**Response side are the verbs.** [verbs.py](dj_hx/verbs.py) holds the seven verbs plus `HxResponse`.
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
the seven check ids W001-E007 are documented in that module's docstring.

**The lint has two surfaces over one rule set.** [hxlint.py](dj_hx/hxlint.py) works on rendered HTML
strings. [templates.py](dj_hx/templates.py) strips Django template syntax (line numbers preserved,
`{{ }}` and value tags become a sentinel the rules skip) so the same rules run over source for
`hx_lint` and check `dj_hx.W005`. Template discovery never walks site-packages.

**The map is split by framework.** [mapcore.py](dj_hx/mapcore.py) is framework-neutral: template scan,
the AST visitor that finds verb calls, the control-vs-handler checks. [hxmap.py](dj_hx/hxmap.py) is the
Django adapter: URLconf walk, `{% url %}` and `resolve()`. New map logic belongs in `mapcore` unless it
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
- `tests/urlconfs/` holds small URLconfs, one per area, that exercise the library directly.
- `tests/test_contact_app.py` and `tests/test_browser.py` run against `example/`, mirroring hx-flask's
  suite for a like-for-like comparison.
- pytest does not run system checks, so check coverage goes through `assert_no_hx_check_issues()`.
