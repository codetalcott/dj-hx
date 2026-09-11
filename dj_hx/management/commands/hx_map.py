"""
manage.py hx_map [--no-check]

Every control in the project's templates mapped to the view that answers it,
classified full or partial by htmx 4's own rule, and checked against the
verbs the view calls; the events views announce and the elements that listen.
"""

from django.core.management.base import BaseCommand, CommandError

from dj_hx.hxmap import print_map


class Command(BaseCommand):
    help = "Map every htmx control in the templates to the view that answers it, and check the agreement."

    def add_arguments(self, parser):
        parser.add_argument("--no-check", action="store_true", help="Print the map without the checks.")

    def handle(self, *args, no_check, **options):
        if print_map(check=not no_check, out=self.stdout):
            raise CommandError("hx_map found errors")
