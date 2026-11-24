"""
The status policy README and llms.txt show is the one tests/test_interactions_browser.py measures: the
desk's layout (tests/desk/pages/layout.html) and its partials' roots (desk.html). Each doc's code blocks are
compared with those files element by element, so a doc cannot drift from what was measured.
"""

import re

import pytest

from tests.conftest import DESK_PAGES, ROOT

ALERT = re.compile(r'<p id="trouble".*?</p>', re.S)
BODY = re.compile(r"<body\b[^>]*>")
STATUS = re.compile(r'hx-status:[^\s=]+="[^"]*"')
ROOTS = re.compile(r"{% partialdef \w+ inline %}\s*(<[^>]*>)")
FENCED = re.compile(r"```[a-z]*\n(.*?)```", re.S)

LAYOUT = (DESK_PAGES / "layout.html").read_text()
DESK = (DESK_PAGES / "desk.html").read_text()


def section(path, start, end):
    """The code blocks of ``path`` from ``start`` to the next ``end``, or to the end of the file."""
    text = (ROOT / path).read_text()
    begin = text.index(start)
    stop = text.find(end, begin + len(start))
    return "\n".join(FENCED.findall(text[begin : stop if stop != -1 else len(text)]))


def flat(html):
    return " ".join(html.split())


DOCS = {
    "README.md": section("README.md", "### The status policy", "\n## "),
    "INTERACTIONS.md": section("INTERACTIONS.md", "## The status policy", "\n## "),
    "llms.txt": section("llms.txt", "Status policy for a site with interactions", "\n### "),
}


def test_every_partial_root_on_the_desk_carries_the_policy():
    roots = ROOTS.findall(DESK)
    assert len(roots) == 7
    for root in roots:
        assert STATUS.findall(root) == ['hx-status:40x:inherited="swap:none"', 'hx-status:5xx:inherited="swap:none"'], root
    assert "htmx-config" not in LAYOUT  # htmx's own noSwap, [204, 304], is left alone


@pytest.mark.parametrize("doc", DOCS)
def test_the_status_policy_in_the_docs_is_the_measured_desk(doc):
    blocks = DOCS[doc]
    assert STATUS.findall(blocks) == STATUS.findall(ROOTS.findall(DESK)[0])
    assert [flat(a) for a in ALERT.findall(blocks)] == [flat(a) for a in ALERT.findall(LAYOUT)]
    for body in BODY.findall(blocks):  # llms.txt shows no <body>
        assert body == BODY.search(LAYOUT).group()
    assert "htmx-config" not in blocks


PARTIALS = re.compile(r"{% partialdef \w+ inline %}\s*(<[^>]*>)(.*?){% endpartialdef %}", re.S)


@pytest.mark.parametrize("doc", ["README.md", "INTERACTIONS.md", "llms.txt"])
def test_every_interaction_partial_the_docs_show_carries_the_policy(doc):
    """A reader copies the first example they see, so every partial with an {% act %} control carries the pair."""
    shown = [root for block in FENCED.findall((ROOT / doc).read_text()) for root, body in PARTIALS.findall(block) if "{% act " in body]
    for root in shown:
        assert STATUS.findall(root) == STATUS.findall(ROOTS.findall(DESK)[0]), root


# ------------------------------------------------------------- the catalogue

ROW = re.compile(r"^\| (?P<title>[^|]+?) \| [^|]+ \| \[more\]\(https://github\.com/codetalcott/dj-hx/blob/main/FAILURES\.md#(?P<anchor>[a-z0-9-]+)\) \|$", re.M)
HEADING = re.compile(r"^## (.+)$", re.M)


def test_every_readme_row_has_its_failures_entry_in_the_same_order():
    """README's "What is loud" table and FAILURES.md are one catalogue: same rows, same order, working anchors."""
    readme = (ROOT / "README.md").read_text()
    table = readme[readme.index("## What is loud") : readme.index("\n## Testing")]
    rows = ROW.findall(table)
    headings = HEADING.findall((ROOT / "FAILURES.md").read_text())
    assert len(rows) >= 31
    assert [title for title, _ in rows] == headings
    for title, anchor in rows:
        assert anchor == re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-"), title


# ------------------------------------------------------------- the client swap

SWAP = re.compile(r"```python\n(import django\.test\n.*?)```", re.S)

SUITE = """
from django.test import Client, SimpleTestCase, TestCase

from dj_hx.testing import HxTestClient


def test_pytest_djangos_fixture(client):
    assert type(client) is HxTestClient


def test_a_client_a_test_builds():
    assert type(Client()) is HxTestClient


class ASimpleTestCase(SimpleTestCase):
    def test_its_client(self):
        assert type(self.client) is HxTestClient


class ATestCase(TestCase):
    def test_its_client(self):
        assert type(self.client) is HxTestClient
"""


def test_readmes_client_swap_reaches_every_client_a_suite_builds(tmp_path):
    """README's conftest.py, run as written in a new suite: pytest-django's client, Client() and TestCase's."""
    import os
    import subprocess
    import sys

    (tmp_path / "conftest.py").write_text(SWAP.search((ROOT / "README.md").read_text()).group(1))
    (tmp_path / "test_swap.py").write_text(SUITE)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "example")])}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--ds=tests.settings", "--rootdir", str(tmp_path), str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert "4 passed" in result.stdout, result.stdout + result.stderr
