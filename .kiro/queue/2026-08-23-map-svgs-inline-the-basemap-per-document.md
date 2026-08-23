---
id: 2026-08-23-map-svgs-inline-the-basemap-per-document
title: Every map SVG inlines its own copy of the basemap, so a real-sized archive multiplies 20MB of tiles into hundreds of MB of documents
status: open
importance: medium
importance_why: Output size grows with document count rather than with route coverage; a full personal archive renders a wiki too large to keep in a PKM or a git repo.
effort: M
kind: gap
area: route-maps, src/fitdocs/render/charts/map.py
created: 2026-08-23
surfaced_by: full-archive demo rebuild of 2478 real .fit files into ~/code/fitdocs-demo
pinned_at: 87ce085
resume_command: "/kiro-spec-requirements route-maps [queue: .kiro/queue/2026-08-23-map-svgs-inline-the-basemap-per-document.md] Stop inlining the basemap into every map SVG; reference shared tile assets instead"
context:
  - .kiro/specs/route-maps/design.md
  - .kiro/specs/route-maps/requirements.md
  - src/fitdocs/render/charts/map.py
  - src/fitdocs/tiles.py
blocked_by: []
---

## What

`compose_map` renders the basemap as one inline `data:image/png;base64` SVG
`<image>` element per covering tile, so every document that has a route carries
its own full copy of the imagery beneath it. The tile *cache* is shared and
deduplicated; the *rendered output* is not. An athlete who runs the same
neighbourhood hundreds of times gets that neighbourhood's tiles re-encoded into
hundreds of separate documents.

Nothing about this is wrong per document — it is what makes a doc a
self-contained artifact, which the spec wants. The gap is that no requirement
considers what it costs at archive scale, and there is no option to reference
shared tile assets instead.

## Why it matters

Output size scales with document count instead of with distinct route coverage.
Measured on a real archive (below): 1235 mapped documents weigh 725 MB of
assets, backed by only 40 MB of distinct cached tiles — an ~18x multiplication
of the same imagery. The finished wiki is 939 MB, rendered from an 81 MB
source archive.

fitdocs is designed to plug into a markdown PKM (`CLAUDE.md`, reference
`joshua-stauffer/pkm`). A wiki path that adds hundreds of megabytes of
base64 to a PKM is one users will not commit to git, which undercuts the
"one rich markdown document per workout, lives in your notes" premise.

## Evidence

Mechanism, `src/fitdocs/render/charts/map.py:292-317` — `_render_tiles` emits
one `<image>` per tile with the bytes inlined:

```
304:        encoded = base64.b64encode(tiles[ref]).decode("ascii")
313:                    "href": f"data:image/png;base64,{encoded}",
```

Measured 2026-08-23 in `~/code/fitdocs-demo`, against the **completed** render
of all 2478 documents (`fitdocs sync inbox --no-prompt`: 2478 written, 0 failed,
0 warnings):

```
$ grep -l "^## Map" wiki/workouts/*.md | wc -l
    1235
$ du -sh wiki wiki/workouts/assets wiki/.cache
939M	wiki
725M	wiki/workouts/assets
 40M	wiki/.cache
$ ls -S wiki/workouts/assets/*-map.svg | head -1 | xargs du -h
1.0M	wiki/workouts/assets/2023-03-12-run-2026-map.svg
```

1235 mapped documents produce 725 MB of assets against a 40 MB shared tile
cache -- an ~18x multiplication of the distinct imagery, and the wiki as a
whole is 939 MB for a 81 MB source archive.

`grep -c base64 wiki/workouts/assets/<a-map>.svg` returns a single composed
payload per file, confirming the imagery is embedded rather than referenced.

## How to pick it up

1. Read `.kiro/specs/route-maps/design.md` first — specifically why the
   inline-`data:` decision was made. It is deliberate (determinism: identical
   bytes base64-encode identically, which is what makes goldens stable), so
   this is a trade-off to re-open, not a defect to correct.
2. Read `src/fitdocs/render/charts/map.py:292-317` and `compose_map` at 428.
   The change is where tile bytes enter the SVG, not in projection or framing.
3. Decide the output contract: a shared `assets/tiles/` directory referenced by
   relative `href`, versus inline, versus a setting. Note that a relative href
   makes a document non-self-contained — check `wiki-contract` before assuming
   that is acceptable, and check whether markdown renderers in the target PKM
   resolve relative hrefs inside an SVG.
4. Done looks like: rendering the same archive twice produces byte-identical
   output (determinism preserved), and total map bytes scale with distinct
   tiles rather than with document count.

## Open questions

- Is a self-contained document a hard requirement of `wiki-contract`, or an
  unstated preference? That answer decides whether referencing is even legal.
- If referencing wins, who owns the shared asset directory's lifecycle —
  `regen` must not orphan or delete tiles a surviving document still points at.
