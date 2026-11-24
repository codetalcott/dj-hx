"""
manage.py hx_lint [paths...] [--warnings-as-errors] [--json]

The htmx 4 lint over template source, without rendering: htmx 2 attributes
and event names, implicit inheritance, unknown swap styles and trigger
modifiers. Every project template directory by default, never site-packages.

``--json`` prints one JSON object instead of lines (``templates``, ``errors``,
``warnings``, ``findings``, ``unreadable``); the exit status is the same.
``dj_hx.templates.lint_templates()`` is the same run, for a test.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from dj_hx.templates import lint_templates


class Command(BaseCommand):
    help = "Lint template source for the htmx 4 vocabulary (htmx 2 idioms, typos, inheritance)."
    # A diagnostic runs while manage.py check fails: check's W005 hint sends you here to read the whole list.
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("paths", nargs="*", help="Template files or directories. Default: every project template directory.")
        parser.add_argument("--warnings-as-errors", action="store_true", help="Exit non-zero on warnings too.")
        parser.add_argument(
            "--json", action="store_true", dest="as_json", help="Print one JSON object instead of lines; the exit status is the same."
        )

    def handle(self, *args: Any, paths: list[str], warnings_as_errors: bool, as_json: bool, **options: Any) -> None:
        run = lint_templates(paths)
        errors = sum(f.severity == "error" or warnings_as_errors for f in run.findings)
        warnings = len(run.findings) - errors
        if as_json:
            # Counted as the exit status counts them; each finding keeps its own severity.
            report = {
                "templates": len(run.files),
                "errors": errors,
                "warnings": warnings,
                "findings": [
                    {"file": f.file, "line": f.line, "rule": f.rule, "severity": f.severity, "element": f.element, "message": f.message}
                    for f in run.findings
                ],
                "unreadable": [{"file": str(path), "error": problem} for path, problem in run.unreadable],
            }
            self.stdout.write(json.dumps(report, indent=2))
        else:
            for path, problem in run.unreadable:
                self.stderr.write(f"{path}: {problem}")
            for f in run.findings:
                style = self.style.ERROR if f.severity == "error" or warnings_as_errors else self.style.WARNING
                self.stdout.write(style(str(f)))
            self.stdout.write(f"hx_lint: {len(run.files)} template(s), {errors} error(s), {warnings} warning(s)")
        if errors:
            raise CommandError(f"{errors} error(s)")
