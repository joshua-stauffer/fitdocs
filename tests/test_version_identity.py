"""Tests for :mod:`fitdocs.version` (design.md `#### VersionSource`, Req
2.1-2.4): the one leaf every version-reporting surface reads from, and the
repository-wide guarantee that no second copy of the released version
literal creeps in.

Three groups:

* Unit tests for :func:`~fitdocs.version.tool_version` and
  :func:`~fitdocs.version.version_display` with the underlying
  ``importlib.metadata.version`` lookup patched to a value that differs from
  the real installed one, so a test that happened to read the real value
  cannot pass by accident (Req 2.2, 2.3, 2.4).
* A repository scan asserting the released version literal from
  ``pyproject.toml``'s ``[project] version`` appears only in the manifest,
  the newest ``CHANGELOG.md`` entry (tolerated absent -- task 1.3 creates the
  file), and each packaged skill's ``SKILL.md`` ``metadata.version`` -- one
  per :data:`fitdocs.agentskill.PACKAGED_SKILLS` entry -- and nowhere else in
  tracked text under ``src/``, ``tests/``, ``docs/``, ``README.md``,
  ``pyproject.toml``, ``CHANGELOG.md`` (Req 2.1).
* ``tests/test_cli.py``, ``tests/test_tiles.py`` and ``tests/test_plugins.py``
  carry the three call-site tests (the eager ``--version`` callback, the tile
  User-Agent, and the plugin listing's built-in version) -- see those files.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

import fitdocs.version as version_module
from fitdocs.agentskill import PACKAGED_SKILLS
from fitdocs.version import DIST_NAME, UNKNOWN_VERSION, tool_version, version_display

_REPO_ROOT = Path(__file__).resolve().parents[1]

# --- unit tests: resolved / unresolved paths --------------------------------


def test_tool_version_returns_the_resolved_metadata_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tool_version()`` returns whatever the metadata lookup resolves --
    pinned against a value that differs from the real installed version, so
    a stub that ignores the patch and reads the real value cannot pass.
    """
    real = tool_version()
    assert real is not None, "fitdocs must be installed for this test to be meaningful"
    patched_value = f"{real}+patched-not-real"

    def _patched(name: str) -> str:
        return patched_value if name == DIST_NAME else real

    monkeypatch.setattr(version_module, "version", _patched)

    assert tool_version() == patched_value
    assert tool_version() != real


def test_tool_version_returns_none_when_package_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tool_version()`` returns ``None`` -- never raises, never a fabricated
    string -- when the distribution is not installed (Req 2.4)."""

    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "version", _raise)

    assert tool_version() is None


def test_version_display_returns_tool_version_when_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``version_display()`` equals ``tool_version()`` whenever the latter is
    not ``None`` (design.md VersionSource invariant)."""
    monkeypatch.setattr(version_module, "version", lambda name: "9.9.9-patched")

    assert version_display() == "9.9.9-patched"
    assert version_display() == tool_version()


def test_version_display_falls_back_to_unknown_token_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``version_display()`` returns :data:`UNKNOWN_VERSION` -- never raises,
    never empty -- when ``tool_version()`` is ``None`` (Req 2.4)."""

    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "version", _raise)

    assert version_display() == UNKNOWN_VERSION
    assert version_display() != ""


def test_lookup_happens_lazily_not_cached_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two successive calls each perform a fresh lookup -- no module-level
    cache -- so a value change between calls (e.g. across a reinstall within
    one process) is observed on the very next call, not stuck on the first.
    """
    values = iter(["first-call-value", "second-call-value"])
    monkeypatch.setattr(version_module, "version", lambda name: next(values))

    first = tool_version()
    second = tool_version()

    assert first == "first-call-value"
    assert second == "second-call-value"
    assert first != second


# --- repository scan: the released version literal appears nowhere else ----


def _released_version(root: Path) -> str:
    manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = manifest["project"]["version"]
    assert isinstance(project_version, str) and project_version
    return project_version


def _tracked_scan_files(root: Path) -> list[Path]:
    """Every tracked *and* untracked-but-not-ignored file under the scanned
    directories/roots, via ``git ls-files -co --exclude-standard``.

    ``-co --exclude-standard`` (cached + others, honouring ``.gitignore``) is
    used rather than a bare ``git ls-files`` so a new in-tree test or source
    file that has not yet been ``git add``-ed still participates in the scan
    -- an untracked file with a stray second copy of the released literal
    would otherwise hide from the walk that is supposed to catch exactly
    that.
    """
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    names = output.splitlines()
    prefixes = ("src/", "tests/", "docs/")
    exact = {"README.md", "pyproject.toml", "CHANGELOG.md"}
    return [root / name for name in names if name.startswith(prefixes) or name in exact]


