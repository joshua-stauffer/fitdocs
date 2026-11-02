# Changelog

Each entry names the contract, envelope and seam versions it carries. A
breaking change for deployments is marked `**Breaking for deployments:**`.

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
