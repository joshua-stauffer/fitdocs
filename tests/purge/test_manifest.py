"""`scripts/purge/manifest.py`: the tree manifest generator (Req 10.3) and
the `training-load` spec-status baseline capture (Req 4.4) task 1 requires.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.purge.manifest import (
    ManifestRow,
    SpecApprovals,
    app,
    build_spec_status_baseline,
    build_tree_manifest,
    count_acceptance_criteria,
    count_requirements,
    count_tasks,
    load_spec_approvals,
    write_spec_status_baseline,
    write_tree_manifest,
)
from typer.testing import CliRunner

runner = CliRunner()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _blob_sha(repo: Path, content: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "--stdin"],
        input=content,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    return root


def test_tree_manifest_has_one_row_per_tracked_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "alpha.txt").write_text("first file\n")
    (repo / "beta.txt").write_text("a second, distinct file\n")
    _git(repo, "add", "alpha.txt", "beta.txt")
    _git(repo, "commit", "-q", "-m", "two files")
    commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    rows = build_tree_manifest(commit, repo)

    assert {row.path for row in rows} == {"alpha.txt", "beta.txt"}
    by_path = {row.path: row for row in rows}
    assert by_path["alpha.txt"].blob == _blob_sha(repo, "first file\n")
    assert by_path["beta.txt"].blob == _blob_sha(repo, "a second, distinct file\n")
    # Pairwise-distinct blob shas -- a fixture where every row shared one
    # blob would leave a swapped path/blob mapping undetected.
    assert by_path["alpha.txt"].blob != by_path["beta.txt"].blob


def test_tree_manifest_reads_the_named_commit_not_the_working_tree(
    tmp_path: Path,
) -> None:
    """The generator must resolve blobs from `commit`'s recorded tree: not
    from `HEAD` (which has since moved to a later commit) and not from the
    working tree (which has since been dirtied on top of that). Three
    distinct contents exist by the end -- the named (base) commit's, the
    later commit `HEAD` now points at, and the uncommitted working-tree edit
    -- so a hardcoded `HEAD` and a disk read are each their own reachable,
    distinguishable wrong answer, not just one shared failure mode.
    """
    repo = _repo(tmp_path)
    (repo / "alpha.txt").write_text("original content\n")
    _git(repo, "add", "alpha.txt")
    _git(repo, "commit", "-q", "-m", "original")
    base_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Advance HEAD to a second commit with different content.
    (repo / "alpha.txt").write_text("second commit content\n")
    _git(repo, "add", "alpha.txt")
    _git(repo, "commit", "-q", "-m", "second")
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() != base_commit

    # Dirty the working tree on top of that, without committing.
    (repo / "alpha.txt").write_text("edited after the second commit\n")

    rows = build_tree_manifest(base_commit, repo)

    assert len(rows) == 1
    assert rows[0].blob == _blob_sha(repo, "original content\n")
    assert rows[0].blob != _blob_sha(repo, "second commit content\n")
    assert rows[0].blob != _blob_sha(repo, "edited after the second commit\n")


def test_build_tree_manifest_sorts_rows_by_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`git ls-tree -r` already emits path-sorted entries for ordinary
    filenames (its own tree sort order coincides with a full-path
    lexicographic sort for names like these), so a real repository cannot
    exercise the `sorted()` call in `build_tree_manifest` -- dropping it
    would still pass against real git output. Stub `subprocess.run` directly
    with rows in deliberately-unsorted order to pin `sorted()` itself.
    """
    unsorted_stdout = (
        f"100644 blob {'b' * 40}\tzeta.txt\n100644 blob {'a' * 40}\talpha.txt\n"
    )

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=(), returncode=0, stdout=unsorted_stdout, stderr=""
        )

    # `scripts.purge.manifest` does `import subprocess` (not `from
    # subprocess import run`), so patching this module's `subprocess.run`
    # patches the same singleton object it calls through.
    monkeypatch.setattr(subprocess, "run", fake_run)

    rows = build_tree_manifest("deadbeef", Path("/nonexistent"))

    assert [row.path for row in rows] == ["alpha.txt", "zeta.txt"]


