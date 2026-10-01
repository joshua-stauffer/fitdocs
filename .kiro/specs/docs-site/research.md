# Research & Design Decisions — docs-site

## Summary
- **Feature**: `docs-site`
- **Discovery Scope**: New Feature (greenfield site build), with integration into
  the existing release/CI guard surface (Complex Integration for the gate and the
  `docs/`/`pyproject.toml` pins).
- **Key Findings**:
  - Zensical 0.0.65 ignores a great deal without a word. It silently drops
    unknown top-level keys, unknown plugins, unknown theme features,
    `exclude_docs`, `not_in_nav`, `hooks`, `edit_uri_template`, per-page
    `edit_url` and `search.suggest`. It **publishes `_`-prefixed files and
    renders `_`-prefixed pages**, and it never checks image or asset links.
    Every guarantee in Requirements 1.4, 6.1 and 6.4 must therefore be enforced
    by the build script, not delegated to the generator.
  - Zensical's `site_dir` is wiped and repopulated on every build, **including
    failed ones**. Both `docs_dir` and `site_dir` must sit inside the config
    file's directory. `serve` writes into `site_dir`. Whether it notices a
    directory swap by rename depends on the platform (on Linux a rename-aside
    followed by a delete is picked up; on macOS a rename-aside is invisible),
    while in-place writes are seen in about 0.25 s on both, so an in-place
    `sync_tree` is the only spelling that works on both.
    This fixes the build-root layout (one dedicated root per mode), the failure
    cleanup (6.6) and the preview sync strategy (7.2).
  - The existing guard cores are reusable unchanged, with no second marker
    list. `tests._forbidden_strings.load/matches` and `tests._content_oracle.scan`
    are what `scripts/check_artifacts.py` already calls. `load(repo_root) is None`
    is the fail-closed signal. `_forbidden_strings` imports `pytest`, so the gate
    needs the dev group; the build logic does not.

## Research Log

### Zensical 0.0.65 behavior (hands-on probe, 2026-09-29)
- **Context**: The brief records a 2026-09-28 prototype. This probe re-verified
  it and filled the gaps the design depends on.
- **Sources Consulted**: `uv pip install zensical==0.0.65` on CPython 3.11.15
  (wheel `cp310-abi3`, `requires_python >=3.10`); `zensical/config.py`;
  https://zensical.org/docs/compatibility/mkdocs/migration/,
  https://zensical.org/docs/compatibility/mkdocs/plugins/,
  https://zensical.org/docs/setup/basics/,
  https://zensical.org/docs/setup/repository/,
  https://zensical.org/docs/setup/validation/.
