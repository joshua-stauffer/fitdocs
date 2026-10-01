# Implementation Plan

## Ground rules for every task

- **Every test function names its mutation.** Its docstring carries a
  `Dies on:` line naming one change to *production* code that turns it red
  (9.3; `change-protocol.md` § Fixture Discrimination).
  - Apply that change, observe red, revert, observe green, and record the run
    in the task's Implementation Notes. Group assertions that one mutation
    kills.
  - Run mutations through `uv run pytest` only.
  - Delete every `__pycache__` directory under `scripts/` before each
    mutation run, `scripts/sitebuild/__pycache__` included:
    `find scripts -name __pycache__ -type d -prune -exec rm -rf {} +` from
    the worktree root. The root `conftest.py` purges bytecode only under
    `src/`, so a same-size edit to `scripts/` reverted within a second can
    run stale bytecode (log WARN 2026-09-18T13:56).
- **Every task's done state includes the static gates.** `uv run ruff check .`,
  `uv run ruff format --check .` and `uv run mypy` are green. `tests/sitebuild`
  is under mypy strict from task 1.1 on.
- **Generator-dependent tests run with the docs group.** Run
  `uv run --group docs pytest tests/sitebuild` for anything behind
  `requires_zensical`.
  - A plain `uv sync` removes Zensical, after which `uv run pytest` *skips*
    those tests, which proves nothing about them (`uv run` alone does not
    remove an already-synced Zensical). Before calling a
    generator-touching task done, run it with `FITDOCS_REQUIRE_SITE_TOOLING=1`
    so a skip is a failure.
  - Mutating `pyproject.toml` under `uv run` silently re-resolves `uv.lock`.
    After any manifest mutation, restore with
    `git show HEAD:uv.lock > uv.lock` and check `git status` (log WARN
    2026-09-18T10:44).
- **Build logic imports only the standard library, `yaml` and
  `scripts.sitebuild`** (8.4). That covers `scripts/build_site.py` and
  `scripts/sitebuild/**`: never `fitdocs`, never `tests`, never
  `markdown_it`, never `zensical` (it is invoked as a subprocess).
  `scripts/check_site.py` and `scripts/make_hero_chart.py` are not build logic
  and have their own allowed imports (design.md § Allowed Dependencies).
- **Out of bounds, never edited:**
  - `scripts/check_artifacts.py`, `tests/_forbidden_strings.py`,
    `tests/_content_oracle.py`, `tests/_content_fingerprints.py`;
  - `.github/workflows/ci.yml`, `.github/workflows/release.yml`;
  - anything under `src/fitdocs/`;
  - every existing test module;
  - every existing `docs/` page except the one row added to `docs/index.md`;
  - `[project.urls]` values other than the added `Homepage`;
  - `website/content/` beyond its `.gitkeep`.

  A task that believes it must touch one of these stops and reports.
- **Wording and literal guards.**
  - The package's current version literal (the `version` value in
    `pyproject.toml`) must not appear anywhere under `tests/` or `docs/`,
    untracked scratch files included (`tests/test_version_identity.py` scans
    `git ls-files -co --exclude-standard`).
  - `docs/website.md` never contains "fitdocs ships no", "ships no
    methodology", "ships no calculator", "registers nothing", "registers
    **nothing**", "is empty on a fresh interpreter" or "two minor releases"
    (`tests/test_docs_guarantees.py:1018-1031`,
    `tests/test_compatibility_policy.py:65`).
  - No file carries the reserved-rights notice phrase or the trademark sign (U+2122).
- **Tracked files are UTF-8 regular files.** Never add `.woff2`, `.ico`,
  `.jpg` or `.webp`. Symbolic-link test cases are created in `tmp_path` only.
- **Tests never write into the repository tree.** Build roots, preview roots
  and content copies live in `tmp_path`.
  - A test that spawns a CLI uses `Path(sys.executable).parent`, never
    `shutil.which`, and passes an explicit `cwd`.
  - It pops `FITDOCS_SITE_CONTENT`, `FITDOCS_FORBIDDEN_STRINGS` and
    `FITDOCS_DATA` from the child environment unless it sets them on purpose.
  - No test reads git history: CI checks out at depth 1.
- **Shared files with live Phase 8 sessions.** `impl-connectors` also appends
  a `docs/index.md` row, a `[project.urls]` key and `CHANGELOG.md`
  `[Unreleased]` bullets. `pyproject.toml` and `uv.lock` are shared by every
  lander.
  - Edit these append-only.
  - Read the agent log and write a `TOUCHING` line before editing them.
  - On rebase, keep both sides.

- [x] 1. Foundation: tooling, the contract model, the fixture site

- [x] 1.1 Add the site-tooling dependency group and the repository wiring every later task relies on
  - **`pyproject.toml`.**
    - Add `docs = ["zensical==0.0.65"]` under `[dependency-groups]`, then
      `uv lock`.
    - The runtime `dependencies`, the empty `optional-dependencies` and the
      `dev` group are untouched.
    - Add `tests/sitebuild` to `[tool.mypy].files`, following the
      listed-test convention. `tests/test_docs_workflow.py` is added by 5.1,
      together with the file itself, because mypy refuses a listed path that
      does not exist.
  - **Git and package markers.**
    - Add an explicit, commented `/website/build/` line to `.gitignore`.
    - Create `website/content/.gitkeep`.
    - Create `scripts/sitebuild/__init__.py`. Its docstring states the
      stdlib-plus-PyYAML rule and that the package never ships.
  - **Test scaffolding.**
    - Create `tests/sitebuild/__init__.py`.
    - Create `tests/sitebuild/conftest.py` with a `requires_zensical`
      fixture. It checks for `Path(sys.executable).parent / "zensical"` and
      skips with the reason `site tooling not installed: uv sync --group docs`.
      When `FITDOCS_REQUIRE_SITE_TOOLING=1` it fails instead of skipping.
    - Add a helper that copies a fixture tree into `tmp_path`.
    - `conftest.py` belongs to this task and 1.3. Later tasks keep their
      helpers in their own test modules, so parallel tasks never contend for
      it.
  - **`tests/sitebuild/test_repo_wiring.py`** (first tests):
    - the runtime dependencies and `optional-dependencies` equal their
      literal pre-spec values;
    - `docs` is exactly `["zensical==0.0.65"]`, with an `==` pin and no range;
    - `git check-ignore -q website/build/probe` succeeds, and
      `git ls-files website/build` is empty;
    - the `requires_zensical` fixture skips with the stated reason, and fails
      under the environment variable (monkeypatched executable path);
    - the Dies-on meta-test: every test function in `tests/sitebuild/*.py`
      and `tests/test_docs_workflow.py` (when present) has a docstring with a
      `Dies on:` line. It must be non-vacuous: at least this module's own
      tests are scanned.
  - **Done when** `uv sync --group docs` then
    `uv run --group docs zensical --version` prints `0.0.65`, and a plain
    `uv sync` still installs no Zensical. `uv run pytest tests/sitebuild` is
    green, and the full suite, ruff, format and mypy are green.
  - _Requirements: 6.7, 8.1, 8.2, 9.3, 9.4, 9.5_

