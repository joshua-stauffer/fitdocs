# fitdocs-relay

A small, self-hostable relay that holds a platform application on the
athlete's behalf, so the fitdocs command line never carries it.

This package is separate from the `fitdocs` tool: its own manifest, its own
lock, and no import of `fitdocs`. The operator-facing contract and the
self-hosting guide live in `docs/relay.md` in the repository.

Development, from this directory:

```
uv sync --locked --extra postgres
uv run pytest -q
```