- **Findings**:
  - **CLI.** `zensical build [-f FILE] [-c/--clean (cache)] [-s/--strict]`,
    `zensical serve [-f FILE] [-a IP:PORT] [-o] [-s (unsupported, warns)]`.
    There is no site-dir flag. The latest release is 0.0.66 (2026-09-28); the
    pin stays 0.0.65 as decided at discovery.
  - **Layout.** `docs_dir`/`site_dir` outside the config directory raise
    `ConfigurationError("site_dir must be within project root")`. A `.cache/`
    is created next to the config.
  - **Theme.** `variant` defaults to `modern` (Inter / JetBrains Mono).
    `variant: classic` gives the Material look.
  - **URLs.** `use_directory_urls` defaults to true: `guide/nested.md` is
    served as `guide/nested/`.
  - **Edit links.** An edit link is exactly `edit_uri` plus the path relative
    to `docs_dir`.
    - The default `edit_uri` is `edit/master/<docs_dir>`, which is wrong on
      both counts.
    - `edit_uri_template` and frontmatter `edit_url` are silently ignored.
    - A page whose `template:` override replaces the `content` block loses the
      edit button.
  - **Copy button.** Added client-side. The static marker is the feature name
    inside `<script id="__config">`.
  - **Search.** `search.json` at the site root, holding the full section text
    of every rendered page, including pages outside the nav.
  - **Files.** Non-markdown files are copied. `_`-prefixed files and
    directories are copied or rendered; dotfiles are skipped. Orphan pages are
    built without a warning. The 0.0.65 sitemap lists nav pages only (fixed in
    0.0.66).
  - **Strict failures** exit 1. The report goes to stderr, always ANSI-coloured
    (`NO_COLOR`/`TERM=dumb` have no effect):
    `Warning: page does not exist` / `anchor does not exist`, followed by a
    `╭─[ <docs_dir-relative path>:<line>:<col> ]` frame. All issues are listed
    before `RuntimeError: Aborted because --strict flag is set` and its
    traceback.
    - A config YAML error is a clean `Error: …` line with no traceback.
    - An unknown markdown extension or a missing template ends in a
      `RuntimeError:` line with no file named.
    - Both `strict: true` and `-s` fail the build.
  - **Not checked:** absolute `http(s)` URLs, `mailto:`, missing images and
    assets, and missing `extra_css` targets.
  - **Silently ignored** (exit 0): unknown top-level keys, plugins (including
    `llmstxt`) and theme features; `exclude_docs`, `not_in_nav`, `hooks`,
    `edit_uri_template`. **Errors** (exit 1): unknown `search` options, unknown
    markdown extensions, a missing template.
  - **`markdown_extensions`** *replaces* Zensical's whole default extension
    set.
  - **serve** picks up these changes: an in-place file edit, a config edit, an
    override-template edit, a new page, a delete, and a re-create. A
    rename-swap of the staged directory is not detected within 20 s on macOS,
    and is platform-dependent on Linux (see above).
    `copytree(dirs_exist_ok=True)` over the tree is detected.
- **Implications**:
  - The allowlist, `_` exclusion, dotfile exclusion, asset-link checks and
    config-asset checks are all script-owned.
  - The build root is dedicated per mode, the failure path deletes `html/`,
    and the preview syncs in place.
  - `edit_uri` is set explicitly, the home template must keep the edit action,
    `variant: classic` is set explicitly, and `markdown_extensions` stays out
    of the allowlist.

### Theme feature names honored by 0.0.65
- **Context**: The allowlist (6.4) needs the set of theme features the pinned
  generator actually implements. There is no official list.
- **Findings**: The names referenced by the 0.0.65 bundle and templates are
  `announce.dismiss`, `content.action.edit`, `content.action.view`,
  `content.code.annotate`, `content.code.copy`, `content.code.select`,
  `content.footnote.tooltips`, `content.lazy`, `content.tabs.link`,
  `content.tooltips`, `header.autohide`, `navigation.expand`,
  `navigation.footer`, `navigation.indexes`, `navigation.instant`,
  `navigation.instant.prefetch`, `navigation.instant.preview`,
  `navigation.instant.progress`, `navigation.path`, `navigation.prune`,
  `navigation.sections`, `navigation.tabs`, `navigation.tabs.sticky`,
  `navigation.top`, `navigation.tracking`, `search.highlight`, `search.share`,
  `toc.follow`, `toc.integrate`. `search.suggest` is absent, so it does
  nothing.
- **Implications**: The allowlist constant is this set, and re-deriving it is
  a step of the pin-bump procedure.

### Existing guard surface (codebase analysis)
- **Sources**:
  - `scripts/check_artifacts.py:91-99,110-149,777-789,872-939`
  - `tests/_forbidden_strings.py:43-45,102,147,435,481`
  - `tests/_content_oracle.py:169`
  - `.github/workflows/ci.yml:23-100`
  - `tests/test_ci_workflow.py:107,137,186,191,300,332,357-451`
  - `tests/test_docs_guarantees.py:81,220-223,884,951,1018-1031,1105-1190,1565-1691`
  - `tests/test_compatibility_policy.py:65,413-431`
  - `tests/test_version_identity.py:131-158`
  - `tests/test_contributing_doc.py:57-126,222-289`
  - `tests/test_forbidden_strings.py:639-710,1015,1274-1351`
  - `pyproject.toml:33-72,161-163`
  - `.gitignore`