- [x] 1.2 Define the content contract and the shared value types
  - Create `scripts/sitebuild/model.py` exactly as design.md § SiteModel
    specifies:
    - the constants `SECTIONS`, `REQUIRED_KEYS`, `OPTIONAL_KEYS`,
      `HERO_KEYS`, `HERO_ACTION_KEYS`, `HOME_PAGE`, `HOME_TEMPLATE`,
      `RESERVED_ROOT_NAMES`, `BRAND_DIR`, `CONTENT_ENV_VAR` and
      `ANNOTATION_MARKER`;
    - `ContentSource`, `ResolvedContent`, `Problem`, `HeroAction`, `Page`,
      `Asset` and `SiteContent`.

    No I/O, standard library only.
  - `Problem.render()` joins the non-empty fields with `": "` and never
    contains a newline. This is the one line format for 2.9, 6.5 and 7.3.
  - **Tests** (`tests/sitebuild/test_model.py`):
    - `SECTIONS` is the eight canonical names in canonical order;
    - render drops empty fields;
    - render of a message containing a newline yields a single line (the
      newline replaced, not kept);
    - the key tuples are disjoint.
  - **Done when** the model imports cleanly under mypy strict and its tests
    are green with named mutations.
  - _Requirements: 2.1, 2.2, 2.3, 2.9_

- [x] 1.3 Build the valid fixture site every later test derives from
  - Create `tests/sitebuild/fixtures/site/` as design.md § Testing Strategy
    describes. It contains:
    - `index.md` in `Home`, with `hero_title`, two `hero_actions` (one
      `primary`, one with site path `get-started/install/`), no
      `hero_tagline`, an annotation block, and a link to a Why page with an
      anchor. The site path must equal an included page's URL path, so one
      Get started page is exactly `get-started/install.md`;
    - a Why page with a plain `---` rule, an annotation block carrying a
      distinctive sentinel word, and a `docs/` GitHub URL to a real heading of
      `docs/configuration.md` (for example the `[load]` table heading);
    - two Get started pages whose `order` disagrees with their alphabetical
      order, one with a fenced code block and one with an image link to
      `images/diagram.svg`;
    - `guides/nested/deep.md`;
    - one Working with LLMs page;
    - a drafted Reference page;
    - `_notes.md` and `_private/secret.md`, each carrying a distinctive
      sentinel word;
    - one dotfile whose name git does not ignore, for example
      `.editor-state`. Never `.DS_Store`, which `.gitignore` drops so it
      would never be committed;
    - `images/diagram.svg`.

    Pages use relative `.md` links only. No athlete data appears anywhere.
  - **Fixture self-test** (`tests/sitebuild/test_fixture_site.py`) asserts
    each species above is present:
    - the annotation sentinel appears only inside annotation blocks;
    - no fixture file contains the package's version literal;
    - every fixture file is UTF-8 and a regular file;
    - `git check-ignore` ignores no fixture file, so every species is
      actually committed.
  - **Done when** the self-test is green and each of its assertions has a
    named mutation. Here the "production" under test is the fixture tree
    itself, so the mutation is to the fixture: deleting the drafted page reds
    the draft-species assertion, and so on.
  - _Requirements: 9.1_

- [x] 2. Core: the planning modules, the gate and the hero chart

- [x] 2.1 Resolve, discover and strip the content directory without ever writing to it
  - In `scripts/sitebuild/content.py`, implement:
    - `resolve_content_dir`: explicit option, then `FITDOCS_SITE_CONTENT`,
      then `<repo>/website/content`. `ContentDirMissing` names the path and
      its `ContentSource`;
    - the discovery walk: `os.scandir`, no symlink following;
      `_`-prefixed and `.`-prefixed components excluded with their subtrees;
      a symlink reported as a `Problem`; `.md` as page candidates; everything
      else as `Asset`; root `llms.txt` / `llms-full.txt` reported as reserved;
    - `strip_annotation`: `rfind(ANNOTATION_MARKER)`, keep `text[: i + 1]`.
  - **Tests** (`tests/sitebuild/test_content.py`, part 1):
    - each resolution source, and precedence when all three are set;
    - the missing-dir message naming both the dir and the source;
    - exclusion of a `_` file, a `_` directory's nested files and a dotfile;
    - a symlink (created in `tmp_path`) reported;
    - a reserved name reported;
    - an asset carried with its relative path;
    - strip cases: marker at the end, no marker, a plain `---` rule kept,
      two markers (the last wins), and remainder byte-equality;
    - a content-dir byte hash unchanged after discovery.
  - **Done when** these tests are green with each assertion's mutation
    recorded. The fixture tree's discovery yields exactly its expected page
    and asset sets.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.11_

- [x] 2.2 Validate frontmatter and the site-level rules, reporting every violation in one run
  - In `scripts/sitebuild/content.py`:
    - **Frontmatter splitting.** Leading `---` line, closing `---` line,
      UTF-8. A `SafeLoader` subclass that rejects duplicate keys. The result
      must be a mapping.
    - **Per-page validation.** Required keys and types:
      - `order` is `int` and never `bool`;
      - `draft` and `primary` are `bool`;
      - text fields are non-empty after strip;
      - `hero_actions` is a non-empty list of mappings with keys within
        `HERO_ACTION_KEYS`.

      Also: unknown keys (including `template`), hero keys off the home page,
      and a section outside `SECTIONS`.
    - **Draft omission**, and **site-level checks**: a duplicate
      `(section, order)` naming both files, no home page (including a drafted
      `index.md`), and no included page.
    - **`load_content`** returns `(SiteContent, ())` or
      `(None, sorted problems)`.
    - **`count_included_pages`**: an unreadable page counts as included.
  - **Tests** (`tests/sitebuild/test_content.py`, part 2):
    - one test per violation class, each asserting the exact file and key in
      the rendered line;
    - `True` as `order` refused;
    - duplicate YAML keys refused;
    - five simultaneous violations all reported in one call;
    - the fixture site loads with no problems into the expected page set,
      with the draft and `_` pages absent;
    - an all-`_` tree reported as holding no included page (2.8);
    - `count_included_pages` for an empty tree, a drafts-only tree and the
      fixture.
  - **Done when** every 2.x criterion has a green test with its mutation
    recorded, and `load_content(fixture)` returns six pages sorted by path.
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

- [x] 2.3 (P) Order pages, map URLs, build the nav and render both llms indexes
  - In `scripts/sitebuild/outline.py`, implement:
    - `ordered_pages`: canonical section order, empty sections omitted,
      ascending `order`;
    - `page_path`: `index.md` → `""`, `a/index.md` → `a/`, `a/b.md` → `a/b/`;
    - `nav_structure`: every page exactly once;
    - `render_llms`: `# site_name`, `> summary`, then per section an `## ` list
      of `- [title](absolute url): description`, with no `Optional` section;
    - `render_llms_full`: per page, `# title`, `Source: url`, a blank line,
      then the body.

    Output is LF-only with exactly one trailing newline.
  - Tests build `SiteContent` values directly from the model types. This task
    does not depend on `content.py`.
  - **Tests** (`tests/sitebuild/test_outline.py`):
    - section order with an empty section omitted;
    - `order` beating alphabetical order;
    - URL mapping for index, nested index and leaf pages;
    - an exact expected `llms.txt` and `llms-full.txt` for a small hand-built
      site;
    - two renders byte-identical.

    Draft and `_` absence from the indexes (5.3) follows from their absence
    in `SiteContent` (2.2). It is pinned end to end over the real fixture in
    4.1.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 3.1, 3.2, 4.6, 5.1, 5.2, 5.3, 5.4_
  - _Boundary: Outline_

- [x] 2.4 (P) Render the generator config and enforce the allowlist
  - In `scripts/sitebuild/config.py`:
    - `TEMPLATE_PATH`, and the allowlist constants exactly as design.md §
      SiteConfig lists them. The theme features are the 29 names from
      research.md; `search.suggest` and `markdown_extensions` are excluded;
    - `load_template`, `render_config` and `check_config`:
      - `check_config` refuses build-owned keys in the template;
      - it names every unknown top-level key, theme key, palette key,
        feature and plugin by dotted path;
      - it allows only `enabled` / `separator` as search plugin options;
    - `referenced_assets` and a deterministic `dump_config`.
  - Tests use in-memory templates. The real template arrives in 3.1.
  - **Tests** (`tests/sitebuild/test_config.py`, part 1):
    - each refusal class singly, naming the key;
    - several at once, all reported;
    - the rendered config sets `docs_dir: staged`, `site_dir: html`,
      `theme.custom_dir: overrides` and the nav;
    - `referenced_assets` returns `extra_css`, `logo` and `favicon`;
    - the dump is byte-identical across runs.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 6.4_
  - _Boundary: SiteConfig_

