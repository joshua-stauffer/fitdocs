# Requirements Document

## Project Description (Input)
fitdocs 0.1.0 is on PyPI, and it has no front door. A newcomer lands on the
README or on `docs/`, which are contract-grade pages: exact, guarded by tests,
and written for someone who already knows what a data root or a disposition
is. Nothing explains what fitdocs is for. Nothing walks a first-time user from
install to a first workout page or gives copy-paste prompts for running it with
an LLM agent. Nothing states the philosophy: local first, private first, own
your data forever, first-class LLM compatible. The maintainer owns fitdocs.ai
and wants a standard Python docs site there, in the house style of uv, Ruff
and FastAPI. It needs a hero home page, nav grouped by section, search, light
and dark mode, copy buttons on every code block, edit-on-GitHub links, and
`llms.txt` / `llms-full.txt` at the root.

The site's copy is hand-written. A 21-page draft exists outside the repository,
and the maintainer will revise it while this spec is implemented and commit it
into `website/content/` only once edited. The build must therefore own nothing
of that copy and be ready to receive it.

This spec delivers:
- **a generator-agnostic build script** (stdlib plus PyYAML) that:
  - stages content from `website/content/`, a flag or an env var;
  - strips the trailing iA Writer annotation block;
  - validates a written-down frontmatter contract (`title`, `description`,
    `section` from a canonical list, `order`, optional `draft` and hero keys);
  - generates the nav;
  - writes a key-allowlisted config from a checked-in template;
  - emits the llms files;
  - runs an exactly pinned Zensical in strict mode;
  - has a `serve` mode that previews out-of-repo content on save;
- the brand brief as theme configuration and `overrides/`, with a demo-data
  hero chart;
- `[dependency-groups] docs`, never optional-dependencies;
- fixture-only tests whose every assertion names the mutation it dies on;
- a `.github/workflows/docs.yml` that builds on relevant changes and deploys to
  GitHub Pages from `main` only, behind a forbidden-strings check over staged
  content and built output that fails closed, with its own workflow test;
- `Homepage = "https://fitdocs.ai"` in `[project.urls]`;
- one new `docs/` page, linked from `docs/index.md`, documenting the site:
  the content contract, build and preview, and the maintainer runbook (DNS,
  Pages settings, content import, the Zensical pin bump);
- a `CONTRIBUTING.md` build-and-preview section pointing at that page.

A broken link or anchor, a bad frontmatter key, an unknown config key or a
forbidden string fails the build before anything publishes. The spec is
complete whether or not the maintainer's copy has landed. `docs/` stays the
sole contract: the site links to it by GitHub URL and never restates it.
Source: `.kiro/specs/docs-site/brief.md`; Phase 9 of
`.kiro/steering/roadmap.md`.

## Introduction

`docs-site` is fitdocs' first deliverable that is neither the installed tool nor
a page of its contract. It is a website, published at fitdocs.ai, whose copy is
written by hand, outside this repository, by the maintainer. The spec builds
the machinery that turns that copy into a site. It never owns the copy itself:
the build reads pages from a content directory and, before anything is
published, checks that they obey a written-down content contract. The
maintainer's pages can be previewed from wherever they sit today and land in
the repository whenever they are ready. Nothing in the build changes when they
do. Every behavior here is therefore proved against fixture pages, and the
spec is complete whether or not the real copy has landed.

Two authorities are kept apart. `docs/` stays the one contract: the site links
out to it by GitHub URL, never copies or restates it, and the build checks
that every such link still resolves, so the friendly layer cannot quietly
drift away from the contract it points at. And nothing reaches the public web
unchecked. Staged content and built output pass the same forbidden-strings
gate the release artifacts do, and when that gate cannot run, nothing
publishes. Until the copy lands, a push to `main` still builds and validates,
but it deploys nothing.

The site generator, its exact pin, the hosting service and the source
directory name were decided at discovery (roadmap Phase 9, 2026-09-28). The
requirements below name them only where an operator must observe them. The
brand's concrete values (palette, typeface, logo treatment) are proposed in
design and approved by the maintainer. These requirements fix only where
those values are stated and how they must behave.

**Amended 2026-09-30.** The quick-spec sanity review found that these
criteria stated a broader contract than the one the design settled.
Criteria 1.4, 1.6, 2.3, 2.10, 3.3 and 6.5 were reworded and 2.11 and 2.12
added. Existing IDs are unchanged. The amendments await maintainer
confirmation, together with the brand values (queue
`2026-09-30-docs-site-design-proposals-await-maintainer`).

## Boundary Context

