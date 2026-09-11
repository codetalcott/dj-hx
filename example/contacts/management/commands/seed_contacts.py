"""manage.py seed_contacts: the book's hundred contacts, replacing whatever is there."""

from pathlib import Path

from django.core.management.base import BaseCommand

from contacts.models import Contact

DATA = Path(__file__).resolve().parents[2] / "contacts.json"


class Command(BaseCommand):
    help = "Load the book's contacts.json into the database (replaces existing rows)."

    def handle(self, *args, **options):
        n = Contact.load_from_json(DATA)
        self.stdout.write(f"loaded {n} contacts")
