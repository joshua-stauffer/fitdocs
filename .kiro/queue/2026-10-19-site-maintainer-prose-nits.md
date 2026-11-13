---
id: 2026-10-19-site-maintainer-prose-nits
title: fitdocs.ai home page ends mid-sentence, and the LLM fundamentals page has typos (maintainer-authored prose)
status: open
importance: medium
importance_why: The live home page publishes an unfinished sentence; only the maintainer should write it.
effort: S
kind: docs
area: docs-site, website/content/index.md, website/content/llm/index.md
created: 2026-10-19
surfaced_by: 0.2 site-copy update (deliberately left untouched in that PR because the prose is the maintainer's voice)
pinned_at: 90cd00b
resume_command: "do: ask the maintainer to finish the last sentence of website/content/index.md and approve the typo fixes listed in .kiro/queue/2026-10-19-site-maintainer-prose-nits.md, then apply them on a chore branch and validate with uv run --group docs python -m scripts.build_site build"
context:
  - website/content/index.md
  - website/content/llm/index.md
  - docs/website.md
blocked_by: []
---

## What
- **The home page.** Its last paragraph stops mid-sentence: "…and writes
  the training plan you describe into the wiki, where it’s matched with ".
  The maintainer's own iCloud draft ends the same way, so this is unfinished
  writing, not an import fault.
- **The LLM fundamentals page.** It has typos in maintainer prose.
- **Why the site PR left them.** The 0.2 site-copy PR (branch
  `chore/site-copy-0-2`) deliberately did not touch either page's prose.

## Why it matters
fitdocs.ai is live. A truncated sentence on the home page is the first thing
a visitor reads.

## Evidence
At 90cd00b:
- `website/content/index.md:22` ends with `where it’s matched with` followed
  by a space and a newline (`tail -c` shows the bytes). The same line has
  "Your LLM put the stats" (likely "puts"), and `:19` spells the product
  "duckdb" (it is "DuckDB").
- `website/content/llm/index.md`:
  - `:23` "outlyers" (outliers);
  - `:28` "A good review answers questions your curious about" (you're) and
    "that you didn’t have known to ask for";
  - `:33` "the type of training your most interested in" (you're).

## How to pick it up
1. Show the maintainer the lines above.
2. They finish the home-page sentence; Claude does not invent it.
3. Apply the agreed fixes on a chore branch.
4. Validate with
   `uv run --group docs python -m scripts.build_site build --build-dir <scratch>`.

Remember that a push to `main` that touches `website/**` deploys the site.

## Update (2026-11-13): typos fixed in PR #5

These are fixed on `chore/site-copy-connectors` (PR #5), at the maintainer's request:
- `index.md`: "Your LLM put" → "Your LLM puts".
- `llm/index.md`: "outlyers" → "outliers", and "your most interested in" → "you’re most interested in".

PR #2's rewrite, recovered into the same PR, had already fixed "duckdb" and line 28 ("you’re curious about", "didn’t know to ask about").

Still open: the home page's last sentence ends at "where it’s matched with". Only the maintainer writes that. Two things are left for the maintainer to decide, since they're grammar rather than typos and weren't queued:
- `index.md:22`: "benchmarks, and fitness curve" (probably "fitness curves").
- `llm/index.md:33`: "every one won’t be the right fit for you" (probably "not every one will be").

## Update (2026-11-13): the home page's last sentence ends

At the maintainer's request, the last sentence of `index.md` now ends at "…and writes the training plan you describe into the wiki." The unfinished "where it’s matched with" clause is gone. The two grammar points in the update above are still open, and the maintainer will follow up on the remaining prose.
