"""
Routes for check W027: names a module-level if, elif or else adds only on a branch the suite's settings do not
take (LANGUAGE_SWITCHER and BETA are unset, DEBUG is off), here and in an app's URLconf it includes.
"""

from django.conf import settings
from django.http import HttpResponse
from django.urls import include, path


def view(request, **kwargs):
    return HttpResponse("")


panel = ([path("panel/", view, name="panel")], "debug")

urlpatterns = [
    path("", view, name="home"),
    path("app/", include("tests.urlconfs.gated_app")),
]

if getattr(settings, "LANGUAGE_SWITCHER", False):
    urlpatterns = [path("i18n/", include("django.conf.urls.i18n"))] + urlpatterns
elif getattr(settings, "BETA", False):
    urlpatterns += [path("beta/", view, name="beta")]
else:
    urlpatterns += [path("closed/", view, name="closed")]  # the branch taken here

if settings.DEBUG:
    urlpatterns += [path("debug/", include(panel))]
