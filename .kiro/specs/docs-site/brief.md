# Brief: docs-site

## Problem

fitdocs 0.1.0 is on PyPI (2026-09-19), but it has no front door. A newcomer
lands on the README or on `docs/`. Those pages are contract-grade: exact,
guarded by tests, and written for someone who already knows what a data root
or a disposition is. Nothing explains what fitdocs is for, walks a first-time
user from install to a first workout page, gives copy-paste prompts for
running it with an LLM agent, or states the philosophy behind it: local
first, private first, own your data forever, first-class LLM compatible.

The maintainer owns the domain fitdocs.ai and wants a standard Python docs
site there. The site's copy is hand-written and hand-edited. A 21-page first
draft exists outside this repository, in an iA Writer folder. The maintainer
will revise it **while this spec is implemented** and commit it only once
edited. The build therefore cannot own, generate or depend on that copy. It
must be ready to receive it.

## Current State

- **No site tooling exists.** There is no `mkdocs.yml`, no site generator in
  any dependency group, and no Pages workflow. `pyproject.toml` has one
  dependency group, `dev` (pytest, ruff, mypy, types-PyYAML,
  markdown-it-py).
- **`docs/` is the contract surface, and heavily guarded.**
  - `tests/test_docs_guarantees.py` reads `README.md` plus `docs/*.md` for
    corpus pins (never-delete, no-watching, resolution order, tile
    opt-out). Its anchor check walks `docs/**/*.md`, and its "project URL"
    rule governs README, CHANGELOG, SKILL.md and the AGENTS.md goldens.
  - `tests/test_install_docs.py` pins headings, phrases and `[load]` and
    `[history]` defaults on named pages.
  - `tests/test_compatibility_policy.py:419` allows the policy phrase only
    in `docs/compatibility.md`.
  - None of these read outside `README.md` and `docs/`. A new top-level
    directory is unguarded unless this spec guards it.
- **Forbidden strings.**
  - `tests/test_forbidden_strings.py` scans every tracked file
    (`git ls-files`), but only when `FITDOCS_FORBIDDEN_STRINGS` is set. It
    skips in CI (`ci.yml:55-56` runs pytest without it).
  - In CI, the `FITDOCS_FORBIDDEN_STRINGS_CONTENT` secret feeds only
    `scripts.check_artifacts` over wheel and sdist members (`ci.yml:73-84`).
  - A published web page is a distribution surface that no gate covers
    today.
- **Packaging is safe by construction.**
  - The sdist is `only-include` = `pyproject.toml`, `README.md`, `LICENSE`,
    `CHANGELOG.md` and `src/fitdocs` (`pyproject.toml:53-63`).
  - `tests/test_release_artifacts.py:3366-3433` asserts the member set
    exactly, derived from that list. A `website/` directory cannot leak.
  - `.gitignore` has no `site/` entry, and MkDocs and Zensical default
    `site_dir` to `site/`.
- **Dependencies.** `tests/test_determinism.py:672-715` pins
  `[project].dependencies` exactly and asserts
  `optional-dependencies == {}`; `tests/test_packaging.py:503-519` repeats
  the pin. No test pins `[dependency-groups]` or `uv.lock`.
- **CI.**
  - `ci.yml` runs on every push and PR.
  - `tests/test_ci_workflow.py` reads only `ci.yml`, and
    `tests/test_release_workflow.py` only `release.yml`. It asserts
    permissions `{contents: read}`, exactly one job, and the pin regex
    `@(v\d+(\.\d+){0,2}|<40-hex>)`.
  - No test globs `.github/workflows/`.
- **Project URLs.**
  - `pyproject.toml:33-44` declares 11 URLs, all on GitHub.
  - `tests/test_packaging.py:296-304` pins `Source`, `Documentation`
    (`.../blob/main/docs/index.md`), `Changelog` and `Issues`, but not the
    key set.
  - There is no `Homepage`.
- **The name "fitdocs.ai" already means something.** It names the reference
  application whose metric logic fitdocs borrows:
  - `README.md:34` links github.com/joshua-stauffer/fitdocs.ai;
  - steering uses the name the same way;
  - `src/fitdocs/metrics/sources.py` provenance says "inherited from
    fitdocs.ai", pinned by `tests/metrics/test_sources.py:1155-1173`.
- **The content draft** (outside the repo, for context only; the maintainer
  owns it):
  - 21 pages with YAML frontmatter `title`, `description`, `section`,
    `order`;
  - a `_README.md` of editorial notes, excluded by its underscore;
  - relative `.md` links between pages;
  - every file ends in an iA Writer authorship block
    (`\n\n---\nAnnotations: 0,N SHA-256 <hash>  \n&Claude: …  \n@Josh:   \n...\n`);
  - sections: Home, Why, Get started, Guides, Working with LLMs,
    Reference, Extend, Project.

## Desired Outcome