- [x] 2.5 (P) Wrap the generator: locate it, run it, and translate its output into problem lines
  - In `scripts/sitebuild/generator.py`, implement:
    - `generator_executable`: next to `sys.executable`, else
      `GeneratorMissing`, whose message names `uv sync --group docs`;
    - `run_build`: `zensical build -f mkdocs.yml --clean` with the root as
      cwd, both streams captured;
    - `translate`:
      - strip ANSI;
      - `Warning:` plus `╭─[ path:line:col ]` frame pairs become
        `Problem(path, "line:col", msg)`;
      - `Error:` and non-abort `RuntimeError:` lines become
        `site generator` problems;
      - an unparsed non-zero exit falls back to the last non-empty line;
      - the traceback is never included;
    - `start_serve`: `-a <addr>`, returns the process.
  - **Capturing the canned outputs** (the pipeline does not exist yet):
    - Hand-write a throwaway Zensical project in a scratch directory
      **outside** the repository. The config file sits beside `staged/` and
      `html/`, as design.md § Build root layout shows.
    - Give it a page with a broken `.md` link and one with a broken anchor.
      Then make a second copy with invalid config YAML, and a third that
      names a missing `template:`.
    - Run `uv run --group docs zensical build -f <dir>/mkdocs.yml` from the
      worktree for each copy, once plain and once under
      `TERM=dumb NO_COLOR=1`, which is docs.yml's environment. Record the
      exact commands and whether the two outputs differ in Implementation
      Notes.
  - **Tests** (`tests/sitebuild/test_generator.py`) run over those captures,
    held as string constants in the test module with the ANSI codes intact.
    If the `TERM=dumb` capture differs, it is a separate constant:
    - two strict warnings across two files;
    - a config `Error:`;
    - a template `RuntimeError:`;
    - an unparseable tail.

    Each maps to the exact expected problem list, with no traceback text.
    Also: the executable is resolved next to `sys.executable`, and a missing
    one raises with the fix command.
  - **Done when** the tests are green with mutations recorded. This needs no
    generator installed.
  - _Requirements: 6.1, 6.2, 6.5_
  - _Boundary: GeneratorAdapter_

- [x] 2.6 (P) Build the site gate over directory trees, failing closed
  - Create `scripts/check_site.py` in the `scripts/` entry-point shape:
    - `python -m scripts.check_site ROOT [ROOT ...]`;
    - it imports `load`, `matches` and `ForbiddenStringsSourceError` from
      `tests._forbidden_strings`, `scan` from `tests._content_oracle`, and
      the constants from `tests._content_fingerprints`, as
      `scripts/check_artifacts.py` does;
    - it walks each root: a symlink is a `LINK` finding; each file's content
      is decoded with `errors="replace"` and checked by token and by oracle;
      each root-relative path is checked by token; an unreadable file is a
      finding;
    - `load() is None` gives one `GATE_NOT_RUN` finding (exit 1, output
      contains `gate_not_run` and names `FITDOCS_FORBIDDEN_STRINGS`);
    - a set-but-unusable source, or a missing root, exits 2;
    - findings never contain matched text.
  - **Tests** (`tests/sitebuild/test_check_site.py`):
    - a synthetic needle, via a test-written match file outside the repo
      (the `tests/test_forbidden_strings.py` technique), found in content and
      in a path;
    - a fingerprinted control value found, using the technique of
      `tests/test_release_artifacts.py:2279-2302`: monkeypatch
      `scripts.check_site.FINGERPRINTS` / `scripts.check_site.WINDOW_LENGTHS`,
      the importing module's names. Patching `tests._content_fingerprints`
      would do nothing. So `check_site` binds them with
      `from tests._content_fingerprints import …` and reads its own module
      globals at call time;
    - a symlink finding;
    - an unreadable file (mode `000` in `tmp_path`, skipped with a reason
      when running as root) reported as a finding, never skipped;
    - a missing root gives exit 2;
    - unset variable gives exit 1 with `gate_not_run`;
    - an unusable source gives exit 2;
    - a clean tree gives exit 0;
    - the needle text absent from all output.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 10.3, 10.4, 10.5_
  - _Boundary: SiteGate_

- [x] 2.7 (P) Generate the demo-data hero chart and pin its reproducibility
  - Create `scripts/make_hero_chart.py`:
    - `demo_spec()` builds a `HeroChartSpec` from closed-form series only:
      0–60 min in 0.5 min steps, power as warm-up, three intervals and
      cool-down, HR as a first-order lag of power, and a smooth synthetic
      elevation backdrop. It uses `HR_COLOR` and `POWER_COLOR` from
      `fitdocs.render.charts.palette`;
    - its docstring states the data are demo data, never an athlete's;
    - every series value is rounded to fixed decimals inside `demo_spec`, so
      the SVG is byte-identical on macOS and on the ubuntu runner.
      Transcendental functions such as `exp` and `sin` may differ in the
      last bit across libm builds;
    - `render()` returns the SVG, and `main` writes to `--output PATH`,
      default `website/assets/hero-chart.svg`. With `--check` it compares
      against that path instead, and exits 1 on drift.
  - Generate and commit `website/assets/hero-chart.svg`.
  - **Tests** (`tests/sitebuild/test_hero_chart.py`):
    - `render()` equals the checked-in file byte-for-byte;
    - `--check` exits 0 now, and 1 against a tampered copy in `tmp_path`
      passed through `--output`;
    - every numeric value in the spec has at most the fixed number of
      decimals;
    - the module performs no file reads for its data: an AST check for
      `open`, `read_text`, `read_bytes` and `csv` inside `demo_spec`.
  - **Done when** the committed SVG exists, `--check` is green, and the
    tests are green with mutations recorded.
  - _Requirements: 3.5, 3.6_
  - _Boundary: HeroGenerator_

- [x] 2.8 Check the links the generator does not: assets, hero targets and `docs/` URLs
  - In `scripts/sitebuild/links.py`, implement:
    - `extract_links`: fence- and code-span-aware. It covers inline links and
      images, reference definitions, and HTML `href` / `src`, with source
      line numbers;
    - `github_slugs`: github-slugger v2 semantics, ATX headings outside
      fences, `-N` duplicate suffixes;
    - `check_links`:
      - relative non-`.md` targets must resolve to an included asset or a
        page's directory URL;
      - relative `.md` targets in markdown link syntax are left to the
        generator (2.10). In raw HTML they are a `Problem` naming the file
        and line (2.12);
      - a relative hero href must equal an included page's `page_path`, and
        an absolute one must be `https://`;
      - a `docs/` GitHub URL's file must exist under `<repo>/docs/`, and its
        anchor must be in `github_slugs` of that file.
  - **Tests** (`tests/sitebuild/test_links.py`):
    - a missing asset, a present asset, and `..` resolution;
    - targets inside fences and code spans ignored;
    - a bad hero href, and a good one;
    - a `docs/` URL with a missing file, a missing anchor, and valid;
    - markdown-syntax `.md` links not reported;
    - a raw-HTML `<a href="other.md">` reported with its file and line
      (2.12);
    - a slugger conformance table: `[load]`, a repeated heading gives `-1`,
      `C++ & Python` gives `c--python`, `snake_case name` gives
      `snake_case-name` (the underscore kept), `TSS / hrTSS — load`, an emoji
      heading, `Café résumé`, a code-span heading, and a heading inside a
      fence is ignored.
  - **Done when** the tests are green with mutations recorded, and the
    fixture's `docs/` link passes against the real `docs/` tree.
  - _Requirements: 2.10, 2.12, 6.1, 6.3_
  - Not parallel: it needs `outline.page_path` (2.3) for hero hrefs and
    `load_content` (2.2) for its fixture check, so it runs after the (P)
    group.

