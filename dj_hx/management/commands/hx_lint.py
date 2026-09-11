"""
manage.py hx_lint [paths...] [--warnings-as-errors]

The htmx 4 lint over template source, without rendering: htmx 2 attributes
and event names, implicit inheritance, unknown swap styles and trigger
modifiers. Every project template directory by default, never site-packages.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from dj_hx.templates import iter_template_files, lint_template_source, template_directories


class Command(BaseCommand):
    help = "Lint template source for the htmx 4 vocabulary (htmx 2 idioms, typos, inheritance)."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*", help="Template files or directories. Default: every project template directory.")
        parser.add_argument("--warnings-as-errors", action="store_true", help="Exit non-zero on warnings too.")

    def handle(self, *args, paths, warnings_as_errors, **options):
        roots = [Path(p) for p in paths] or template_directories()
        files = []
        for root in roots:
            files += [root] if root.is_file() else list(iter_template_files([root]))
        ignore = set(getattr(settings, "HX_LINT_IGNORE", ()))
        errors = warnings = 0
        for path in files:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                self.stderr.write(f"{path}: {exc}")
                continue
            for f in lint_template_source(source, file=str(path), extensions=getattr(settings, "HX_EXTENSIONS", ())):
                if f.rule in ignore or f.severity == "info":
                    continue
                if f.severity == "error" or warnings_as_errors:
                    errors += 1
                    self.stdout.write(self.style.ERROR(str(f)))
                else:
                    warnings += 1
                    self.stdout.write(self.style.WARNING(str(f)))
        self.stdout.write(f"hx_lint: {len(files)} template(s), {errors} error(s), {warnings} warning(s)")
        if errors:
            raise CommandError(f"{errors} error(s)")
