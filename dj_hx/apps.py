"""App configuration: registers the system checks and imports the project's interactions."""

from django.apps import AppConfig


class DjHxConfig(AppConfig):
    name = "dj_hx"
    label = "dj_hx"
    verbose_name = "dj-hx"

    def ready(self):
        from . import checks  # noqa: F401  (registration side effect)
        from .interactions import import_views

        # Interactions live in <app>/views.py; importing each now registers every route before the
        # URLconf is first read, whatever order the project's urls.py imports things in.
        import_views()
