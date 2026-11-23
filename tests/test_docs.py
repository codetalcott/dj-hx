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


PARTIALS = re.compile(r"{% partialdef \w+ inline %}\s*(<[^>]*>)(.*?){% endpartialdef %}", re.S)


@pytest.mark.parametrize("doc", ["README.md", "llms.txt"])
def test_every_interaction_partial_the_docs_show_carries_the_policy(doc):
    """A reader copies the first example they see, so every partial with an {% act %} control carries the pair."""
    shown = [root for block in FENCED.findall((ROOT / doc).read_text()) for root, body in PARTIALS.findall(block) if "{% act " in body]
    for root in shown:
        assert STATUS.findall(root) == STATUS.findall(ROOTS.findall(DESK)[0]), root


# ------------------------------------------------------------- the catalogue

ROW = re.compile(r"^\| (?P<title>[^|]+?) \| [^|]+ \| \[more\]\(FAILURES\.md#(?P<anchor>[a-z0-9-]+)\) \|$", re.M)
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
