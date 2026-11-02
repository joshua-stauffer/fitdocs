# Changelog

Each entry names the contract, envelope and seam versions it carries. A
breaking change for deployments is marked `**Breaking for deployments:**`.

## Unreleased

- Deploy contract version: 1
- Envelope version: 1
- Seam version: 1
- Additive: the Strava target. Apart from migration `0002_target_custody`
  below, which every relay applies whether or not the target is configured, a
  relay with `FITDOCS_RELAY_STRAVA_CLIENT_ID` unset is unchanged: it answers every Strava route `not-offered`, opens no
  Strava connection, and keeps no Strava record. Deploy contract 1,
  envelope 1 and seam 1 are restated above because no existing variable,
  command, answer or seam call changed.
- Variables. Setting `FITDOCS_RELAY_STRAVA_CLIENT_ID` enables the target; the
  other variables are then required or optional as the deploy contract lists
  them. Required with the client id: `FITDOCS_RELAY_STRAVA_CLIENT_SECRET`,
  `FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN`, `FITDOCS_RELAY_PUBLIC_URL`,
  `FITDOCS_RELAY_ENCRYPTION_KEYS`, `FITDOCS_RELAY_OPERATOR_NAME` and
  `FITDOCS_RELAY_SUPPORT_CONTACT`. Optional: `FITDOCS_RELAY_PRIVACY_POLICY_URL`,
  `FITDOCS_RELAY_STRAVA_API_URL`, `FITDOCS_RELAY_STRAVA_OAUTH_URL`,
  `FITDOCS_RELAY_STRAVA_WEB_URL`, `FITDOCS_RELAY_STRAVA_LINKS` (`activity`,
  the default, or `relay`), `FITDOCS_RELAY_STRAVA_RATE_LIMIT` and
  `FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT`. A variable of the target set without
  the client id is a configuration error naming the variable.
- Routes. Envelope routes `/v1/targets/strava/connect`,
  `/v1/targets/strava/connect/poll`, `/v1/targets/strava/publish`,
  `/v1/targets/strava/upload` and `/v1/targets/strava/disconnect`; pages
  `/connect/strava`, `/strava/callback`, `/go/` followed by a publication id,
  `/privacy` and `/robots.txt`; and `/strava/webhook/` followed by the webhook
  secret, which Strava calls.
- Commands. `strava webhook create`, `strava webhook show` and
  `strava webhook delete` manage the webhook subscription; `reencrypt`
  re-encrypts stored Strava tokens under the current encryption key; and
  `new-encryption-key` prints a fresh key for
  `FITDOCS_RELAY_ENCRYPTION_KEYS`.
- Schema. Migration `0002_target_custody` adds the connection, publication and
  budget tables on SQLite and PostgreSQL. The change is additive: no 0.1.0
  table or column changes. Every relay needs it: until it is applied,
  `/readyz` reports `schema-behind` and `migrate --check` exits `3`.

## 0.1.0 (unreleased)

- Deploy contract version: 1
- Envelope version: 1
- Seam version: 1
- First release of the relay server: a small HTTP service that answers fitdocs
  clients in envelope version 1. It checks and revokes bearer tokens,
  whether an operator minted them or a registration issued them, reports its capabilities,
  and, when an extension supplies a registration provider, runs the
  register-and-poll exchange. The probes are `/livez` and `/readyz`.
- Storage is SQLite by default; PostgreSQL is available through the
  `postgres` extra. `fitdocs-relay migrate` brings the schema forward and
  `migrate --check` exits `3` while migrations are pending.
- Operators create, list and delete principals, and mint, list and revoke
  tokens, with the `fitdocs-relay` command line; a token is shown once, when
  it is minted, and only a keyed digest of it is stored.
- A deployment is configured by the eleven environment variables in the
  deploy contract and runs from the relay image as an unprivileged user on
  port 8080. The seam lets a wrapper add routes and a registration provider,
  using the relay's token issuance and record store, without changing the
  relay.