- [x] 3. Integration: theme, staging, pipeline, preview, CLI

- [x] 3.1 Create the theme: config template, home override and the brand in one place
  - **`website/mkdocs.template.yml`** carries:
    - `site_name`, `site_url: https://fitdocs.ai/` and `site_description`;
    - `repo_url`, `repo_name` and `edit_uri: edit/main/website/content/`;
    - `use_directory_urls: true` and `strict: true`;
    - `theme`: `name: material`, `variant: classic`, `font: false`,
      `logo: _brand/logo.svg`, `favicon: _brand/logo.svg`;
    - the features: `navigation.instant`, `navigation.tracking`,
      `navigation.sections`, `navigation.path`, `navigation.top`,
      `navigation.footer`, `toc.follow`, `search.highlight`,
      `content.code.copy` and `content.action.edit`;
    - three palette entries: automatic via `(prefers-color-scheme)`, then
      light `default`, then dark `slate`, each with a toggle and `custom`
      colors;
    - `extra_css: [_brand/brand.css]` and `plugins: [search]`.

    It has no build-owned key.
  - **`website/overrides/home.html`** extends `main.html` and:
    - renders `hero_title`, `hero_tagline` and each `hero_actions` entry only
      inside a conditional;
    - gives a `primary` action the primary-button class;
    - emits links through the `url` filter;
    - shows `_brand/hero-chart.svg` with demo-chart alt text;
    - keeps the page's edit action.
  - **`website/assets/brand.css`**:
    - the design's palette custom properties for the `default` and `slate`
      schemes (header `#1f2933`, accent `#b8324b` / `#f07d8e`);
    - the system text and monospace font stacks;
    - the hero layout;
    - a light card behind the chart in both schemes.
  - **`website/assets/logo.svg`**: the placeholder mark.
  - **Tests** (`tests/sitebuild/test_theme.py`, plus part 2 of
    `test_config.py`):
    - the real template passes `check_config` after `render_config`;
    - it pins the required values for 4.1, 4.2, 4.3, 4.4 and 4.6;
    - each hero key in `home.html` sits inside an `if` block;
    - `home.html` includes the edit action;
    - `brand.css` defines the palette and font custom properties for both
      schemes;
    - no other file under `website/` defines them.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Depends: 2.4, 2.7_

- [x] 3.2 Stage a build root as bytes, write it fresh, or sync it in place
  - In `scripts/sitebuild/stage.py`, implement:
    - `plan_tree`, producing:
      - `mkdocs.yml`;
      - `staged/<page>` as the stripped text. For `index.md` only, the line
        `template: home.html` is inserted after the opening `---`;
      - `staged/<asset>` byte-identical;
      - `staged/_brand/*` from `website/assets/`;
      - `staged/llms.txt` and `staged/llms-full.txt`;
      - `overrides/*` from `website/overrides/`;
    - `write_tree`: remove the managed paths, then write;
    - `sync_tree`: write only differing files, delete managed files absent
      from the map, prune emptied directories, never rename or replace a
      directory, and leave `html/` and `.cache/` alone.
  - **Tests** (`tests/sitebuild/test_stage.py`, over the fixture):
    - every non-home staged page equals `strip_annotation(source)` exactly;
    - the home page differs by exactly the one injected line;
    - assets are byte-identical at the same path;
    - `_brand/` and both llms files are present;
    - no path under `staged/` begins with a content `_` name other than
      `_brand`;
    - `sync_tree` modify, add and delete happen in place, with the `staged/`
      directory inode unchanged and `html/` untouched;
    - `write_tree` writes nothing outside the root.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 1.3, 1.5, 1.6, 1.8, 3.3, 7.2_

- [x] 3.3 Orchestrate one build into one root, with the location and failure guarantees
  - In `scripts/sitebuild/pipeline.py`, implement:
    - `guard_root`: a root inside the repo must be under `website/build/`,
      else `BuildRootRefused`; a root outside the repo is allowed;
    - `build`:
      1. clear the managed paths;
      2. load the content and template;
      3. if the content loaded, run the link checks, render and check the
         config, render the llms texts, and build the tree with `plan_tree`
         (pure, in memory);
      4. check the config's referenced assets against that planned tree;
      5. collect every script-level problem;
      6. on any problem, stop without writing or running the generator;
      7. otherwise `write_tree` and `run_build`, deleting `html/` on
         generator failure;
    - `render_llms` takes `site_name` from the template's `site_name`, its
      summary from `site_description`, and `site_url` from `site_url`;
    - `BuildOutcome` carries the tree and the page count.
    - Defaults are `website/build/site` and `website/build/preview`.
  - **Tests** (`tests/sitebuild/test_pipeline.py`, with `run_build`
    monkeypatched to a recording stub):
    - content, link and config problems together all reported in one outcome
      (2.9);
    - a script-level failure never calls the stub and leaves no `html/`;
    - a template whose `extra_css` names a file absent from the planned tree
      is reported, with the stub not called;
    - a stub generator failure leaves no `html/` even when the stub created
      one;
    - a success keeps `html/`;
    - a repo-internal root outside `website/build/` refused, and a `tmp_path`
      root allowed;
    - the fixture plans its expected tree.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 2.9, 6.6, 6.7_

- [x] 3.4 Keep a preview serving the last content that built cleanly
  - In `scripts/sitebuild/preview.py`, implement:
    - `snapshot`: `(mtime_ns, size)` per file over the content dir,
      `website/overrides/`, `website/assets/` and the template;
    - the `serve` loop with an injectable stop event:
      - the first build goes into `check/`;
      - on success, `sync_tree` into `live/`, then start the serve process
        once;
      - on each snapshot change, rebuild into `check/`;
      - on failure, print the rendered problem lines to `out` and leave
        `live/` untouched;
      - terminate the serve process on exit.
  - **Tests** (`tests/sitebuild/test_preview.py`, unit part: the build and
    serve launcher are stubbed, so no generator is needed):
    - create, change and delete are each detected;
    - a failing rebuild prints the same lines as `build` and leaves `live/`
      byte-unchanged;
    - a later success syncs;
    - an initial failure starts no server until a success;
    - the serve process is terminated on stop;
    - nothing is written outside the preview root;
    - the content dir is unchanged.
  - **Done when** the tests are green with mutations recorded.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 3.5 Expose build, serve and status as the one command, and guard the build logic's imports
  - Create `scripts/build_site.py` in the `scripts/` entry-point shape, with
    subcommands:
    - `build [--content] [--build-dir] [--verbose]`;
    - `serve [--content] [--build-dir] [--addr]`, default
      `127.0.0.1:8000`;
    - `status [--content]`, which prints exactly `has_content=true` or
      `has_content=false`.

    Relative paths resolve against the repo root. Exit codes are:
    - 0 on success;
    - 1 on problems, one rendered line each on stderr, with `--verbose`
      appending the generator output;
    - 2 on `ContentDirMissing`, `GeneratorMissing` or `BuildRootRefused`,
      with the message naming the dir and source (1.2).
  - **Tests** (`tests/sitebuild/test_cli.py`, via `main(argv)` with capsys and
    `run_build` stubbed where a generator is not the subject):
    - each exit code;
    - the 1.2 message;
    - `status` lines for the default content dir, a drafts-only dir and the
      fixture. The default-dir case monkeypatches the module's `REPO_ROOT`
      to a `tmp_path` root holding only `website/content/.gitkeep`. The test
      never reads the real `website/content/`, so it stays green when the
      maintainer's copy lands;
    - `--verbose` appends the generator output;
    - the parser accepts exactly the documented flags.
  - **Import guard** (`tests/sitebuild/test_repo_wiring.py`): every module in
    `scripts/sitebuild/` plus `scripts/build_site.py` imports only standard
    library modules (`sys.stdlib_module_names`), `yaml`, `__future__` and
    `scripts.sitebuild`. It is non-vacuous: it asserts the scanned set is
    exactly the ten files of `scripts/sitebuild/` (with `__init__.py`)
    named in design.md, plus `scripts/build_site.py`.
  - **Done when** the tests are green with mutations recorded. As a one-time
    manual check, recorded in Implementation Notes and not as a test, a real
    run of `python -m scripts.build_site status` in the repo prints
    `has_content=false`.
  - _Requirements: 1.1, 1.2, 6.5, 7.1, 8.4, 10.6_

