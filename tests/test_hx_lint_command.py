"""manage.py hx_lint and the Django template stripper."""

import io
import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from dj_hx.templates import URLFOR, lint_template_source, lint_templates, strip_template_syntax


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


def test_ids_a_template_builds_are_not_one_id():
    # A production form gave two fields' {{ field.id_for_label }}; 0.1.0 reported them as one id twice.
    source = '<input id="{{ form.name.id_for_label }}"><input id="{{ form.collaborator_emails.id_for_label }}">'
    assert lint_template_source(source) == []
    assert rules(lint_template_source('<i id="spin"></i><i id="spin"></i>')) == ["duplicate-id"]


def test_an_id_in_branches_only_one_of_which_renders_counts_once():
    # A private app with no htmx: <img id="composite-image"> in each branch of {% if %} / {% else %}.
    assert lint_template_source('{% if a %}<h2 id="t">A</h2>{% else %}<h2 id="t">B</h2>{% endif %}') == []
    assert lint_template_source('{% for r in rows %}<p id="t">{{ r }}</p>{% empty %}<p id="t">-</p>{% endfor %}') == []
    assert lint_template_source('{% ifchanged r.day %}<h3 id="t"></h3>{% else %}<hr id="t">{% endifchanged %}') == []
    across = '{% if a %}\n  <div>\n    <img id="t">\n  </div>\n{% elif b %}\n  <img id="t">\n{% endif %}'
    assert lint_template_source(across) == []
    # Both can render: separate {% if %}s, or one outside the branch.
    assert rules(lint_template_source('{% if a %}<i id="t"></i>{% endif %}{% if b %}<b id="t"></b>{% endif %}')) == ["duplicate-id"]
    assert rules(lint_template_source('<i id="t"></i>{% if a %}<b id="t"></b>{% endif %}')) == ["duplicate-id"]
    # A branch inside a start tag keeps the attribute after it, and the line numbers stay the source's.
    findings = lint_template_source('<p>\n{% if a %}<button {% if b %}hx-swap="sideways"{% endif %}>x</button>{% endif %}')
    assert [(f.rule, f.line) for f in findings] == [("unknown-swap-style", 2)]


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


def test_command_json_is_one_object_for_a_script_and_the_same_exit_status(tmp_path):
    (tmp_path / "bad.html").write_text('<button hx-post="/x/" hx-vars="a:1">x</button>\n<a hx-get="/y/" hx-swap="outerhtml">y</a>')
    (tmp_path / "warn.html").write_text('<div hx-target="#t"><button hx-post="/a/">a</button></div>')
    out = io.StringIO()
    with pytest.raises(CommandError, match="2 error"):
        call_command("hx_lint", str(tmp_path), "--json", stdout=out)
    report = json.loads(out.getvalue())  # nothing else on stdout
    assert {k: report[k] for k in ("templates", "errors", "warnings", "unreadable")} == {
        "templates": 2, "errors": 2, "warnings": 1, "unreadable": []
    }
    assert [(Path(f["file"]).name, f["line"], f["rule"], f["severity"], f["element"]) for f in report["findings"]] == [
        ("bad.html", 1, "htmx2-attribute", "error", "button"),
        ("bad.html", 2, "swap-style-case", "error", "a"),
        ("warn.html", 1, "implicit-inheritance", "warning", "div"),
    ]
    assert all(f["message"] for f in report["findings"])
    out = io.StringIO()
    with pytest.raises(CommandError, match="1 error"):  # counted as the exit status counts; severities kept
        call_command("hx_lint", str(tmp_path / "warn.html"), "--json", "--warnings-as-errors", stdout=out)
    report = json.loads(out.getvalue())
    assert (report["errors"], report["warnings"], report["findings"][0]["severity"]) == (1, 0, "warning")
    out = io.StringIO()
    call_command("hx_lint", str(tmp_path / "warn.html"), "--json", stdout=out)
    assert json.loads(out.getvalue())["errors"] == 0


def test_lint_templates_is_the_commands_run_for_a_projects_own_test(tmp_path):
    """A project's ratchet reads this rather than dj_hx.templates' pieces, so it cannot drift from hx_lint."""
    from django.test import override_settings

    (tmp_path / "bad.html").write_text('<a hx-get="/y/" hx-swap="outerhtml">y</a>\n<div hx-target="#t"><button hx-post="/a/">a</button></div>')
    run = lint_templates([tmp_path])
    assert run.files == [tmp_path / "bad.html"] and run.unreadable == []
    assert [(f.rule, f.line) for f in run.findings] == [("swap-style-case", 1), ("implicit-inheritance", 2)]
    with override_settings(HX_LINT_IGNORE=["implicit-inheritance"]):
        assert [f.rule for f in lint_templates([tmp_path]).findings] == ["swap-style-case"]
    assert len(lint_templates().files) == 6  # by default, the project's template directories


def test_command_defaults_to_the_projects_template_directories():
    out = io.StringIO()
    call_command("hx_lint", stdout=out)
    assert "6 template(s), 0 error(s), 0 warning(s)" in out.getvalue()


def test_the_tools_run_while_check_fails(tmp_path, capsys):
    """A private app's five E022s, in templates nothing rendered, stopped hx_lint and hx_map, which W005 points to."""
    from django.core.management import load_command_class
    from django.test import override_settings

    from dj_hx.testing import hx_check_messages
    from tests.conftest import on_disk

    (tmp_path / "dead.html").write_text("<a href=\"{% url 'gone' %}\">x</a>\n<img id=\"t\"><img id=\"t\">")
    with override_settings(ROOT_URLCONF="tests.urlconfs.reversing", TEMPLATES=on_disk(tmp_path)):
        assert "dj_hx.E022" in {m.id for m in hx_check_messages()}  # manage.py check fails
        with pytest.raises(SystemExit):  # the lint's own error, not the system check's
            load_command_class("dj_hx", "hx_lint").run_from_argv(["manage.py", "hx_lint"])
        out, err = capsys.readouterr()
        assert "hx_lint: 1 template(s), 1 error(s)" in out and "SystemCheckError" not in err
        load_command_class("dj_hx", "hx_map").run_from_argv(["manage.py", "hx_map"])
        assert "hx map: 0 controls" in capsys.readouterr().out