- **Findings**:
  - **scripts/ convention.**
    - `REPO_ROOT = Path(__file__).resolve().parents[1]`.
    - An argparse `_build_parser()` with `prog="python -m scripts.<name>"`, a
      `main(argv) -> int`, and `raise SystemExit(main(sys.argv[1:]))`.
    - Exit codes are 0 clean, 1 findings, 2 hard error.
    - mypy strict covers `scripts/` through `[tool.mypy].files`, and ruff
      covers every non-ignored `.py`.
  - **Gate.** `load(repo_root) -> ForbiddenStrings | None` returns `None` only
    when `FITDOCS_FORBIDDEN_STRINGS` is unset, and raises
    `ForbiddenStringsSourceError` when the variable is set but unusable.
    - `matches(text, fs)` and `oracle_scan(text, FINGERPRINTS, WINDOW_LENGTHS,
      SALT)` are the per-file cores.
    - `scan_tree` decodes strictly and never runs the oracle, so it is not
      suitable.
    - `check_artifacts._is_text_like` excludes `.html/.css/.js/.svg`, so it is
      not reusable for built output.
    - The permissive decode loop in `test_forbidden_strings.py:669-710` is the
      model to follow.
    - `ci.yml` writes the secret to `$RUNNER_TEMP/forbidden-strings.txt` and
      fails closed on an empty secret with `::error::gate_not_run`.
  - **Workflow tests.** They load YAML with `yaml.safe_load`, where
    `doc[True]` is the `on` key. The pin regex is
    `@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$`, and bash step bodies run through
    `bash -eo pipefail`. No test globs `.github/workflows/`.
  - **Docs guards.**
    - The corpus is README plus top-level `docs/*.md`, so a new page joins it.
    - Positive pin: "performs no watching and no scheduling". Negative pins
      include "fitdocs ships no".
    - "two minor releases" may appear only in `docs/compatibility.md`.
    - The entry-point check needs its 10 required links. Other pages need not
      be linked, though a table row is the convention.
    - `_heading_slugs` (test_docs_guarantees.py:884) is not a GitHub-faithful
      slugger: it deletes `_`, adds no `-1` suffixes and is not fence-aware.
  - **Version identity.** The literal `0.1.0` is forbidden in tracked or
    untracked non-ignored files under `src/`, `tests/` and `docs/`, and in
    `README.md` and `CHANGELOG.md` outside their permitted places.
    `website/`, `scripts/`, `.github/` and `.kiro/` are not scanned.
  - **Notice/mark guard** (ungated, runs everywhere). Every tracked file must
    be a regular file and valid UTF-8 unless it ends `.fit`/`.png`/`.gz`, so
    `.woff2`, `.ico` and `.jpg` fail. The reserved-rights phrase and the trademark sign (U+2122) are
    forbidden.
  - **CONTRIBUTING.** Its 8 H2s stay in order and new H2s are allowed. The
    fenced blocks in "The three quality gates" must equal the ci.yml gate
    commands. Relative links must resolve.
  - **pyproject.**
    - `[project.urls]` has 11 keys; only Source, Documentation, Changelog and
      Issues are pinned by value, and no test pins order or key set.
    - `[dependency-groups]` has only `dev`, and there is no
      `[tool.uv] default-groups`, so plain `uv sync` installs dev only.
    - `optional-dependencies == {}` is pinned.
  - **`.gitignore`** already ignores `build/` at any depth. The sdist ships
    `.gitignore`, so a new line changes its content but not the member set.
  - **Hero chart.**
    - `render_hero_chart(spec: HeroChartSpec) -> str`
      (`src/fitdocs/render/charts/hero.py:164`) is pure and deterministic.
    - `HeroChartSpec(x, x_unit, series, backdrop, width=800, height=260)` and
      `HeroSeries(label, unit, color, values)`.
    - The colors are `HR_COLOR #d5455f` and `POWER_COLOR #cd6600`.
    - `test_preserved_guarantees.py:456-550` byte-pins `src/fitdocs/render` and
      the golden file set, so nothing new goes there.
