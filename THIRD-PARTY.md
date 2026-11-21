# Third-party code

## Vendored into the package

- `dj_hx/hxlint.py`, `dj_hx/hx_vocab.py` — from [hx-flask], the sibling project
  for Flask. The vocabulary is generated there from the htmx 4.0.0 source tree.
  Vendored so dj-hx has no dependency on it. MIT.
- `dj_hx/urlconf.py` — from [dj-fixi], the sibling project for Fixi.js. MIT.

`tools/sync_shared.py` refreshes all three and `tests/test_shared_core.py`
pins them when the neighbouring checkouts are present.

## Vendored into the example

`example/` is a port of *Hypermedia Systems*' contact.app, kept close to the
book's Flask original so the two can be compared line for line.

- `example/contacts/static/js/htmx-4.0.0.js` — htmx, by Big Sky Software. 0BSD.
- `example/contacts/static/js/hx-live-4.0.0.js` — the hx-live extension. 0BSD.
- `example/contacts/static/missing.css` — missing.css, by Ollie Williams
  and contributors. MIT.
- `example/contacts/static/img/spinning-circles.svg` — from SVG Loaders, by
  Sam Herbert. MIT.
- `example/contacts/contacts.json`, the routes and the templates — from
  *Hypermedia Systems* (Gross, Stepinski, Akşimşek), whose sample application
  is published under the BSD 2-Clause license.

## Vendored into the tests

The desk app the browser tests drive loads these, checked by sha256 against
the npm tarballs (`tests/desk/static/desk/README.md` has the hashes).

- `tests/desk/static/desk/htmx-4.0.2.min.js` — htmx, by Big Sky Software,
  from `htmx.org@4.0.2`. 0BSD.
- `tests/desk/static/desk/_hyperscript-0.9.94.min.js` — _hyperscript
  (github.com/bigskysoftware/_hyperscript), from `hyperscript.org@0.9.94`.
  The tarball's `LICENSE` is 0BSD; its `package.json` says BSD 2-Clause.

[hx-flask]: https://github.com/codetalcott/hx-flask
[dj-fixi]: https://github.com/codetalcott/dj-fixi
