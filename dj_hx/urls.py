"""
Every interaction's route. Include it once, at the site root::

    path("", include("dj_hx.urls"))

The routes reverse under the ``dj_hx`` namespace (``{% act %}`` does that). A minted route carries its
own ``x/`` prefix; a ``route=`` path is used as given.
"""

from .interactions import (  # noqa: F401  filled by @interaction as each interactions module is imported
    bind_routes,
    urlpatterns,
)

app_name = "dj_hx"

# First read after ready() has imported every interactions module, so each route can point at what its module
# holds under the handler's name: a view decorator written above @interaction then wraps the route.
bind_routes()
