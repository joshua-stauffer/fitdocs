---
id: 2026-10-01-docs-site-design-text-drift
title: "docs-site design.md/research.md text drifted from the merged code: dependency lists, Problem.where forms, entry-point path convention, Linux rename wording"
status: open
importance: low
importance_why: "Prose only; misleads the next spec that extends the site tooling."
effort: S
kind: docs
area: docs-site, .kiro/specs/docs-site/design.md, .kiro/specs/docs-site/research.md, scripts/sitebuild/model.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-design-text-drift.md] docs-site design.md/research.md text drifted from the merged code: dependency lists, Probl"
context:
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/research.md
  - scripts/sitebuild/model.py
blocked_by: []
---

## What
(a) design § Architecture dependency lists omit preview→config (TEMPLATE_PATH), preview→model (Problem), build_site→model (CONTENT_ENV_VAR). (b) The `Problem.where` comment in model.py omits bare line numbers, `hero_actions[N].href` and dotted config keys (docs/website.md lists them). (c) design § Existing Architecture says entry points have a fixed shape, but build_site resolves relative paths from REPO_ROOT, check_site from the cwd, and make_hero_chart has no REPO_ROOT. (d) research.md ~line 19/91 says rename detection is 'platform-dependent on Linux' and gives 'about 0.25 s on both' from a macOS-only measurement; on Linux detection depends on whether the old dir is deleted.

## Why it matters
Next spec touching scripts/sitebuild reads a wrong import graph and conventions.

## Evidence
- Reported by the design-validation and 4.2 reviewers; (b) `scripts/sitebuild/model.py` Problem docstring; (c) `scripts/check_site.py:62` vs `scripts/make_hero_chart.py` (no REPO_ROOT) (pinned at ba76d03).

## How to pick it up
1. Re-read design.md § Architecture and § Existing Architecture against `grep -n '^from\|^import' scripts/sitebuild/*.py scripts/*.py`.
2. Correct the lists, the model.py comment, and either the convention text or the scripts.
3. Reword research.md's Linux sentences.

## Also (surfaced by the line-offset remediation review, 2026-10-01)
- `docs/website.md` § Failures and exit codes does not say that `--verbose` generator output refers to the staged copy, whose `index.md` positions are one line higher than the reported problem line (the injected `template:` line). One sentence; pin it in `tests/sitebuild/test_website_doc.py`.
- `stage.INJECTED_LINE` is a literal `2` rather than derived from `_FENCE`/`_inject_template`; a test pins it, but deriving it removes the duplication.