- [x] 4. Validation against the real generator

- [x] 4.1 Smoke-test a real build of the fixture site, and each failure class
  - Create `tests/sitebuild/test_build_smoke.py`, entirely behind
    `requires_zensical`. It builds the fixture into `tmp_path` through
    `pipeline.build` and asserts:
    - the nav order in rendered HTML;
    - every included page written as `<path>/index.html` and listed in
      `search.json`;
    - `llms.txt` and `llms-full.txt` at the root, equal to the Outline
      renders for the loaded fixture;
    - `content.code.copy` and `content.action.edit` in the `__config`
      script;
    - an edit href `…/edit/main/website/content/<page path>` on every page,
      the home page included;
    - the annotation sentinel absent from every HTML file and from
      `search.json`;
    - the draft and `_` pages absent from the output and from `search.json`;
    - the drafted page's title, and the sentinels of `_notes.md` and
      `_private/secret.md`, absent from both `llms.txt` and `llms-full.txt`;
    - the home page shows the hero title, both actions (one primary) and the
      chart, and no tagline element;
    - `_brand/brand.css` linked.
  - Separate builds from one-edit copies each fail with the file named and
    no `html/` left:
    - a broken `.md` link (the problem names file and line);
    - a broken cross-page anchor;
    - a broken same-page anchor;
    - a link to the drafted page.
  - If the real output shows the translator or the template wrong, fix them
    in their own modules here, and record it in Implementation Notes.
  - **Done when**
    `FITDOCS_REQUIRE_SITE_TOOLING=1 uv run --group docs pytest tests/sitebuild/test_build_smoke.py`
    is green with mutations recorded, and a manual
    `uv run --group docs python -m scripts.build_site build --content tests/sitebuild/fixtures/site`
    exits 0.
  - _Requirements: 1.8, 2.4, 3.3, 3.4, 4.1, 4.3, 4.4, 4.6, 5.1, 5.2, 5.3, 6.1, 6.2, 6.6, 9.1, 9.2_

- [x] 4.2 Prove the live preview end to end against the real generator
  - Add the integration part of `tests/sitebuild/test_preview.py`, behind
    `requires_zensical`:
    - run `serve` on a free port, in a thread with a stop event, over a
      `tmp_path` copy of the fixture (a directory outside the repository);
    - poll HTTP until the home page is served;
    - edit a page, and see the new text served within a bounded timeout;
    - add a page, and see it served; delete it, and see a 404;
    - break a page's frontmatter: the problem line is printed and the old
      text is still served; fix it, and the fix is served;
    - the content copy's byte hash is unchanged throughout;
    - the server process is gone after stop.
  - **Done when** it is green under `FITDOCS_REQUIRE_SITE_TOOLING=1` locally,
    with mutations recorded. It must use in-place sync only, because a
    rename-swap is invisible to `serve`.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 5. Automation: the docs workflow and its test

- [x] 5.1 Build, gate and deploy the site from `.github/workflows/docs.yml`, with its workflow test
  - Write `docs.yml` exactly per design.md § DocsWorkflow:
    - the `push` and `pull_request` `paths` lists;
    - workflow `permissions: {contents: read}`, and env `TERM: dumb`,
      `NO_COLOR: "1"`;
    - job `build`:
      1. checkout `@v7.0.1`;
      2. setup-uv `@v10.2.0`;
      3. `uv python install 3.11`;
      4. `uv sync --group docs`;
      5. the site tests via `uv run --group docs pytest …`, with
         `FITDOCS_REQUIRE_SITE_TOOLING: "1"`;
      6. `status >> "$GITHUB_OUTPUT"`;
      7. the real build, or the fixture build with its `::notice::`;
      8. the ci.yml fail-closed secret step, verbatim;
      9. the `check_site` gate over `website/build/site/staged` and
         `website/build/site/html`;
      10. `upload-pages-artifact@v5.0.0`, only on a push to main with
          content.
    - job `deploy`: the same condition, `needs: build`,
      `permissions: {pages: write, id-token: write}`, the `github-pages`
      environment, `concurrency: {group: pages, cancel-in-progress: false}`,
      and `deploy-pages@v5.0.1`.
  - Write `tests/test_docs_workflow.py` in the style of
    `tests/test_ci_workflow.py`, with each test carrying its `Dies on:` line.
    Add it to `[tool.mypy].files` in the same change.
    It asserts:
    - both path lists (10.1);
    - the deploy and upload conditions (10.2);
    - the gate precedes the upload and names both directories (10.3);
    - the secret step's body, run through `bash -eo pipefail`, exits 1 with
      `gate_not_run` when the secret is empty, and writes the file when it is
      set (10.4);
    - no `continue-on-error` on the gate (10.5);
    - the fixture step's `if` negates the real build's, and it emits the
      notice (10.6);
    - the exact permissions, with only `deploy` elevated (10.7);
    - every `uses:` matches `@(v\d+\.\d+\.\d+|[0-9a-f]{40})$`, with a
      negative control on `@main` and a bare major (10.8);
    - the site-test step sets the tooling variable (9.5);
    - every `scripts.<name>` command's flags parse with that module's
      `_build_parser()`.
  - Run `actionlint` if it is installed, skipping with a reason otherwise,
    as `test_ci_workflow.py` does.
  - **Done when** `tests/test_docs_workflow.py` is green with mutations
    recorded, the Dies-on meta-test covers it, and mypy is green on it.
  - _Requirements: 9.5, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_
  - _Depends: 2.6, 3.5_

- [ ] 6. Documentation and project metadata

- [ ] 6.1 Document the site in `docs/website.md` and link it from the entry point
  - Write `docs/website.md` with these sections:
    - an intro stating that it documents the repository's website and is
      not one of the contracts governed by the compatibility policy, linking
      `compatibility.md` (11.6);
    - the content contract in full, derived from the model constants (11.3);
    - building and previewing, including `--content` / `FITDOCS_SITE_CONTENT`
      for an out-of-repo directory, `--verbose`, and the failure line format
      (11.4);
    - the statement that rebuild-on-save belongs to the repository's site
      tooling. fitdocs itself performs no watching and no scheduling (11.7);
    - the maintainer runbook: DNS records, domain verification TXT, Pages
      settings (Source "GitHub Actions", custom domain, Enforce HTTPS, and
      the `github-pages` environment limited to `main`), the content import
      step, and the Zensical pin-bump procedure, which includes re-deriving
      the feature allowlist (11.5).
  - Add one row to `docs/index.md`'s table, before the Contributing row.
    This is append-only against `impl-connectors`' row: write `TOUCHING`
    first.
  - **Tests** (`tests/sitebuild/test_website_doc.py`):
    - every value of `SECTIONS`, `REQUIRED_KEYS`, `OPTIONAL_KEYS`,
      `HERO_KEYS` and `HERO_ACTION_KEYS`, plus `CONTENT_ENV_VAR` and the
      default content dir, appears in the page;
    - the build, serve and `--content` commands appear;
    - the runbook subsections, the four A and four AAAA values, and the TXT
      name appear;
    - the stated Zensical pin equals `pyproject.toml`'s `docs` pin;
    - the 11.6 and 11.7 sentences appear;
    - the page states the symlink refusal, the reserved root names
      `llms.txt` / `llms-full.txt`, and that page links use markdown link
      syntax (raw-HTML page links refused), so the 2.11 and 2.12 rules are
      part of the stated contract (11.3);
    - `docs/index.md` links `website.md`.
  - Run the existing docs guard suite unchanged (11.9):
    `tests/test_docs_guarantees.py`, `tests/test_install_docs.py`,
    `tests/test_compatibility_policy.py` and `tests/test_version_identity.py`.
  - **Done when** the new tests are green with mutations recorded, and every
    existing docs guard is green without edits.
  - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.9_
  - _Depends: 1.2, 3.5_

