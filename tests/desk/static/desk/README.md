# Vendored for the browser tests

The desk app's pages (`tests/desk/pages/`) load these two files, so
`tests/test_interactions_browser.py` runs on the htmx and _hyperscript that the
start-up checks' rulings were read from. `example/` stays on htmx 4.0.0.

| File | Source | sha256 |
|---|---|---|
| `htmx-4.0.2.min.js` | `dist/htmx.min.js` in the npm tarball `htmx.org@4.0.2` | `fd25ba3fe5e44768756f23862a6daa4f928192199a121e825e882e719bc8aabd` |
| `_hyperscript-0.9.94.min.js` | `dist/_hyperscript.min.js` in the npm tarball `hyperscript.org@0.9.94` | `4f48d7379281c7271f0a3d14907d68f9814280d757c12bf1e99d49a103b9b86a` |

Checked 2026-11-20 with `npm pack htmx.org@4.0.2 hyperscript.org@0.9.94` and
`shasum -a 256`. Both tarballs carry a Zero-Clause BSD `LICENSE`.
