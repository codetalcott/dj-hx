"""The system checks: quiet on the example project, and each one on its own defect."""

import pytest
from django.conf import settings
from django.test import override_settings

from dj_hx.testing import assert_no_hx_check_issues, hx_check_messages


def ids():
    return sorted(m.id for m in hx_check_messages())


def test_the_example_project_passes_every_check():
    assert_no_hx_check_issues()


def test_w001_when_the_middleware_is_absent():
    with override_settings(MIDDLEWARE=[m for m in settings.MIDDLEWARE if "dj_hx" not in m]):
        assert ids() == ["dj_hx.W001"]


def test_e002_when_listed_before_message_middleware():
    ours = "dj_hx.middleware.HxMiddleware"
    theirs = "django.contrib.messages.middleware.MessageMiddleware"
    order = [m for m in settings.MIDDLEWARE if m not in (ours, theirs)] + [ours, theirs]
    with override_settings(MIDDLEWARE=order):
        messages = hx_check_messages()
    assert [m.id for m in messages] == ["dj_hx.E002"] and "Move HxMiddleware below MessageMiddleware" in messages[0].hint


def test_w003_and_w004_for_the_messages_template():
    with override_settings(HX_MESSAGES_TEMPLATE=None):
        assert ids() == ["dj_hx.W003"]
    with override_settings(HX_MESSAGES_TEMPLATE="layout.html#flash"):
        messages = hx_check_messages()
    assert [m.id for m in messages] == ["dj_hx.W004"] and "partialdef flash" in messages[0].hint


def test_w005_names_the_template_and_the_rule(tmp_path):
    (tmp_path / "old.html").write_text('{# <div hx-ext="sse"> #}\n<div hx-ext="sse" hx-swap="outerhtml"></div>')
    (tmp_path / "fine.html").write_text('<div hx-get="{% url \'x\' %}" hx-swap="outerHTML swap:1s"></div>')
    templates = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [tmp_path], "APP_DIRS": False}]
    with override_settings(TEMPLATES=templates, HX_MESSAGES_TEMPLATE=None):
        messages = [m for m in hx_check_messages() if m.id == "dj_hx.W005"]
    assert len(messages) == 1 and messages[0].obj.endswith("old.html")
    assert "htmx2-attribute" in messages[0].msg and "swap-style-case" in messages[0].msg and "line 2" in messages[0].hint
    with override_settings(TEMPLATES=templates, HX_MESSAGES_TEMPLATE=None, HX_LINT_IGNORE=["htmx2-attribute", "swap-style-case"]):
        assert "dj_hx.W005" not in ids()


def test_w006_only_below_django_6(monkeypatch, settings):
    import django

    from dj_hx import checks

    settings.INSTALLED_APPS = [a for a in settings.INSTALLED_APPS if a != "template_partials"]
    monkeypatch.setattr(django, "VERSION", (5, 2, 0, "final", 0))
    assert [m.id for m in checks.check_partials_available()] == ["dj_hx.W006"]
    monkeypatch.setattr(django, "VERSION", (6, 0, 0, "final", 0))
    assert checks.check_partials_available() == []


def test_checks_stay_quiet_when_dj_hx_is_not_installed():
    with override_settings(INSTALLED_APPS=[a for a in settings.INSTALLED_APPS if a != "dj_hx"], HX_MESSAGES_TEMPLATE=None):
        assert ids() == []


@pytest.mark.parametrize("silenced", [["dj_hx.W003"]])
def test_silenced_system_checks_is_honored(silenced):
    with override_settings(HX_MESSAGES_TEMPLATE=None, SILENCED_SYSTEM_CHECKS=silenced):
        assert_no_hx_check_issues()
