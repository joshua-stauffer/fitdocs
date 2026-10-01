"""The page ``docs/website.md`` states the contract as built (11.2-11.7, 11.9).

The values come from ``scripts.sitebuild.model`` and from ``pyproject.toml``,
so a new key, section or pin forces a documentation edit. The page is the
thing under test: a ``Dies on:`` line names an edit to that page or to
``docs/index.md``, except where it names a change to the model or to
``pyproject.toml``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from scripts.sitebuild.model import (
    CONTENT_ENV_VAR,
    HERO_ACTION_KEYS,
    HERO_KEYS,
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    RESERVED_ROOT_NAMES,
    SECTIONS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "docs" / "website.md"
INDEX = REPO_ROOT / "docs" / "index.md"

# GitHub's documented apex addresses (research.md, "GitHub Pages deployment
# via Actions").
A_RECORDS = tuple(f"185.199.{octet}.153" for octet in range(108, 112))
AAAA_RECORDS = tuple(f"2606:50c0:800{n}::153" for n in range(4))

# The type each key is documented as, from design.md "Content contract".
KEY_TYPES = {
    "title": "string",
    "description": "string",
    "section": "string",
    "order": "integer",
    "draft": "boolean",
    "hero_title": "string",
    "hero_tagline": "string",
    "hero_actions": "list",
}
HERO_ACTION_TYPES = {"label": "string", "href": "string", "primary": "boolean"}


def _squash(text: str) -> str:
    """``text`` with runs of whitespace collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _text() -> str:
    """The page text with runs of whitespace collapsed to one space."""
    return _squash(PAGE.read_text(encoding="utf-8"))


def _section(heading: str) -> str:
    """The raw text under the heading line ``heading`` up to the next heading
    of the same or a higher level."""
    lines = PAGE.read_text(encoding="utf-8").splitlines()
    level = len(heading) - len(heading.lstrip("#"))
    start = lines.index(heading)
    body: list[str] = []
    for line in lines[start + 1 :]:
        match = re.match(r"(#+) ", line)
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _table_rows(section: str) -> dict[str, str]:
    """Rows of the markdown table in ``section`` keyed by their first cell,
    backticks stripped."""
    rows: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"\| `([^`]+)` \|(.*)\|\s*$", line)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


def _docs_pin() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pins = [p for p in data["dependency-groups"]["docs"] if p.startswith("zensical")]
    assert len(pins) == 1, pins
    return str(pins[0])


def test_page_exists_and_is_not_empty() -> None:
    """The page exists, opens with an H1, and carries the contract heading.

    Dies on: deleting docs/website.md, or renaming its `## The content contract`
    heading.
    """
    text = PAGE.read_text(encoding="utf-8")
    assert text.startswith("# "), "docs/website.md has no H1"
    assert "## The content contract" in text.splitlines()


def test_frontmatter_table_lists_every_key_with_its_type() -> None:
    """Every required, optional and hero key is a table row, carrying its type.

    Dies on: deleting the `draft` row, changing the `order` row's type word
    from integer to string, dropping "required, not a boolean" from it, or
    adding a key to `OPTIONAL_KEYS` in the model.
    """
    rows = _table_rows(_section("### Frontmatter keys"))
    documented = REQUIRED_KEYS + OPTIONAL_KEYS + HERO_KEYS
    assert set(documented) == set(KEY_TYPES), "KEY_TYPES is out of step with the model"
    assert set(rows) == set(documented), sorted(set(rows) ^ set(documented))
    for key, type_word in KEY_TYPES.items():
        assert type_word in rows[key], (
            f"{key} row does not say {type_word}: {rows[key]}"
        )
    assert "required, not a boolean" in rows["order"], rows["order"]


def test_frontmatter_rows_state_who_may_carry_each_key() -> None:
    """A required key's row says required and does not name index.md, a hero
    key's row says root `index.md` only and is not required, and an optional
    key's row says optional.

    Dies on: dropping "required" from the `title` row, adding "index.md" to the
    `title` row, dropping "root `index.md` only" from the `hero_title` row, or
    changing "optional" to "sometimes" on the `draft` row.
    """
    rows = _table_rows(_section("### Frontmatter keys"))
    for key in REQUIRED_KEYS:
        assert "required" in rows[key].lower(), key
        assert "index.md" not in rows[key], key
    for key in HERO_KEYS:
        assert "root `index.md` only" in rows[key], key
        assert "required" not in rows[key].lower(), key
    for key in OPTIONAL_KEYS:
        assert "optional" in rows[key].lower(), key