- [ ] 6.2 Declare the homepage, add the CONTRIBUTING section and owe the changelog entry
  - Insert `Homepage = "https://fitdocs.ai"` as the **first**
    `[project.urls]` key. The other ten keys and values stay byte-identical.
    Write `TOUCHING` first: `impl-connectors` appends `Connectors`.
  - Add a final `## Building the website` H2 to `CONTRIBUTING.md`: one
    paragraph, no fenced blocks, inline `uv sync --group docs` / `build` /
    `serve`, and a relative link to `docs/website.md`.
  - Add one `### Added` bullet under `CHANGELOG.md` `## [Unreleased]`
    declaring the Homepage project URL. It must satisfy
    `tests/test_changelog.py`'s format rules.
  - **Tests** (`tests/sitebuild/test_repo_wiring.py`):
    - `Homepage` is present and first;
    - each of the ten pre-spec keys is present with its literal pre-spec
      value. This is a subset check, and later keys are allowed:
      `impl-connectors` appends `Connectors`, so an exact key-set equality
      would red on rebase;
    - the CONTRIBUTING section exists and links `docs/website.md`.

    Then run `tests/test_packaging.py`, `tests/test_contributing_doc.py`,
    `tests/test_changelog.py` and `tests/test_ci_workflow.py` unchanged.
  - **Done when** these are green, with mutations recorded for the new
    assertions.
  - _Requirements: 11.1, 11.8_

- [ ] 7. Feature validation

- [ ] 7.1 Validate the whole feature after rebasing onto `main`
  - Rebase onto current `main` and resolve the shared files by keeping both
    sides.
  - **Full gates.** Run the complete class-validation row:
    `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`.
    Then run
    `FITDOCS_REQUIRE_SITE_TOOLING=1 uv run --group docs pytest tests/sitebuild tests/test_docs_workflow.py`.
  - **Preserved guarantees** (8.1, 8.3, 11.9). Confirm by the existing suite
    alone:
    - `tests/test_release_artifacts.py` (sdist and wheel member sets
      unchanged);
    - `tests/test_determinism.py` and `tests/test_packaging.py`;
    - the docs guards and `tests/test_forbidden_strings.py`.
  - **End-to-end checks by hand.**
    - `python -m scripts.make_hero_chart --check` exits 0.
    - `uv run --group docs python -m scripts.build_site build --content tests/sitebuild/fixtures/site`
      exits 0.
    - `python -m scripts.check_site website/build/site/staged website/build/site/html`
      exits 1 with `gate_not_run` when the variable is unset, and exits 0 with
      a synthetic match file outside the repo.
  - **Done when** every gate is green after the rebase, and the report lists
    each requirement ID with its covering test. A partial or unpinned clause
    is stated as such.
  - _Requirements: 8.1, 8.3, 9.1, 11.9_

## Implementation Notes

- 1.1 (4 review rounds): a test that guards "plain `uv sync` installs no Zensical" must cover every manifest route to a default install: direct entries in any non-`docs` group, PEP 735 `{include-group = ...}` chains, `[tool.uv] default-groups` (list or `"all"`), and the deprecated `[tool.uv] dev-dependencies`, which uv 0.11 still merges into `dev`. `uv export --no-hashes --format requirements.txt` shows what a default sync installs. A cyclic group manifest cannot reach pytest, because uv fails first. The `git ls-files website/build` half of the 6.7 test is pinned: it was checked by force-adding a file in a disposable index. The `requires_zensical` tests spawn an inner pytest through a symlinked interpreter in a fake `bin/`, and that passed in a Linux container (uv-managed 3.11, non-root, `GITHUB_ACTIONS=true TERM=dumb`). The general `build/` ignore rule also covers `website/build/`, so the explicit line is pinned only by `git check-ignore -v`. Restore `uv.lock` after a mutation with `cp` from a snapshot, not `git show HEAD:uv.lock`, while the task's own lock additions are uncommitted.
- 1.2 (2 rounds): `Problem.render()` builds each field with `" ".join(field.splitlines())`, drops a field that is empty after that, and joins the rest with `": "`. All other whitespace is kept exactly (a whitespace-only field is not empty and stays). Later tasks inherit this line format. **For 2.2:** PyYAML's `str(e)` spans several lines (context, the snippet line, a caret line); it never *ends* in a newline. `render()` flattens it into one long line with the snippet's indentation kept, so ContentLoader should choose what YAML error text goes into `Problem.message` (e.g. `problem_mark` line and column plus `problem`) instead of the raw multi-line `str(e)`.
- 1.3 (3 rounds): `tests/sitebuild/fixtures/site/` has 6 included pages (index, why, get-started/{install,first-run}, guides/nested/deep, llms/prompts), a drafted `reference/cli.md` titled "Command reference" (sentinel DRAFTSENTINELCOBALT), `_notes.md`, `_private/secret.md` (PRIVATESENTINELONYX), `.editor-state` (DOTFILESENTINELWILLOW) and `images/diagram.svg`. The Why link anchor is `#load-calculator-selection-and-training-load-computation`. The self-test reads bytes (no universal newlines), refuses CR and BOM, validates frontmatter against the model constants with a duplicate-refusing SafeLoader, and is fence-aware (column-0 fences only). Derived fixtures must not be named `build/` or `data/` (gitignored). A test that checks a string is absent must search the whole file, not compare whole frontmatter values. Known non-blocking survivor: a home link written in a code span.
- 2.1 (5 rounds; round 5 was a docstring sentence fixed by the controller, not an implementer, and verified by the reviewer): `content.discover(content_dir) -> Discovery(pages, assets, problems)`, all sorted (problems by `(path, where, message)`). 2.2 builds `load_content`/`count_included_pages` on it. **Controller rulings:**
  - A symlink anywhere is a Problem. `is_symlink()` is checked before the `_`/`.` exclusion. Excluded directories, and a reserved root `llms.txt/` / `llms-full.txt/` directory, are walked for symlinks only; nothing under them becomes a page or asset.
  - An unlistable excluded directory is skipped (`OSError`, the walk continues). An unlistable **included** directory raises, so pages never vanish silently (exact handling queued: `2026-09-30-docs-site-unreadable-dirs-and-special-files-in-content`).
  - Empty `FITDOCS_SITE_CONTENT` is treated as unset (precedent: `src/fitdocs/config.py:55-61`). Whitespace-only is not, and fails as `ContentDirMissing`.
  - Reserved names are matched case-sensitively.

  Other notes:
  - `_tree_hash` in `test_content.py` records the root itself (mode and mtime), so a create-then-unlink or a chmod of the content dir is caught.
  - Mutations that make production write must run with `-k 'not test_fixture_discovery_yields'`. 2.1 once stripped the real fixture's directory modes.
  - Queued: `2026-09-30-docs-site-annotation-marker-misses-crlf-and-space-blank-lines` (medium).
