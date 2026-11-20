from django.apps import AppConfig


class RotaConfig(AppConfig):
    # A label unlike any part of the module path, so a minted route shows it came from the label.
    name = "tests.interactions_app"
    label = "rota"
