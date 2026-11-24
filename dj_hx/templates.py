"""
Project template source, for the static lint and the map.

The rendered-response lint is the surface that matters (``HxTestClient``);
this is the same rule set over template files, for ``manage.py hx_lint`` and
the ``dj_hx.W005`` check. Django template syntax is stripped first: ``{{ }}``
and value-producing tags (``{% url %}``, ``{% static %}``, custom tags)
become a computed value the rules do not judge; block tags become
whitespace; comments go. Line numbers survive.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

from . import hxlint
from .hxlint import JINJA, Finding, branch_marker

__all__ = [
    "URLFOR",
    "ACT_MARK",
    "ActTag",
    "UrlTag",
    "url_tags",
    "in_site_packages",
    "template_directories",
    "iter_template_files",
    "template_sources",
    "strip_template_syntax",
    "partial_sources",
    "lint_template_source",
]

URLFOR = "URLFOR:"
ACT_MARK = re.compile(r"__ACT(\d+)__")  # what strip_template_syntax(acts=...) leaves for the n-th {% act %}

_COMMENT = re.compile(r"\{#.*?#\}|\{%\s*comment\b.*?%\}.*?\{%\s*endcomment\s*%\}", re.S)
_EXPR = re.compile(r"\{\{.*?\}\}", re.S)
_TAG = re.compile(r"\{%.*?%\}", re.S)
_URL_TAG = re.compile(r"\{%\s*url\s+(['\"])([\w:.-]+)\1(.*?)%\}", re.S)
_ACT_TAG = re.compile(r"\{%\s*act\s+(.*?)%\}", re.S)
_KEYWORD = re.compile(r"^\w+=")  # as Django's token_kwargs reads a tag argument
_QUOTED = re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'" r'|"[^"\\]*(?:\\.[^"\\]*)*"')  # Django's constant_string, untranslated
_SITE_NAMES = ("site-packages", "dist-packages")
_PARTIALDEF = re.compile(r"\{%\s*(partialdef|endpartialdef)\b(.*?)%\}", re.S)
_BLOCK_TAGS = re.compile(
    r"^(?:if|elif|else|endif|for|empty|endfor|block|endblock|extends|load|with|endwith|"
    r"spaceless|endspaceless|autoescape|endautoescape|verbatim|endverbatim|include|"
    r"blocktrans(?:late)?|endblocktrans(?:late)?|filter|endfilter|ifchanged|endifchanged|"
    r"partialdef|endpartialdef|partial|regroup|cycle|resetcycle|debug|templatetag|lorem|"
    r"comment|endcomment|csrf_token)\b"
)


@dataclass(frozen=True)
class ActTag:
    """One ``{% act %}`` tag of a template's source, as the start-up checks read it."""

    line: int
    name: str | None  # None when a variable names the interaction
    keywords: tuple[str, ...]
    positional: int
    stored_as: str | None  # the variable of ``{% act ... as url %}``, which writes nothing where it stands


@dataclass(frozen=True)
class UrlTag:
    """One ``{% url %}`` tag of a template's source, as check E022 reads it."""

    line: int
    name: str | None  # None when the name is built at run time: a variable, or a filter on the name
    positional: int
    keywords: tuple[str, ...]
    stored_as: str | None  # the variable of ``{% url ... as var %}``, where a failed reverse stores ""


def tags_span_lines() -> bool:
    """
    Whether this Django's lexer reads a ``{% %}`` written across lines as a tag: true from 6.2
    (release notes, "Multiline template tags"), false before, when it is text. Asked of the lexer, not
    of the version, so a backport or a change of mind cannot make E022 silently wrong.
    """
    from django.template.base import Lexer, TokenType

    return Lexer("{% url\n'x' %}").tokenize()[0].token_type is TokenType.BLOCK


def url_tags(source: str) -> list[UrlTag]:
    """
    Every ``{% url %}`` tag in a template's source, read by Django's own lexer and split as its url
    tag splits one. A tag in a comment or in ``{% verbatim %}`` is not a tag. One written across lines
    is a tag from Django 6.2 (``tags_span_lines()``), and text before, which the lexer decides.
    """
    from django.template.base import Lexer, TokenType

    found: list[UrlTag] = []
    commented = False
    for token in Lexer(source).tokenize():
        if token.token_type is not TokenType.BLOCK:
            continue
        if commented:  # {% comment %} skips every token up to its {% endcomment %}, as the parser does
            commented = token.contents != "endcomment"
            continue
        bits = token.split_contents()
        if bits[:1] == ["comment"]:
            commented = True
            continue
        if bits[:1] != ["url"] or len(bits) < 2:
            continue
        name, arguments = bits[1], bits[2:]
        stored_as = None
        if len(arguments) >= 2 and arguments[-2] == "as":
            stored_as, arguments = arguments[-1], arguments[:-2]
        keywords = tuple(bit.split("=", 1)[0] for bit in arguments if _KEYWORD.match(bit))
        quoted = _QUOTED.fullmatch(name)
        assert token.lineno is not None  # Django numbers every token it lexes
        found.append(UrlTag(token.lineno, name[1:-1] if quoted else None, len(arguments) - len(keywords), keywords, stored_as))
    return found


def _keep_lines(match, filler: str) -> str:
    return "\n" * match.group(0).count("\n") + filler


def _act_tag(match, acts: list[ActTag]) -> str:
    from django.utils.text import smart_split

    bits = list(smart_split(match.group(1).strip()))
    stored_as = None
    if len(bits) >= 2 and bits[-2] == "as":
        stored_as, bits = bits[-1], bits[:-2]
    head, arguments = (bits[0], bits[1:]) if bits else ("", [])
    quoted = len(head) >= 2 and head[0] == head[-1] and head[0] in "'\""
    keywords = tuple(bit.split("=", 1)[0] for bit in arguments if _KEYWORD.match(bit))
    line = match.string.count("\n", 0, match.start()) + 1
    acts.append(ActTag(line, head[1:-1] if quoted else None, keywords, len(arguments) - len(keywords), stored_as))
    return _keep_lines(match, f"__ACT{len(acts) - 1}__")


