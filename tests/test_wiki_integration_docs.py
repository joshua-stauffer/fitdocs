"""Conformance for task 5.4: the wiki-integration documentation, plus its
two assigned residuals (design.md "WikiIntegrationDocs", "E2E Tests -> Skill
command", "Doc references leave the repository"; Req 8.6, 8.7, 8.9).

Four properties, one per group below:

(a) `docs/wiki-integration.md` exists with the six H2 sections in the fixed
    order the task specifies; the packaged-skills section names every
    `fitdocs.agentskill.PACKAGED_SKILLS` entry; the install/verify/update
    sections each mention `fitdocs skill`, and the update section also
    mentions `metadata.version`.
(b) every fenced `fitdocs` command anywhere on the page is a real command
    (and every named option a real option) in the installed tool's own typer
    registry -- reusing `tests/test_agent_skill.py`'s `_COMMAND_MAP`,
    `_FITDOCS_COMMAND_RE`, and `_OPTION_TOKEN_RE`, the exact machinery that
    already binds the packaged skills' own fenced commands to the tool.
(c) every relative link on the page resolves to a real sibling file, and
    every `#anchor` resolves to a real heading slug in its target (or the
    page itself) -- reusing `tests/test_docs_guarantees.py`'s
    `_heading_slugs`/`_anchor_links`.
(d) the task's own Observable: the page's numbered "Adopting fitdocs into an
    existing wiki" recipe, parsed from its own fenced `bash` blocks (never
    hand-copied), actually drains an existing scratch wiki's inbox end to
    end and leaves generated documents and the ownership declaration behind
    -- and, run a second time (the "Updating a skill" section's own fenced
    commands against that same installed copy), replaces rather than nests
    the installed skill directory.

Plus one of the two residuals: the README's `## Agent skills` section names
every `PACKAGED_SKILLS` entry (below). The other residual -- deleting the
corpus-wide negative pin in `tests/test_docs_guarantees.py` that named the
then-unshipped `fitdocs-workouts` skill -- is a deletion in that module
itself, not something this module re-checks; the implementer's report
records the mutation that confirmed the deleted pin used to fail on the
now-shipped skill name.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from fitdocs.agentskill import PACKAGED_SKILLS
from fitdocs.declaration import CONTRACT_DOCUMENTATION_URL
from tests.fixtures import builder
from tests.test_agent_skill import (
    _COMMAND_MAP,
    _FENCE_BLOCK_RE,
    _FITDOCS_COMMAND_RE,
    _OPTION_TOKEN_RE,
)
from tests.test_docs_guarantees import (
    _agent_skills_section,
    _anchor_links,
    _heading_slugs,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC_PATH = _REPO_ROOT / "docs" / "wiki-integration.md"

#: Fixed H2 order the task's Deliverable 1 mandates.
_EXPECTED_HEADINGS = (
    "The packaged skills",
    "Installing a skill",
    "Confirming a skill is active",
    "Updating a skill after upgrading fitdocs",
    "Adopting fitdocs into an existing wiki",
    "What the wiki's agent does next",
)


def _doc_text() -> str:
    assert _DOC_PATH.is_file(), "docs/wiki-integration.md does not exist"
    return _DOC_PATH.read_text(encoding="utf-8")


def _h2_headings(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", text, re.M)


def _section(text: str, heading: str, headings_in_order: tuple[str, ...]) -> str:
    """The text of the H2 section named ``heading``, up to the next H2 (or EOF)."""
    idx = headings_in_order.index(heading)
    start_pat = re.escape(f"## {heading}")
    if idx + 1 < len(headings_in_order):
        end_pat = re.escape(f"## {headings_in_order[idx + 1]}")
        match = re.search(rf"{start_pat}\n(.*?)^{end_pat}", text, re.S | re.M)
    else:
        match = re.search(rf"{start_pat}\n(.*)\Z", text, re.S | re.M)
    assert match is not None, f"could not isolate section {heading!r}"
    return match.group(1)


# --- (a) heading order, packaged-skills coverage, install/verify/update ----


def test_heading_order_matches_the_fixed_sequence() -> None:
    text = _doc_text()
    headings = _h2_headings(text)
    # Positive control: the walk found at least six headings, never zero.
    assert len(headings) >= 6, f"expected >= 6 H2 headings, found {headings}"
    assert headings == list(_EXPECTED_HEADINGS), (
        f"H2 heading order does not match the fixed sequence: {headings}"
    )


def test_packaged_skills_section_names_every_registered_skill() -> None:
    # Positive control: the registry itself must carry >= 2 entries, or the
    # membership loop below would pass having checked at most one name.
    assert len(PACKAGED_SKILLS) >= 2, (
        f"expected >= 2 packaged skills, found {PACKAGED_SKILLS}"
    )
    text = _doc_text()
    section = _section(text, "The packaged skills", _EXPECTED_HEADINGS)
    for name in PACKAGED_SKILLS:
        assert name in section, f"{name!r} is not named in 'The packaged skills'"


@pytest.mark.parametrize(
    "heading",
    [
        "Installing a skill",
        "Confirming a skill is active",
        "Updating a skill after upgrading fitdocs",
    ],
)
def test_install_verify_update_sections_mention_fitdocs_skill(heading: str) -> None:
    text = _doc_text()
    section = _section(text, heading, _EXPECTED_HEADINGS)
    assert "fitdocs skill" in section, f"{heading!r} does not mention 'fitdocs skill'"


def test_update_section_names_metadata_version() -> None:
    text = _doc_text()
    section = _section(
        text, "Updating a skill after upgrading fitdocs", _EXPECTED_HEADINGS
    )
    assert "metadata.version" in section


def test_installing_a_skill_section_offers_both_copy_and_symlink() -> None:
    text = _doc_text()
    section = _section(text, "Installing a skill", _EXPECTED_HEADINGS)
    assert "cp -R" in section, "'Installing a skill' does not offer a copy form"
    assert "ln -s" in section, "'Installing a skill' does not offer a symlink form"


# --- (b) every fenced fitdocs command exists in the registered surface -----


def test_every_fenced_fitdocs_command_exists_in_the_registered_surface() -> None:
    text = _doc_text()
    fences = _FENCE_BLOCK_RE.findall(text)
    checked = 0
    for lang, content in fences:
        if lang not in ("bash", "sh"):
            continue
        for line in content.splitlines():
            stripped = line.strip().lstrip("$").strip()
            match = _FITDOCS_COMMAND_RE.match(stripped)
            if match is None:
                continue
            checked += 1
            command_name = match.group(1)
            assert command_name in _COMMAND_MAP, (
                f"{command_name!r} is not a registered fitdocs command"
            )
            command = _COMMAND_MAP[command_name]
            allowed_opts = {
                opt for param in command.params for opt in getattr(param, "opts", ())
            }
            for token in _OPTION_TOKEN_RE.findall(stripped):
                assert token in allowed_opts, (
                    f"{token!r} is not an option of {command_name!r} "
                    f"(allowed: {sorted(allowed_opts)})"
                )
    # Positive control: the page must actually carry fenced fitdocs commands,
    # or the loop above passed having validated nothing.
    assert checked >= 4, f"expected >= 4 fenced fitdocs command lines, found {checked}"


# --- (c) every relative link and anchor resolves ----------------------------


def test_every_relative_link_and_anchor_resolves() -> None:
    text = _doc_text()
    links = _anchor_links(text)
    plain_links = re.findall(r"\]\(([^)\s#]+)\)", text)

    checked = 0
    for target, anchor in links:
        checked += 1
        target_path = _DOC_PATH.parent / target if target else _DOC_PATH
        assert target_path.is_file(), f"anchor link target does not exist: {target!r}"
        slugs = _heading_slugs(target_path.read_text(encoding="utf-8"))
        assert anchor in slugs, (
            f"anchor {anchor!r} does not resolve in {target_path} "
            f"(have {sorted(slugs)})"
        )

    for target in plain_links:
        if target.startswith(("http://", "https://")):
            continue
        checked += 1
        target_path = _DOC_PATH.parent / target
        assert target_path.is_file(), f"relative link target does not exist: {target!r}"

    assert checked >= 3, f"expected >= 3 links checked, found {checked}"


# --- README residual: every registered skill named -------------------------


def test_readme_agent_skills_section_names_every_registered_skill() -> None:
    assert len(PACKAGED_SKILLS) >= 2
    readme_text = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = _agent_skills_section(readme_text)
    for name in PACKAGED_SKILLS:
        assert name in section, f"{name!r} is not named in README's '## Agent skills'"


# --- (d) the task's Observable: the recipe runs start to finish ------------


def _section_bash_blocks(text: str, heading: str) -> list[str]:
    """Every fenced ``bash`` block inside the section named ``heading``, in
    document order -- parsed from the page text itself, never hand-copied,
    so an edit to that section which breaks its commands reds a test rather
    than a frozen expectation of what the section says."""
    section = _section(text, heading, _EXPECTED_HEADINGS)
    return [
        content for lang, content in _FENCE_BLOCK_RE.findall(section) if lang == "bash"
    ]


def _adopting_recipe_bash_blocks(text: str) -> list[str]:
    """Every fenced ``bash`` block inside the "Adopting fitdocs into an
    existing wiki" section, in document order."""
    return _section_bash_blocks(text, "Adopting fitdocs into an existing wiki")