- 2.2 (3 rounds): `load_content(content_dir) -> (SiteContent, ())` or `(None, sorted problems)`; `count_included_pages` counts any unreadable page as included.
  - **Controller rulings.** `_StrictLoader.construct_object` wraps ANY non-YAMLError exception from a PyYAML constructor into a positioned ConstructorError. SafeConstructor raises IndexError, KeyError and AttributeError, not just ValueError, so the exception list is not enumerated. A reader error maps its character offset to file L:C. An unknown key is named with `str(key)`, but with `repr` for an empty or whitespace-only text key.
  - **Duplicate slots.** A `(section, order)` slot is recorded for every non-drafted page whose own section and order are valid, whatever its other violations (2.9).
  - **Reviewer-confirmed readings.** A draft's other violations still fail the load. Drafts are outside the duplicate check. A BOM before `---` is refused as "no frontmatter". Hero `href` shape is 2.8's job.
  - **Message shapes.** `path: L:C: invalid frontmatter YAML: <problem>` in file coordinates. A duplicate is one Problem per slot, on the first path, naming the others. The empty-tree problem has an empty path.
  - **Open.** A CRLF body with a CRLF annotation block still leaks; see queue `2026-09-30-docs-site-annotation-marker-misses-crlf-and-space-blank-lines`. A CRLF frontmatter fence is refused as "no frontmatter".
- 2.5 capture record: the throwaway project is `mkdocs.yml` beside `staged/` and `overrides/`, with config `site_name`, `docs_dir: staged`, `site_dir: html`, `strict: true`, `theme: {variant: classic, custom_dir: overrides}` (no `theme.name`: `theme.name: modern` gives "Theme 'modern' is not installed"). Each copy was run as `uv run --group docs zensical build -f <dir>/mkdocs.yml`, once plain and once with `TERM=dumb NO_COLOR=1`; stdout and stderr were byte-identical, so there is one constant per case, and every case exits 1.
  - Strict: two ANSI `Warning:` blocks with `╭─[ path:line:col ]` frames, then `2 issues found`, then a traceback ending `RuntimeError: Aborted because --strict flag is set`.
  - Bad YAML: `Error: Encountered an error parsing the configuration file: ...` plus detail lines, with no ANSI and no traceback.
  - Missing template: `No issues found`, then a traceback ending `RuntimeError: template not found: ...`.
  - Traceback paths are normalised to `/path/to/repo`.
  - 2.5 (2 rounds, parallel stream impl/ds-2-5). `run_build(root) -> GeneratorResult(ok, problems, output)`; `translate` runs inside it and `ok = returncode == 0`. Reviewer-accepted choices:
    - An `Error:` problem keeps only its first line. The generated mkdocs.yml was already parsed by the script, and the full text is in `output` for `--verbose`.
    - A frameless warning becomes a path-less problem, and a warning pairs with the first frame before the next report line, even across a blank line.
    - Fallback candidates exclude traceback frames, and an empty non-zero exit reads "exited with status N".
    - Output is stdout then stderr; the report is on stderr.
    - A broken Jinja template reports as `site generator: syntax error: ... (in bad.html:2)`.

    Test stubs are `#!/bin/sh`, which works because CI is ubuntu-only.
- 2.4 (3 rounds, parallel stream `impl/ds-2-4`; round 3 was a one-sentence docstring fix applied by the controller and verified by the reviewer).
  - `dump_config` follows the design's `sort_keys=False`, so it keeps the template's key order. It also uses a no-alias SafeDumper and `allow_unicode=True`, so **3.2/3.3 must write mkdocs.yml with `encoding="utf-8"`**.
  - `check_config` problems use path `website/mkdocs.template.yml` with a dotted `where` (`theme.palette[1].bogus`, `theme.features.<name>`, `plugins.search.<opt>`). Names must match exactly: no case-folding and no stripping.
  - Constraints on the 3.1 template: no `nav`, `docs_dir`, `site_dir` or `theme.custom_dir`; `plugins` must be a list; `theme` is a mapping or absent/null.
  - A 3.1-shaped template was probed and passes.
- 2.3 (3 rounds, parallel stream impl/ds-2-3):
  - `nav_structure` returns `[{section: [{title: "<path>.md"}]}]`, the shape 2.4's `render_config` takes.
  - URLs are `site_url` (trailing `/` stripped, then one `/` added) + `page_path`; `index.md` maps to `site_url` itself.
  - Reviewer-accepted gap-fills:
    - An unknown section raises `ValueError`.
    - Equal `order` values tie-break by path.
    - In llms-full the body is CRLF/CR→LF then `.strip("\n")` only, so indentation and hard breaks are kept.
    - llms-full renders `body`, never `staged_text`.
  - Current behaviour pinned by exact literals: a title or summary containing CR/LF renders split (queued as a follow-up, low).
  - design.md traceability row 4.6 corrected from `page_url` to `page_path`.
- 2.7 (3 rounds, parallel stream impl/ds-2-7):
  - `scripts/make_hero_chart.py` renders through the real `fitdocs.render.charts.hero.render_hero_chart`.
  - DECIMALS=1.
  - The SVG is byte-identical on macOS arm64 and on Linux amd64 and arm64 (reviewer container runs, sha256 `c3a06796…668c`), and under Python 3.11–3.14.
  - The file-read scan covers the whole module except `main`, which reads the SVG under `--check`.
  - The checked-in SVG is pinned both byte-for-byte and as well-formed SVG (ElementTree) with `render() == render_hero_chart(demo_spec())`.
  - Regenerate with `uv run python -m scripts.make_hero_chart`.
  - The forbidden-strings scan of the SVG was not run locally (the variable is unset); the docs.yml gate covers it.
- 2.6 (3 rounds, parallel stream impl/ds-2-6):
  - `python -m scripts.check_site ROOT [ROOT ...]` matches check_artifacts: exit 0 clean, 1 findings, 2 hard error; the same `gate_not_run` wording; `kind\tsubject\tdetail\tremedy` on stderr.
  - The walk covers dot-entries and reads whole files. Directories are path-checked.
  - FIFOs and sockets are reported `unreadable` without being opened.
  - Per-entry type lookups sit inside `try`. Every OSError detail carries only the exception type name.
  - A needle-named entry gets the subject `<root>/<redacted path #N>`, where N is its ordinal in the walk. Matched text never reaches output on any path.
  - GATE_NOT_RUN does not walk.
  - Subject is `<root>/<rel>`; design § SiteGate was amended to match, at merge.
- 3.1 (3 rounds, parallel stream impl/ds-3-1).
  - **home.html.** It overrides `block content` of `main.html`: hero first, then `{{ super() }}`, which keeps Material's `partials/actions.html` edit action. Hero keys are read as `page.meta.hero_*`, each inside its own `{% if %}`. A primary action gets `md-button md-button--primary`, and hrefs and the chart `src` go through the `url` filter.
  - **Verified live.** A real Zensical 0.0.65 smoke build (reviewer) rendered the hero, the buttons, the chart with demo alt text, `rel="edit"` to `edit/main/website/content/…`, brand.css at every depth, and no third-party font request.
  - **Brand-value scan.** The 4.5 one-place scan (test_theme `_brand_leaks`) walks every file under `website/` except top-level `build/` and `content/`; content is the maintainer's copy, per the controller ruling. It exempts only `website/assets/brand.css`, and flags:
    - brand hex, case-insensitive;
    - `--(md|fd)-*:` declarations;
    - CSS colour functions;
    - `font-family`.

    Any future override or asset that mentions these outside brand.css reds that test.
  - **Test tooling.** jinja2 is loaded via importlib behind `requires_zensical`, since it is a transitive dependency of zensical.
  - **Queued.** The duplicate home-page h1 (hero plus `h1#__skip`), low.