def test_hero_action_table_lists_every_action_key_with_its_type() -> None:
    """Each `hero_actions` entry key is a row with its type. `label` and `href`
    say required and non-empty and not optional, and `primary` says optional.

    Dies on: deleting the `primary` row, changing its type word from boolean,
    changing "required" to "needed" on `label`, or dropping "non-empty" from
    `href`.
    """
    rows = _table_rows(_section("### The home page hero"))
    assert set(rows) == set(HERO_ACTION_KEYS), sorted(set(rows) ^ set(HERO_ACTION_KEYS))
    for key, type_word in HERO_ACTION_TYPES.items():
        assert type_word in rows[key], f"{key}: {rows[key]}"
    assert "optional" in rows["primary"].lower()
    for key in ("label", "href"):
        assert "required, non-empty" in rows[key], key
        assert "optional" not in rows[key].lower(), key


def test_hero_href_rule_is_stated() -> None:
    """An `href` is an absolute https URL or a trailing-slash site path.

    Dies on: deleting the "https://" or "trailing-slash" wording from the hero
    section.
    """
    section = _squash(_section("### The home page hero"))
    assert "absolute `https://` URL" in section
    assert "trailing-slash site path" in section


def test_hero_entry_and_placement_rules_are_stated() -> None:
    """An unknown entry key fails, and hero keys are allowed on the root
    index.md only, a nested index.md included.

    Dies on: deleting either sentence from the hero section.
    """
    section = _squash(_section("### The home page hero"))
    assert "An entry with any other key fails." in section
    assert (
        "A hero key on any page other than the root `index.md` fails, "
        "a nested `guides/index.md` included."
    ) in section


def test_sections_are_listed_in_the_model_order() -> None:
    """The eight sections appear as an ordered list, in SECTIONS order.

    Dies on: swapping two list items, dropping one section, or adding a name
    to `SECTIONS` in the model.
    """
    body = _section("### Sections")
    listed = re.findall(r"^\d+\. `([^`]+)`\s*$", body, flags=re.MULTILINE)
    assert tuple(listed) == SECTIONS


def test_content_resolution_names_the_env_var_option_and_default_dir() -> None:
    """The resolution order is option, then the environment variable, then
    website/content/, with an empty variable counting as unset.

    Dies on: renaming the variable in the page or in the model, swapping list
    items, or removing the empty-value sentence.
    """
    body = _squash(_section("### Where content comes from"))
    positions = [
        body.find("`--content`"),
        body.find(f"`{CONTENT_ENV_VAR}`"),
        body.find("`website/content/`"),
    ]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions), positions
    assert f"An empty `{CONTENT_ENV_VAR}` is treated as unset" in body


def test_build_serve_status_and_content_commands_appear() -> None:
    """The exact commands a maintainer types are present, each on a line of its own.

    Dies on: deleting the `serve` command line, changing the build command line
    to another module, or deleting the `--content` or environment-variable example.
    """
    lines = PAGE.read_text(encoding="utf-8").splitlines()
    for command in (
        "uv sync --group docs",
        "uv run --group docs python -m scripts.build_site build",
        "uv run --group docs python -m scripts.build_site serve",
        "uv run python -m scripts.build_site status",
    ):
        assert command in lines, command
    assert any(
        line.startswith(
            "uv run --group docs python -m scripts.build_site build --content "
        )
        for line in lines
    ), "no --content example"
    assert any(
        line.startswith(f"{CONTENT_ENV_VAR}=")
        and line.endswith("uv run --group docs python -m scripts.build_site build")
        for line in lines
    ), "no env-var example for an out-of-repo directory"


def _bullets(section: str) -> dict[str, str]:
    """Bullets shaped ``- `code` means ...`` keyed by the code, whitespace squashed."""
    found: dict[str, str] = {}
    for match in re.finditer(
        r"^- `(\d)` means ((?:.+(?:\n  .+)*))", section, flags=re.MULTILINE
    ):
        found[match.group(1)] = _squash(match.group(2))
    return found


