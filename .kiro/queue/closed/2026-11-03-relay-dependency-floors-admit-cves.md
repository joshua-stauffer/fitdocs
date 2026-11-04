---
id: 2026-11-03-relay-dependency-floors-admit-cves
title: The relay's dependency floors admit known CVEs in starlette, cryptography and h11 (the lockfile is clean)
status: done
importance: medium
importance_why: Any install of the relay package that resolves from its floors instead of relay/uv.lock can get vulnerable versions, including h11 request smuggling, which matters more once the extension adds 10 MB webhook routes.
effort: S
kind: chore
area: relay-server, relay/pyproject.toml, relay/uv.lock, relay/CHANGELOG.md
created: 2026-11-03
surfaced_by: /kiro-discovery (Phase 14 extension viability check; verified against OSV in the same run)
pinned_at: 6ca533d8
resume_command: "do: raise relay/pyproject.toml floors to starlette>=1.3.1, cryptography>=50.0.0, add h11>=0.16, re-lock relay/uv.lock, add a relay/CHANGELOG.md entry, and run the relay suite"
context:
  - relay/pyproject.toml
  - relay/uv.lock
  - relay/CHANGELOG.md
  - relay/tests/test_contract.py
  - .github/workflows/relay.yml
blocked_by: []
---

## What

`relay/pyproject.toml` declares `starlette>=1.0,<2` (line 10),
`uvicorn>=0.30,<1` (line 11) and `cryptography>=44,<51` (line 12). Each
floor admits versions with published advisories, and nothing sets a floor
for `h11`, which uvicorn pulls in.

## Why it matters

`relay/uv.lock` pins clean versions: starlette 1.10.0, cryptography 50.0.2,
h11 0.16.0. OSV reports 0 advisories for each. So the image built from the
lock is not affected. But two other installs resolve from the floors instead:
- a `pip install` of the relay package;
- a derived image that re-resolves.

Either can land on a vulnerable version. h11 before 0.16.0 accepts
malformed chunked bodies, which enables request smuggling. Phase 14's
extension adds webhook routes that accept bodies of at least 10 MB, which
makes that path more exposed.

## Evidence

All checked 2026-11-03 against `https://api.osv.dev/v1/query` (PyPI
ecosystem). The fixed-in versions are OSV's `fixed` events.
- **starlette 1.0.0:**
  - CVE-2026-48710 (GHSA-86qp-5c8j-p5mr), fixed in 1.0.1;
  - CVE-2026-48817 (GHSA-x746-7m8f-x49c), fixed in 1.1.0;
  - CVE-2026-48818 (GHSA-wqp7-x3pw-xc5r), fixed in 1.1.0;
  - CVE-2026-54282 (GHSA-jp82-jpqv-5vv3), fixed in 1.3.0;
  - CVE-2026-54283 (GHSA-82w8-qh3p-5jfq), fixed in 1.3.1.

  The minimum safe floor is **1.3.1**.
- **cryptography 44.0.0:**
  - CVE-2024-12797, fixed in 44.0.1;
  - CVE-2026-26007, fixed in 46.0.5;
  - CVE-2026-34073, fixed in 46.0.6;
  - GHSA-537c-gmf6-5ccf (bundled OpenSSL), fixed in 48.0.1;
  - CVE-2026-69249, fixed in 49.0.0;
  - CVE-2026-69247, fixed in **50.0.0**.

  The minimum safe floor is **50.0.0**. The viability subagent's suggested
  48.0.1 is too low, which this item corrects.
- **h11 0.14.0:** GHSA-vqfr-h8mv-ghfj (CVE-2025-43859, malformed
  chunked-encoding bodies, request smuggling), fixed in 0.16.0.
- **The locked versions** (`relay/uv.lock`: starlette 1.10.0, cryptography
  50.0.2, h11 0.16.0) return 0 advisories from the same queries.

## How to pick it up

1. Work on a branch and worktree, per `.kiro/steering/change-protocol.md`.
2. In `relay/pyproject.toml`:
   - `starlette>=1.3.1,<2`;
   - `cryptography>=50.0.0,<51`;
   - add `h11>=0.16`, a direct floor on a transitive dependency, with a
     comment naming the CVE.
3. `cd relay && uv lock`. The locked versions should not move, since they
   already satisfy the floors. Confirm with a diff of `relay/uv.lock`.
4. Check whether `relay/tests/test_contract.py` or the image smoke tests pin
   the dependency list, and update any pin.
5. Add a `relay/CHANGELOG.md` entry under `## Unreleased`.
6. Validate: the relay suite with the PostgreSQL service, as in
   `.github/workflows/relay.yml`, plus ruff and mypy. Push, and check
   branch CI before merging.

Done means the floors exclude every advisory above, and relay CI is green.

## Open questions

- Whether the `<51` cap on cryptography should move. 51.x is not assessed
  here.

## Resolution
Done 2026-11-04: `starlette>=1.7,<2`, `cryptography>=50.0.0,<51`, and a direct `h11>=0.16`. `uv lock` moved no version.

The item's proposed `starlette>=1.3.1` was the advisory floor, but the relay does not work there. Run against exact floor versions, 15 request-log tests fail on 1.3.1 to 1.6.0 (the record's route is `None`) and pass from 1.7.0. A control with the locked versions separated this from environment artifacts. The old `>=1.0` floor had the same problem, hidden by the lockfile.

Evidence, all the same day: with the relay package installed on starlette 1.7.0, cryptography 50.0.0, h11 0.16.0 and uvicorn 0.30.0, the relay suite gives 6 failed, 2727 passed, and the 6 are the known failures from the missing PostgreSQL extra, the same 6 as with locked versions. OSV reports 0 advisories at each of those versions, so `uvicorn`'s floor stays. The `<51` cap on cryptography is unchanged: 51.x is still not assessed, and nothing requires it yet.