- **Implications**: A new gate module reimplements only the tree walk and
  calls the cores. The docs page wording must avoid three pinned phrases and
  the version literal. Brand assets are SVG and CSS only, with no vendored
  fonts. The hero generator lives in `scripts/`, outside the build logic.

### GitHub Pages deployment via Actions
- **Sources**:
  - https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
  - https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site
  - https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages
  - https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
  - https://github.com/actions/starter-workflows/blob/main/pages/static.yml
  - https://github.com/actions/upload-pages-artifact/blob/v5.0.0/action.yml
- **Findings**:
  - **Latest exact tags** (2026-09-29): `actions/checkout@v7.0.1`,
    `astral-sh/setup-uv@v10.2.0` (no floating major tag since v8),
    `actions/upload-pages-artifact@v5.0.0`, `actions/deploy-pages@v5.0.1`,
    `actions/configure-pages@v6.0.0`.
  - **Deploy job.** It needs `pages: write` and `id-token: write`, plus the
    `github-pages` environment. The starter workflow uses the concurrency group
    `pages` with `cancel-in-progress: false`.
  - **Artifact.** The upload tars with `--dereference` and excludes `.git`,
    `.github` and dotfiles by default. The site is limited to 1 GB.
  - **Custom domain.** An Actions-published site needs no CNAME file, and any
    existing one is ignored.
    - The domain is set in repo Settings → Pages.
    - Verification is a TXT record `_github-pages-challenge-<owner>.<domain>`,
      kept in place.
    - Apex A records are `185.199.108–111.153`; AAAA records are
      `2606:50c0:8000–8003::153`. `www` gets a CNAME to `<owner>.github.io`.
    - Enforce HTTPS can take up to 24 h to become available.
- **Implications**: The deploy job is minimal (`deploy-pages` only, with no
  `configure-pages` step). DNS and verification go in the runbook (11.5).

### llms.txt
- **Sources**: https://llmstxt.org/ (source https://llmstxt.org/index.md);
  https://www.mintlify.com/blog/simplifying-docs-with-llms-txt.
- **Findings**:
  - **llms.txt.** An H1 project name is the only required element. It is
    followed by a blockquote summary, optional prose, and H2-delimited file
    lists of `- [name](url): notes`. `## Optional` has a special meaning.
  - **llms-full.txt** is a de-facto convention (Mintlify), not part of the
    spec: every page's full text in one file.
- **Implications**: The file-list sections are named after the canonical
  sections. None is named `Optional`, so no page is marked skippable by
  accident. The `llms-full.txt` layout is ours to define: per page, a title
  heading, a source URL line, then the body.

### GitHub heading slugs vs. the site's slugs
- **Sources**: https://github.com/Flet/github-slugger (`index.js`,
  `script/generate-regex.js`, v2.0.0), plus a measured Zensical build.
- **Findings**:
  - **GitHub (github-slugger).** Lowercase the text. Remove the
    non-alphabetic characters of these Unicode categories: Other_Number;
    Close, Final, Initial, Open and Other punctuation; Dash_Punctuation
    except `-`; Symbol (including emoji); Control, Private_Use, Format and
    Unassigned; and Separator except the plain space. Turn each space into `-`
    without collapsing hyphens, suffix duplicates `-1`, `-2`, …, and keep
    code-span text. **Connector_Punctuation (`_`) is kept.** Verified
    2026-09-30 against
    https://raw.githubusercontent.com/Flet/github-slugger/master/script/generate-regex.js;
    the probe summary's "all punctuation except `-`" was wrong on this
    point.
  - **Zensical** uses Python-Markdown's toc slugify (ASCII fold, collapse
    hyphens, `_1` for duplicates), which differs on duplicates, `&`, `—`,
    emoji and accents.