def test_exit_code_bullets_each_state_their_meaning() -> None:
    """Each exit code has its own meaning: 0 success, 1 problems, and 2 for
    every way the command could not run, including a missing generator.

    Dies on: rewording any one code's bullet, for example the `2` bullet's
    "a missing generator" to "a missing template", or its lead "the command
    could not run" to "the command failed".
    """
    bullets = _bullets(_section("### Failures and exit codes"))
    assert set(bullets) == {"0", "1", "2"}
    assert bullets["0"] == "success."
    assert bullets["1"] == "the input has problems, listed as above."
    assert bullets["2"].startswith("the command could not run: ")
    for cannot_run in (
        "a missing content directory",
        "a missing generator",
        "a refused build root",
        "an empty `--content`",
        "a preview process that exited by itself",
    ):
        assert cannot_run in bullets["2"], cannot_run
    assert "success" not in bullets["1"] + bullets["2"]
    assert "problems" not in bullets["2"]


def test_exit_two_scope_is_limited_to_runs_refused_before_building() -> None:
    """A run refused before it builds or serves has written nothing, and a
    preview whose serve process exits has already built into its preview root.

    Dies on: restoring the unscoped sentence "Such a run has written nothing",
    or deleting the preview-root sentence.
    """
    section = _squash(_section("### Failures and exit codes"))
    assert "A run refused before it builds or serves has written nothing." in section
    assert (
        "A preview whose serve process exits has already built into its preview root."
        in section
    )
    assert "Such a run has written nothing" not in section


def test_failure_line_format_and_fields_are_stated() -> None:
    """The one-line shape and every form each field takes.

    Dies on: deleting `path: where: message`, the template path, the
    `site generator` path, the `hero_actions[N].href` form, or `--verbose`.
    """
    body = _squash(_section("### Failures and exit codes"))
    assert "`path: where: message`" in body
    assert "relative to the content directory" in body
    assert "`website/mkdocs.template.yml`" in body
    assert "`site generator`" in body
    for form in (
        "a frontmatter key",
        "`hero_actions[N].href`",
        "a line number",
        "a `line:col` position",
        "a dotted configuration key",
    ):
        assert form in body, form
    assert "Pass `--verbose` to also print the generator's own output" in body


def test_build_root_rules_are_stated() -> None:
    """Inside the repository a build root lies under website/build/, a root
    outside the repository is allowed, and no root may overlap the content dir.

    Dies on: deleting the `website/build/` rule, the outside-root sentence or
    the overlap rule.
    """
    body = _squash(_section("### The build root"))
    assert "a build root must be under `website/build/`" in body
    assert (
        "A root outside the repository is allowed when it does not overlap the "
        "content directory."
    ) in body
    assert (
        "must never overlap the content directory: a root inside it, equal to it, "
        "or containing it is refused"
    ) in body
    assert "`--build-dir`" in body


def test_runbook_steps_are_numbered_in_order_with_verification_before_dns() -> None:
    """The runbook subsections are the numbered steps in this order, and the
    domain is verified, and the custom domain configured, before the DNS records.

    Dies on: renaming or reordering one `###` heading under the runbook, for
    example moving `### 3. Add the DNS records` above `### 1. Verify the domain`.
    """
    body = _section("## Maintainer runbook")
    headings = re.findall(r"^### (.+)$", body, flags=re.MULTILINE)
    assert headings == [
        "1. Verify the domain",
        "2. Configure Pages",
        "3. Add the DNS records",
        "4. Turn on Enforce HTTPS",
        "5. Import the content",
        "6. Bump the Zensical pin",
    ]
    order = {h.split(". ", 1)[1]: body.index(f"### {h}") for h in headings}
    assert order["Verify the domain"] < order["Configure Pages"]
    assert order["Configure Pages"] < order["Add the DNS records"]
    assert order["Add the DNS records"] < order["Turn on Enforce HTTPS"]
    intro = _squash(body.split("### ", 1)[0])
    assert (
        "verifying the domain first, then setting the custom domain, then creating "
        "the DNS records"
    ) in intro
    assert (
        "If the DNS records are created before the domain is verified and set as "
        "the custom domain, someone else can publish a Pages site on the domain in "
        "the gap."
    ) in intro