def test_build_tree_manifest_skips_commit_type_gitlink_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fitdocs has no submodule, so no real repository can exercise the
    `if obj_type != "blob": continue` filter -- dropping it stays green
    against every fixture that only ever adds ordinary files. Stub
    `subprocess.run` with one `commit`-type entry (a submodule gitlink, which
    `git ls-tree` reports with `obj_type == "commit"` and no blob content of
    its own) mixed in with an ordinary blob, to pin the filter directly.
    """
    stdout = (
        f"160000 commit {'c' * 40}\tvendor/submodule\n"
        f"100644 blob {'a' * 40}\talpha.txt\n"
    )

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=(), returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    rows = build_tree_manifest("deadbeef", Path("/nonexistent"))

    assert [row.path for row in rows] == ["alpha.txt"]


def test_write_tree_manifest_round_trips_path_mode_blob(tmp_path: Path) -> None:
    out = tmp_path / "scratch" / "M0.tsv"
    rows = [
        ManifestRow(path="a.txt", mode="100644", blob="a" * 40),
        ManifestRow(path="b.txt", mode="100755", blob="b" * 40),
    ]

    write_tree_manifest(rows, out)

    lines = out.read_text().splitlines()
    assert lines == [
        "a.txt\t100644\t" + "a" * 40,
        "b.txt\t100755\t" + "b" * 40,
    ]


_REQUIREMENTS_MD = """# Requirements Document

### Requirement 1: First
**Objective:** a thing.

#### Acceptance Criteria

1. First criterion.
2. Second criterion.
3. Third criterion.
4.Not a criterion -- missing the whitespace `_CRITERION_ITEM` requires after
the number's dot (pins `r"^\\d+\\.\\s"`'s `\\s`; narrowing to `r"^\\d+\\."`
would count this line too).

### Requirement 2: Withdrawn
**WITHDRAWN.** No acceptance criteria section at all.

### Requirement 3: Third
**Objective:** another thing.

1. Not a criterion -- a numbered line sitting outside any "Acceptance
   Criteria" heading, the section-scoping decoy.

#### Acceptance Criteria

1. Only one here.

#### Something Else

1. A differently-named `####` heading with its own numbered list -- the
   heading-name decoy. Relaxing the scoping regex to match any `#### `
   heading (not only `Acceptance Criteria`) would pull these two lines in
   too, since this fixture would otherwise have no differently-named `####`
   heading to catch it.
2. Second line under the decoy heading, also not a criterion.

### Notes

A non-Requirement `###` heading -- the exact counterpart of the `####
Something Else` decoy above, but one level up: relaxing
`_REQUIREMENT_HEADING` from `^### Requirement \\d+` to `^### ` would count
this heading as a fourth requirement too.

### Requirement Numbering Scheme

A second `###` decoy, distinguishing the narrower relaxation: this heading
does start with "### Requirement " but has no trailing digit, so it catches
dropping only the `\\d+` (leaving `^### Requirement ` with no digit
requirement at all) even though the first decoy above does not -- "### Notes"
never starts with "### Requirement " regardless of which relaxation is
applied, so it cannot distinguish this narrower mutation from the correct
regex.
"""

_TASKS_MD = """# Implementation Plan

- [x] 1. Major one
- [x] 1.1 Sub one
- [ ] 1.2 Sub two, not done
  - [x] 1.2.1 Indented sub-sub-task, counted at any indentation depth
- [x] 2. Major two
- [X] 3. Major three, marked done with a capital X -- pins `[ xX]` against
  narrowing to `[ x]`, which would leave this line uncounted as completed.