- **In scope**:
  - the site's source layout, its build and its local preview, including
    preview of a content directory outside the repository;
  - the content contract (frontmatter keys, the canonical section list, the
    home page's hero keys, `draft`, the `_` and `.` exclusions, the
    symlink and reserved-name refusal, the link form, the annotation block)
    and its validation;
  - navigation generated from frontmatter;
  - the machine-readable site indexes (`llms.txt`, `llms-full.txt`);
  - the theme configuration, brand and hero, the hero chart built from demo
    data;
  - the site tooling's dependency group and exact pin;
  - fixture-based tests and a smoke test over a real build;
  - the deploy workflow, its forbidden-strings gate and its workflow test;
  - `Homepage` in `[project.urls]`;
  - a `CONTRIBUTING.md` section;
  - one new `docs/` page documenting the site, linked from `docs/index.md`.
- **Out of scope**:
  - the site's copy, and importing it (the maintainer's own commit);
  - every existing `docs/` page apart from one new link in `docs/index.md`;
  - every existing docs guard, and `Documentation` in `[project.urls]`;
  - `ci.yml` and `release.yml`;
  - an API reference, versioned docs, translations, a blog, analytics and
    comments;
  - DNS records, domain verification and the repository's Pages settings,
    which are documented for the maintainer, not automated;
  - a design pass beyond the brand brief;
  - rewording "fitdocs.ai" where it names the reference app, and the other
    Phase 9 direct-implementation candidates.
- **Adjacent expectations**:
  - distribution owns `pyproject.toml`, `CONTRIBUTING.md`, `CHANGELOG.md`
    and the forbidden-strings gate. This spec adds to the first three without
    breaking any existing pin: in `CHANGELOG.md`, one `[Unreleased]` entry
    that the Changelog duty owes for the new project URL. It reuses the gate
    and its secret without changing either;
  - the wheel and sdist contents are unchanged;
  - the runtime dependency list is unchanged;
  - the new `docs/` page passes every existing docs guard as written.

## Requirements

### Requirement 1: Content source and staging
**Objective:** As the maintainer, I want the build to read my pages from wherever they live and prepare them without touching them, so that I can keep editing my draft while the build is being developed.

#### Acceptance Criteria
1. The Site Build shall resolve its content directory in this order: an explicit command-line option, then an environment variable, then `website/content/` in the repository.
2. When the resolved content directory does not exist, the Site Build shall fail with a message naming the directory and the source it was resolved from.
3. The Site Build shall never create, modify, rename or delete any file in the content directory.
4. When a file or directory name in the content directory begins with `_` or `.`, the Site Build shall exclude it, and everything beneath it, from the site.
5. The Site Build shall carry every included non-markdown file into the site at the same relative path it has in the content directory.
6. When a page ends in an annotation block (the text from the last occurrence of a blank line, then `---`, then a line beginning `Annotations:`, to the end of the file), the Site Build shall remove that block and leave the rest of the page byte-for-byte unchanged, except for the one line Requirement 3.3 adds to the home page.
7. When a page contains a `---` horizontal rule that does not begin an annotation block, the Site Build shall keep it.
8. The Site Build shall not include any part of an annotation block in any page, search index or site index it produces.

### Requirement 2: The content contract
**Objective:** As the maintainer, I want one stated set of rules for my pages that the build checks exactly, so that a mistake in my copy is caught before it is published and never silently changes the site.

#### Acceptance Criteria
1. The Site Build shall require every included page to carry frontmatter with `title` (non-empty text), `description` (non-empty text), `section` (one value from the canonical section list) and `order` (an integer).
2. The Site Build shall use this canonical section list, in this order: Home, Why, Get started, Guides, Working with LLMs, Reference, Extend, Project.
3. The Site Build shall accept `draft` (true or false) as an optional key on any page, and `hero_title`, `hero_tagline` and `hero_actions` as optional keys on the home page only. `hero_actions` is a list of entries, each with `label` and `href` and optionally `primary` (true or false); an `href` is an absolute `https://` URL or the trailing-slash site path of an included page (for example `get-started/install/`).
4. When a page has `draft: true`, the Site Build shall exclude it from the navigation, the built site, search and both site indexes.
5. If a page lacks a required key, carries a key the contract does not allow, carries a value of the wrong type, names a section outside the canonical list, or carries a hero key while not being the home page, then the Site Build shall fail.
6. If two included pages in the same section share an `order` value, then the Site Build shall fail naming both files.
7. If the content directory holds included pages but no home page (`index.md` at its root), then the Site Build shall fail.
8. If the content directory holds no included page, then the Site Build shall fail with a message saying so.
9. When the Site Build finds contract violations, it shall report every violation in one run, each naming the file and the key, before exiting unsuccessfully.
10. The Site Build shall accept links between pages in a page body written in markdown link syntax as relative paths to the target's `.md` source file, optionally with a `#anchor`.
11. If the content directory contains a symbolic link, or a file named `llms.txt` or `llms-full.txt` at its root, then the Site Build shall fail naming it.
12. If a page links to another page's `.md` source from raw HTML rather than markdown link syntax, then the Site Build shall fail naming the file and line.

