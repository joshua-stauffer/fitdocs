"""Every packaged skill file is a member of the built wheel (design:
SkillWheelTest, task 3.1).

A sibling of :mod:`tests.test_forbidden_strings`, not an extension: that
module's artifact scans are the encumbered-content-purge spec's Req 11.7
absence guards (forbidden-string content and name absence only); this module
owns a different question entirely -- *presence* of every file the locator
(:mod:`fitdocs.agentskill`) lists for a registered skill, once packaged into
a real wheel. ``tests.test_forbidden_strings._build_artifact`` is imported
rather than copied, so this module adds no second, independent ``uv build``
subprocess recipe of its own.

Each test names the production mutation it exists to red; see
change-protocol.md's Fixture Discrimination section. "Production" here
includes the build inputs -- ``.gitignore`` and the skill files themselves --
because hatchling's silent wheel packaging (design.md "Existing Architecture
Analysis") makes those inputs part of what each assertion is about.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fitdocs.agentskill import PACKAGED_SKILLS, SKILLS_DIR, skill_files, skill_root
from tests.test_forbidden_strings import _build_artifact

WheelFixture = tuple[Path, frozenset[str]]


def _repo_root() -> Path:
    """The repository root, from this file's location -- depth-sensitive,
    so guarded: a ``pyproject.toml`` must live directly under it, or
    ``parents[1]`` is pointed at the wrong directory and ``uv build`` would
    run outside the project tree and fail with an unrelated error;
    asserting here names the actual cause instead.
    """
    root = Path(__file__).resolve().parents[1]
    assert (root / "pyproject.toml").is_file(), (
        f"{root} does not look like the repository root (no pyproject.toml "
        "at that depth) -- Path(__file__).resolve().parents[1] is pointed "
        "at the wrong directory"
    )
    return root


@pytest.fixture(scope="module")
def wheel_members(tmp_path_factory: pytest.TempPathFactory) -> WheelFixture:
    """Build exactly one wheel for the whole module and return its path and
    the frozenset of its member names. Module-scoped: one ``uv build`` per
    test run, not one per test (design.md's stated cost, "seconds on a warm
    cache", paid once).
    """
    out_dir = tmp_path_factory.mktemp("skill-wheel")
    _build_artifact(_repo_root(), out_dir, "--wheel")
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"
    wheel_path = wheels[0]
    with zipfile.ZipFile(wheel_path) as wheel:
        members = frozenset(name for name in wheel.namelist() if not name.endswith("/"))
    return wheel_path, members


def test_wheel_build_names_the_wheel_and_the_member_count(
    wheel_members: WheelFixture,
) -> None:
    """Observable required by the task: the test's output names the wheel
    and the member count. Printed under ``-s``; the wheel name is also
    embedded in the assertion message so that observable survives a
    captured run even without ``-s``.
    """
    wheel_path, members = wheel_members
    print(f"built wheel: {wheel_path.name}, {len(members)} member(s)")
    assert members, (
        f"built wheel {wheel_path.name} opened zero members -- the member "
        "scan is inspecting nothing, not proving the wheel is complete"
    )


def test_every_packaged_skill_file_is_a_wheel_member(
    wheel_members: WheelFixture,
) -> None:
    """For every registered skill and every file the locator lists for it,
    the wheel member path ``fitdocs/skills/<name>/<relative path>`` is
    present. Mutation: append ``skills/`` to ``.gitignore`` (hatchling
    drops the whole directory -- the member assertion reds); rename
    ``example-block.toml`` to ``example-block.fit`` (the ``*.fit``
    ``.gitignore`` rule drops that one member -- the assertion reds through
    ``skill_files``, which still lists the renamed file on disk).
    """
    examined: set[str] = set()
    _, members = wheel_members
    for name in PACKAGED_SKILLS:
        root = skill_root(name)
        assert root is not None, (
            f"packaged skill {name!r} has no installed root in this test "
            "environment -- the locator itself must resolve before its "
            "wheel membership can be checked"
        )
        for path in skill_files(name):
            relative = path.relative_to(root).as_posix()
            member = f"fitdocs/{SKILLS_DIR}/{name}/{relative}"
            examined.add(member)
            assert member in members, (
                f"{member} is listed by skill_files({name!r}) but is not a "
                "member of the built wheel"
            )
    assert examined, (
        "no packaged skill file was examined -- PACKAGED_SKILLS or "
        "skill_files resolved to nothing, so the member pin above never ran"
    )
    assert "fitdocs/skills/build-training-block/SKILL.md" in examined, (
        "the literal SKILL.md member path for build-training-block was "
        "never examined -- the walk did not reach the skill this task names"
    )
    assert "fitdocs/skills/build-training-block/example-block.toml" in examined, (
        "the literal example-block.toml member path was never examined -- "
        "the walk did not reach the skill's companion file"
    )


def test_positive_controls_fitdocs_package_files_are_members(
    wheel_members: WheelFixture,
) -> None:
    """Positive controls unrelated to the skill machinery: if these are
    absent, the wheel itself is broken, not the skill packaging -- a
    baseline the skill-specific pins above can be trusted against.
    """
    _, members = wheel_members
    assert "fitdocs/py.typed" in members
    assert "fitdocs/__init__.py" in members


def test_no_wheel_member_under_skills_names_an_unregistered_directory(
    wheel_members: WheelFixture,
) -> None:
    """Negative pin: the first path component after ``fitdocs/skills/`` for
    every wheel member must be a registered name. Mutation: add
    ``src/fitdocs/skills/phantom/SKILL.md`` -- an unregistered directory
    that ships in the wheel (nothing in ``.gitignore`` excludes it) -- and
    this pin reds.
    """
    prefix = f"fitdocs/{SKILLS_DIR}/"
    examined = 0
    _, members = wheel_members
    for member in members:
        if not member.startswith(prefix):
            continue
        examined += 1
        top = member[len(prefix) :].split("/", 1)[0]
        assert top in PACKAGED_SKILLS, (
            f"{member} sits under an unregistered skill directory {top!r} "
            f"-- PACKAGED_SKILLS is {PACKAGED_SKILLS!r}"
        )
    assert examined, (
        "no wheel member under fitdocs/skills/ was examined -- this guard's "
        "walk is looking at the wrong prefix"
    )


def test_no_wheel_member_under_skills_has_a_data_component(
    wheel_members: WheelFixture,
) -> None:
    """Negative pin related to the ``.gitignore`` ``data/`` trap
    (design.md "Existing Architecture Analysis"): no member path under
    ``fitdocs/skills/`` may have ``data`` as a path component. The
    ``.gitignore`` ``data/`` rule is directory-only, so a *directory* named
    ``data`` never reaches the wheel and cannot red this pin; what does red
    it is a shipped member with a literal ``data`` component that the
    directory rule does not catch -- a *file* literally named ``data``, or
    the ``.gitignore`` ``data/`` rule being lifted so a ``data/`` directory
    ships after all.
    """
    prefix = f"fitdocs/{SKILLS_DIR}/"
    examined = 0
    _, members = wheel_members
    for member in members:
        if not member.startswith(prefix):
            continue
        examined += 1
        assert "data" not in Path(member).parts, (
            f"{member} has a 'data' path component under fitdocs/skills/"
        )
    assert examined, (
        "no wheel member under fitdocs/skills/ was examined -- this guard's "
        "walk is looking at the wrong prefix"
    )