"""


def test_count_requirements_counts_withdrawn_ones_too(tmp_path: Path) -> None:
    requirements_md = tmp_path / "requirements.md"
    requirements_md.write_text(_REQUIREMENTS_MD)

    assert count_requirements(requirements_md) == 3


def test_count_acceptance_criteria_scoped_to_the_heading(tmp_path: Path) -> None:
    requirements_md = tmp_path / "requirements.md"
    requirements_md.write_text(_REQUIREMENTS_MD)

    # 3 (Requirement 1) + 0 (Requirement 2, withdrawn, no section) + 1
    # (Requirement 3's real criterion) = 4. Requirement 3 also carries a
    # numbered line outside any "#### Acceptance Criteria" heading (the
    # section-scoping decoy) and a differently-named "#### Something Else"
    # heading with its own two-item numbered list (the heading-name decoy),
    # neither of which must be counted. Requirement 1 also carries a
    # `4.Not a criterion` line with no whitespace after the dot -- pins
    # `_CRITERION_ITEM`'s `\s`: narrowing the regex from `r"^\d+\.\s"` to
    # `r"^\d+\."` counts that line too, reading 5 (confirmed by execution,
    # see DISCRIMINATION).
    assert count_acceptance_criteria(requirements_md) == 4


def test_count_tasks_reports_total_and_completed_separately(tmp_path: Path) -> None:
    tasks_md = tmp_path / "tasks.md"
    tasks_md.write_text(_TASKS_MD)

    total, completed = count_tasks(tasks_md)

    # 1, 1.1, 1.2, the indented 1.2.1, 2, and the capital-X 3 -- six lines at
    # two different indentation depths, five marked done (all but 1.2). The
    # capital-X line pins `_TASK_LINE`'s `[ xX]`: narrowing it to `[ x]`
    # leaves that line uncounted entirely (total 5), and dropping
    # `match.group(1).lower()` for a bare `== "x"` comparison counts it as
    # not-done (completed 4) -- both confirmed by execution (see
    # DISCRIMINATION).
    assert total == 6
    assert completed == 5


def _spec_dir(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "some-feature"
    spec_dir.mkdir()
    (spec_dir / "requirements.md").write_text(_REQUIREMENTS_MD)
    (spec_dir / "tasks.md").write_text(_TASKS_MD)
    (spec_dir / "spec.json").write_text(
        json.dumps(
            {
                "phase": "implementation",
                "ready_for_implementation": True,
                "approvals": {
                    "requirements": {"generated": True, "approved": False},
                    "design": {"generated": True, "approved": False},
                    "tasks": {"generated": False, "approved": True},
                },
            }
        )
    )
    return spec_dir


def test_build_spec_status_baseline_reads_all_six_approval_booleans_distinctly(
    tmp_path: Path,
) -> None:
    """Each phase's own `(generated, approved)` pair is complementary
    (`(True, False)` or `(False, True)`), so every *intra-phase* field-swap
    -- reading `design.approved` where `design.generated` belongs, or the
    same within `requirements` or `tasks` -- reds. Confirmed by execution
    (see DISCRIMINATION in the status report), not merely by inspection.

    `requirements` and `design` carry the same `(True, False)` pair here
    while `tasks` carries the complementary `(False, True)`, so this
    fixture alone leaves four *same-role, cross-phase* single-line
    mutations undetected: reading `requirements_generated` from `design`'s
    `generated` field instead of its own, the reverse (`design_generated`
    reading from `requirements`), and the same pair of directions for
    `approved` (`requirements_approved`/`design_approved`). Every other
    same-role cross-phase swap involves `tasks` and reds against this
    fixture.

    The sibling test below,
    `test_load_spec_approvals_catches_the_cross_phase_tie_this_fixture_misses`,
    uses a second `spec.json` arrangement whose tie falls on `design`/`tasks`
    instead, which reds all four mutations this fixture misses (confirmed
    by execution -- see DISCRIMINATION). Between the two fixtures, all
    twelve same-role cross-phase mutations red.
    """
    spec_dir = _spec_dir(tmp_path)

    baseline = build_spec_status_baseline("some-feature", spec_dir)

    assert baseline.feature == "some-feature"
    assert baseline.requirement_count == 3
    assert baseline.criterion_count == 4
    assert baseline.total_task_count == 6
    assert baseline.completed_task_count == 5
    assert baseline.approvals == SpecApprovals(
        requirements_generated=True,
        requirements_approved=False,
        design_generated=True,
        design_approved=False,
        tasks_generated=False,
        tasks_approved=True,
    )
    assert baseline.phase == "implementation"
    assert baseline.ready_for_implementation is True


def test_load_spec_approvals_catches_the_cross_phase_tie_this_fixture_misses(
    tmp_path: Path,
) -> None:
    """Companion to the test above: here `design` and `tasks` share the same
    `(True, False)` pair while `requirements` carries the complementary
    `(False, True)`. This reds the four same-role cross-phase mutations the
    other fixture's `requirements`/`design` tie leaves undetected --
    `requirements_generated`/`design_generated` and
    `requirements_approved`/`design_approved`, both directions each --
    confirmed by execution (see DISCRIMINATION). The blind spot of *this*
    fixture is the complementary set, the `design`/`tasks` swaps, which the
    other fixture reds. Between the two fixtures, all twelve same-role
    cross-phase mutations red; no single fixture can do this alone, since
    two boolean values and three phases sharing each field name force at
    least one tie per field (pigeonhole)."""
    spec_json = tmp_path / "spec.json"
    spec_json.write_text(
        json.dumps(
            {
                "phase": "implementation",
                "ready_for_implementation": True,
                "approvals": {
                    "requirements": {"generated": False, "approved": True},
                    "design": {"generated": True, "approved": False},
                    "tasks": {"generated": True, "approved": False},
                },
            }
        )
    )

    approvals, phase, ready_for_implementation = load_spec_approvals(spec_json)

    assert approvals == SpecApprovals(
        requirements_generated=False,
        requirements_approved=True,
        design_generated=True,
        design_approved=False,
        tasks_generated=True,
        tasks_approved=False,
    )
    assert phase == "implementation"
    assert ready_for_implementation is True


def test_write_spec_status_baseline_round_trips_through_json(tmp_path: Path) -> None:
    spec_dir = _spec_dir(tmp_path)
    baseline = build_spec_status_baseline("some-feature", spec_dir)
    out = tmp_path / "scratch" / "spec-status-baseline.json"

    write_spec_status_baseline(baseline, out)

    written = json.loads(out.read_text())
    assert written["requirement_count"] == 3
    assert written["criterion_count"] == 4
    assert written["total_task_count"] == 6
    assert written["completed_task_count"] == 5
    assert written["approvals"]["requirements_approved"] is False
    assert written["approvals"]["tasks_approved"] is True


def test_load_spec_approvals_reads_absent_phase_and_readiness_as_none(
    tmp_path: Path,
) -> None:
    """`phase` and `ready_for_implementation` are read with `.get`, so a
    `spec.json` missing either reads `None` rather than a fabricated
    default -- but only those two fields have that behaviour; a missing
    approvals key raises instead (see the sibling test below), and the
    docstring is narrowed to name only the two fields it actually
    describes."""
    spec_json = tmp_path / "spec.json"
    spec_json.write_text(
        json.dumps(
            {
                "approvals": {
                    "requirements": {"generated": True, "approved": False},
                    "design": {"generated": True, "approved": False},
                    "tasks": {"generated": False, "approved": True},
                }
            }
        )
    )

    approvals, phase, ready_for_implementation = load_spec_approvals(spec_json)

    assert phase is None
    assert ready_for_implementation is None
    assert approvals.requirements_generated is True


def test_load_spec_approvals_raises_on_a_missing_approvals_key(
    tmp_path: Path,
) -> None:
    """Unlike `phase`/`ready_for_implementation`, a missing approvals entry
    is not read as `None` -- it raises `KeyError`, because a fabricated
    `False` there would misreport the spec's actual approval state."""
    spec_json = tmp_path / "spec.json"
    spec_json.write_text(
        json.dumps(
            {
                "phase": "implementation",
                "ready_for_implementation": True,
                "approvals": {
                    "requirements": {"generated": True, "approved": False},
                    "design": {"generated": True, "approved": False},
                    # "tasks" is missing entirely.
                },
            }
        )
    )

    with pytest.raises(KeyError):
        load_spec_approvals(spec_json)


