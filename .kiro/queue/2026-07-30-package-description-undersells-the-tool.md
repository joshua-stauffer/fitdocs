---
id: 2026-07-30-package-description-undersells-the-tool
title: pyproject's description calls fitdocs a "pure library layer" and becomes the PyPI summary line
status: open
importance: low
importance_why: One line, but it is the single sentence PyPI renders under the package name and the first thing anyone evaluating fitdocs reads. It describes a decoding library; the tool ships five CLI commands, markdown rendering, route maps and an inbox. Wrong in the one place a user cannot miss it.
effort: S
kind: docs
area: distribution, pyproject.toml
created: 2026-07-30
surfaced_by: Phase 5 discovery (going public) — publish-readiness audit of the package manifest
pinned_at: c3d2201
resume_command: "do: Rewrite pyproject.toml:4's description to cover what fitdocs actually is — .fit files to one markdown document per workout, with charts and pluggable training-load — rather than the decoding layer alone. Keep it to one line; it is the PyPI summary."
context:
  - pyproject.toml
  - README.md
  - .kiro/specs/distribution/tasks.md
  - src/fitdocs/cli.py
blocked_by: []
---

## What

`pyproject.toml:4` reads:

```toml
description = "Decode .fit files into a typed activity model with derived metrics (pure library layer)."
```

That was accurate when the package was `fit-ingest` and nothing else. It is
the project's `description` field, so it becomes the summary line PyPI shows
under the package name, the text `pip show fitdocs` prints, and the blurb in
search results.

The shipped tool is considerably more: `src/fitdocs/cli.py` registers five
commands (`sync`, `regen`, `load`, `check`, `plugins`), and the package
renders markdown documents, SVG charts, route maps over basemap tiles, an
inbox with a drain protocol, and a plugin platform for training-load
calculators. "Pure library layer" describes one internal seam of it.

## Why it matters

This is the only sentence about fitdocs that a person sees before deciding
whether to read further, and it is published in a place that is awkward to
correct — a released version's metadata is immutable on PyPI, so a wrong
description ships until the next release.

Low importance because it is one line and nothing depends on it
mechanically. Filed rather than fixed in passing because `distribution` task
1.2 ("Complete the package manifest and add the license file") is the natural
home and may already intend to catch it — but it does not name the
description field, so nothing guarantees it.

## Evidence

Pinned at `22b4adf`.

```
$ grep -n '^description' pyproject.toml
4:description = "Decode .fit files into a typed activity model with derived metrics (pure library layer)."

$ grep -n '@app.command' src/fitdocs/cli.py
207:@app.command("sync")
346:@app.command("regen")
376:@app.command("load")
408:@app.command("check")
437:@app.command("plugins")
```

No `[project.classifiers]` and no `[project.urls]` table exist either — both
are `distribution`'s task 1.2 and both are named in
`.kiro/steering/roadmap.md` › Phase 5 › Existing Spec Updates, so they are
tracked and this item does not duplicate them.

## How to pick it up

1. If `distribution` task 1.2 is being implemented, fold this in there and
   close this item rather than doing it twice.
2. Otherwise it is a one-line edit. Match the framing the readme rewrite
   (`distribution` task 5.2) settles on, so the two do not disagree.

## Open questions

None.
