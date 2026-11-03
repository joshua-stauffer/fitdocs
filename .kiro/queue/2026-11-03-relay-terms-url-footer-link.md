---
id: 2026-11-03-relay-terms-url-footer-link
title: Optional FITDOCS_RELAY_TERMS_URL so the relay's own pages link an operator's terms
status: open
importance: low
importance_why: The relay's Strava pages link only the privacy policy; an operator with terms (the hosted deployment) cannot make the relay's footers link them.
effort: S
kind: gap
area: relay-server, strava-publish, relay/src/fitdocs_relay/strava/pages.py, relay/src/fitdocs_relay/contract.py
created: 2026-11-03
surfaced_by: shelving relay-legal-pages (maintainer)
pinned_at: 6fcbea20
resume_command: "do: add an optional FITDOCS_RELAY_TERMS_URL deploy-contract row; when set, every fitdocs-written relay page's footer links it as 'Terms of use' after the privacy link; unset changes nothing"
context:
  - relay/src/fitdocs_relay/strava/pages.py
  - relay/src/fitdocs_relay/contract.py
  - relay/src/fitdocs_relay/strava/config.py
  - docs/relay.md
  - .kiro/specs/relay-legal-pages/design.md
blocked_by: []
---

## What
The relay's fitdocs-written pages (the Strava connect page, its callback,
`/privacy`, `/go/` and the error pages) have a footer that links the privacy
policy and shows the support contact. `FITDOCS_RELAY_PRIVACY_POLICY_URL`
lets an operator point the policy link elsewhere. There is no counterpart
for terms.

The shelved relay-legal-pages spec had designed one: `Operator.terms_url`,
an optional `https` row, and a footer link that appears only when a terms
address exists. The maintainer called it optional when shelving the spec.

## Why it matters
The hosted deployment publishes terms at `https://api.fitdocs.ai/terms`
(static, served by Caddy). Without this row, the Strava connect page an
athlete sees before granting access does not link those terms. Strava does
not require it, and the hosted deployment's own pages can link the terms.
Pick this up if the maintainer wants the terms linked from the relay's
pages too.

## Evidence
- `relay/src/fitdocs_relay/strava/pages.py` `_footer` at 6fcbea20: one
  "Privacy policy" link, then the support contact.
- `relay/src/fitdocs_relay/contract.py` at 6fcbea20: `ENV_PRIVACY_POLICY_URL`
  exists and no terms row does.
- `.kiro/specs/relay-legal-pages/design.md` PageShell (shelved): the designed
  shape, `terms_address(operator) -> str | None`.

## How to pick it up
1. Add `ENV_TERMS_URL` beside `ENV_PRIVACY_POLICY_URL` in `contract.py`,
   validated as `https` like the policy address.
2. Thread it into `Operator`, and render the terms link in `_footer` only
   when it is set.
3. Done means:
   - the contract-table pin and the footer tests pass;
   - with the row unset, every page's footer is unchanged;
   - one sentence in `docs/relay.md`, with no documentation test (the
     maintainer's code-only testing rule).