def test_dns_section_has_four_a_and_four_aaaa_records() -> None:
    """Every apex A and AAAA address appears in the DNS section, and every IPv4
    and IPv6 address in the section is one of those eight.

    Dies on: changing one octet of one address, deleting one record line, or
    adding a ninth address in IPv4, compressed or uncompressed IPv6 form.
    """
    body = _section("### 3. Add the DNS records")
    a_rows = re.findall(r"^\| A \| `([0-9.]+)` \|", body, flags=re.MULTILINE)
    aaaa_rows = re.findall(r"^\| AAAA \| `([0-9a-f:]+)` \|", body, flags=re.MULTILINE)
    assert tuple(a_rows) == A_RECORDS
    assert tuple(aaaa_rows) == AAAA_RECORDS
    # IPv4, and any IPv6 form: a run of hex digits and colons holding two or
    # more colons.
    tokens = re.findall(
        r"(?:\d{1,3}\.){3}\d{1,3}|[0-9A-Fa-f]*(?::[0-9A-Fa-f]*){2,}", body
    )
    assert sorted(tokens) == sorted((*A_RECORDS, *AAAA_RECORDS)), tokens
    assert "docs.github.com" in body, "the page must say where the addresses came from"
    assert "`www` CNAME record pointing at `joshua-stauffer.github.io`" in _squash(body)


def test_verification_txt_name_is_stated() -> None:
    """The domain-verification TXT record name and its keep-in-place rule.

    Dies on: renaming the record (for example dropping the `_github-pages-`
    prefix), or deleting "Keep the record in place".
    """
    body = _squash(_section("### 1. Verify the domain"))
    assert "`_github-pages-challenge-<owner>`" in body
    assert "Keep the record in place" in body


def test_pages_settings_are_all_stated() -> None:
    """Three bullets: Source, the environment restriction and the custom domain.

    Dies on: deleting any one of the three bullets.
    """
    body = _section("### 2. Configure Pages")
    bullets = [
        _squash(b) for b in re.findall(r"^- (.+(?:\n  .+)*)", body, flags=re.MULTILINE)
    ]
    assert len(bullets) == 3, bullets
    assert 'Source "GitHub Actions"' in bullets[0]
    assert (
        "`github-pages` environment to deployment from the `main` branch" in bullets[1]
    )
    assert "custom domain `fitdocs.ai`" in bullets[2]


def test_enforce_https_step_is_stated() -> None:
    """Enforce HTTPS is its own step, offered only after the records resolve.

    Dies on: deleting the "only after" sentence or the Enforce HTTPS wording.
    """
    body = _squash(_section("### 4. Turn on Enforce HTTPS"))
    assert "turn on Enforce HTTPS" in body
    assert "GitHub offers it only after the records resolve" in body


def test_content_import_step_is_stated() -> None:
    """Copy into website/content/, annotation blocks may stay for LF files, commit.

    Dies on: deleting the annotation sentence, or the `website/content/` copy
    instruction.
    """
    body = _squash(_section("### 5. Import the content"))
    assert "into `website/content/`" in body
    assert "annotation blocks may stay when the files use LF line endings" in body
    assert "by commit" in body


def test_stated_zensical_pin_equals_the_docs_group_pin() -> None:
    """The pin in the page equals pyproject's docs pin, and no other Zensical
    pin is stated.

    Dies on: editing the pin in the page (for example `0.0.65` to `0.0.64`),
    or pyproject's docs pin without the page, or adding a second pin in any
    spelling (`zensical == 0.0.64`, `zensical>=0.0.64`).
    """
    pin = _docs_pin()
    assert pin.startswith("zensical=="), pin
    text = PAGE.read_text(encoding="utf-8")
    stated = {
        re.sub(r"\s+", "", m)
        for m in re.findall(
            r"zensical\s*(?:===?|[<>!~]=|[<>])\s*[0-9][0-9A-Za-z.]*", _squash(text)
        )
    }
    assert stated == {pin}, (stated, pin)


def test_pin_bump_procedure_rederives_the_feature_allowlist() -> None:
    """The bump is an ordered procedure that re-derives ALLOWED_FEATURES.

    Dies on: deleting the `ALLOWED_FEATURES` step, the test command step, the
    `uv lock` mention, or the release-notes step.
    """
    body = _section("### 6. Bump the Zensical pin")
    steps = [
        _squash(step)
        for step in re.findall(r"^\d+\. (.+(?:\n {3}.+)*)", body, flags=re.MULTILINE)
    ]
    assert len(steps) >= 5, steps
    assert any("ALLOWED_FEATURES" in s for s in steps)
    assert any("FITDOCS_REQUIRE_SITE_TOOLING=1" in s for s in steps)
    assert any("uv lock" in s for s in steps)
    assert any("release notes" in s for s in steps)


