---
id: 2026-10-31-relay-image-wrapper-install-path
title: Deploy contract v1 does not say how a wrapper package gets into the relay image
status: open
importance: medium
importance_why: A deployment that wraps the relay (FITDOCS_RELAY_EXTENSIONS) must make its module importable in the image's environment; today it would have to reverse-engineer the Dockerfile, and nothing pins what it relies on.
effort: S
kind: gap
area: relay-server, relay/Dockerfile, fitdocs_relay.contract, docs/relay.md
created: 2026-10-31
surfaced_by: question after /kiro-spec-batch (Phase 14) about starting deployment work in parallel
pinned_at: 4dd73188
resume_command: "/kiro-spec-design relay-server [queue: .kiro/queue/2026-10-31-relay-image-wrapper-install-path.md] Add the image's environment location and a derived-image rule to deploy contract v1"
context:
  - .kiro/specs/relay-server/design.md
  - .kiro/specs/relay-server/requirements.md
blocked_by: []
---

## What
The relay loads wrappers by `module:attribute` references in
`FITDOCS_RELAY_EXTENSIONS` (relay-server design, Seam, `load_extensions`), so
the wrapper module must be importable inside the image. Deploy contract v1
pins the image user (10001), port (8080), entrypoint, command, the `/data`
directory and the environment table. It does not pin where the image's
virtual environment lives, whether the runtime stage can install into it, or
how a deployment builds a derived image that adds a wrapper. The Dockerfile
"copies the venv" without naming a path.

## Why it matters
A wrapping deployment is a stated audience of the deploy contract (Req 9
objective, Req 10). Without a pinned location, a derived image depends on an
unpinned detail of the Dockerfile, and a relay update can break it without the
contract version moving (Req 9.12).

## Evidence
- `.kiro/specs/relay-server/design.md:1100-1102`: the image constants are
  `IMAGE_USER_ID`, `IMAGE_PORT`, `IMAGE_ENTRYPOINT`, `IMAGE_DEFAULT_COMMAND`;
  there is no environment-path constant.
- `.kiro/specs/relay-server/design.md:1538-1542`: the runtime stage "copies
  the venv", with no path, and no installer is named for the runtime stage.
- `grep -n -i "venv\|PYTHONPATH\|site-packages" .kiro/specs/relay-server/design.md`
  finds only those two lines.

## How to pick it up
1. Decide the shape: a fixed environment path (an `IMAGE_VENV` constant on
   `PATH`) plus a documented derived-image recipe, or a build argument that
   names extra packages to install in the build stage.
2. Add it to deploy contract v1 before relay-server is implemented (no
   version bump needed while unimplemented): requirement 9.1/9.10 wording,
   the `contract.py` constants, the Dockerfile notes, the `docs/relay.md`
   section, and a test that pins it.
3. Optionally extend `relay/scripts/image_smoke.sh` to build a derived image
   with a trivial test extension and check that it loads.