def _version_literal_pattern(literal: str) -> re.Pattern[str]:
    """A whole-token match for *literal*: neither preceded nor followed by a
    digit or a dot, so a longer version that merely embeds *literal* as a
    prefix or suffix -- e.g. one with an extra leading or trailing digit, or
    a ``.devN`` suffix -- does not falsely match.
    """
    escaped = re.escape(literal)
    return re.compile(rf"(?<![\d.]){escaped}(?![\d.])")


def _find_version_literal(files: list[Path], literal: str) -> dict[Path, list[int]]:
    """1-indexed line numbers containing *literal* as a whole token, per file
    that has at least one match. Binary/undecodable files are skipped rather
    than raising -- this is a text scan.
    """
    pattern = _version_literal_pattern(literal)
    matches: dict[Path, list[int]] = {}
    for file_path in files:
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hit_lines = [
            line_no
            for line_no, line in enumerate(text.splitlines(), start=1)
            if pattern.search(line)
        ]
        if hit_lines:
            matches[file_path] = hit_lines
    return matches


def test_boundary_pattern_rejects_longer_embedding_versions() -> None:
    """The scan's own matching -- not the mutation-target production code --
    must not treat ``7.7.7`` as present inside ``17.7.7`` or ``7.7.7.dev1``.
    A naive substring test (``literal in line``) would wrongly match both.
    """
    pattern = _version_literal_pattern("7.7.7")

    assert pattern.search('version = "7.7.7"')
    assert not pattern.search('version = "17.7.7"')
    assert not pattern.search('version = "7.7.7.dev1"')
    assert not pattern.search('version = "7.7.75"')


def test_repository_scan_finds_release_literal_only_in_permitted_locations() -> None:
    """Requirement 2.1: the released version literal is declared in exactly
    one place, and appears nowhere else in tracked text under the scanned
    roots except the equality-checked copies design.md names -- the
    manifest itself, the newest ``CHANGELOG.md`` entry (tolerated absent),
    and each packaged skill's recorded version.

    Two occurrences elsewhere in this tree are legitimate non-declarations
    -- decided by reading each one, not guessed -- and are explicitly
    allowlisted by file, line text, and exact occurrence count rather than
    silently ignored:

    * ``docs/plugins.md`` -- an example third-party plugin's own
      ``pyproject.toml`` snippet (package name ``fitdocs-mycalc``), unrelated
      to this project's own version.
    * ``tests/load/test_packaging.py`` -- a comment illustrating the sdist's
      ``fitdocs-X.Y.Z/`` member-name prefix format, not a live declaration.

    (``tests/test_cli.py`` previously carried a third, in-boundary
    non-declaration -- a ``PluginInfo`` fixture's arbitrary stub calculator
    version that happened to collide with the released literal. That fixture
    now uses a non-colliding stub version, so it no longer needs an
    allowlist entry.)
    """
    released_version = _released_version(_REPO_ROOT)
    scan_files = _tracked_scan_files(_REPO_ROOT)
    assert scan_files, "the walk is looking at the wrong directory"

    matches = _find_version_literal(scan_files, released_version)

    permitted_whole_files = {_REPO_ROOT / "pyproject.toml"}
    changelog = _REPO_ROOT / "CHANGELOG.md"
    if changelog.is_file():
        # Task 1.3 creates this file; when present, only its newest release
        # entry (the first "## [" heading's section) is a permitted copy.
        permitted_whole_files.add(changelog)
    for skill_name in PACKAGED_SKILLS:
        skill_file = _REPO_ROOT / "src" / "fitdocs" / "skills" / skill_name / "SKILL.md"
        assert skill_file.is_file(), f"packaged skill file missing: {skill_file}"
        permitted_whole_files.add(skill_file)

    # Matched by the *matched line's own text*, not its line number: a line
    # number would silently stop discriminating the moment an unrelated edit
    # shifts either file, either falsely reddening this test or -- worse --
    # falsely greening it against a genuinely new occurrence that happens to
    # land on an allowlisted line number. Each allowlisted line text also
    # carries its expected occurrence *count*, so a second copy of the same
    # allowlisted text appearing in the file (an out-of-boundary duplicate
    # that would otherwise slip through unnoticed since its text is already
    # known) is caught too, not just text absent from the allowlist.
    packaging_comment_text = (
        f'# ``"fitdocs-{released_version}/docs/reference/some_table.csv"``), not a bare'
    )
    known_non_declaration_line_counts: dict[Path, dict[str, int]] = {
        _REPO_ROOT / "docs" / "plugins.md": {f'version = "{released_version}"': 1},
        _REPO_ROOT / "tests" / "load" / "test_packaging.py": {
            packaging_comment_text: 1
        },
    }

    unexpected: list[tuple[Path, int]] = []
    observed_counts: dict[Path, dict[str, int]] = {}
    for file_path, lines in matches.items():
        if file_path in permitted_whole_files:
            continue
        allowlisted_counts = known_non_declaration_line_counts.get(file_path, {})
        file_lines = file_path.read_text(encoding="utf-8").splitlines()
        for line_no in lines:
            text = file_lines[line_no - 1].strip()
            if text in allowlisted_counts:
                observed_counts.setdefault(file_path, {})
                observed_counts[file_path][text] = (
                    observed_counts[file_path].get(text, 0) + 1
                )
                continue
            unexpected.append((file_path, line_no))

    assert not unexpected, (
        "unexpected occurrence(s) of the released version literal "
        f"{released_version!r} outside the permitted/allowlisted set: {unexpected}"
    )

    count_mismatches: list[tuple[Path, str, int, int]] = []
    for file_path, expected_counts in known_non_declaration_line_counts.items():
        seen_counts = observed_counts.get(file_path, {})
        for text, expected in expected_counts.items():
            actual = seen_counts.get(text, 0)
            if actual != expected:
                count_mismatches.append((file_path, text, expected, actual))
    assert not count_mismatches, (
        "allowlisted line text occurred a different number of times than "
        f"expected (file, text, expected, actual): {count_mismatches}"
    )

    # Positive control: the permitted set is not vacuous -- the manifest and
    # every packaged skill actually contain the literal, not merely exist.
    assert _REPO_ROOT / "pyproject.toml" in matches
    for skill_name in PACKAGED_SKILLS:
        skill_file = _REPO_ROOT / "src" / "fitdocs" / "skills" / skill_name / "SKILL.md"
        assert skill_file in matches, f"{skill_file} missing the released version"