- `https://fitdocs.ai` serves a fast, searchable, light- and dark-mode docs
  site in the house style of uv, Ruff and FastAPI docs:
  - a hero home page;
  - nav grouped by section;
  - copy buttons on every code block, which the prompt library depends on;
  - edit-on-GitHub links;
  - `llms.txt` and `llms-full.txt` at the site root.
- The maintainer can preview their out-of-repo draft with one command that
  rebuilds on save, at any time, without committing anything.
- When the maintainer commits their edited copy into `website/content/`,
  the next push to `main` deploys it. Nothing in the build changes to accept
  it.
- A broken internal link or anchor, a malformed or missing frontmatter key,
  an unknown config key, or a forbidden string in content or output fails
  the build before anything is published.
- The build and its tests run entirely from fixture pages. The spec is
  complete, green and merged whether or not the maintainer's copy has
  landed.

## Approach

**Zensical plus a generator-agnostic build script** (chosen at discovery,
2026-09-28).

The script (`scripts/build_site.py` or similar) is plain Python with PyYAML,
which is already a dependency. It:
1. resolves the content directory: an explicit flag, else an environment
   variable, else `website/content/`;
2. stages every non-`_` markdown file into a build directory, stripping the
   trailing iA Writer annotation block (the suffix from the last
   `\n\n---\nAnnotations:` to end of file) and preserving relative layout
   and non-markdown assets;
3. validates frontmatter: `title`, `description`, `section` (one of the
   canonical section list) and `order` (int) are required. `draft: true`
   excludes a page. Missing, extra or duplicate values fail with a
   file-named message;
4. generates the explicit `nav:` grouped by `section` in canonical order,
   then by `order`;
5. injects `template: home.html` into the home page;
6. writes `mkdocs.yml` for the build from a checked-in template, checking
   every key against an allowlist, because Zensical silently ignores unknown
   keys, plugins and theme features;
7. writes `llms.txt` (title and description per page, absolute trailing-slash
   URLs) and `llms-full.txt` (the stripped bodies);
8. runs `zensical build` with `strict: true` and turns its traceback into a
   one-line, file-named failure.

A `serve` mode reruns steps 1–7 on change and serves the result. Zensical
is pinned exactly (`zensical==0.0.65` at discovery). Because all custom
logic lives in the script and the config template is Material-compatible,
falling back to `mkdocs-material` on MkDocs 1.6 is a dependency swap.

Why: the maintained successor to Material, already used by FastAPI; logic
kept out of generator hooks, which Zensical lacks; and the content/build
separation falls naturally out of the staging step. Material for MkDocs (end
of life 2027-05-05) and Sphinx+Furo were rejected; see the roadmap's Phase 9
approach decision.

**Viability (2026-09-28)**: a throwaway prototype built the real 21-page
draft end to end. Nav order, strict failures on missing pages and anchors,
theme features, the frontmatter-driven hero, `serve`, and every cross-page
anchor in the draft all worked. The build took about 0.3 s and produced
1.5 MB.

## Scope

- **In**:
  - `website/` source layout: `content/` (empty or placeholder until the
    maintainer's commit), `overrides/` (theme templates, including the home
    hero), `mkdocs.template.yml` and brand assets; build output gitignored;
  - the build script and its `build` and `serve` modes, including
    out-of-repo content (`--content PATH` / an env var);
  - **the content contract**, written down for the maintainer:
    - frontmatter keys and allowed `section` values;
    - optional hero keys on `index.md` (`hero_title`, `hero_tagline`,
      `hero_actions`);
    - `draft`, the `_` prefix rule, the relative-link form, and the
      annotation block;
  - the brand brief (palette, typeface, logo placeholder), realized as theme
    configuration and `overrides/` CSS. The hero shows the power-vs-HR chart
    from a checked-in demo SVG, never a real athlete's data;
  - `[dependency-groups] docs` with the exact Zensical pin;
  - `.gitignore` for build output;
  - tests:
    - fixture content covering nested sections, ordering, `draft`, the `_`
      exclusion, the annotation strip, the hero injection, llms output and
      config allowlist rejection;
    - a smoke test over a real build: nav order, `llms.txt` present,
      copy-button and edit-link features present, a broken link and a broken
      anchor each failing;
    - the fixtures must discriminate. Each assertion names the mutation it
      dies on (`change-protocol.md` § Fixture Discrimination);
  - `.github/workflows/docs.yml`:
    - build on PRs and pushes touching `website/`, the script or the
      template; deploy to GitHub Pages from `main` only;
    - `pages: write` and `id-token: write` scoped to the deploy job;
    - actions pinned by exact tag or SHA;
    - a forbidden-strings check over staged content and built output using
      the existing secret, failing closed as `ci.yml` does;
    - a matching `tests/test_docs_workflow.py`;
  - `Homepage = "https://fitdocs.ai"` in `[project.urls]`;
  - **the docs-site documentation, in `docs/`** (maintainer, 2026-09-28):
    one new page (working name `docs/website.md`), linked from
    `docs/index.md`, holding:
    - the content contract above;
    - building and previewing the site, including out-of-repo content;
    - the maintainer runbook: DNS records, Pages settings and domain
      verification, the content import step, the Zensical pin-bump
      procedure;
  - a short `CONTRIBUTING.md` section on building and previewing the site
    that points at that page.
