# dj-htmx-cbv

Class-based-view ergonomics for **Django + [HTMX 4](https://four.htmx.org)**, layered on
[django-htmx](https://django-htmx.readthedocs.io).

> **Status: v0.1.0 (lean).** `HxView`, `HxResponseMixin` (configurable, 422 by default),
> the protocol-agnostic `ContextPersistenceMixin`/`OptimizedQueryMixin`, and a thin
> `HxTestClient` are implemented and tested (24 tests), with a runnable `example/`.
> Form-rendering helpers are intentionally out of scope.

## Why this exists

It is the HTMX-4 sibling of [dj-fixi](https://github.com/codetalcott/dj-fixi). dj-fixi
inherited several features from HTMX's wire protocol — server-driven client events
(`HX-Trigger`), retarget/reswap — that **Fixi.js does not implement**, so they were inert
there. HTMX 4 *does* implement that full protocol, so those features work for real here.

## Design

**Don't reinvent the plumbing.** `django-htmx` already provides everything low-level:

- `request.htmx` — detection plus `.target`, `.trigger`, `.boosted`, …
- `trigger_client_event(response, name, params, after=…)` — sets `HX-Trigger*`
- `reswap()`, `retarget()`, `reselect()`, `push_url()`, `HttpResponseClientRedirect`, …

This package adds only the CBV ergonomics that django-htmx intentionally leaves out:

| Component | dj-fixi analog | Notes |
|---|---|---|
| `HxView` | `FxView` | Fragment vs full-page selection via HTMX 4's `HX-Request-Type` (or `request.htmx`). |
| `HxResponseMixin` | `FxResponseMixin` | `form_valid`/`form_invalid` render fragments and fire events via `trigger_client_event`; use `retarget`/`reswap` for server-driven targeting. |
| `ContextPersistenceMixin`, `OptimizedQueryMixin` | same | Protocol-agnostic; ported ~verbatim. |
| `HxTestClient` | `FxTestClient` | Form-encoded bodies + `HX-Request`/`HX-Request-Type`. |

**Defaults differ from dj-fixi:** HTMX's default swap is `innerHTML` (Fixi's is
`outerHTML`).

## Form errors and status (422)

`HxResponseMixin.form_invalid` returns **422** by default (the correct, increasingly
conventional status for validation failures). htmx only *swaps* error responses when its
`responseHandling` config allows the status, so add a meta tag (as `example/` does):

```html
<meta name="htmx-config"
      content='{"responseHandling":[{"code":"204","swap":false},{"code":"[23]..","swap":true},{"code":"422","swap":true},{"code":"[45]..","swap":false,"error":true}]}'>
```

Don't want to touch `responseHandling`? Set `hx_invalid_status = 200` on your view.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e . pytest pytest-django
pytest                                   # 24 tests
cd example && python manage.py migrate && python manage.py runserver
```

The `example/` app proves it end-to-end: htmx fragment swaps, a server-fired
`formSuccess` event that makes the list refetch itself, and 422 validation errors that
swap in (the server-driven behavior Fixi structurally cannot do).

## Possible later work

- Whether to factor the protocol-agnostic mixins into a small shared core with dj-fixi.
- Final package name (`dj-htmx-cbv` is a placeholder).
- `retarget`/`reswap`/OOB ergonomics and form-rendering helpers, *if* demand warrants —
  deliberately omitted to keep this a thin layer over django-htmx.

## License

MIT
