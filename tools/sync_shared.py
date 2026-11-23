"""
Copy the shared core from its canonical homes, and record which commit it came from.

``hxlint.py``, ``hx_vocab.py`` and ``mapcore.py`` are hx-flask's (the linter
and the map engine are pure Python over HTML strings and ASTs; the vocabulary
is generated there from the htmx source tree by ``tools/gen_vocab.py``).
``urlconf.py`` is dj-fixi's. dj-hx vendors them so it has no dependency on
either.

    python tools/sync_shared.py

writes the four files from the checkouts at ``HX_FLASK`` and ``DJ_FIXI``
(``~/projects/hx-flask`` and ``~/projects/dj-fixi`` by default) and the commit
each is at into ``tools/shared.lock``. A commit that is not on any remote
branch is refused: ``tests/test_shared_core.py`` fetches the files at the
recorded commits from GitHub, so CI enforces the pin with no neighbour checked
out, and an unpushed commit would make that test fail for everyone else.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

HX_FLASK = pathlib.Path(os.environ.get("HX_FLASK", "~/projects/hx-flask")).expanduser()
DJ_FIXI = pathlib.Path(os.environ.get("DJ_FIXI", "~/projects/dj-fixi")).expanduser()
TOOLS = pathlib.Path(__file__).resolve().parent
PKG = TOOLS.parent / "dj_hx"
LOCK = TOOLS / "shared.lock"
GITHUB = "https://raw.githubusercontent.com/codetalcott/{repo}/{sha}/{path}"

IMPORT_FLASK = "import hx_vocab as V\n"
IMPORT_DJANGO = "from . import hx_vocab as V\n"
IMPORT_MAPCORE = (
    ("import hx_vocab as vocab\n", "from . import hx_vocab as vocab\n"),
    ("from hxlint import ", "from .hxlint import "),
)


class Offline(Exception):
    """GitHub could not be reached; the pin cannot be checked here."""


class Source:
    """Where an upstream's files are read from: a checkout, or GitHub at a recorded commit."""

    def __init__(self, repo: str, checkout: pathlib.Path | None = None, sha: str | None = None):
        self.repo, self.checkout, self.sha = repo, checkout, sha

    def read(self, path: str) -> str:
        if self.checkout is not None:
            return (self.checkout / path).read_text()
        url = GITHUB.format(repo=self.repo, sha=self.sha, path=path)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read().decode()
        except urllib.error.HTTPError as exc:
            raise FileNotFoundError(f"{url}: HTTP {exc.code}; is tools/shared.lock's commit for {self.repo} pushed?") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise Offline(f"{url}: {exc.reason if hasattr(exc, 'reason') else exc}") from exc

    def __repr__(self):
        return f"{self.repo} at {self.checkout or self.sha}"


def expected_hxlint(source: Source) -> str:
    src = source.read("hxlint.py")
    if IMPORT_FLASK not in src:
        sys.exit("hxlint.py no longer imports hx_vocab the way sync_shared expects")
    return src.replace(IMPORT_FLASK, IMPORT_DJANGO, 1)


def expected_vocab(source: Source) -> str:
    return source.read("hx_vocab.py")


def expected_mapcore(source: Source) -> str:
    src = source.read("mapcore.py")
    for flask, django in IMPORT_MAPCORE:
        if flask not in src:
            sys.exit("mapcore.py no longer imports the way sync_shared expects")
        src = src.replace(flask, django, 1)
    return src


def expected_urlconf(source: Source) -> str:
    """dj-fixi's body under dj-hx's docstring (the docstring names the package)."""
    theirs = source.read("dj_fixi/urlconf.py")
    ours = (PKG / "urlconf.py").read_text()
    marker = "from __future__ import annotations"
    return ours.split(marker, 1)[0] + marker + theirs.split(marker, 1)[1]


FROM_HX_FLASK = (("hxlint.py", expected_hxlint), ("hx_vocab.py", expected_vocab), ("mapcore.py", expected_mapcore))
FROM_DJ_FIXI = (("urlconf.py", expected_urlconf),)


def pinned() -> dict[str, str]:
    """``{"hx-flask": sha, "dj-fixi": sha}`` from tools/shared.lock."""
    return dict(line.split() for line in LOCK.read_text().splitlines() if line.strip() and not line.startswith("#"))


def pushed_head(checkout: pathlib.Path) -> str:
    """The checkout's HEAD, which must be on a remote branch, so GitHub serves the files at it."""
    git = lambda *args: subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, check=True).stdout  # noqa: E731
    sha = git("rev-parse", "HEAD").strip()
    if not git("branch", "-r", "--contains", sha).strip():
        sys.exit(f"{checkout} is at {sha[:12]}, which is on no remote branch. Push it first: the lock records a commit "
                 "GitHub must serve, or tests/test_shared_core.py fails everywhere but here.")
    if git("status", "--porcelain").strip():
        sys.exit(f"{checkout} has uncommitted changes; commit and push them first, so the lock names what was copied.")
    return sha


def main() -> None:
    sources = ((Source("hx-flask", HX_FLASK), FROM_HX_FLASK), (Source("dj-fixi", DJ_FIXI), FROM_DJ_FIXI))
    shas = {source.repo: pushed_head(source.checkout) for source, _ in sources}
    for source, files in sources:
        for name, expected in files:
            (PKG / name).write_text(expected(source))
            print(f"synced dj_hx/{name} from {source.repo} {shas[source.repo][:12]}")
    LOCK.write_text(
        "# The commit each vendored file was copied from, written by tools/sync_shared.py. tests/test_shared_core.py\n"
        "# fetches the files at these commits from GitHub and compares, so the pin holds in CI too.\n"
        + "".join(f"{repo} {sha}\n" for repo, sha in shas.items())
    )
    print(f"wrote {LOCK.relative_to(TOOLS.parent)}")


if __name__ == "__main__":
    main()
