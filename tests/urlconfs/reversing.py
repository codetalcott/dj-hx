"""
Routes for check E022: each of Django's converters, a custom one, a re_path, a namespace whose prefix takes
one, and routes chosen by their extra kwargs (one name on two routes, told apart by fmt).
"""

from django.http import HttpResponse
from django.urls import include, path, re_path, register_converter


class FourDigitYear:
    regex = "[0-9]{4}"

    def to_python(self, value):
        return int(value)

    def to_url(self, value):
        return f"{value:04d}"


register_converter(FourDigitYear, "yyyy")


def view(request, **kwargs):
    return HttpResponse("")


shop = (
    [path("cart/", view, name="cart"), path("items/<slug:item>/", view, name="item")],
    "shop",
)

urlpatterns = [
    path("", view, name="home"),
    path("contacts/<int:contact_id>/edit/", view, name="contacts_edit"),
    path("pages/<str:title>/", view, name="page"),
    path("tags/<slug:tag>/", view, name="tag"),
    path("files/<path:rest>", view, name="file"),
    path("tokens/<uuid:token>/", view, name="token"),
    path("archive/<yyyy:year>/", view, name="archive"),
    re_path(r"^legacy/(?P<code>[A-Z]{3})/$", view, name="legacy"),
    path("stores/<int:store>/", include(shop)),
    path("feed/", view, {"fmt": "rss"}, name="feed"),
    path("feed.atom", view, {"fmt": "atom"}, name="feed"),
    path("blog/", view, {"page": 1}, name="blog"),
]
