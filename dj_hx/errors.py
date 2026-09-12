"""
Every error dj-hx can raise. Each message names the handler and says what to change.

The verbs raise the ones whose outcome is certain at call time (a page answering
a request that targets an element). The rest are *recorded* on the response by
the verbs and the middleware, logged, and raised by ``HxTestClient``, so a
residual false positive cannot become a 500 in production.
"""


class HxError(Exception):
    """Base class."""


class HxProtocolError(HxError):
    """The request is htmx but not htmx 4 (``HX-Request`` without ``HX-Request-Type``)."""


class HxPageIntoFragment(HxError):
    """``page()`` answered a request whose target is not the body."""


class HxFragmentIntoPage(HxError):
    """``fragment()`` or ``text()`` answered a boosted or body-targeted htmx request."""


class HxRedirectIntoFragment(HxError):
    """A 3xx answered a request whose target is not the body; fetch would follow it there."""


class HxNoSwap(HxError):
    """A 204 answered a partial request; htmx 4 leaves the target untouched."""


class HxBareResponse(HxError):
    """A response no verb built answered a request that targets an element."""


class HxUnknownPartial(HxError):
    """A ``partial=`` names a template partial the template does not define."""


class HxPartialRootId(HxError):
    """A partial rendered into ``<hx-partial>`` has no root element carrying ``id=<name>``."""


class HxMessagesUnconfigured(HxError):
    """Messages were added on a fragment response and ``HX_MESSAGES_TEMPLATE`` is unset."""


class HxLintError(HxError):
    """The rendered HTML failed the htmx 4 lint (see ``dj_hx.hxlint``)."""

    def __init__(self, findings, where=""):
        self.findings = list(findings)
        head = f"dj-hx lint found {len(self.findings)} issue(s)" + (f" in {where}" if where else "")
        super().__init__(head + ":\n  " + "\n  ".join(str(f) for f in self.findings))


class HxRedirectError(AssertionError):
    """``HxTestClient``: a redirect answered a full request and the test did not say what it wanted."""