- **Implications**:
  - Requirement 6.3 (links to `docs/` on GitHub) needs a GitHub-faithful
    slugger of our own. It must be fence-aware and apply duplicate suffixes.
  - Requirement 6.2 (links inside the site) uses the generator's own slugs
    through its strict anchor check, so the two schemes never mix.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Script-first pipeline plus a pinned renderer | Pure planning modules (content, links, outline, config) produce a byte map; a stager writes it; the generator renders it in strict mode | Every guarantee is testable without the generator; generator swap is a dependency change | Duplicates a little of what a mature generator would validate | Chosen: Zensical ignores too much to be trusted with any guarantee |
| Generator hooks and plugins | Custom logic as MkDocs hooks or plugins | Idiomatic in MkDocs 1.x | Zensical has no `hooks:` and silently ignores unlisted plugins | Rejected at discovery |
| Generator-native nav (awesome-nav or literate-nav) | Let a plugin order pages | No nav code | Sorts by path or title only, not by `section`/`order` | Rejected at discovery |

## Design Decisions

### Decision: One build root per mode, everything the generator sees inside it
- **Context**: Zensical requires `docs_dir` and `site_dir` inside the config
  directory, wipes `site_dir` on every build, and `serve` writes into
  `site_dir` too.
- **Alternatives Considered**:
  1. Put the config at the repo root and point `docs_dir` at `website/content/`.
     This fails 1.3 (the content directory must never be modified) and
     out-of-repo preview.
  2. Use one shared root for build and preview. Serve and build would then
     clobber each other's `site_dir`.
- **Selected Approach**: A build root is a dedicated directory holding
  `mkdocs.yml`, `staged/` (docs_dir), `overrides/` (custom_dir, copied from
  `website/overrides/`) and `html/` (site_dir), plus Zensical's `.cache/`.
  - `build` uses `website/build/site/`; `serve` uses `website/build/preview/`,
    with a check root and a live root.
  - Every generated path in the config is relative, so the same config text is
    valid in any root.
  - A `--build-dir` inside the repository is accepted only under
    `website/build/`.
- **Rationale**: This satisfies 6.6, 6.7 and 7.4 by construction. It also lets
  tests build into `tmp_path`.
- **Trade-offs**: `website/overrides/` is copied into every root, and preview
  must watch it too.

### Decision: Build-owned assets are staged under `_brand/`
- **Context**: The logo, brand stylesheet and hero chart must be in the built
  site whatever the content holds. Whether Zensical copies static files from
  `custom_dir` was not verified.
- **Selected Approach**: `website/assets/*` is staged to `staged/_brand/`.
  Content paths beginning with `_` are excluded before staging (1.4), so no
  content file can collide with a build-owned path. Zensical copies
  `_`-prefixed files (verified).
- **Trade-offs**: A `_brand/` URL segment is public. Pages published by
  Actions are served as-is, with no Jekyll pass that would drop `_` paths.

### Decision: Template injection into the home page, and hero actions as site URLs
- **Context**: The hero layout needs `template: home.html` in page meta, which
  is the only verified selection mechanism. Hero buttons need URLs, and
  templates cannot resolve `.md` paths.
- **Alternatives Considered**:
  1. Detect the home page in `main.html` via `page.is_homepage`, which is
     unverified in Zensical's template context.
  2. Rewrite hero `.md` hrefs into URLs in staged frontmatter, which adds a
     second transformation.