def _run_recipe_block(
    command_text: str, *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one recipe block as a bash script, ``-e`` so a failing non-final
    line (for example the first half of a ``&&`` pair, or any earlier
    statement in a multi-line block) fails the block instead of being masked
    by a later line's own exit status."""
    return subprocess.run(
        ["bash", "-e", "-c", command_text],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_adopting_recipe_runs_end_to_end_against_a_scratch_wiki(tmp_path: Path) -> None:
    # Resolved from the *running interpreter*, never `shutil.which("fitdocs")`:
    # a developer machine can carry a global `fitdocs` shim (e.g.
    # `~/.local/bin/fitdocs` from a prior `uv tool install`) earlier on PATH
    # than this checkout's own console script, in which case `which` silently
    # exercises that foreign install instead of the code under test. The
    # console script sits in the same directory as the interpreter running
    # this test (`.venv/bin/python` alongside `.venv/bin/fitdocs`) for every
    # supported invocation (`uv run pytest`, `.venv/bin/pytest`), so deriving
    # it from `sys.executable` can never resolve outside this checkout.
    fitdocs_exe = Path(sys.executable).parent / "fitdocs"
    assert fitdocs_exe.is_file(), (
        f"no fitdocs console script found next to the running interpreter: "
        f"{fitdocs_exe} -- required to execute the recipe"
    )

    text = _doc_text()
    blocks = _adopting_recipe_bash_blocks(text)
    update_blocks = _section_bash_blocks(
        text, "Updating a skill after upgrading fitdocs"
    )
    # Positive control: the recipe must actually carry fenced commands to run,
    # or every assertion below would pass having executed nothing.
    assert len(blocks) >= 4, f"expected >= 4 fenced bash blocks, found {len(blocks)}"
    assert update_blocks, "the 'Updating a skill' section has no fenced bash blocks"

    # No block may reference the real user's home -- a `~` or `$HOME` in a
    # recipe command would defeat the HOME/proxy containment set up below by
    # resolving outside the scratch tree.
    for block in [*blocks, *update_blocks]:
        assert "~" not in block and "$HOME" not in block, (
            f"recipe block references the real HOME: {block!r}"
        )

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    notes = wiki / "notes.md"
    notes.write_text("# My existing notes\n\nSome content the agent wrote by hand.\n")
    notes_before = notes.read_bytes()

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Falsity-before: no workouts/ directory exists prior to the recipe.
    assert not (wiki / "workouts").exists()

    env = os.environ.copy()
    env["PATH"] = f"{fitdocs_exe.parent}{os.pathsep}{env.get('PATH', '')}"
    env.pop("FITDOCS_DATA", None)
    # Containment: an isolated HOME (so nothing reads or writes the real
    # developer's home directory) and an unreachable proxy on both schemes,
    # so *any* network fetch this recipe execution triggered -- through any
    # code path, not only the tile fetch the synthetic no-GPS fixtures happen
    # to make unreachable already -- would fail loudly rather than silently
    # succeeding.
    env["HOME"] = str(fake_home)
    env["HTTP_PROXY"] = "http://127.0.0.1:9"
    env["HTTPS_PROXY"] = "http://127.0.0.1:9"

    for block in blocks:
        command_text = block.replace("<skills-dir>", str(skills_dir))
        if "fitdocs sync" in command_text:
            # Deliverable's assigned fixture point: two synthetic .fit files
            # dropped into the recipe's own inbox directory before the drain
            # step, never before (so the inbox-creation step is genuinely
            # exercised) and never after (so the drain genuinely sees them).
            inbox = wiki / "inbox"
            assert inbox.is_dir(), (
                "recipe's inbox directory does not exist before the drain step"
            )
            (inbox / "one.fit").write_bytes(
                builder.small_sport_fit_bytes(9401, "hiking", timestamp_offset=0)
            )
            (inbox / "two.fit").write_bytes(
                builder.small_sport_fit_bytes(9402, "cycling", timestamp_offset=100_000)
            )
        result = _run_recipe_block(command_text, cwd=wiki, env=env)
        assert result.returncode == 0, (
            f"recipe step failed:\n$ {command_text}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        if "fitdocs sync" in command_text:
            # A GPS-carrying fixture reaching the (proxied, unreachable) tile
            # fetch would surface as a warning, not a failure (Req 4.4) --
            # this run's warnings count must be genuinely zero, not merely
            # "the run exited 0", or a future fixture change that adds GPS
            # alongside a dropped `[tiles] enabled = false` step could pass
            # this test while silently attempting a network fetch.
            assert re.search(r"Warnings\s*\S?\s*0\s*\S?\s*$", result.stdout, re.M), (
                f"expected a zero Warnings row in the sync output:\n{result.stdout}"
            )

    workout_docs = [
        p for p in (wiki / "workouts").glob("*.md") if p.name != "AGENTS.md"
    ]
    assert len(workout_docs) == 2, (
        f"expected 2 workout documents, found {[p.name for p in workout_docs]}"
    )

    agents_md = wiki / "workouts" / "AGENTS.md"
    assert agents_md.is_file(), (
        "workouts/AGENTS.md (the ownership declaration) is missing"
    )
    assert CONTRACT_DOCUMENTATION_URL in agents_md.read_text(encoding="utf-8"), (
        "workouts/AGENTS.md does not name the published ownership contract"
    )

    skill_md = skills_dir / "fitdocs-workouts" / "SKILL.md"
    assert skill_md.is_file(), (
        "the fitdocs-workouts skill was not installed at <skills-dir>"
    )
    assert re.search(
        r"^name:\s*fitdocs-workouts\s*$", skill_md.read_text(encoding="utf-8"), re.M
    ), "the installed SKILL.md's frontmatter name is not fitdocs-workouts"

    check_result = _run_recipe_block("fitdocs check", cwd=wiki, env=env)
    assert check_result.returncode == 0, (
        f"fitdocs check did not exit 0 after the recipe:\n"
        f"stdout:\n{check_result.stdout}\nstderr:\n{check_result.stderr}"
    )

    assert notes.read_bytes() == notes_before, (
        "the pre-existing notes.md was modified by the recipe"
    )

    # The task's second Observable: re-running the "Updating a skill" section's
    # own fenced commands against the copy the recipe just installed must
    # *replace* it, not nest a second copy inside it (round-2 review: a bare
    # `cp -R` into an already-populated destination copies INTO it).
    nested = skills_dir / "fitdocs-workouts" / "fitdocs-workouts"
    for update_block in update_blocks:
        command_text = update_block.replace("<skills-dir>", str(skills_dir))
        update_result = _run_recipe_block(command_text, cwd=wiki, env=env)
        assert update_result.returncode == 0, (
            f"update step failed:\n$ {command_text}\n"
            f"stdout:\n{update_result.stdout}\nstderr:\n{update_result.stderr}"
        )
    assert not nested.exists(), (
        f"updating the skill nested a second copy inside itself: {nested}"
    )
    assert re.search(
        r"^name:\s*fitdocs-workouts\s*$", skill_md.read_text(encoding="utf-8"), re.M
    ), (
        "after updating, the top-level SKILL.md's frontmatter name is not "
        "fitdocs-workouts"
    )