- **Out**:
  - the site's copy: the maintainer's own commit into `website/content/`;
  - any change to existing `docs/` pages other than the one new link in
    `docs/index.md`; any change to existing docs guards; any change to
    `Documentation` in `[project.urls]`;
  - API reference via mkdocstrings (a follow-on);
  - versioned docs, i18n, a blog, analytics, comments;
  - DNS, domain verification and repo Pages settings (maintainer-only
    steps, documented not automated);
  - a design pass beyond the brief (a follow-on).

## Boundary Candidates

- **Content contract vs build.** The frontmatter schema, layout and
  annotation format are the only interface between the maintainer's copy and
  the build. Stating it once, and validating it in the script, is what lets
  the two proceed in parallel.
- **Build script vs site generator.** All custom logic lives in the script,
  which the generator never sees. The generator is a pinned, swappable
  renderer.
- **Build vs deploy.** Building and validating (local and CI) is separable
  from publishing (the Pages job on `main`, gated on forbidden strings).
- **Site vs `docs/`.** The site links to `docs/` by absolute GitHub URL. It
  never includes, copies or re-states the contract, so `docs/` guards stay
  the sole authority. The site's own documentation (content contract, build,
  runbook) is the one thing this spec adds to `docs/`: a new page that the
  existing guards cover like any other.

## Out of Boundary

- Writing, editing or importing the maintainer's page copy. A fixture page
  is test data, not site content.
- Existing `docs/` pages (apart from one link in `docs/index.md`) and any
  existing docs guard.
- Renaming or rewording "fitdocs.ai" in README, steering or runtime
  provenance. That is a Phase 9 direct-implementation candidate.
- Fixing `fitdocs plan`'s `--methodology` hint, or amending the CHANGELOG
  (Phase 9 direct-implementation candidates).
- Changing `ci.yml` or `release.yml`. The docs workflow is a separate file
  with its own test.

## Upstream / Downstream

- **Upstream**:
  - distribution: `pyproject.toml`, `[project.urls]`, `CONTRIBUTING.md`,
    `docs/releasing.md`, the CI conventions and action-pin format;
  - the forbidden-strings mechanism: `scripts/check_artifacts.py`, the
    `FITDOCS_FORBIDDEN_STRINGS_CONTENT` secret and
    `tests/test_forbidden_strings.py`;
  - PyYAML (already a runtime dependency) for frontmatter.
- **Downstream**:
  - the maintainer's content commit;
  - a later Claude Design restyle of `overrides/`;
  - an mkdocstrings API reference;
  - Phase 8 connector pages;
  - any future move of the Zensical pin to 0.1.x (due 2026-11-05).

## Existing Spec Touchpoints

- **Extends**: distribution. `Homepage` in `[project.urls]`,
  `CONTRIBUTING.md` build instructions beside its pinned `uv sync` text
  (`tests/test_contributing_doc.py:111-118`), and a new `docs/` page for the
  site's documentation, linked from the `docs/index.md` entry point
  (`tests/test_docs_guarantees.py:1105-1190`). Carried out inside this spec,
  and recorded under Phase 9 › Existing Spec Updates.
- **Adjacent**:
  - wiki-contract and the docs guard tests: no existing `docs/` page or
    guard changes; the new page must pass them (corpus pins, anchor walk,
    the `docs/index.md` link check);
  - `ci.yml` and `release.yml`: not touched; the new workflow mirrors
    their pin and permission conventions.

## Constraints

- **The runtime dependency list is frozen.** Site tooling goes only in
  `[dependency-groups] docs`, never `optional-dependencies`
  (`tests/test_determinism.py:715`). The build script imports nothing
  outside the stdlib and PyYAML, apart from invoking the pinned generator.
- **The Zensical pin is exact and bumped on purpose.** It is alpha:
  0.0.x, releases every few days, and unknown config silently ignored. A
  bump must pass the smoke test.
- **No personal data in the repo** (`structure.md`). The hero chart and any
  screenshots come from demo data. Fixture pages contain no athlete data.
- **Nothing publishes unchecked.** The forbidden-strings check runs over
  what is deployed and fails closed when its secret is absent, matching
  `ci.yml:73-84`.
- **The build output directory must not be `site/`** unless it is
  gitignored, and it must never be tracked.
- **Everything lands under `change-protocol.md`:** worktree, `impl/docs-site`
  branch, push on every commit, and a `--ff-only` merge with validation
  green.