- 2.8 (4 rounds, parallel stream `impl/ds-2-8`).
  - **Zensical 0.0.65, as measured by the reviewer's probe builds:**
    - Quoted raw-HTML `href`, `src` and `xlink:href` are rewritten source-relatively, exactly like markdown links.
    - Unquoted values, root-relative `/x`, `srcset` and `poster` are left untouched.
    - `strict: true` reports a missing asset in NEITHER markdown nor HTML, so LinkChecker is the only guard for 6.1.
  - **Resolution.** Link targets resolve against the page's source directory. A relative unquoted `href`/`src` is a Problem ("quote the value"); it is not resolved.
  - **Link attributes.** `(?<![\w:.-])(?:xlink:href|href|src)`: `xlink:src`, `foo:href`, `:href`, `data-href` and `data.src` are not link attributes.
  - **`github_slugs`.**
    - Matches github-slugger v2, checked across the full code-point range with node on the real source.
    - It keeps the Alphabetic So carve-out (circled, squared, negative-circled and negative-squared Latin letters, U+24B6–24E9 and U+1F130–1F189 sub-ranges) and the `-1-1` collision loop.
    - Its limits: Unicode 13 (JS) vs stdlib 14+, and it slugs raw heading source, not rendered text.
  - **Hero hrefs.** Every absolute hero href must be `https://`; a docs URL is then also checked.
  - **Signature.** `check_links(content, *, repo_root)`.
  - **Queued follow-ups (low):**
    - srcset/poster;
    - escaped destinations;
    - reference definitions in containers;
    - relative llms.txt links refused.
- 6.2 depends on 6.1 (undeclared in the plan): the CONTRIBUTING link to docs/website.md is checked by tests/test_contributing_doc.py::test_every_relative_link_in_contributing_doc_resolves. Run 6.2 after 6.1. CHANGELOG allows only https:// or # link targets, so the Homepage bullet names the URL as text.
- 3.2 (4 rounds, parallel stream impl/ds-3-2).
  - **Pinned.** `sync_tree` in-place behaviour was verified live: under a real `zensical serve`, pages updated about 0.26 s after a sync, while a rename-swap control went undetected. `write_tree` removes all four MANAGED paths, `html/` included, even when one is a symlink. A leftover `html` link otherwise fails every build with "site_dir must be within project root".
  - **Symlink and path rules.** No writer follows a link out of the root: lstat everywhere, lexists for dangling links. `_check_keys` refuses any key outside mkdocs.yml/staged/overrides, plus `..`, `.`, empty parts and NUL. `plan_tree` raises ValueError on a duplicate key and on a home page without an opening `---\n`.
  - **Source directories.** `_read_dir` skips dot-entries at any depth relative to the source dir.
  - **Consumer contract.** 3.3 and 3.4 must pass only `plan_tree` output to the writers.
  - **UNPINNED.** L20 and L21: symlinks and special files inside the repo-owned website/assets and website/overrides (queued).
- 3.3 (2 rounds).
  - **Interface.** `build(...) -> BuildOutcome(ok, problems, generator_output, tree, page_count)`. `page_count` is `len(content.pages)` when the content loaded, else 0.
  - **guard_root.** Decides containment by file identity: some ancestor samefile the repo; the `website` ancestor at index ≥2; the next component named exactly `build`. `website/build` itself is refused. Case and firmlink spellings of the repo are refused into content (probed on macOS against the real worktree).
  - **Order.** The managed-path clear runs first, but only when the root exists, so a failed first build creates nothing.
  - **Error handling.**
    - A template missing site_name, site_description or site_url is a Problem, co-reported with config problems.
    - Template problems are re-pathed to `website/mkdocs.template.yml`.
    - Any exception, including KeyboardInterrupt, removes html/ and re-raises.
  - **Verified with real Zensical (reviewer).** The fixture builds with ok and 6 pages, with llms at the html root. A missing .svg yields one line and no html/. A broken Jinja override yields a generator problem and no html/.
  - **For 3.4 and 3.5.** 3.5 MUST call `generator_executable()` BEFORE `build()`, because design says an exit-2 run touches nothing. 3.4 MUST decide the live sync on `outcome.ok`, not `outcome.tree`, because the tree is set on generator failure.
- 3.4 (2 rounds).
  - **Loop.** The preview builds into `check/`. `sync_tree` into `live/` runs only on `outcome.ok`. The serve process starts once, after the first success.
  - **Snapshot.** Records `(mtime_ns, size)` per file over content, overrides, assets and the template. Nested links are recorded but not followed.
  - **Serve exit (controller addition).** If the serve process exits on its own (port taken), the loop prints `site generator: serve exited with status N` and returns 2. The design was amended to say so.
  - **Verified against real Zensical (reviewer smoke run).** It handled serve, edit, add, delete (404), broken frontmatter with the old text still served, and the fix, then a clean stop (-15). A taken port returns 2 in about 1 s. The serve and snapshot signatures match the design.
  - **Test harness.** `drive()` runs `serve` in a daemon thread with a bounded join, so a loop that ignores `stop` fails the test instead of hanging CI.
  - **Not pinned here.** "The served site reflects the change" against the real generator is 4.2's job.
  - **For 3.5:**
    - map serve's return 2 to exit 2;
    - call `generator_executable()` before `serve()` and `build()`;
    - refuse a build root that lies inside the resolved content dir, since guard_root alone allows a root inside an out-of-repo content dir (checked by file identity).
- 3.5 (3 rounds).
  - **Commands.** `python -m scripts.build_site {build,serve,status}`:
    - Exit codes: 0 on success; 1 on problems, one line each on stderr, with `--verbose` appending the generator output; 2 when it could not run.
    - Relative paths (and a relative FITDOCS_SITE_CONTENT) anchor to REPO_ROOT.
    - An empty FITDOCS_SITE_CONTENT is unset. `--content ""` exits 2.
    - `status` prints `has_content=true|false` and works without the generator. Manual check: in the repo it prints `has_content=false`.
  - **Checks run before any build or serve, so an exit-2 run writes nothing.** In order:
    1. content;
    2. `guard_root`;
    3. overlap: a build root inside, equal to, or containing the content dir is refused, decided by file identity;
    4. `generator_executable()`.
  - **`guard_root` extension (controller addition, 3.5 round 1).** It now also refuses the repo root and any ancestor of it, by identity. `--build-dir ..` would otherwise clear `<parent>/{html,staged,overrides,mkdocs.yml}`.
  - **Tests.**
    - Identity rules are pinned on every filesystem by making `Path.resolve` a no-op.
    - The import guard in test_repo_wiring.py covers exactly the 10 `scripts/sitebuild` files plus `build_site.py`.
    - The reviewer ran the real CLI: case and firmlink spellings of the repo and its parents are refused; SIGINT exits 0; a taken port exits 2.
  - **For 5.1.** `_build_parser()` parses the design's workflow commands.
- 4.1 (2 rounds, parallel stream impl/ds-4-1). `test_build_smoke.py` builds the fixture once with real Zensical in about 2 s. Findings from the real output:
  - search.json sits at the html root, with `items[].location` of `""` for home and `why/#anchor` for sections.
  - Material's active page carries `label for=__toc` and a `#` link, which the nav parser skips.
  - Zensical writes html/ BEFORE a strict abort, so removing html/ on generator failure is load-bearing.
  - Zensical itself drops dotfiles on copy.

  Other notes:
  - llms equality is recomputed through outline, so outline's order and format are pinned in test_outline.py.
  - `plugins: [search]` is pinned in test_config.py; Zensical writes search.json regardless.
  - Linux runs so far were aarch64 only. The first ubuntu amd64 evidence is the docs.yml CI run.