def test_scan_catches_a_second_literal_declaration_introduced_outside_the_permitted_set(
    tmp_path: Path,
) -> None:
    """A synthetic regression check for the scan machinery itself: a file
    under a scanned root that repeats a synthetic version literal outside
    every permitted location must be reported, proving the scan is not
    vacuously permissive (the anti-pattern the repo-scan test above cannot
    exercise against itself, since the real tree has none to catch). A
    synthetic literal (``7.7.7``), not the real released version, is used
    here so this test file itself never contains a second copy of the
    genuine literal for the repository scan to (correctly) flag.
    """
    (tmp_path / "src").mkdir()
    offending_file = tmp_path / "src" / "leaked_version.py"
    offending_file.write_text('__version__ = "7.7.7"\n', encoding="utf-8")
    other_file = tmp_path / "src" / "unrelated.py"
    other_file.write_text("x = 1\n", encoding="utf-8")

    matches = _find_version_literal([offending_file, other_file], "7.7.7")

    assert offending_file in matches
    assert matches[offending_file] == [1]
    assert other_file not in matches


# --- no import-time metadata read, in a fresh interpreter -------------------


_NO_IMPORT_TIME_READ_SCRIPT = """
import importlib.metadata

calls = []


def _recording_version(name):
    calls.append(name)
    raise importlib.metadata.PackageNotFoundError(name)


# Patched before any ``fitdocs`` module is imported, so a module-scope read
# anywhere on the ``fitdocs.cli`` import chain (cli -> tiles -> plugins ->
# version) is observed here rather than silently reading the real, installed
# metadata undetected.
importlib.metadata.version = _recording_version

import fitdocs.cli  # noqa: E402

assert calls == [], f"import-time importlib.metadata.version call(s): {calls}"

from typer.testing import CliRunner  # noqa: E402

runner = CliRunner()
result = runner.invoke(fitdocs.cli.app, ["--version"])
assert result.exit_code == 0, repr(result.output)
assert result.output.strip() == "unknown", repr(result.output)
print("import ok")
"""


def test_no_import_time_metadata_read_and_version_option_degrades_gracefully() -> None:
    """Design.md's VersionSource invariant -- "the lookup is performed
    lazily, at the point of use ... never at import time" (Req 2.1-2.4) --
    proven in a **fresh interpreter**, not merely by reading the source: an
    in-process patch after ``fitdocs`` is already imported would be a
    ``sys.modules`` cache hit and could not observe a module-scope read that
    already happened at the real import time.

    ``importlib.metadata.version`` is replaced with a call-recording stub
    *before* ``fitdocs.cli`` -- which pulls in ``tiles``, ``plugins``, and
    ``version`` -- is imported for the first time in this process. Zero
    recorded calls after that import proves nothing in the chain reads
    metadata at module scope. The same patched, always-raising stub is then
    left in place while ``--version`` is invoked through the real Typer app,
    proving the eager callback still degrades to :data:`UNKNOWN_VERSION`
    and exits 0 rather than raising, end to end through the CLI surface
    (not just the leaf function in isolation).
    """
    result = subprocess.run(
        [sys.executable, "-c", _NO_IMPORT_TIME_READ_SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"script failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "import ok" in result.stdout, f"no success marker; stdout={result.stdout!r}"