def test_intro_states_the_page_is_outside_the_compatibility_policy() -> None:
    """11.6: the text before the first H2 says the page documents the
    repository's website, is not a contract the compatibility policy governs,
    and links compatibility.md.

    Dies on: deleting the sentence, or the compatibility.md link, from the intro,
    or moving it below the first H2.
    """
    intro = _squash(PAGE.read_text(encoding="utf-8").split("\n## ", 1)[0])
    assert (
        "documents the repository's website and is not one of the contracts "
        "governed by the [compatibility policy](compatibility.md)"
    ) in intro


def test_rebuild_on_save_belongs_to_the_site_tooling() -> None:
    """11.7: rebuild-on-save is the site tooling's, and fitdocs performs no
    watching and no scheduling.

    Dies on: deleting either clause of the sentence.
    """
    text = _text()
    assert "rebuild-on-save belongs to the repository's site tooling" in text
    assert "fitdocs itself performs no watching and no scheduling" in text


def test_reserved_names_and_symlink_refusal_are_stated() -> None:
    """2.11: every reserved root name, and that a symbolic link anywhere is refused.

    Dies on: deleting `llms-full.txt` from the page, or the symlink sentence.
    """
    body = _squash(_section("### Names that are excluded or refused"))
    for name in RESERVED_ROOT_NAMES:
        assert f"`{name}`" in body, name
    assert "A symbolic link anywhere in the content directory is refused" in body
    assert "reserved root names" in body


def test_exclusion_rules_are_stated() -> None:
    """1.4: a leading `_` or `.` excludes the file or directory and everything under it.

    Dies on: deleting the exclusion sentence.
    """
    body = _squash(_section("### Names that are excluded or refused"))
    assert (
        "whose name begins with `_` or `.` is excluded, with everything beneath it"
    ) in body


def test_link_rules_are_stated() -> None:
    """2.10/2.12: markdown link syntax; a raw-HTML link to a `.md` source is
    refused while one to a page URL is accepted; an unquoted relative raw-HTML
    href or src is refused while absolute and fragment-only ones are not;
    assets resolve relative to the linking page; docs/ pages by GitHub URL.

    Dies on: deleting or rewording any one of those sentences, for example
    reversing the `.md` rule to "A raw-HTML link to a page URL ... is refused".
    """
    body = _squash(_section("### Links"))
    assert (
        "Links between pages use markdown link syntax with a relative path to the "
        "target's `.md` source file, optionally followed by an `#anchor`."
    ) in body
    assert (
        "A raw-HTML link to a `.md` source file is refused, and the message names "
        "the file and line."
    ) in body
    assert (
        "A raw-HTML link to a page URL such as `get-started/install/` is accepted."
        in body
    )
    assert (
        "Inside raw HTML a relative `href` or `src` value must be quoted: an "
        "unquoted relative raw-HTML `href` or `src` value is refused."
    ) in body
    assert "An unquoted absolute or `#fragment`-only value is not refused." in body
    assert "relative to the directory of the page that links them" in body
    assert "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/" in body


def test_drafts_rule_is_stated() -> None:
    """`draft: true` excludes a page everywhere.

    Dies on: shortening the exclusion list in the Drafts section.
    """
    drafts = _squash(_section("### Drafts"))
    assert "`draft: true`" in drafts
    assert "navigation, the built site, search and both site indexes" in drafts


def test_annotation_block_rule_and_its_limits_are_stated() -> None:
    """The block is defined by an empty line, `---` and an `Annotations:` line
    to the end of the file, files use LF, and a CRLF body after LF frontmatter or
    a blank line holding spaces are stated as not stripped.

    Dies on: deleting the LF sentence or the limitation paragraph, or changing
    "removes such a block".
    """
    body = _squash(_section("### The annotation block"))
    assert (
        "an empty line (no spaces), then `---`, then a line beginning `Annotations:`"
        in body
    )
    assert "to the end of the file" in body
    assert "Files use LF line endings." in body
    assert "The build removes such a block" in body
    assert (
        "A block in a CRLF body after LF frontmatter, or one whose blank line "
        "before `---` holds spaces, is not stripped and stays in the page."
    ) in body