- **Selected Approach**:
  - Staging inserts exactly one line, `template: home.html`, directly after the
    home page's opening `---`. It is the only change to any page other than
    the annotation strip; every other page is staged byte-for-byte as stripped.
  - `template` is not a content key, so a page that sets it is a violation.
  - `hero_actions[].href` is authored as an absolute `https://` URL or as a
    site path in trailing-slash form (`get-started/install/`). The script
    validates a relative href against the URL paths of included pages.
- **Rationale**: This uses only mechanisms the probe verified, and keeps 1.6's
  byte-exactness auditable in one rule.
- **Follow-up**: The maintainer's draft may shape `hero_actions` differently.
  The contract defines the shape and the draft adapts to it when imported.

### Decision: Script-level validation before the generator, generator strictness for page links and anchors
- **Context**:
  - Zensical strict catches missing pages and anchors, cross-page and
    same-page, and reports all of them.
  - It does not catch assets, `extra_css`/logo targets, template links, or
    links to `docs/` on GitHub.
- **Selected Approach**:
  - **The script checks:** the content contract (2.x); asset and non-page
    link targets (6.1); hero hrefs (6.1); GitHub `docs/` URLs with a
    GitHub-faithful slugger (6.3); config allowlist and config-referenced
    assets (6.4).
  - **The generator checks:** `.md` page targets (including draft and
    excluded pages, which are simply absent from `staged/`) and anchors (6.1,
    6.2), under `strict: true`.
  - Every issue is reported as one `path[:where]: message` line (6.5).
- **Rationale**: This covers each requirement once, with no second anchor
  slugger for the site's own headings.

### Decision: Preview = the build pipeline in a check root, then an in-place sync into the live root
- **Context**:
  - 7.3 wants failures reported in the build's own form, with the last good
    site kept serving.
  - `serve --strict` is unsupported.
  - A rename-swap is not reliably seen by `serve` (platform-dependent).
- **Selected Approach**:
  - The preview polls the content dir, `website/overrides/`,
    `website/assets/` and the config template, with stdlib `os.scandir` and
    `(mtime_ns, size)` snapshots every 0.5 s.
  - On a change it runs the full `build` pipeline, with strict generator, into
    `preview/check`.
  - On success it syncs the tree in place into `preview/live`: it writes
    changed files, deletes removed ones, and never renames directories.
    `zensical serve` runs on `preview/live` and rebuilds from those writes.
  - On failure it prints the same lines as `build` and leaves `live`
    untouched.
- **Trade-offs**: Each save runs two generator builds (check, then serve's
  rebuild), about 0.3 s each at the draft's size. That is acceptable.
  inotify behavior on Linux was not probed; in-place writes are the portable
  path.

### Decision: The forbidden-strings gate is a new script over directory trees, reusing the cores
- **Context**: 10.3–10.5 require the gate over staged content and built output.
  Both `check_artifacts.py` and `ci.yml` are out of bounds.
- **Selected Approach**: `scripts/check_site.py` walks the given roots.
  - Any symlink is a finding.
  - Every file is decoded permissively; its content goes through
    `matches` + `oracle_scan`, and its root-relative path through `matches`.
  - `load() is None` produces `GATE_NOT_RUN` (exit 1, message contains
    `gate_not_run`). A set-but-unusable source is exit 2.
  - It imports the cores and defines no marker list.
- **Trade-offs**: It needs the dev group at run time, because
  `tests._forbidden_strings` imports `pytest`. It is not build logic, so 8.4
  still holds for the build modules.

### Decision: Brand values (proposed, maintainer approval at design review)
- **Context**: The requirements leave concrete brand values to the design
  (Introduction; 4.5).