### Requirement 3: Navigation and home page
**Objective:** As a site visitor, I want pages grouped and ordered the way the maintainer intends, with a proper landing page, so that I can find my way from "what is this" to the detail I need.

#### Acceptance Criteria
1. The Site Build shall group the navigation by `section`, in canonical section order, omitting sections that have no included page.
2. The Site Build shall order pages within a section by ascending `order`.
3. The Site Build shall render the home page with the hero layout, showing `hero_title`, `hero_tagline` and `hero_actions` when present, by adding one `template` line to the frontmatter of the home page's built copy. That line is not a content key, and a page that sets `template` itself violates Requirement 2.5.
4. Where the home page omits a hero key, the Site Build shall render the hero without that element rather than substituting default text.
5. The Site Build shall show the power-vs-heart-rate hero chart on the home page from an image checked into the repository and generated from demo data, never from a real athlete's data.
6. The repository shall record how the hero chart image was produced, so that it can be regenerated.

### Requirement 4: Site features and brand
**Objective:** As a site visitor, I want the conventions of modern Python tool documentation, so that the site is fast to search, comfortable to read and easy to copy prompts from.

#### Acceptance Criteria
1. The Published Site shall offer full-text search over every included page.
2. The Published Site shall offer light and dark modes, follow the visitor's system preference by default, and let the visitor switch.
3. The Published Site shall show a copy button on every code block.
4. The Published Site shall show, on every page, an edit link that opens that page's source file under `website/content/` in the repository on GitHub.
5. The Published Site shall apply one palette, typeface and logo placeholder, stated in one place in the repository, in both light and dark modes.
6. The Published Site shall serve every page at a trailing-slash URL under `https://fitdocs.ai/`.

### Requirement 5: Machine-readable site indexes
**Objective:** As a user running fitdocs with an LLM agent, I want the site in the standard machine-readable form, so that the agent can read the documentation directly.

#### Acceptance Criteria
1. The Site Build shall publish `llms.txt` at the site root, following the llmstxt.org structure: the site title, a summary, then one entry per included page giving its title, absolute URL and description, grouped by section in navigation order.
2. The Site Build shall publish `llms-full.txt` at the site root, containing every included page's body with frontmatter and annotation blocks removed, in navigation order.
3. The Site Build shall exclude draft pages and `_`-prefixed files from both indexes.
4. When the content is unchanged, the Site Build shall produce byte-identical `llms.txt` and `llms-full.txt`.

### Requirement 6: Build validation and failure reporting
**Objective:** As the maintainer, I want every kind of broken page to stop the build with a message I can act on, so that a defect is fixed before it is published, not after.

#### Acceptance Criteria
1. If a page links to another page or asset that is not in the built site, including a draft or excluded page, then the Site Build shall fail.
2. If a link's `#anchor` does not match a heading in its target page (the same page or another), then the Site Build shall fail.
3. If a page links to a file or anchor under `docs/` by its GitHub URL (`https://github.com/joshua-stauffer/fitdocs/blob/main/docs/...`) and that file does not exist in the repository's `docs/` tree, or that anchor does not match a heading slug as GitHub generates it, then the Site Build shall fail.
4. If the site configuration contains a key, theme feature or plugin that is not on the build's allowlist, then the Site Build shall fail naming it.
5. When the site generator itself fails, the Site Build shall report each generator problem as a single line naming the offending file where one is known, and shall keep the full generator output available on request.
6. When the Site Build fails, it shall exit with a non-zero status and shall leave no partially built site in the output location.
7. The Site Build shall write its output to a location that is ignored by git and is never tracked.

### Requirement 7: Local preview
**Objective:** As the maintainer, I want a single command that shows my draft as the site will look and refreshes as I save, so that I can edit copy against the real rendering without committing anything.

#### Acceptance Criteria
1. The Site Preview shall build and serve the site locally from a content directory resolved as in Requirement 1.1, including a directory outside the repository.
2. When a file in the content directory is created, changed or deleted, the Site Preview shall rebuild, and the served site shall reflect the change without a restart.
3. If a rebuild fails validation, the Site Preview shall report the failure in the same form as the Site Build and keep running, and shall serve the change once it is fixed.
4. The Site Preview shall not create or modify any file in the content directory or among the repository's tracked files.

### Requirement 8: Site tooling and dependencies
**Objective:** As a fitdocs user and contributor, I want the site tooling kept strictly apart from the tool itself, so that installing fitdocs is unchanged and the site build is reproducible.

