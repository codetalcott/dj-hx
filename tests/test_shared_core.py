"""
The shared core is vendored, not forked: hxlint.py, hx_vocab.py and mapcore.py
are hx-flask's, urlconf.py is dj-fixi's. When the neighbours are checked out,
the copies must match what tools/sync_shared.py would write.
"""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sync_shared  # noqa: E402


@pytest.mark.skipif(not sync_shared.HX_FLASK.exists(), reason="hx-flask is not checked out")
def test_hxlint_and_vocab_match_hx_flask():
    assert (ROOT / "dj_hx" / "hxlint.py").read_text() == sync_shared.expected_hxlint()
    assert (ROOT / "dj_hx" / "hx_vocab.py").read_text() == sync_shared.expected_vocab()
    assert (ROOT / "dj_hx" / "mapcore.py").read_text() == sync_shared.expected_mapcore()


@pytest.mark.skipif(not sync_shared.DJ_FIXI.exists(), reason="dj-fixi is not checked out")
def test_urlconf_matches_dj_fixi():
    assert (ROOT / "dj_hx" / "urlconf.py").read_text() == sync_shared.expected_urlconf()


def test_the_vocabulary_is_htmx_4():
    from dj_hx import hx_vocab

    assert hx_vocab.VERSION.startswith("4.")
