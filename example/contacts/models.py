"""
The book's Contact model on the ORM. Same surface as contacts_model.py in
Hypermedia Systems: ``errors``, ``validate()``, ``all(page)``, ``search()``,
``count()`` (slow on purpose, to demonstrate lazy loading), and the Archiver.
"""

import json
import threading
import time
from random import random

from django.db import models

PAGE_SIZE = 10


class Contact(models.Model):
    first = models.CharField(max_length=100, blank=True)
    last = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=254, blank=True)

    class Meta:
        ordering = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.errors = {}

    def __str__(self):
        return json.dumps({"id": self.id, "first": self.first, "last": self.last, "phone": self.phone, "email": self.email})

    def update(self, first, last, phone, email):
        self.first, self.last, self.phone, self.email = first, last, phone, email

    def validate(self) -> bool:
        self.errors = {}
        if not self.email:
            self.errors["email"] = "Email Required"
        elif Contact.objects.filter(email=self.email).exclude(pk=self.pk).exists():
            self.errors["email"] = "Email Must Be Unique"
        return not self.errors

    @classmethod
    def count(cls) -> int:
        time.sleep(2)
        return cls.objects.count()

    @classmethod
    def all(cls, page=1):
        page = int(page)
        start = (page - 1) * PAGE_SIZE
        return list(cls.objects.all()[start : start + PAGE_SIZE])

    @classmethod
    def search(cls, text):
        q = models.Q(first__contains=text) | models.Q(last__contains=text) | models.Q(email__contains=text) | models.Q(phone__contains=text)
        return list(cls.objects.filter(q))

    @classmethod
    def find(cls, id_):
        contact = cls.objects.filter(pk=int(id_)).first()
        if contact is not None:
            contact.errors = {}
        return contact

    @classmethod
    def load_from_json(cls, path) -> int:
        with open(path) as f:
            rows = json.load(f)
        cls.objects.all().delete()
        cls.objects.bulk_create(cls(id=r["id"], first=r["first"], last=r["last"], phone=r["phone"], email=r["email"]) for r in rows)
        return len(rows)


class Archiver:
    archive_status = "Waiting"
    archive_progress = 0
    thread = None

    def status(self):
        return Archiver.archive_status

    def progress(self):
        return Archiver.archive_progress

    def run(self):
        if Archiver.archive_status == "Waiting":
            Archiver.archive_status = "Running"
            Archiver.archive_progress = 0
            Archiver.thread = threading.Thread(target=self.run_impl, daemon=True)
            Archiver.thread.start()

    def run_impl(self):
        for i in range(10):
            time.sleep(1 * random())
            if Archiver.archive_status != "Running":
                return
            Archiver.archive_progress = (i + 1) / 10
        time.sleep(1)
        if Archiver.archive_status != "Running":
            return
        Archiver.archive_status = "Complete"

    def archive_content(self) -> str:
        return json.dumps([json.loads(str(c)) for c in Contact.objects.all()], indent=2)

    def reset(self):
        Archiver.archive_status = "Waiting"

    @classmethod
    def get(cls):
        return Archiver()