#### Acceptance Criteria
1. The fitdocs package's runtime dependency list shall be the pre-docs-site list plus `duckdb>=1.2,<2`, added by analytics-index; site tooling shall add no runtime dependencies, and optional dependencies shall remain empty.
2. The repository shall declare the site tooling in its own dependency group, with the site generator pinned to one exact version.
3. The fitdocs wheel and sdist shall contain exactly the members they contain today.
4. The site build logic shall depend only on the Python standard library and the YAML library fitdocs already depends on, apart from invoking the pinned site generator.

### Requirement 9: Tests
**Objective:** As a contributor, I want tests that fail when any promised build behavior breaks, so that a generator pin bump or a script edit cannot silently regress the site.

#### Acceptance Criteria
1. The test suite shall exercise every behavior in Requirements 1–3, 5 and 6 against fixture pages. Fixture pages contain no athlete data and are not site copy.
2. The test suite shall include a smoke test over a real build that checks navigation order, both site indexes, the copy-button and edit-link features, and that a broken link and a broken anchor each fail the build.
3. The test suite shall name, for each assertion, the change to the build that makes it fail.
4. Where the site tooling is not installed, the site-generator tests shall skip with a stated reason.
5. While the docs workflow runs the test suite, the site-generator tests shall run, and a skip there shall fail the workflow.

### Requirement 10: Deployment workflow
**Objective:** As the maintainer, I want the site built on every relevant change and published only from `main` after the forbidden-strings gate passes, so that fitdocs.ai always matches `main` and never carries encumbered content.

#### Acceptance Criteria
1. When a pull request or a push changes the site source, the build logic, the site configuration template, the site tooling pin, the `docs/` tree (whose files and anchors the site links to) or the workflow itself, the Docs Workflow shall build and validate the site.
2. The Docs Workflow shall deploy to the hosting service only from a push to `main`, never from a pull request or another branch.
3. The Docs Workflow shall run the forbidden-strings check over the staged content and the built output before any deploy step.
4. If the forbidden-strings match data is unavailable to the workflow, for any trigger including a pull request from a fork, then the Docs Workflow shall fail and shall not deploy.
5. If the forbidden-strings check finds a match, then the Docs Workflow shall fail and shall not deploy.
6. While the repository's content directory holds no included page, the Docs Workflow shall build and validate the fixture site and shall skip the deploy step, reporting that it did so.
7. The Docs Workflow shall grant publishing permissions only to the job that deploys and read-only repository access everywhere else.
8. The Docs Workflow shall reference every external action by an exact version tag or a full commit SHA.
9. The test suite shall include a workflow test for the Docs Workflow, covering Requirements 10.1–10.8, in the style of the existing CI and release workflow tests.

### Requirement 11: Project metadata and documentation
**Objective:** As a newcomer and as the maintainer, I want the site discoverable from the package and the site's own workings documented alongside the rest of the repository's docs, so that visitors find the site and the maintainer can run, feed and maintain it without this spec in hand.

#### Acceptance Criteria
1. The fitdocs package metadata shall declare `Homepage` as `https://fitdocs.ai`, and shall keep `Documentation` and every other existing project URL unchanged.
2. The repository shall add one page under `docs/` documenting the site, linked from `docs/index.md`, and shall change no other existing `docs/` page.
3. The site documentation page shall state the content contract of Requirement 2 in full.
4. The site documentation page shall explain how to build the site and how to preview it, including against a content directory outside the repository.
5. The site documentation page shall give the maintainer runbook: the DNS records, the Pages settings and domain verification, the content import step, and the procedure for bumping the site generator pin.
6. The site documentation page shall state that it documents the repository's website and is not one of the contracts governed by the compatibility policy.
7. The site documentation page shall make clear that the preview's rebuild-on-save belongs to the repository's site tooling, not to the fitdocs tool, and shall not contradict the published guarantee that fitdocs performs no watching and no scheduling.
8. `CONTRIBUTING.md` shall gain a section on building and previewing the site that points at the site documentation page, and every existing `CONTRIBUTING.md` pin shall still hold.
9. The site documentation page and the `docs/index.md` change shall pass every existing docs guard unchanged.

## Amendment 1 (2026-10-06): the docs-site dependency baseline includes the index, landed by analytics-index

Requirement 8.1 now defines the runtime dependency list as the pre-docs-site
list plus `duckdb>=1.2,<2`, added by analytics-index. The docs-site tooling
adds no runtime dependency, and optional dependencies remain empty. This is
pinned by `tests/sitebuild/test_repo_wiring.py::test_runtime_dependencies_are_the_pre_spec_literals`.
