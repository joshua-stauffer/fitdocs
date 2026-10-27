---
id: 2026-10-27-basemap-compose-path-has-no-cross-platform-byte-pin
title: Req 5.2 cross-platform determinism is pinned for WebP encode only, not for the LANCZOS resize/composite path
status: open
importance: low
importance_why: Only mixed or non-256 px tile sizes go through resize; default OSM tiles are 256 px at density 1, so today's maps are covered, but a provider change could break macOS-vs-Linux byte identity unnoticed.
effort: S
kind: gap
area: compact-chart-assets, src/fitdocs/basemap.py, tests/test_basemap.py
created: 2026-10-27
surfaced_by: /kiro-validate-impl compact-chart-assets
pinned_at: 10610817
resume_command: "do: add a compose_basemap SHA-256 golden over mixed-size factory tiles (e.g. 256 + 384 px, forcing LANCZOS resize and alpha composite) and confirm it matches on macOS and Linux CI"
context:
  - src/fitdocs/basemap.py
  - tests/test_basemap.py
  - tests/support/tiles.py
  - .kiro/specs/compact-chart-assets/requirements.md
blocked_by: []
---

## What
The cross-platform golden `_GOLDEN_SHA256` (tests/test_basemap.py ~:520-542)
hashes `encode_canvas` on one fixed synthetic canvas. Nothing pins the bytes
of `compose_canvas`'s LANCZOS resize and `alpha_composite` across platforms.
Those steps run whenever tile sizes differ or a tile's density is not 1.
macOS x86-64 is not covered at all. The encode golden was verified on macOS
arm64, on linux arm64/amd64 containers (amd64 emulated), and on Linux x86-64
CI.

## Why it matters
Requirement 5.2 promises the same bytes on every supported platform for the
same installed dependency versions. Pillow's resize uses platform SIMD paths.
If those diverge, a user who syncs from two machines would see every map
rewritten on each switch.

## Evidence
Reported by the validation reviewer subagent. The golden's scope is visible
in tests/test_basemap.py. No compose-level SHA test exists: `grep -n
"compose_basemap" tests/test_basemap.py` finds only behavioural asserts.

## How to pick it up
1. Build a fixed plan with 2–4 factory tiles of mixed sizes (`tile_factory.map_like` at 256 and 384 px) so that density > 1 and a resize is forced.
2. Pin the SHA-256 of `compose_basemap(...).data` and check it on branch CI (Linux). If you can reach macOS x86-64, check it there too.
3. Remember the 1.2 lesson: if this path proves non-portable, a byte pin is the wrong guarantee. Amend Req 5.2 instead.
</content>
</invoke>
<invoke name="Bash">
<parameter name="command">cd /Users/josh/code/fitdocs_oss; for f in /Users/josh/code/fitdocs-compact-assets/.kiro/queue/2026-10-27-*; do echo "$(basename $f) :: $(grep -m1 '^id:' $f)"; done
git -C /Users/josh/code/fitdocs-compact-assets add .kiro/queue/2026-10-27-basemap-compose-path-has-no-cross-platform-byte-pin.md .kiro/queue/2026-10-27-transparent-tile-pixels-now-composite-onto-white.md
git -C /Users/josh/code/fitdocs-compact-assets commit -q -m "queue: two compact-chart-assets validation follow-ups"
git -C /Users/josh/code/fitdocs-compact-assets push -q; git -C /Users/josh/code/fitdocs-compact-assets log --oneline -1