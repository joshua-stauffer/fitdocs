---
id: 2026-09-30-docs-guard-heading-slugs-not-github-faithful
title: The docs anchor guards' _heading_slugs diverges from GitHub's slugger (drops "_", no duplicate suffixes, not fence-aware)
status: open
importance: low
importance_why: Today's docs pass either way, but the guard can accept an anchor GitHub never generates and reject one it does, so a broken or valid docs link is misjudged silently.
effort: S
kind: bug
area: tests/test_docs_guarantees.py, tests/test_releasing_docs.py, tests/test_contributing_doc.py
created: 2026-09-30
surfaced_by: /kiro-spec-quick docs-site --auto (design discovery)
pinned_at: 9881cab
resume_command: "do: Make tests/test_docs_guarantees.py::_heading_slugs (and its copy at tests/test_releasing_docs.py:171) follow github-slugger v2 -- keep '_', add -1/-2 duplicate suffixes, skip headings inside fenced code -- then run the docs guard suite and show each fix with a mutation"
context:
  - tests/test_docs_guarantees.py
  - tests/test_releasing_docs.py
  - tests/test_contributing_doc.py
  - .kiro/specs/docs-site/research.md
blocked_by: []
---

## What
`_heading_slugs` claims to produce "every GitHub-flavoured anchor slug"
(`tests/test_docs_guarantees.py:884-901`), but it diverges from
github-slugger in three ways:
- It deletes `_` (`text.replace("_", "")`). GitHub keeps underscores:
  Connector_Punctuation is not in github-slugger's removal list.
- It never adds GitHub's `-1`, `-2`, … suffixes to repeated headings.
- It treats a `#` line inside a fenced code block as a heading.

The same function is duplicated at `tests/test_releasing_docs.py:171`. The
`CONTRIBUTING.md` anchor check (`tests/test_contributing_doc.py:266-289`)
uses the same slugs.

## Why it matters
These guards exist to prove that `docs/` anchor links work on GitHub:
- A link to a heading containing `_` is rejected when correct, and accepted
  when wrong.
- A link to the second of two same-named headings (`#x-1`) is rejected.
- A code sample containing `# comment` lines manufactures slugs that let a
  broken link pass.

Nothing is broken today, but the guard's verdict and GitHub's behaviour
differ exactly where a future page is most likely to break.

## Evidence
- `tests/test_docs_guarantees.py:898-900`:
  `text = re.sub(r"[^\w\s-]", "", text.replace("_", ""))`, with no duplicate
  bookkeeping and no fence tracking in the line loop at :895.
- github-slugger's removal categories
  (https://raw.githubusercontent.com/Flet/github-slugger/master/script/generate-regex.js,
  fetched 2026-09-30): Other_Number, Close, Final, Initial, Open, Other and
  Dash punctuation, Symbol, Control, Private_Use, Format, Unassigned,
  Separator. No Connector_Punctuation, and ` ` and `-` are excluded from
  removal.
- The docs-site spec builds a faithful slugger for its own site→`docs/`
  links: design.md § LinkChecker, task 2.8, and its conformance table. That
  slugger lives in `scripts/sitebuild/links.py` and cannot be imported by
  tests without coupling guard tests to site tooling.

## How to pick it up
1. Read `_heading_slugs` at both locations, and the anchor walk at
   `tests/test_docs_guarantees.py:951`.
2. Fix the three divergences in one shared helper; for example, move it to a
   `tests/_github_slugs.py` that both modules import. Keep it standard
   library only.
3. Run the docs guard suite. For each divergence, add a synthetic-markdown
   test naming its mutation, following the Fixture Discrimination gate in
   change-protocol.md.
