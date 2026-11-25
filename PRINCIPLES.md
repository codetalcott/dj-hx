# Principles, stated so an agent can apply them

The three rules have working consequences. Each is a sentence to check code
against.

- **Never return `HttpResponseRedirect`, `HttpResponse("")`, a 204 or
  `django.shortcuts.render` to an htmx request.** Say what happened:
  `redirect`, `removed`, `text`, `render(request, template, partial)`, and
  `navigate` when the answer is another page whatever the control targets (a
  login check). With `HX_REQUIRE_VERBS`, a response no verb built that answers
  a partial request is recorded (`HxBareResponse`), and so is any 3xx.
- **Never read `HX-Source` or `HX-Target`.** The real question is whether the
  client asked for a page or a fragment: `wants_page(request)`.
- **Announce facts; do not update regions.** Prefer `.trigger("contacts-changed")`
  with `hx-trigger="contacts-changed from:body"` on the element that cares, and
  `.partial()` only when the handler already holds the data. `.trigger()` always
  names a target, so the event lands whether or not the swap removed the element
  that asked.
- **The template predicts the DOM effect; the handler predicts the resource
  effect and the representation.** `.retarget()` and `.reswap()` exist and break
  the first half; use them with a comment saying why.
- **Every control says `{% url %}`, or `{% act %}` for an interaction.** Then a
  control names the view that answers it, a search for the view finds every
  caller, and the trailing slash cannot drift from the route.
- **Every name is literal.** `render(request, "index.html", "rows")` is matched
  by `{% partialdef rows %}` in that file; nothing is derived from a naming
  scheme. The one convention, a partial's root `id` equals its name, is checked
  at the render.

Silent failure, not API surface, is the friction, for people and agents alike.
Every row of the catalogue below lands on the first tier it can: delete the
dependency (there is no `source` or `target` to read; `.trigger()` cannot omit
a target), else fail at the first deterministic moment (the verbs raise, the
guard records, `HxTestClient` raises), else check statically (the lint, the
map, the system checks), else document.

What was rejected, and why:

- **Controls declared in Python**, an `hx_attrs(get=..., target=...)` helper or
  control objects beside the view. It hides what the search box does from a
  reader of `index.html`, it is a vocabulary agents have never seen, and it does
  not enforce the agreement it seems to promise. `hx_map` does, from the HTML
  people and agents already write.
- **Server-side retargeting as a default.** `HX-Retarget`, `HX-Reswap` and
  `HX-Location` make a control's DOM effect invisible from the template.
  `HX-Redirect` is not one of them: it replaces the page instead of changing
  what the control swaps, and `navigate` sends it only where a 303 would land
  inside the target.
- **htmx 2 compatibility.** Without `HX-Request-Type` the page-or-fragment
  question is a guess.
- **Decorators that render a returned dict, as first proposed.** A view that
  sometimes returns a dict and sometimes a redirect has two return types, which
  is an agent trap. `@interaction` (below) is that decorator, made safe by
  three rules: one return type, a dict of context keys or `None`, and anything
  else, a response included, raises; the reply is always the partial it
  declares, a refusal's 422 included; and leaving the page is a plain view's
  job, through `navigate()`. What it costs: one more concept beside the verbs,
  and routes minted for interactions (`x/<app label>/<handler>/…`) instead of
  written in the app's URLconf, served by one more include.
