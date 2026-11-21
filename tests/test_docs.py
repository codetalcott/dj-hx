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
    """The code blocks of ``path`` between the line that starts with ``start`` and the next one with ``end``."""
    text = (ROOT / path).read_text()
    begin = text.index(start)
    return "\n".join(FENCED.findall(text[begin : text.index(end, begin + len(start))]))


def flat(html):
    return " ".join(html.split())


DOCS = {
    "README.md": section("README.md", "### The status policy", "\n## "),
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