# Sentences a reader relies on, each pinned so that deleting it turns this red.
CONTRACT_SENTENCES = (
    "The chosen directory must exist",
    "A relative path, whether from the option or from the variable, is read "
    "from the repository root",
    'An empty `--content ""` is refused.',
    "The build never creates, changes, renames or deletes anything in the "
    "content directory.",
    "A content directory with no included page fails",
    "one with included pages but no `index.md` at its root fails",
    "Every other included file is an asset and is copied into the site at the "
    "same relative path.",
    "Dotfiles such as an editor's state file are excluded this way.",
    "including one under a name that begins with `_` or `.` and one inside an "
    "excluded directory",
    "whatever kind of entry carries them",
    "Reserved names are matched exactly, with letter case significant.",
    "a file with CRLF line endings, or with a byte-order mark before the first "
    "`---`, is refused as having no frontmatter",
    "A CRLF body after LF frontmatter is not refused",
    "That includes the generator's own `template` key.",
    "the text from the last occurrence of an empty line (no spaces), then `---`",
    "In the GitHub account's own Settings (not the repository's), open Pages",
    "and the line before `---` is empty, because the build strips them",
    "Two included pages in one section with the same `order` fail, and the "
    "message names both files.",
    "A section with no included page is left out.",
    "Within a section, pages are ordered by ascending `order`.",
    "leaves out any element whose key is missing; it never substitutes default text",
    "Its other frontmatter is still checked.",
    "A link to a draft page fails, the same as a link to a page that does not exist.",
    "the heading's id as the site generator makes it, which differs from "
    "GitHub's slug for punctuation runs and non-ASCII letters",
    "`## Foo & Bar!` is `#foo-bar` and `# Café -- Über_x` is `#cafe-uber_x`",
    "A key not in this table is refused, and so is a value of the wrong type.",
    "reports every violation it finds in one run",
    "names the directory and which of the three sources chose it",
    "so it appears in no page, search index or site index",
    "It accepts `--content` and `FITDOCS_SITE_CONTENT` exactly as `build` does, "
    "so an out-of-repo directory can be previewed",
    "the preview rebuilds",
    "A build writes the site to `website/build/site/html/`",
    "A link to a page or asset that is not in the built site fails.",
    "The build checks that the file exists in the repository and that any "
    "`#anchor` matches a heading there.",
    "A `---` rule that does not begin such a block is kept.",
    "It prints `has_content=true` or `has_content=false` and does not need the "
    "generator.",
    "It honours `--content` and `FITDOCS_SITE_CONTENT` as `build` does.",
    "A failed build leaves no `html/` behind.",
    "That directory is ignored by git.",
    "The repository itself and its parent directories are refused.",
    "serves it at `127.0.0.1:8000`",
    "`--addr HOST:PORT` changes the address",
    "keeps serving the previous good site, and serves the change once it is fixed",
    "The generator silently ignores a feature name it does not know, so the "
    "allowlist is the only check.",
    "GitHub offers it only after the records resolve",
    "The first deploy fails without it.",
    "needs no `CNAME` file",
    "The site deploys only from `main`, and only when the content directory "
    "holds an included page",
    "is never part of the installed package",
)


def test_contract_sentences_each_appear_on_the_page() -> None:
    """Each listed sentence appears in the page, and the list has no duplicates.

    Dies on: deleting or rewording any one listed sentence in docs/website.md.
    """
    text = _text()
    assert len(set(CONTRACT_SENTENCES)) == len(CONTRACT_SENTENCES)
    missing = [sentence for sentence in CONTRACT_SENTENCES if sentence not in text]
    assert not missing, missing


def test_every_environment_variable_named_on_the_page_is_a_real_one() -> None:
    """The only FITDOCS_ variables the page names are the content variable and
    the site-tooling switch the pin-bump step runs with.

    Dies on: inventing or misspelling a variable on the page, for example
    `FITDOCS_SITE_DIR`.
    """
    known = {CONTENT_ENV_VAR, "FITDOCS_REQUIRE_SITE_TOOLING"}
    named = set(re.findall(r"FITDOCS_[A-Z_]+", PAGE.read_text(encoding="utf-8")))
    assert named == known, named


def test_index_links_the_page_before_the_contributing_row() -> None:
    """docs/index.md carries a row linking website.md, placed before the
    Contributing row.

    Dies on: removing the row from docs/index.md, or moving it after the
    Contributing row.
    """
    rows = [
        line
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.startswith("|")
    ]
    website = [i for i, r in enumerate(rows) if "](website.md)" in r]
    contributing = [i for i, r in enumerate(rows) if "](../CONTRIBUTING.md)" in r]
    assert len(website) == 1, website
    assert len(contributing) == 1, contributing
    assert website[0] < contributing[0]
