from django.apps import AppConfig


class DeskConfig(AppConfig):
    # Installed by tests/settings.py for its label, which mints the routes, and for its static files.
    name = "tests.desk"
    label = "desk"
