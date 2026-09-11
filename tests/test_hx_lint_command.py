"""manage.py hx_lint and the Django template stripper."""

import io

import pytest
from django.core.management import CommandError, call_command

from dj_hx.templates import URLFOR, lint_template_source, strip_template_syntax


def rules(findings):
    return [f.rule for f in findings]


def test_template_syntax_becomes_html_the_parser_can_judge():
    source = (
        '{% load static %}{# <a hx-ext="sse"> #}\n'
        "<a hx-get=\"{% url 'x' pk %}\" hx-swap=\"outerhtml\">x</a>\n"
        '{% if ok %}<b hx-target="{{ sel }}" hx-get="{{ u }}" hx-trigger="load delay:{{ d }}">z</b>{% endif %}\n'
        '{% comment %}\nhx-vars="a:1"\n{% endcomment %}<form>{% csrf_token %}<button hx-delete="/c/">d</button></form>'
    )
    findings = lint_template_source(source, file="t.html")
    assert rules(findings) == ["swap-style-case", "delete-without-include", "delete-default-swap"]
    assert findings[0].line == 2 and findings[0].file == "t.html"
    assert findings[1].line == 6  # comment lines still count
    stripped = strip_template_syntax(source)
    assert "hx-ext" not in stripped and "hx-vars" not in stripped
    assert strip_template_syntax(source, url_marker=True).count(URLFOR + "x") == 1
    assert URLFOR not in strip_template_syntax("{% url 'x' as u %}<a hx-get=\"{{ u }}\">", url_marker=True)


def test_source_mode_leaves_page_level_rules_off():
    assert lint_template_source('<a hx-get="/x/" hx-target="#defined-in-layout">x</a>') == []


def test_command_reports_findings_with_file_and_line_and_fails(tmp_path):
    (tmp_path / "bad.html").write_text('<button hx-post="/x/" hx-vars="a:1">x</button>\n<a hx-get="/y/" hx-swap="outerhtml">y</a>')
    out = io.StringIO()
    with pytest.raises(CommandError, match="2 error"):
        call_command("hx_lint", str(tmp_path), stdout=out)
    text = out.getvalue()
    assert "htmx2-attribute" in text and f"{tmp_path / 'bad.html'}:1" in text
    assert "swap-style-case" in text and "bad.html:2" in text
    assert "1 template(s), 2 error(s), 0 warning(s)" in text


def test_command_is_quiet_on_clean_templates_and_strict_on_request(tmp_path):
    (tmp_path / "ok.html").write_text('<a hx-get="{% url \'x\' %}" hx-target="closest tr">x</a>')
    (tmp_path / "warn.html").write_text('<div hx-target="#t"><button hx-post="/a/">a</button></div>')
    out = io.StringIO()
    call_command("hx_lint", str(tmp_path / "ok.html"), stdout=out)
    assert "1 template(s), 0 error(s), 0 warning(s)" in out.getvalue()
    call_command("hx_lint", str(tmp_path / "warn.html"), stdout=io.StringIO())
    with pytest.raises(CommandError):
        call_command("hx_lint", str(tmp_path / "warn.html"), warnings_as_errors=True, stdout=io.StringIO())


def test_command_defaults_to_the_projects_template_directories():
    out = io.StringIO()
    call_command("hx_lint", stdout=out)
    assert "6 template(s), 0 error(s), 0 warning(s)" in out.getvalue()
