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

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
