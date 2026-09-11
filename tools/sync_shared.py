"""
Copy the shared core from its canonical homes.

``hxlint.py`` and ``hx_vocab.py`` are hx-flask's (the linter is pure Python
over HTML strings; the vocabulary is generated there from the htmx source
tree by ``tools/gen_vocab.py``). ``urlconf.py`` is dj-fixi's. dj-hx vendors
them so it has no dependency on either; ``tests/test_shared_core.py`` pins
the copies when the neighbours are checked out.

    python tools/sync_shared.py
"""

from __future__ import annotations

import os
import pathlib
import sys

HX_FLASK = pathlib.Path(os.environ.get("HX_FLASK", "~/projects/hx-flask")).expanduser()
DJ_FIXI = pathlib.Path(os.environ.get("DJ_FIXI", "~/projects/dj-fixi")).expanduser()
PKG = pathlib.Path(__file__).resolve().parent.parent / "dj_hx"

IMPORT_FLASK = "import hx_vocab as V\n"
IMPORT_DJANGO = "from . import hx_vocab as V\n"


def expected_hxlint() -> str:
    src = (HX_FLASK / "hxlint.py").read_text()
    if IMPORT_FLASK not in src:
        sys.exit("hxlint.py no longer imports hx_vocab the way sync_shared expects")
    return src.replace(IMPORT_FLASK, IMPORT_DJANGO, 1)


def expected_vocab() -> str:
    return (HX_FLASK / "hx_vocab.py").read_text()


def expected_urlconf() -> str:
    """dj-fixi's body under dj-hx's docstring (the docstring names the package)."""
    theirs = (DJ_FIXI / "dj_fixi" / "urlconf.py").read_text()
    ours = (PKG / "urlconf.py").read_text()
    marker = "from __future__ import annotations"
    return ours.split(marker, 1)[0] + marker + theirs.split(marker, 1)[1]


def main() -> None:
    for name, expected in (("hxlint.py", expected_hxlint), ("hx_vocab.py", expected_vocab), ("urlconf.py", expected_urlconf)):
        (PKG / name).write_text(expected())
        print(f"synced dj_hx/{name}")


if __name__ == "__main__":
    main()
