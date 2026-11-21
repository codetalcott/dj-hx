"""
The desk's page and its interactions. Not named views.py, so dj-hx's ready() does not register them for the
whole suite, beside the rota app's: the ``desk`` fixture imports this module afresh, with the rota app's
interactions set aside, and puts them back after.

- ``notify`` has a declared refusal and a trigger that a hyperscript listener on the page hears.
- ``sign_off`` chooses its path with ``route=``, and its control is a ``<form method="post" hx-action>``.
- ``morph``, ``sync``, ``selfswap``, ``retitle`` and ``nearest`` each answer one control that the start-up
  checks accept and the browser tests measure: two outer swaps (E013), a self-replacing control and
  click-to-edit's ``hx-target:inherited="this"`` (E012), and ``hx-target="closest #nearest"`` (E012).
"""

from django.http import Http404

from dj_hx import interaction, page

MEASURED = ("morph", "sync", "selfswap", "retitle", "nearest")
TITLES = ("Draft", "Revised", "Final")

# The desk's state. A test changes it to make a request fail; a fresh import starts it over.
DESK = {
    "members": {3: "Ada", 7: "Bo"},
    "notified": set(),
    "mail_down": False,
    "signed": set(),
    "replies": dict.fromkeys(MEASURED, 0),
}


class AlreadyNotified(Exception):
    """A declared refusal: the reply is the notify partial with this message, status 422."""


def desk_context(request):
    """The page's context, and every reply's: each name a partial reads, with its default."""
    replies = dict(DESK["replies"])
    return {
        "members": [{"id": pk, "name": name} for pk, name in DESK["members"].items()],
        "lead": 3,
        "notified": None,
        "error": None,
        "signed": False,
        "replies": replies,
        "title": TITLES[replies["retitle"] % len(TITLES)],
    }


def desk(request):
    return page(request, "desk.html", desk_context(request))


@interaction("POST", partial="desk.html#notify", context=desk_context, refuses=(AlreadyNotified,), triggers=("notified",))
def notify(request, member: int):
    if DESK["mail_down"]:
        raise RuntimeError("The mail server is down.")  # not declared: a 500
    if member not in DESK["members"]:
        raise Http404(f"No member {member} is at the desk.")  # removed since the page was rendered
    name = DESK["members"][member]
    if member in DESK["notified"]:
        raise AlreadyNotified(f"{name} was notified already.")
    DESK["notified"].add(member)
    return {"notified": name}


@interaction("POST", partial="desk.html#signoff", context=desk_context, route="desk/members/<int:member>/sign-off")
def sign_off(request, member: int):
    DESK["signed"].add(member)
    return {"signed": True}


def _replied(name):
    DESK["replies"][name] += 1


@interaction("POST", partial="desk.html#morphed", context=desk_context)
def morph(request):
    _replied("morph")


@interaction("POST", partial="desk.html#synced", context=desk_context)
def sync(request):
    _replied("sync")


@interaction("POST", partial="desk.html#selfswap", context=desk_context)
def selfswap(request):
    _replied("selfswap")


@interaction("POST", partial="desk.html#title", context=desk_context)
def retitle(request):
    _replied("retitle")


@interaction("POST", partial="desk.html#nearest", context=desk_context)
def nearest(request):
    _replied("nearest")
