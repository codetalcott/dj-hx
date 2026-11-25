"""An app's URLconf with a route of its own behind DEBUG, included by tests/urlconfs/gated.py."""

from django.conf import settings
from django.urls import path

from .gated import view

app_name = "app"

urlpatterns = [path("", view, name="index")]

if settings.DEBUG:
    urlpatterns += [path("explain/", view, name="explain")]