def _init_repo_with_two_commits(tmp_path: Path) -> tuple[Path, str]:
    """A repo with a base commit, a later commit that moves `HEAD`, and a
    dirtied working tree on top -- three distinct contents, so a CLI command
    reading the wrong one of the three is its own reachable, distinguishable
    wrong answer."""
    repo = _repo(tmp_path)
    (repo / "alpha.txt").write_text("original content\n")
    _git(repo, "add", "alpha.txt")
    _git(repo, "commit", "-q", "-m", "original")
    base_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "alpha.txt").write_text("second commit content\n")
    _git(repo, "add", "alpha.txt")
    _git(repo, "commit", "-q", "-m", "second")
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() != base_commit

    (repo / "alpha.txt").write_text("edited after the second commit\n")
    return repo, base_commit


def test_manifest_tree_subcommand_writes_the_named_commit_not_head(
    tmp_path: Path,
) -> None:
    repo, base_commit = _init_repo_with_two_commits(tmp_path)
    out = tmp_path / "scratch" / "M0.tsv"
    # Deliberately abbreviated, so a "record the commit-ish verbatim, do not
    # resolve it" mutant is its own reachable, distinguishable wrong answer:
    # the short form is not even the right length for a durable record.
    abbreviated_commit = base_commit[:8]
    assert abbreviated_commit != base_commit

    result = runner.invoke(
        app,
        [
            "tree",
            abbreviated_commit,
            "--out",
            str(out),
            "--repo-root",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert len(lines) == 1
    path, mode, blob = lines[0].split("\t")
    assert path == "alpha.txt"
    assert blob == _blob_sha(repo, "original content\n")
    assert blob != _blob_sha(repo, "second commit content\n")
    assert blob != _blob_sha(repo, "edited after the second commit\n")

    # The sibling meta file records the full resolved commit id, not the
    # abbreviated form given on the command line (which will not still name
    # anything once the base commit itself has ceased to exist) and not HEAD
    # (which has since moved).
    meta = json.loads((tmp_path / "scratch" / "M0.tsv.meta.json").read_text())
    assert meta["commit"] == base_commit
    assert len(meta["commit"]) == 40


def test_resolve_commit_resolves_an_abbreviated_commit_to_its_full_id(
    tmp_path: Path,
) -> None:
    from scripts.purge.manifest import resolve_commit

    repo = _repo(tmp_path)
    (repo / "alpha.txt").write_text("content\n")
    _git(repo, "add", "alpha.txt")
    _git(repo, "commit", "-q", "-m", "one")
    full = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert resolve_commit(full[:8], repo) == full
    assert resolve_commit("HEAD", repo) == full


def test_manifest_spec_status_subcommand_writes_the_baseline_file(
    tmp_path: Path,
) -> None:
    _spec_dir(tmp_path)
    out = tmp_path / "scratch" / "spec-status-baseline.json"

    result = runner.invoke(
        app,
        [
            "spec-status",
            "some-feature",
            "--out",
            str(out),
            "--specs-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    written = json.loads(out.read_text())
    assert written["feature"] == "some-feature"
    assert written["requirement_count"] == 3
    assert written["criterion_count"] == 4
    assert written["total_task_count"] == 6
    assert written["completed_task_count"] == 5
