"""
manage.py hx_map [--no-check] [--by-template | --json]

Every control in the project's templates mapped to the view that answers it,
classified full or partial by htmx 4's own rule, and checked against the
verbs the view calls; the events views announce and the elements that listen.

``--by-template`` reads the same map from the other end: every template and
partial a view names, and who renders it. ``--json`` prints the whole map as
one JSON object (``mapcore.map_json()``), with the same exit status.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from dj_hx.hxmap import print_map


class Command(BaseCommand):
    help = "Map every htmx control in the templates to the view that answers it, and check the agreement."
    # A diagnostic runs while manage.py check fails, so the map can show what the failure is about.
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--no-check", action="store_true", help="Print the map without the checks.")
        view = parser.add_mutually_exclusive_group()
        view.add_argument("--by-template", action="store_true", help="Group by template and partial: who renders each one.")
        view.add_argument(
            "--json", action="store_true", dest="as_json", help="Print the map as one JSON object; the exit status is the same."
        )

    def handle(self, *args: Any, no_check: bool, by_template: bool, as_json: bool, **options: Any) -> None:
        if print_map(check=not no_check, out=self.stdout, by_template=by_template, as_json=as_json):
            raise CommandError("hx_map found errors")