- **Selected Approach**:
  - **Palette.**
    - Header: graphite `#1f2933` with white text (14.8:1).
    - Light mode: accent and links in HR-deep red `#b8324b` (5.8:1 on white).
    - Dark mode (`slate` scheme): accent `#f07d8e` (6.2:1 on `#1e2129`).
    - The chart's own `#d5455f` is used decoratively only, never for text.
  - **Typeface.** System UI and monospace stacks with `theme.font: false`, so
    no request goes to a third-party font host. That fits
    "private first", and no font files are vendored (the tracked-file guard
    refuses `.woff2`).
  - **Logo.** A placeholder monochrome SVG (a page outline with a pulse line)
    that also serves as the favicon.
  - **Theme.** `variant: classic`.
  - All colors and font stacks live in `website/assets/brand.css`.
- **Rationale**: It ties the brand to the product's own hero chart, meets AA
  contrast, and involves no third-party requests.

### Decision: Dotfiles and symbolic links in the content directory
- **Context**:
  - The iA Writer folder may hold `.DS_Store` and similar files.
  - Zensical skips dotfiles, and the Pages artifact excludes them.
  - Symlinks are refused by the Pages artifact and by the gate.
- **Selected Approach**:
  - Names beginning with `.` are excluded like `_` names. They would never
    reach the site anyway, and the contract says so explicitly.
  - A symbolic link in the content directory is a contract violation naming
    the file, never silently followed or dropped.
- **Follow-up**: Both rules are stated in the content contract (11.3).

## Synthesis Outcomes
- **Generalization**:
  - Nav order, `llms.txt` order and `llms-full.txt` order are one ordering
    function, `outline.ordered_pages`.
  - Contract violations, link problems, config problems and translated
    generator issues share one `Problem` shape and one line format. That is
    what makes 2.9, 6.5 and 7.3 "the same form".
- **Build vs. adopt**:
  - Adopted: Zensical (rendering, search, strict page/anchor checks), the
    purge guard cores, and GitHub's Pages actions.
  - Built: the content contract, the link and asset checks the generator
    skips, the GitHub slugger (none exists in stdlib, and the test-side
    `_heading_slugs` is not faithful), llms output (Zensical has none) and the
    in-place preview sync.
  - Rejected: `watchdog` (adds a dependency, 8.4) in favor of stdlib polling;
    `markdown-it-py` for link extraction (dev-only, 8.4) in favor of a
    fence-aware regex scanner scoped to inline links, images, reference
    definitions and HTML `href`/`src`.
- **Simplification**:
  - No `configure-pages` step, no `workflow_dispatch`, no log file (the
    `--verbose` flag is the "on request" path), no `markdown_extensions`
    override.
  - One `stage.plan_tree` byte map serves build, preview and the byte-exactness
    tests.

## Risks & Mitigations
- **Zensical alpha churn.** The pin is exact, the pin-bump procedure re-derives
  the feature allowlist, and the smoke test (9.2) must pass.
- **Failure-format drift in Zensical.** The translator falls back to reporting
  the final error line verbatim when it cannot parse a frame. A canned-output
  unit test pins today's format, and the smoke test pins end-to-end behavior.
- **Linux file-watch behavior.** The preview uses in-place writes, and the
  preview test runs in the docs workflow on ubuntu.
- **Rebase conflict with `connectors`.** Both specs add one `docs/index.md`
  row and one `[project.urls]` key. Homepage goes first in `[project.urls]`,
  so the edits are not adjacent. The index row conflict is keep-both.
- **Main is red** (queue `2026-09-29-main-red-since-agents-skills-symlinks`).
  Validation at merge must distinguish that pre-existing failure from
  regressions.

## References
- https://zensical.org/docs/compatibility/mkdocs/migration/ — unsupported
  mkdocs.yml keys
- https://zensical.org/docs/compatibility/mkdocs/plugins/ — supported plugins;
  "silently ignores the configuration for plugins that are not listed"
- https://zensical.org/docs/setup/repository/ — `repo_url`, `edit_uri`,
  `content.action.edit`
- https://llmstxt.org/ — llms.txt structure
- https://github.com/Flet/github-slugger — the GitHub heading slug algorithm
- https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
  — Actions publishing, permissions, no CNAME
- https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages
  — the TXT challenge record
