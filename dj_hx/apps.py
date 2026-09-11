"""App configuration. Its only job is to register the system checks."""

from django.apps import AppConfig


class DjHxConfig(AppConfig):
    name = "dj_hx"
    label = "dj_hx"
    verbose_name = "dj-hx"

    def ready(self):
        from . import checks  # noqa: F401  (registration side effect)
