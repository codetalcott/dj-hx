"""
Every interaction's route. Include it once, at the site root::

    path("", include("dj_hx.urls"))

The routes reverse under the ``dj_hx`` namespace (``{% act %}`` does that). A minted route carries its
own ``x/`` prefix; a ``route=`` path is used as given.
"""

from .interactions import urlpatterns  # noqa: F401  filled by @interaction as each app's views module is imported

app_name = "dj_hx"