def strip_template_syntax(source: str, *, url_marker: bool = False, acts: list[ActTag] | None = None) -> str:
    """Django template source as HTML the parser can read, line numbers intact.

    With ``url_marker``, ``{% url 'name' ... %}`` becomes ``URLFOR:name`` so the
    map can resolve the control to its view. With ``acts``, the n-th
    ``{% act %}`` becomes ``__ACT<n>__`` (``ACT_MARK``) and its ``ActTag`` is
    appended to ``acts``, so a check can tell which element's attribute holds it.
    """
    source = _COMMENT.sub(lambda m: _keep_lines(m, ""), source)
    if url_marker:
        source = _URL_TAG.sub(
            lambda m: _keep_lines(m, JINJA if " as " in f" {m.group(3)} " else URLFOR + m.group(2)), source
        )
    if acts is not None:
        source = _ACT_TAG.sub(lambda m: _act_tag(m, acts), source)
    source = _EXPR.sub(lambda m: _keep_lines(m, JINJA), source)

    def tag(m):
        # A branch tag ({% if %}, {% else %}, {% empty %}, ...) leaves hxlint's marker, so the lint knows which
        # elements cannot render together; another block tag leaves a space, a value tag the sentinel.
        body = m.group(0)[2:-2].strip()
        return _keep_lines(m, branch_marker(body) or (" " if _BLOCK_TAGS.match(body) else JINJA))

    return _TAG.sub(tag, source)


def partial_sources(source: str) -> dict[str, tuple[int, str]]:
    """
    ``{"notify": (line, body)}`` for each ``{% partialdef %}`` in a template's source: the source
    between its tags, comments dropped, and the line that source starts on.
    """
    source = _COMMENT.sub(lambda m: _keep_lines(m, ""), source)
    found: dict[str, tuple[int, str]] = {}
    opened: list[tuple[str, int]] = []
    for m in _PARTIALDEF.finditer(source):
        if m.group(1) == "partialdef":
            opened.append(((m.group(2).split() or [""])[0], m.end()))
        elif opened:
            name, start = opened.pop()
            found.setdefault(name, (source.count("\n", 0, start) + 1, source[start : m.start()]))
    return found


def lint_template_source(source: str, file: str | None = None, extensions=()) -> list[Finding]:
    """Findings for one template's source, without rendering it (page-level rules off)."""
    return hxlint.lint_html(
        strip_template_syntax(source), extensions=extensions, is_document=False, file=file, source_mode=True
    )


def in_site_packages(path) -> bool:
    """
    True for a path inside the interpreter's site-packages, so not the project's: sysconfig's
    ``purelib`` and ``platlib``, and the ``site-packages`` or ``dist-packages`` directories that
    ``site.getsitepackages()`` and ``site.getusersitepackages()`` report (distro layouts, ``pip
    install --user``). On Windows ``getsitepackages()`` also lists the prefix itself, which can
    hold the project, so only those two names count from ``site``. A virtualenv older than
    ``getsitepackages()`` lacks it, so each ``site`` call is guarded.
    """
    import site
    import sysconfig

    paths = sysconfig.get_paths()
    roots = [paths["purelib"], paths["platlib"]]
    for name in ("getsitepackages", "getusersitepackages"):
        try:
            found = getattr(site, name)()
        except Exception:  # AttributeError where an old virtualenv's site.py lacks it
            continue
        roots += [str(d) for d in ([found] if isinstance(found, str) else found) if Path(d).name in _SITE_NAMES]
    if isinstance(path, str):
        # A template's origin name can be a SafeString, and pathlib below Python 3.12 refuses to intern a str
        # subclass; str.__str__ gives the plain string (SafeString's own __str__ returns itself).
        path = str.__str__(path)
    path = Path(path).resolve()
    return any(path.is_relative_to(root) for root in _resolved(tuple(roots)))


@functools.lru_cache(maxsize=16)
def _resolved(directories: tuple[str, ...]) -> tuple[Path, ...]:
    """The site-packages roots, resolved once per set of directories rather than on every call."""
    return tuple(Path(d).resolve() for d in directories)


def template_directories() -> list[Path]:
    """
    Every directory a DjangoTemplates engine reads project templates from:
    ``DIRS`` plus app template directories, never site-packages.
    """
    from django.template import engines
    from django.template.backends.django import DjangoTemplates

    seen: list[Path] = []
    try:
        backends = list(engines.all())
    except Exception:
        return []
    for backend in backends:
        if not isinstance(backend, DjangoTemplates):
            continue
        dirs = list(backend.engine.dirs)
        for loader in backend.engine.template_loaders:
            dirs += getattr(loader, "get_dirs", lambda: [])()
        for d in dirs:
            path = Path(d).resolve()
            if path in seen or in_site_packages(path):
                continue
            seen.append(path)
    return seen


def iter_template_files(directories, suffixes=(".html", ".htm")):
    for directory in directories:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix in suffixes and path.is_file():
                yield path


def template_sources(directories=None) -> dict[str, str]:
    """``{"contacts/index.html": source}`` for every project template; first directory wins."""
    sources: dict[str, str] = {}
    for directory in directories if directories is not None else template_directories():
        directory = Path(directory)
        for path in iter_template_files([directory]):
            name = path.relative_to(directory).as_posix()
            if name not in sources:
                try:
                    sources[name] = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
    return sources
