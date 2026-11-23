"""
The shared core is vendored, not forked: hxlint.py, hx_vocab.py and mapcore.py are hx-flask's, urlconf.py
is dj-fixi's. The copies must match the upstream files at the commits tools/shared.lock records, fetched
from GitHub, so the pin holds in CI with no neighbour checked out; and when a neighbour is checked out, they
must match it too, which says "upstream moved, run tools/sync_shared.py" the day it does.
"""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sync_shared  # noqa: E402
from sync_shared import FROM_DJ_FIXI, FROM_HX_FLASK, Offline, Source  # noqa: E402


def matches(source, files):
    for name, expected in files:
        try:
            want = expected(source)
        except Offline as exc:
            pytest.skip(f"cannot reach GitHub to check the pin: {exc}")
        assert (ROOT / "dj_hx" / name).read_text() == want, f"dj_hx/{name} differs from {source}: run tools/sync_shared.py"


@pytest.mark.parametrize("repo, files", [("hx-flask", FROM_HX_FLASK), ("dj-fixi", FROM_DJ_FIXI)])
def test_the_copies_match_the_pinned_upstream_commit(repo, files):
    """Enforced everywhere: the files at tools/shared.lock's commit, from GitHub."""
    sha = sync_shared.pinned()[repo]
    assert len(sha) == 40, f"tools/shared.lock: {repo}'s commit should be a full sha, not {sha!r}"
    matches(Source(repo, sha=sha), files)


@pytest.mark.skipif(not sync_shared.HX_FLASK.exists(), reason="hx-flask is not checked out")
def test_the_copies_match_the_hx_flask_checkout():
    matches(Source("hx-flask", sync_shared.HX_FLASK), FROM_HX_FLASK)


@pytest.mark.skipif(not sync_shared.DJ_FIXI.exists(), reason="dj-fixi is not checked out")
def test_the_copies_match_the_dj_fixi_checkout():
    matches(Source("dj-fixi", sync_shared.DJ_FIXI), FROM_DJ_FIXI)


def test_the_vocabulary_is_htmx_4():
    from dj_hx import hx_vocab

    assert hx_vocab.VERSION.startswith("4.")
