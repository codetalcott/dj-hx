"""
A rota: a page of members to notify, and two interactions. dj-hx's ready() imports this module.
The templates are in-memory, served by the ``rota`` fixture in tests/test_interactions.py.
"""

from dj_hx import interaction, page

ROTA = {"spring": [3, 7]}


class NotOnRota(Exception):
    """A declared refusal: the reply is the partial with ``error``, status 422."""


def rota_context(request, contest):
    return {"contest": contest, "members": ROTA.get(contest, []), "notified": None, "error": None}


def rota(request, contest):
    """The page; it renders the region notify() replies with, from the same context."""
    return page(request, "rota.html", rota_context(request, contest))


@interaction("POST", partial="rota.html#notify", context=rota_context, refuses=(NotOnRota,),
             triggers=("notified", "rota-changed"))
def notify(request, contest: str, member: int):
    if member not in ROTA.get(contest, []):
        raise NotOnRota(f"Member {member} is not on the {contest} rota.")
    return {"notified": member}


def reviewer_context(request, member):
    return {"member": member, "notified": False}


@interaction("POST", partial="reviewers.html#reviewer", context=reviewer_context, route="reviewers/<int:member>/notify")
def notify_reviewer(request, member: int):
    return {"notified": True}
