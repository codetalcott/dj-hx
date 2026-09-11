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

import re
from pathlib import Path

from . import hxlint
from .hxlint import JINJA, Finding

__all__ = [
    "URLFOR",
    "template_directories",
    "iter_template_files",
    "template_sources",
    "strip_template_syntax",
    "lint_template_source",
]

URLFOR = "URLFOR:"

_COMMENT = re.compile(r"\{#.*?#\}|\{%\s*comment\b.*?%\}.*?\{%\s*endcomment\s*%\}", re.S)
_EXPR = re.compile(r"\{\{.*?\}\}", re.S)
_TAG = re.compile(r"\{%.*?%\}", re.S)
_URL_TAG = re.compile(r"\{%\s*url\s+(['\"])([\w:.-]+)\1(.*?)%\}", re.S)
_BLOCK_TAGS = re.compile(
    r"^(?:if|elif|else|endif|for|empty|endfor|block|endblock|extends|load|with|endwith|"
    r"spaceless|endspaceless|autoescape|endautoescape|verbatim|endverbatim|include|"
    r"blocktrans(?:late)?|endblocktrans(?:late)?|filter|endfilter|ifchanged|endifchanged|"
    r"partialdef|endpartialdef|partial|regroup|cycle|resetcycle|debug|templatetag|lorem|"
    r"comment|endcomment|csrf_token)\b"
)


def _keep_lines(match, filler: str) -> str:
    return "\n" * match.group(0).count("\n") + filler


def strip_template_syntax(source: str, *, url_marker: bool = False) -> str:
    """Django template source as HTML the parser can read, line numbers intact.

    With ``url_marker``, ``{% url 'name' ... %}`` becomes ``URLFOR:name`` so the
    map can resolve the control to its view.
    """
    source = _COMMENT.sub(lambda m: _keep_lines(m, ""), source)
    if url_marker:
        source = _URL_TAG.sub(
            lambda m: _keep_lines(m, JINJA if " as " in f" {m.group(3)} " else URLFOR + m.group(2)), source
        )
    source = _EXPR.sub(lambda m: _keep_lines(m, JINJA), source)

    def tag(m):
        body = m.group(0)[2:-2].strip()
        return _keep_lines(m, " " if _BLOCK_TAGS.match(body) else JINJA)

    return _TAG.sub(tag, source)


def lint_template_source(source: str, file: str | None = None, extensions=()) -> list[Finding]:
    """Findings for one template's source, without rendering it (page-level rules off)."""
    return hxlint.lint_html(
        strip_template_syntax(source), extensions=extensions, is_document=False, file=file, source_mode=True
    )


def template_directories() -> list[Path]:
    """
    Every directory a DjangoTemplates engine reads project templates from:
    ``DIRS`` plus app template directories, never site-packages.
    """
    import sysconfig

    from django.template import engines
    from django.template.backends.django import DjangoTemplates

    site = {Path(sysconfig.get_paths()[k]).resolve() for k in ("purelib", "platlib")}
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
            if path in seen or any(path.is_relative_to(s) for s in site):
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
