"""`scripts/purge/adopt.py`: `HistoryReplacement`'s asserted carry-over
checklist, the identity precondition and the scratch-to-target move (task
7.3, design.md `#### HistoryReplacement`, Req 5.3, 7.3, 11.13).

Every fixture here builds synthetic paths under `tmp_path` and a synthetic
git repository with `git init`, except
`test_assert_carry_over_treats_a_blank_path_as_missing`, which deliberately
uses `Path("")` -- the process cwd -- to exercise the blank-path guard, and
takes an unused `tmp_path` parameter only for fixture-signature consistency
with its neighbours. `assert_commit_identity`'s tests never touch the real
machine-wide global git config: they override `GIT_CONFIG_GLOBAL` to point
at a scratch file under `tmp_path` instead.
"""

from __future__ import annotations

import ast
import inspect
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.purge.adopt import (
    _AGENT_LOG_NAME,
    AdoptionError,
    CarryOverError,
    CarryOverItem,
    IdentityError,
    _content_digest,
    assert_carry_over,
    assert_commit_identity,
    build_checklist,
    move_clone,
)


def _reported_names(error: BaseException) -> list[str]:
    """Parse the item names out of a `CarryOverError`'s "unaccepted
    item(s):" message, so tests can assert exactly which names were reported
    without relying on substring containment (several item names are
    substrings of one another, e.g. "shared agent log" is a substring of
    "root symlink to the shared agent log"). Each entry opens with the fixed
    "\\n  - " marker and carries its name on that first line and its reason
    on the next -- item names contain both ": " and parentheses, so only the
    line break separates the two unambiguously."""
    return [entry.splitlines()[0] for entry in str(error).split("\n  - ")[1:]]


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    """A generic doomed-root/destination-root pair for `assert_carry_over`'s
    own tests, independent of any particular checklist item's real-world
    shape: a *doomed* source root and a destination root a caller-built
    `CarryOverItem` might point at. Siblings under `tmp_path`, so neither
    contains the other."""
    source_root = tmp_path / "source-repo"
    clone_root = tmp_path / "clone"
    source_root.mkdir()
    clone_root.mkdir()
    return source_root, clone_root


def _is_within_for_test(path: Path, root: Path) -> bool:
    """Whether `path` lies inside `root`, derived independently of
    `adopt._is_within` (which uses `Path.is_relative_to`): a precondition
    assertion that called the code under test could not disagree with it.
    `os.path.commonpath` over both resolved paths answers the same question
    by a different route."""
    resolved_root = str(root.resolve())
    return os.path.commonpath([str(path.resolve()), resolved_root]) == resolved_root


def _copy_across(source: Path, destination: Path) -> Path:
    """Copy `source` to `destination` the way the `HistoryReplacement`
    carry-over step must: **copy**, so the source is still intact when the
    checklist is asserted against it, never move -- and with
    `symlinks=True`, preserving links rather than dereferencing them, which
    is what `adopt._content_digest` compares inside a directory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)
    return destination


def _filesystem_folds_case(root: Path) -> bool:
    """Whether the filesystem under `root` treats two spellings differing
    only in case as the same name -- probed, never assumed, because the
    answer differs between this repository's own machine (macOS, folding)
    and a Linux CI filesystem (not folding)."""
    probe = root / "CaseProbe"
    probe.mkdir()
    return (root / "caseprobe").exists()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "alpha.txt").write_text("first commit content\n")
    _git(root, "add", "alpha.txt")
    _git(root, "commit", "-q", "-m", "initial")
    return root


# ---------------------------------------------------------------------------
# assert_carry_over
# ---------------------------------------------------------------------------


def test_assert_carry_over_passes_when_every_item_is_at_the_destination(
    tmp_path: Path,
) -> None:
    """The positive case, with both item classes present: a carried file, a
    carried directory, and an artifact preserved in place outside both
    roots."""
    source_root, clone_root = _roots(tmp_path)
    (source_root / "a.txt").write_text("present\n")
    (source_root / "corpus").mkdir()
    (source_root / "corpus" / "one.fit").write_bytes(b"\x00binary\n")
    preserved = tmp_path / "scratch" / "artifact.tsv"
    preserved.parent.mkdir()
    preserved.write_text("row\n")
    _copy_across(source_root / "a.txt", clone_root / "a.txt")
    _copy_across(source_root / "corpus", clone_root / "corpus")

    assert_carry_over(
        (
            CarryOverItem(
                name="item-a",
                path=clone_root / "a.txt",
                source=source_root / "a.txt",
            ),
            CarryOverItem(
                name="item-corpus",
                path=clone_root / "corpus",
                source=source_root / "corpus",
            ),
            CarryOverItem(name="item-preserved", path=preserved),
        ),
        doomed_root=source_root,
    )  # must not raise


def test_assert_carry_over_rejects_a_checklist_pointed_at_the_doomed_root(
    tmp_path: Path,
) -> None:
    """**The queue item's defect, as a regression test**
    (`.kiro/queue/2026-08-09-adopt-checklist-can-destroy-carried-material`).
    Every item's path is the file at the *source* root -- the directory 7.4
    is about to destroy. The precondition assertions establish that the old
    `Path.exists()` implementation passed this exact fixture: all three
    paths do exist at the moment of the check. They are then deleted."""
    source_root, _clone_root = _roots(tmp_path)
    doomed_log = source_root / "agent-log"
    doomed_data = source_root / "data"
    doomed_workbook = source_root / "source-material.bin"
    doomed_log.write_text("2020-01-01T00:00:00Z\tp\tCLAIM\tx\n")
    doomed_data.mkdir()
    (doomed_data / "one.fit").write_bytes(b"\x00fit\n")
    doomed_workbook.write_bytes(b"\x00workbook\n")
    # The false positive, stated as a fact about the fixture rather than
    # assumed: an existence-only checklist accepts every one of these.
    assert doomed_log.exists()
    assert doomed_data.exists()
    assert doomed_workbook.exists()

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (
                CarryOverItem(name="doomed-log", path=doomed_log, source=doomed_log),
                CarryOverItem(name="doomed-data", path=doomed_data, source=doomed_data),
                CarryOverItem(
                    name="doomed-workbook",
                    path=doomed_workbook,
                    source=doomed_workbook,
                ),
            ),
            doomed_root=source_root,
        )

    assert sorted(_reported_names(excinfo.value)) == [
        "doomed-data",
        "doomed-log",
        "doomed-workbook",
    ]
    assert "about to be destroyed" in str(excinfo.value)


def test_assert_carry_over_rejects_a_preserved_item_inside_the_doomed_root(
    tmp_path: Path,
) -> None:
    """The same defect for the other item class: a one-shot artifact that
    happens to live inside the repository directory is not preserved by
    existing, it is destroyed with it. Only the doomed one is named."""
    source_root, _clone_root = _roots(tmp_path)
    inside = source_root / "artifact-inside.tsv"
    inside.write_text("row\n")
    outside = tmp_path / "artifact-outside.tsv"
    outside.write_text("row\n")

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (
                CarryOverItem(name="artifact-outside", path=outside),
                CarryOverItem(name="artifact-inside", path=inside),
            ),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["artifact-inside"]


@pytest.mark.parametrize("spelling", ["symlink-into-doomed", "dot-dot-into-doomed"])
def test_assert_carry_over_resolves_a_preserved_destination_before_containment(
    tmp_path: Path, spelling: str
) -> None:
    """**The destination side of `_is_within` must be resolved, and for a
    preserved-in-place item that resolution is the only guard there is** --
    `source is None`, so `samefile` and the content digest never run.

    Two spellings that land inside the doomed root without naming it
    literally: a symlink in the clone whose target is the doomed file, and a
    `../`-spelled path. Both `is_relative_to` as written (a pure
    path-component comparison against the unresolved path) reads as outside
    the doomed root, which is why the precondition below asserts the
    unresolved spelling really does look outside -- otherwise this fixture
    would pass for the wrong reason."""
    source_root, clone_root = _roots(tmp_path)
    doomed_artifact = source_root / "artifact.tsv"
    doomed_artifact.write_text("row\n")
    if spelling == "symlink-into-doomed":
        destination = clone_root / "artifact-link.tsv"
        destination.symlink_to(doomed_artifact)
    else:
        destination = clone_root / ".." / source_root.name / "artifact.tsv"

    # Unresolved, this path does not look like it is inside the doomed root;
    # resolved, it is. That gap is the whole point of the test.
    assert not Path(*destination.parts).is_relative_to(source_root)
    assert _is_within_for_test(destination, source_root)

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="preserved-artifact", path=destination),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["preserved-artifact"]
    assert "about to be destroyed" in str(excinfo.value)


def test_assert_carry_over_folds_case_the_way_the_filesystem_does(
    tmp_path: Path,
) -> None:
    """On a case-folding filesystem -- which is what this repository sits on
    -- a doomed root spelled `Source-Repo` and a destination spelled
    `source-repo/...` name the same directory to the operating system, while
    `Path.is_relative_to` compares path components and says they do not.
    The item would be accepted and then deleted with the directory.

    The fold is **probed, not assumed**: on a case-sensitive filesystem the
    two spellings really are different directories, there is no false pass
    to close, and this test skips with that said rather than passing
    vacuously."""
    if not _filesystem_folds_case(tmp_path):
        pytest.skip(
            "filesystem under tmp_path is case-sensitive; the case-folding "
            "false pass this test pins cannot arise here"
        )
    doomed_root = tmp_path / "Source-Repo"
    doomed_root.mkdir()
    (doomed_root / "artifact.tsv").write_text("row\n")
    folded = tmp_path / "source-repo" / "artifact.tsv"
    # The filesystem says this is the same file; a component comparison does not.
    assert folded.exists()
    assert not folded.is_relative_to(doomed_root)

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="case-folded-artifact", path=folded),),
            doomed_root=doomed_root,
        )

    assert _reported_names(excinfo.value) == ["case-folded-artifact"]


def test_assert_carry_over_rejects_a_carried_item_with_a_blank_source(
    tmp_path: Path,
) -> None:
    """`Path("")` normalises to `Path('.')` on the source side too, where it
    would make the digest comparison read the process working directory
    instead of the material. A blank source means nothing was proven, so it
    is a failure rather than a satisfied item."""
    source_root, clone_root = _roots(tmp_path)
    destination = clone_root / "workbook.bin"
    destination.write_bytes(b"\x00workbook\n")

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (
                CarryOverItem(
                    name="blank-source-workbook", path=destination, source=Path("")
                ),
            ),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["blank-source-workbook"]
    assert "blank source path" in str(excinfo.value)


def test_assert_carry_over_rejects_a_destination_that_is_the_same_file(
    tmp_path: Path,
) -> None:
    """A destination outside the doomed root that is nonetheless the *same
    file* as its source -- a hard link, which every containment check
    accepts because its path really is outside. `Path.samefile` is what
    catches it, and without it the source's deletion would take the
    "carried" copy's only inode with it."""
    source_root, clone_root = _roots(tmp_path)
    source = source_root / "workbook.bin"
    source.write_bytes(b"\x00workbook\n")
    destination = clone_root / "workbook.bin"
    os.link(source, destination)
    assert not _is_within_for_test(destination, source_root)
    assert destination.exists()

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (
                CarryOverItem(
                    name="hardlinked-workbook", path=destination, source=source
                ),
            ),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["hardlinked-workbook"]
    assert "same file" in str(excinfo.value)


def test_assert_carry_over_rejects_a_same_named_destination_with_other_content(
    tmp_path: Path,
) -> None:
    """Existence at the destination is not enough either: an empty
    placeholder created by a half-finished copy exists, is outside the
    doomed root, and is not the same file -- and is still not the material.
    Only the content comparison rejects it."""
    source_root, clone_root = _roots(tmp_path)
    source = source_root / "workbook.bin"
    source.write_bytes(b"\x00workbook contents\n")
    placeholder = clone_root / "workbook.bin"
    placeholder.write_bytes(b"")

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="workbook", path=placeholder, source=source),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["workbook"]
    assert "differs from the source" in str(excinfo.value)


@pytest.mark.parametrize(
    ("damage", "corrupted_bytes"),
    [("truncated-to-zero-length", b""), ("silently-altered", b"\x00NOT one\n")],
)
def test_assert_carry_over_rejects_a_carried_directory_whose_entry_content_changed(
    tmp_path: Path, damage: str, corrupted_bytes: bytes
) -> None:
    """**The realistic `data/` failure, and the one a name-only digest
    misses.** An interrupted `cp -R`/`rsync` leaves every filename present
    with one file truncated to zero length or half-written; every entry name
    still matches, the entry count still matches, and the directory still
    exists. Only the digest's *content* component -- `entry.read_bytes()` --
    can tell those apart from a complete copy, and this is the fixture that
    pins it: both damage shapes are checked, because zero-length is the
    plausible interruption and a same-length-different-bytes edit is the
    plausible silent corruption.

    The assertions below establish that nothing *else* about the fixture
    could be doing the rejecting: the entry names are identical on both
    sides and the counts match."""
    source_root, clone_root = _roots(tmp_path)
    source = source_root / "data"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "one.fit").write_bytes(b"\x00one\n")
    (source / "two.fit").write_bytes(b"\x00two\n")
    destination = _copy_across(source, clone_root / "data")
    (destination / "nested" / "one.fit").write_bytes(corrupted_bytes)

    source_names = sorted(str(p.relative_to(source)) for p in source.rglob("*"))
    destination_names = sorted(
        str(p.relative_to(destination)) for p in destination.rglob("*")
    )
    assert source_names == destination_names, damage

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="data-corpus", path=destination, source=source),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["data-corpus"]
    assert "differs from the source" in str(excinfo.value)


def test_content_digest_distinguishes_an_empty_directory_from_a_zero_byte_file(
    tmp_path: Path,
) -> None:
    """The `dir:`/`file:` kind prefix, pinned rather than assumed to matter.
    Both hash to sha256's empty digest -- measured below as an explicit
    precondition -- so without the prefix a carried directory emptied by a
    failed copy would compare equal to a zero-byte file of the same name,
    and vice versa. The prefix is the only thing separating them."""
    empty_file = tmp_path / "empty-file"
    empty_file.write_bytes(b"")
    empty_dir = tmp_path / "empty-dir"
    empty_dir.mkdir()

    file_digest = _content_digest(empty_file)
    dir_digest = _content_digest(empty_dir)

    # The hash halves really are identical -- so the prefix is doing all the
    # work here, not incidentally agreeing with a difference elsewhere.
    assert file_digest.split(":", 1)[1] == dir_digest.split(":", 1)[1]
    assert file_digest != dir_digest


def test_assert_carry_over_rejects_a_carried_directory_whose_symlink_target_changed(
    tmp_path: Path,
) -> None:
    """A symlinked subdirectory used to digest as a contentless `dir` entry,
    because `is_dir()` follows the link while `rglob` does not descend into
    it -- so two trees whose links pointed at different directories, holding
    different content, digested identically. Entries that are symlinks now
    digest as their link target text. The precondition assertion records
    that both sides still have the same entry names."""
    source_root, clone_root = _roots(tmp_path)
    first_target = tmp_path / "first-target"
    second_target = tmp_path / "second-target"
    first_target.mkdir()
    second_target.mkdir()
    (first_target / "payload.bin").write_bytes(b"\x00first\n")
    (second_target / "payload.bin").write_bytes(b"\x00second, different\n")
    source = source_root / "data"
    source.mkdir()
    (source / "linked").symlink_to(first_target)
    destination = clone_root / "data"
    destination.mkdir()
    (destination / "linked").symlink_to(second_target)
    assert sorted(p.name for p in source.iterdir()) == sorted(
        p.name for p in destination.iterdir()
    )

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="data-corpus", path=destination, source=source),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["data-corpus"]


def test_assert_carry_over_rejects_a_carried_directory_linking_into_the_doomed_root(
    tmp_path: Path,
) -> None:
    """A link inside a carried tree pointing back at the repository about to
    be destroyed. The digest cannot catch this one -- source and destination
    agree exactly, which is the whole problem -- and the containment check
    is about the item's own path, so the tree's contents need their own
    check. The equal-digest precondition is asserted rather than assumed."""
    source_root, clone_root = _roots(tmp_path)
    (source_root / "inside.txt").write_text("lives in the doomed root\n")
    source = source_root / "data"
    source.mkdir()
    (source / "one.fit").write_bytes(b"\x00one\n")
    (source / "back-link").symlink_to(source_root / "inside.txt")
    destination = _copy_across(source, clone_root / "data")
    assert _content_digest(source) == _content_digest(destination)

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="data-corpus", path=destination, source=source),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["data-corpus"]
    assert "will dangle" in str(excinfo.value)


def test_assert_carry_over_rejects_a_carried_directory_missing_one_entry(
    tmp_path: Path,
) -> None:
    """`data/` is 3.5 MB of real activity files, and a partial copy is the
    realistic failure. A directory whose top level matches but which is
    missing one nested file must be rejected -- which is why the digest
    covers every entry's relative path and content, not the directory's own
    existence."""
    source_root, clone_root = _roots(tmp_path)
    source = source_root / "data"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "one.fit").write_bytes(b"\x00one\n")
    (source / "two.fit").write_bytes(b"\x00two\n")
    destination = _copy_across(source, clone_root / "data")
    (destination / "nested" / "one.fit").unlink()

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="data-corpus", path=destination, source=source),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["data-corpus"]


def test_assert_carry_over_accepts_a_carried_directory_copied_whole(
    tmp_path: Path,
) -> None:
    """Falsity check for the digest: the same nested fixture, copied
    completely, must pass -- so the rejection above is about the missing
    entry and not about directories being rejected on principle."""
    source_root, clone_root = _roots(tmp_path)
    source = source_root / "data"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "one.fit").write_bytes(b"\x00one\n")
    (source / "two.fit").write_bytes(b"\x00two\n")
    destination = _copy_across(source, clone_root / "data")

    assert_carry_over(
        (CarryOverItem(name="data-corpus", path=destination, source=source),),
        doomed_root=source_root,
    )  # must not raise


def test_assert_carry_over_rejects_a_carried_item_whose_source_is_already_gone(
    tmp_path: Path,
) -> None:
    """Copy, assert, then vacate -- in that order. If the material was
    *moved* rather than copied, the source is gone and nothing at the
    destination has been verified against anything; that must halt rather
    than pass on the destination's mere existence."""
    source_root, clone_root = _roots(tmp_path)
    source = source_root / "workbook.bin"
    source.write_bytes(b"\x00workbook\n")
    destination = _copy_across(source, clone_root / "workbook.bin")
    source.unlink()

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="moved-workbook", path=destination, source=source),),
            doomed_root=source_root,
        )

    assert _reported_names(excinfo.value) == ["moved-workbook"]
    assert "copy, assert, then vacate" in str(excinfo.value)


def test_assert_carry_over_accepts_two_symlinks_with_different_targets(
    tmp_path: Path,
) -> None:
    """The root `agent-log` symlink, specifically. The carried link must
    point at the *clone's* git directory, so the two links' targets differ
    by design; what has to match is the log content they resolve to. A
    comparison of link targets would red this; following the link is what
    makes it pass."""
    source_root, clone_root = _roots(tmp_path)
    source_git_dir = tmp_path / "source-git-dir"
    clone_git_dir = tmp_path / "clone-git-dir"
    source_git_dir.mkdir()
    clone_git_dir.mkdir()
    log_text = "2020-01-01T00:00:00Z\tp\tCLAIM\tx\n"
    (source_git_dir / "agent-log").write_text(log_text)
    (clone_git_dir / "agent-log").write_text(log_text)
    (source_root / "agent-log").symlink_to(source_git_dir / "agent-log")
    (clone_root / "agent-log").symlink_to(clone_git_dir / "agent-log")
    assert (source_root / "agent-log").readlink() != (
        clone_root / "agent-log"
    ).readlink()

    assert_carry_over(
        (
            CarryOverItem(
                name="root symlink",
                path=clone_root / "agent-log",
                source=source_root / "agent-log",
            ),
        ),
        doomed_root=source_root,
    )  # must not raise


def test_assert_carry_over_names_every_unaccepted_item_not_only_the_first(
    tmp_path: Path,
) -> None:
    """A loop over the checklist does not, by itself, pin the whole
    collection: an implementation that stops at the first unaccepted item
    would still pass a fixture with only one. Two unaccepted items,
    non-adjacent (an accepted item sits between them), and an independent
    count anchor on the *number of names actually reported* -- not a
    substring count in the message, which a fixture whose item names happen
    to contain that substring cannot distinguish from a first-only
    implementation. The two failures also have *different* reasons (one
    absent, one content mismatch) so a report that collapses to a single
    reason is caught too."""
    source_root, clone_root = _roots(tmp_path)
    (source_root / "present.txt").write_text("present\n")
    _copy_across(source_root / "present.txt", clone_root / "present.txt")
    (source_root / "alpha.txt").write_text("alpha\n")
    (source_root / "omega.txt").write_text("omega\n")
    (clone_root / "omega.txt").write_text("not omega\n")

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (
                CarryOverItem(
                    name="alpha-absent",
                    path=clone_root / "alpha.txt",
                    source=source_root / "alpha.txt",
                ),
                CarryOverItem(
                    name="middle-present",
                    path=clone_root / "present.txt",
                    source=source_root / "present.txt",
                ),
                CarryOverItem(
                    name="omega-differing",
                    path=clone_root / "omega.txt",
                    source=source_root / "omega.txt",
                ),
            ),
            doomed_root=source_root,
        )

    reported = _reported_names(excinfo.value)
    assert "alpha-absent" in reported
    assert "omega-differing" in reported
    assert len(reported) == 2


def test_assert_carry_over_raises_on_an_empty_item_sequence(tmp_path: Path) -> None:
    """`assert_carry_over(())` must never be a silent pass over zero items --
    the exact defeat the module's own docstring previously (and falsely)
    claimed could not happen: `missing` computed over an empty sequence is
    empty, is falsy, and the old implementation returned `None`."""
    with pytest.raises(CarryOverError, match="zero items"):
        assert_carry_over((), doomed_root=tmp_path)


def test_assert_carry_over_requires_the_doomed_root_by_keyword(
    tmp_path: Path,
) -> None:
    """`doomed_root` is keyword-only and has no default: a caller cannot
    omit it, and cannot supply it positionally where a `Sequence` is
    expected. Both defeats are checked, because "keyword-only" and
    "non-defaultable" are two different guarantees."""
    source_root, clone_root = _roots(tmp_path)
    (clone_root / "a.txt").write_text("a\n")
    items = (CarryOverItem(name="item-a", path=clone_root / "a.txt"),)

    with pytest.raises(TypeError):
        assert_carry_over(items)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        assert_carry_over(items, source_root)  # type: ignore[call-arg]


def test_carry_over_item_requires_keyword_arguments(tmp_path: Path) -> None:
    """`path` and `source` are two `Path` fields whose transposition is the
    mistake the whole checklist exists to catch, so the dataclass is
    `kw_only`: a positional construction must not be accepted at all."""
    with pytest.raises(TypeError):
        CarryOverItem("item", tmp_path / "a", tmp_path / "b")  # type: ignore[call-arg]


def test_assert_carry_over_treats_a_blank_path_as_missing(tmp_path: Path) -> None:
    """`Path("")` normalises to `Path('.')`, and `Path('.').exists()` is
    always `True` -- confirm the precondition is false first (a naive
    `.exists()`-only check would pass this fixture), then confirm the guard
    rejects it as missing rather than present."""
    blank_item = CarryOverItem(name="blank-path-item", path=Path(""))
    assert blank_item.path.exists()  # the naive check would wrongly pass

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over((blank_item,), doomed_root=tmp_path / "doomed")

    assert "blank-path-item" in _reported_names(excinfo.value)


def test_assert_carry_over_treats_a_dangling_symlink_as_missing(
    tmp_path: Path,
) -> None:
    """The root `agent-log` symlink case: a symlink that exists as a link
    but resolves to nothing must count as missing, the same as an absent
    file -- `Path.exists()` follows the link."""
    source_root, clone_root = _roots(tmp_path)
    target = clone_root / "nonexistent-target"
    link = clone_root / "dangling-link"
    link.symlink_to(target)
    assert not target.exists()

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(
            (CarryOverItem(name="dangling-symlink-item", path=link),),
            doomed_root=source_root,
        )

    assert "dangling-symlink-item" in str(excinfo.value)


# ---------------------------------------------------------------------------
# build_checklist -- re-scoped to the .git-resident items (task 7.3,
# design.md `#### HistoryReplacement` step 6, Decision 7 constraint 4)
# ---------------------------------------------------------------------------


def _real_git_dir(tmp_path: Path, name: str = "repo") -> Path:
    """A genuine `.git` directory -- via a real `git init`, a commit and a
    `git gc`, using the same `_repo`/`_git` helpers the rest of this file
    already uses -- so the "standard git furniture" fixtures are measured
    against what git actually creates rather than a hand-typed guess."""
    repo = _repo(tmp_path, name)
    _git(repo, "gc", "-q")
    return repo / ".git"


def _write_agent_log(
    git_dir: Path, text: str = "2020-01-01T00:00:00Z\tp\tCLAIM\tx\n"
) -> Path:
    log = git_dir / _AGENT_LOG_NAME
    log.write_text(text)
    return log


def test_build_checklist_lists_the_shared_agent_log_first(tmp_path: Path) -> None:
    """The one item Decision 7 names explicitly: always built, first in the
    checklist, carried from the old `.git` to the fresh one -- present or
    not, the same "always checked, never conditional" posture the retired
    `CloneAdoption` checklist already applied to this same item."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)

    checklist = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    assert checklist[0] == CarryOverItem(
        name="shared agent log",
        path=clone_git_dir / _AGENT_LOG_NAME,
        source=old_git_dir / _AGENT_LOG_NAME,
    )


def test_build_checklist_lists_the_agent_log_even_when_absent(tmp_path: Path) -> None:
    """ "Always checked, never conditional" means the item is built whether
    or not `old_git_dir` actually carries an `agent-log` entry -- the same
    posture the retired `CloneAdoption` checklist already applied. `build_checklist`
    must not silently omit the item just because there is nothing there yet;
    `assert_carry_over` is what turns the absence into a failure."""
    old_git_dir = _real_git_dir(tmp_path, "old")  # no agent-log written
    clone_git_dir = _real_git_dir(tmp_path, "clone")

    checklist = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    assert len(checklist) == 1
    assert checklist[0].name == "shared agent log"
    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(checklist, doomed_root=old_git_dir)
    assert "shared agent log" in _reported_names(excinfo.value)


def test_build_checklist_ignores_standard_git_furniture(tmp_path: Path) -> None:
    """A genuine `.git` directory as `git init` + a commit + `gc` actually
    leaves it (COMMIT_EDITMSG, config, description, HEAD, hooks, index,
    info, logs, objects, packed-refs, refs -- measured, not assumed), plus
    ORIG_HEAD, FETCH_HEAD and worktrees/ added by hand: every one of these
    entries this repository's own primary `.git` genuinely carries right
    now. None of it is foreign, so none of it may appear in the checklist or
    halt the build."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)
    (old_git_dir / "ORIG_HEAD").write_text("0" * 40 + "\n")
    (old_git_dir / "FETCH_HEAD").write_text("")
    (old_git_dir / "worktrees" / "some-worktree").mkdir(parents=True)

    checklist = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    assert len(checklist) == 1
    assert checklist[0].name == "shared agent log"


def test_build_checklist_ignores_lost_found(tmp_path: Path) -> None:
    """`.git/lost-found/` -- real `.fit` activity files a past `fsck`
    extracted -- is deliberately not carried: the archive keeps it whole,
    and it must neither appear in the checklist nor halt the build."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)
    lost_found_entry = old_git_dir / "lost-found" / "commit" / "deadbeef"
    lost_found_entry.parent.mkdir(parents=True)
    lost_found_entry.write_bytes(b"\x00recovered activity\n")

    checklist = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    assert len(checklist) == 1
    assert checklist[0].name == "shared agent log"


def test_build_checklist_halts_on_a_foreign_entry_no_item_anticipates(
    tmp_path: Path,
) -> None:
    """The measured case, not a hypothetical one: this very repository's own
    primary `.git` (`$(git rev-parse --git-common-dir)`) carries
    `sha-rewrite-map-2026-07-26.tsv`, a scratch artifact left directly in the
    git directory by the retired rewrite machinery -- genuinely foreign,
    genuinely present, and exactly the shape this enumeration exists to
    catch rather than silently leave behind. The precondition establishes
    that the same fixture, minus this one file, builds cleanly -- so nothing
    else in the fixture is what raises."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)
    precondition = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)
    assert len(precondition) == 1

    (old_git_dir / "sha-rewrite-map-2026-07-26.tsv").write_text("old\tnew\n")

    with pytest.raises(CarryOverError) as excinfo:
        build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    assert "sha-rewrite-map-2026-07-26.tsv" in str(excinfo.value)


def test_build_checklist_names_every_foreign_entry_not_only_the_first(
    tmp_path: Path,
) -> None:
    """A loop over the enumerated entries does not, by itself, pin the whole
    collection: an implementation that halts on the first foreign entry
    would still pass a fixture with only one. Two foreign entries, and an
    independent check that both names surface in the halt message."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)
    (old_git_dir / "alpha-foreign.tsv").write_text("x\n")
    (old_git_dir / "zulu-foreign.tsv").write_text("x\n")

    with pytest.raises(CarryOverError) as excinfo:
        build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    message = str(excinfo.value)
    assert "alpha-foreign.tsv" in message
    assert "zulu-foreign.tsv" in message


def test_build_checklist_refuses_the_old_git_dir_as_the_clone_git_dir(
    tmp_path: Path,
) -> None:
    """Handing the same `.git` directory twice is the single mistake that
    destroys the material: every item would then be built against the
    directory the swap archives. The fixture is otherwise entirely valid --
    the agent log genuinely exists -- so nothing but the two paths being the
    same directory can be what raises."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    _write_agent_log(old_git_dir)

    with pytest.raises(CarryOverError, match="non-nested"):
        build_checklist(clone_git_dir=old_git_dir, old_git_dir=old_git_dir)


@pytest.mark.parametrize("nesting", ["clone-inside-old", "old-inside-clone"])
def test_build_checklist_refuses_nested_git_dirs(tmp_path: Path, nesting: str) -> None:
    """Distinct paths are not enough: a fresh `.git` nested inside the old
    one is archived with it, and an old `.git` nested inside the fresh one
    cannot be archived without taking the fresh one too."""
    if nesting == "clone-inside-old":
        old_git_dir = _real_git_dir(tmp_path, "old")
        _write_agent_log(old_git_dir)
        clone_git_dir = old_git_dir / "nested-clone"
        clone_git_dir.mkdir()
    else:
        clone_git_dir = tmp_path / "outer-clone-git"
        clone_git_dir.mkdir()
        old_git_dir = clone_git_dir / "nested-old"
        old_git_dir.mkdir()
        _write_agent_log(old_git_dir)

    with pytest.raises(CarryOverError, match="non-nested"):
        build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)


@pytest.mark.parametrize("blank_field", ["clone_git_dir", "old_git_dir"])
def test_build_checklist_raises_on_a_blank_git_dir(
    tmp_path: Path, blank_field: str
) -> None:
    """`Path("")` normalises to `Path('.')`, whose containment check against
    the other (real) directory is meaningless -- a blank path must be
    refused explicitly rather than silently compared. The message is
    asserted to name the blank-path reason specifically: with `old_git_dir`
    blank, `Path("")` also normalises to the process's real working
    directory, whose own real entries (this very checkout's
    `pyproject.toml`, `scripts/`, ...) are genuinely foreign to
    `_STANDARD_GIT_FURNITURE`, so a mutant that deletes only the blank-path
    guard still raises there -- via the foreign-entry halt over the process
    cwd -- and a bare `pytest.raises(CarryOverError)` could not tell the two
    apart."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)
    kwargs: dict[str, Path] = {
        "clone_git_dir": clone_git_dir,
        "old_git_dir": old_git_dir,
    }
    kwargs[blank_field] = Path("")

    with pytest.raises(CarryOverError, match="blank"):
        build_checklist(**kwargs)


def test_build_checklist_requires_old_git_dir_to_be_a_directory(
    tmp_path: Path,
) -> None:
    """An `old_git_dir` that does not exist cannot be enumerated -- this
    must raise rather than silently building a checklist that never checked
    anything foreign."""
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    missing_old_git_dir = tmp_path / "does-not-exist"

    with pytest.raises(CarryOverError):
        build_checklist(clone_git_dir=clone_git_dir, old_git_dir=missing_old_git_dir)


def test_build_checklist_then_assert_carry_over_passes_when_the_log_is_carried(
    tmp_path: Path,
) -> None:
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    log_source = _write_agent_log(old_git_dir)
    _copy_across(log_source, clone_git_dir / _AGENT_LOG_NAME)

    checklist = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    assert_carry_over(checklist, doomed_root=old_git_dir)  # must not raise


def test_build_checklist_then_assert_carry_over_fails_when_the_log_is_not_carried(
    tmp_path: Path,
) -> None:
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    _write_agent_log(old_git_dir)
    # clone_git_dir carries no agent-log at all

    checklist = build_checklist(clone_git_dir=clone_git_dir, old_git_dir=old_git_dir)

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(checklist, doomed_root=old_git_dir)

    assert _reported_names(excinfo.value) == ["shared agent log"]


def test_full_checklist_passes_against_the_clone_and_fails_against_the_old_git_dir(
    tmp_path: Path,
) -> None:
    """The whole point, end to end, on one fixture: the same log content,
    checked with the fresh `.git` as the destination, passes; checked with
    the doomed old `.git` as the destination -- exactly what a caller who
    mixed up the two paths would produce -- fails, naming the log. The
    precondition establishes the false positive an existence-only check
    would have accepted: the source copy genuinely still exists at the
    moment of the check."""
    old_git_dir = _real_git_dir(tmp_path, "old")
    clone_git_dir = _real_git_dir(tmp_path, "clone")
    log_source = _write_agent_log(old_git_dir)
    _copy_across(log_source, clone_git_dir / _AGENT_LOG_NAME)

    against_clone = build_checklist(
        clone_git_dir=clone_git_dir, old_git_dir=old_git_dir
    )
    assert_carry_over(against_clone, doomed_root=old_git_dir)  # must not raise

    (item,) = against_clone
    assert item.source is not None
    against_old = (CarryOverItem(name=item.name, path=item.source, source=item.source),)
    assert against_old[0].path.exists()  # an existence check would pass this

    with pytest.raises(CarryOverError) as excinfo:
        assert_carry_over(against_old, doomed_root=old_git_dir)

    assert _reported_names(excinfo.value) == ["shared agent log"]


# ---------------------------------------------------------------------------
# assert_commit_identity
# ---------------------------------------------------------------------------


def _identity_env(tmp_path: Path, global_email: str | None) -> dict[str, str]:
    global_cfg = tmp_path / "scratch-global-gitconfig"
    if global_email is not None:
        global_cfg.write_text(f"[user]\n\temail = {global_email}\n")
    env = {"GIT_CONFIG_GLOBAL": str(global_cfg)}
    return env


def test_assert_commit_identity_passes_when_both_scopes_match(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "config", "--local", "user.email", "noreply@fitdocs.example")
    env = _identity_env(tmp_path, "noreply@fitdocs.example")

    assert_commit_identity(repo, "noreply@fitdocs.example", env=env)  # must not raise


def test_assert_commit_identity_raises_naming_only_local_when_local_is_wrong(
    tmp_path: Path,
) -> None:
    """Half of the symmetric guard: local drift with a correct global value
    must be caught, and the message must name `local`, not `global` -- a
    fixture with global also wrong could not tell "checks local" from
    "checks global" apart."""
    repo = _repo(tmp_path)
    _git(repo, "config", "--local", "user.email", "personal@example.com")
    env = _identity_env(tmp_path, "noreply@fitdocs.example")

    with pytest.raises(IdentityError) as excinfo:
        assert_commit_identity(repo, "noreply@fitdocs.example", env=env)

    message = str(excinfo.value)
    assert "local" in message
    assert "global" not in message


def test_assert_commit_identity_raises_naming_only_global_when_global_is_wrong(
    tmp_path: Path,
) -> None:
    """The other half: global drift with a correct local value. A fresh
    clone inherits global configuration (design.md's own stated hazard), so
    this direction is the one that matters most and must be pinned
    independently of the local check above."""
    repo = _repo(tmp_path)
    _git(repo, "config", "--local", "user.email", "noreply@fitdocs.example")
    env = _identity_env(tmp_path, "personal@example.com")

    with pytest.raises(IdentityError) as excinfo:
        assert_commit_identity(repo, "noreply@fitdocs.example", env=env)

    message = str(excinfo.value)
    assert "global" in message
    assert "local" not in message


def test_assert_commit_identity_names_both_scopes_when_both_are_wrong(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "config", "--local", "user.email", "personal-a@example.com")
    env = _identity_env(tmp_path, "personal-b@example.com")

    with pytest.raises(IdentityError) as excinfo:
        assert_commit_identity(repo, "noreply@fitdocs.example", env=env)

    message = str(excinfo.value)
    assert "local" in message
    assert "global" in message


def test_assert_commit_identity_treats_an_unset_global_scope_as_a_mismatch(
    tmp_path: Path,
) -> None:
    """A global scope with no `user.email` configured at all (no scratch
    config file written) must be treated as not matching -- not silently
    accepted because there was nothing to compare against."""
    repo = _repo(tmp_path)
    _git(repo, "config", "--local", "user.email", "noreply@fitdocs.example")
    env = _identity_env(tmp_path, global_email=None)

    with pytest.raises(IdentityError) as excinfo:
        assert_commit_identity(repo, "noreply@fitdocs.example", env=env)

    assert "global" in str(excinfo.value)


# ---------------------------------------------------------------------------
# move_clone
# ---------------------------------------------------------------------------


def test_move_clone_moves_the_directory_to_the_target_path(tmp_path: Path) -> None:
    clone = tmp_path / "scratch-clone"
    clone.mkdir()
    marker = clone / "marker.txt"
    marker.write_text("clone content\n")
    target = tmp_path / "adopted-repo"

    result = move_clone(clone, target)

    assert result == target
    assert (target / "marker.txt").read_text() == "clone content\n"
    assert not clone.exists()


def test_move_clone_refuses_to_overwrite_an_existing_target(tmp_path: Path) -> None:
    clone = tmp_path / "scratch-clone"
    clone.mkdir()
    (clone / "marker.txt").write_text("clone content\n")
    target = tmp_path / "adopted-repo"
    target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("must survive untouched\n")

    with pytest.raises(AdoptionError):
        move_clone(clone, target)

    # Neither side moved: the clone is still exactly where it was, and the
    # pre-existing target directory's own content is untouched.
    assert clone.exists()
    assert (clone / "marker.txt").read_text() == "clone content\n"
    assert sentinel.read_text() == "must survive untouched\n"


# ---------------------------------------------------------------------------
# structural: no destructive call anywhere in this module's own source
#
# **Scope note.** Task 5.5's own observable is "the tool has no code path
# that removes the source directory," and task 7.3 keeps it true while
# re-scoping the checklist. This guard is pinned to `adopt.py` as it stands
# at 7.3: any red means re-verify by hand before touching a pin.
#
# **Why name-set rules (blocklist or allowlist) cannot discriminate here.**
# `adopt.py` legitimately needs `subprocess.run` and `shutil.move`, and each
# of those names is, by itself, sufficient to destroy or vacate the source
# directory (`subprocess.run(["git", ..., "clean", "-xdff"])`;
# `shutil.move(str(source_repo), ...)`). Any rule that discriminates on the
# *set of names* used must admit both of those names to allow the module's
# real behaviour, and admitting them admits destruction too. The
# discriminating information lives in the *arguments* passed to those two
# names and in *how many times, and in what syntactic position*, each
# appears -- not in the name set. Three arms below cover exactly that:
# ---------------------------------------------------------------------------


def _bound_names(tree: ast.AST) -> set[str]:
    """Every name `source` binds -- by a `def`/`class` statement, a function
    argument, a `Name` in `Store` context (a plain assignment target and a
    comprehension target are both `ast.Name` nodes with `ast.Store` context,
    so both are covered without a separate case), or an import (using the
    bound local name: the `asname` if aliased, otherwise the top-level
    component of the imported name)."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            # `except OSError as error:` binds `error` exactly as an
            # assignment does, but the binding is an `ExceptHandler.name`
            # string rather than an `ast.Name` in `Store` context, so the
            # clause above cannot see it. Without this case the handler's
            # variable is reported as a *free* name and would have to be
            # pinned as one, which would record something untrue about the
            # module's surface.
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
    return bound


# -- Arm A: closed surface allowlist ----------------------------------------
#
# Pinned by exact equality against `scripts/purge/adopt.py`'s own AST at the
# time this task landed: every `ast.Attribute.attr`, every free `ast.Name`
# (`Load` context, minus every name `_bound_names` reports bound), and every
# `ast.Import`/`ast.ImportFrom` (module dotted with the imported name).
# Deviation in *either* direction -- an attribute/name/import the module
# uses that is not pinned, or (when walking the module's own full source)
# one that is pinned but no longer used -- is reported; the latter is what
# makes this a pre-7.4 invariant rather than a one-way allowlist, and is
# also why a standalone code snippet shorter than the full module (as used
# by the planted-evasion tests below) is *always* reported as non-conforming
# regardless of content -- the snippet is missing nearly all of the pinned
# baseline. That is intentional: this arm is precise only when applied to
# the whole module (clean, or the whole module plus one evasion appended,
# which preserves every pinned baseline item and reports only the addition).

#
# Re-pinned when the carry-over checklist became a transfer check rather
# than an existence check (the 2026-08-09 queue item). The twelve
# attributes, one free name and one import added then are all **read-only
# inspection**: `hashlib.sha256`/`update`/`hexdigest`/`encode` (digesting),
# `read_bytes`/`is_dir`/`rglob` (reading), `resolve`/`relative_to`/
# `is_relative_to`/`samefile` (path comparison), `source` (the new
# `CarryOverItem` field), and `OSError` (turning an unreadable path into a
# named checklist failure). None of them can remove or move anything, and
# the two effectful names Arms B and C govern are unchanged -- still one
# `subprocess.run` and one `shutil.move` call site, with the same argument
# shapes.
#
# Re-pinned again in the same change's review round, for three more
# read-only names: `is_symlink` and `readlink` (a directory entry that is a
# symlink now digests as its link target instead of being followed, which
# closed a measured false pass) and `parents` (walking a resolved path's
# ancestors to compare them to the doomed root by filesystem identity,
# which closed the case-folding false pass). Reading a link's target and
# iterating a path's ancestors remove nothing.
#
# Re-measured at task 7.3, when `build_checklist` was re-scoped from the
# retired working-tree carry-over to a run-time enumeration of the old
# `.git` directory. Removed (no longer present in the module's own source):
# `extend`, `get`, `items`, `keys` (the scratch-artifacts mapping and the
# multi-item list `build_checklist` used to assemble are both gone -- it
# returns a fixed one-item tuple built by a plain literal now), `set` (no
# longer used to compare label sets), and the two `fitdocs.config` imports
# (`DATA_ROOT_ENV`, `POINTER_RELPATH` -- `detect_data_root_forms` is
# retired with the working-tree carry-over it served). Added: `iterdir`
# (the run-time enumeration itself), `len` and `frozenset` (the foreign-entry
# count message and `_STANDARD_GIT_FURNITURE`). None of the additions can
# remove or move anything, and the two effectful names Arms B and C govern
# are unchanged -- still one `subprocess.run` and one `shutil.move` call
# site, with the same argument shapes.
_PINNED_ATTRS = frozenset(
    {
        "Exit",
        "append",
        "echo",
        "encode",
        "environ",
        "exists",
        "hexdigest",
        "is_dir",
        "is_relative_to",
        "is_symlink",
        "iterdir",
        "join",
        "move",
        "name",
        "parents",
        "path",
        "read_bytes",
        "readlink",
        "relative_to",
        "resolve",
        "returncode",
        "rglob",
        "run",
        "samefile",
        "sha256",
        "source",
        "stdout",
        "strip",
        "update",
    }
)
_PINNED_FREE_NAMES = frozenset(
    {
        "OSError",
        "RuntimeError",
        "bool",
        "dict",
        "frozenset",
        "len",
        "list",
        "sorted",
        "str",
        "tuple",
    }
)
_PINNED_IMPORTS = frozenset(
    {
        "__future__.annotations",
        "hashlib",
        "os",
        "shutil",
        "subprocess",
        "collections.abc.Mapping",
        "collections.abc.Sequence",
        "dataclasses.dataclass",
        "pathlib.Path",
        "typer",
    }
)


def _arm_a_surface_hits(tree: ast.AST) -> list[str]:
    found_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    bound = _bound_names(tree)
    found_free_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    } - bound
    found_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                found_imports.add(f"{module}.{alias.name}")

    hits: list[str] = []
    for label, found, pinned in (
        ("attr", found_attrs, _PINNED_ATTRS),
        ("free-name", found_free_names, _PINNED_FREE_NAMES),
        ("import", found_imports, _PINNED_IMPORTS),
    ):
        for item in sorted(found ^ pinned):
            hits.append(f"surface-{label}:{item}")
    return hits


# -- Arm B: argv/argument pinning for the two admitted effectful names ------
#
# `subprocess.run` and `shutil.move` are both admitted by Arm A (they are
# `adopt.py`'s only legitimate effectful calls), so this arm pins the exact
# argument shape each is allowed to appear with.

_EFFECTFUL_ATTRS = frozenset({"run", "move"})
_PINNED_RUN_ARGV_SHAPES: frozenset[tuple[int, tuple[str | None, ...]]] = frozenset(
    {(6, ("git", "-C", None, "config", None, "user.email"))}
)
_PINNED_MOVE_UNPARSE = frozenset({"shutil.move(str(clone), str(target))"})

# A pinned *shape* (argv shape / unparsed call text) is not a pinned *call
# site*: two textually-identical call sites collapse into the same set
# element and a duplicate is invisible to a set-equality comparison alone.
# These two counts pin how many `subprocess.run(...)` / `shutil.move(...)`
# calls the module may contain in total, alongside the shape pins above, so
# a second call site sharing the pinned shape (e.g. a helper wrapping
# `shutil.move(str(clone), str(target))` a second time) is reported even
# though its shape is individually recognised.
_PINNED_RUN_CALL_COUNT = 1
_PINNED_MOVE_CALL_COUNT = 1


def _arm_b_argument_hits(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    run_shapes: set[tuple[int, tuple[str | None, ...]]] = set()
    move_unparses: set[str] = set()
    run_call_count = 0
    move_call_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "run":
            run_call_count += 1
            first_arg = node.args[0] if node.args else None
            if isinstance(first_arg, ast.List):
                run_shapes.add(
                    (
                        len(first_arg.elts),
                        tuple(
                            elt.value
                            if isinstance(elt, ast.Constant)
                            and isinstance(elt.value, str)
                            else None
                            for elt in first_arg.elts
                        ),
                    )
                )
            else:
                # a non-list argv (e.g. a shell string with shell=True)
                # cannot be shape-checked at all -- flag it outright.
                hits.append("subprocess-run-non-list-argv")
        elif node.func.attr == "move":
            move_call_count += 1
            move_unparses.add(ast.unparse(node))

    if run_shapes and run_shapes != _PINNED_RUN_ARGV_SHAPES:
        for shape in sorted(run_shapes - _PINNED_RUN_ARGV_SHAPES, key=repr):
            hits.append(f"subprocess-run-argv:{shape!r}")
    if move_unparses and move_unparses != _PINNED_MOVE_UNPARSE:
        for call_text in sorted(move_unparses - _PINNED_MOVE_UNPARSE):
            hits.append(f"shutil-move-call:{call_text}")
    if run_call_count and run_call_count != _PINNED_RUN_CALL_COUNT:
        hits.append(f"subprocess-run-call-count:{run_call_count}")
    if move_call_count and move_call_count != _PINNED_MOVE_CALL_COUNT:
        hits.append(f"shutil-move-call-count:{move_call_count}")
    return hits


# -- Arm C: position pinning (closes aliasing) -------------------------------
#
# `subprocess.run` / `shutil.move` may appear only as the callee of a call
# (`x.run(...)`), never as a bare reference (`_sr = subprocess.run`, or as a
# plain argument to `functools.partial`) -- Arm B only inspects `Call.func`
# position, so a bare reference to either name evades it entirely.


def _arm_c_position_hits(tree: ast.AST) -> list[str]:
    call_func_ids = {
        id(call.func) for call in ast.walk(tree) if isinstance(call, ast.Call)
    }
    hits: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _EFFECTFUL_ATTRS
            and id(node) not in call_func_ids
        ):
            hits.append(f"bare-reference:{node.attr}")
    return hits


def _removal_call_names(source: str) -> list[str]:
    """Walk `source`'s AST and return a label for every shape Arms A, B and
    C (above) flag. This holds for `scripts/purge/adopt.py` exactly as it
    stands at task 7.3 (see the module-level scope note above this
    section)."""
    tree = ast.parse(source)
    hits: list[str] = []
    hits.extend(_arm_a_surface_hits(tree))
    hits.extend(_arm_b_argument_hits(tree))
    hits.extend(_arm_c_position_hits(tree))
    return hits


def _real_module_source() -> str:
    """`scripts/purge/adopt.py`'s own source text, read fresh each call (a
    tiny file; no caching payoff worth the staleness risk)."""
    import scripts.purge.adopt as adopt_module

    return Path(inspect.getfile(adopt_module)).read_text(encoding="utf-8")


def _planted(snippet: str) -> str:
    """The real module's own source with `snippet` appended at module level.
    Arm A's surface check is a **symmetric** difference (see
    `_arm_a_surface_hits`), so feeding it a short snippet in isolation
    always reports non-empty regardless of the snippet's content -- nearly
    every pinned attribute, free name and import the real module uses would
    be absent from a two-line fragment. Every planted-evasion fixture below
    is therefore appended to a full copy of the module's own source instead:
    every pinned surface item the real module uses stays present (the
    "missing" side of the symmetric difference stays empty), so what Arm A
    reports is only ever the genuinely new content the snippet introduces --
    the same shape the VERIFICATION mutation testing for this task uses
    directly against `scripts/purge/adopt.py` on disk."""
    return _real_module_source() + "\n" + snippet


def test_removal_call_detector_reports_a_planted_removal_call() -> None:
    """Positive control for `_removal_call_names` itself: proves the walk
    can find something, so that the module-source test below going green
    means "found nothing to report" rather than "the detector cannot report
    anything." Twenty independently-plausible evasions, each planted at
    module level after a full copy of `adopt.py`'s own real source (see
    `_planted`) so only the planted addition -- never the fixture's own
    brevity -- is what a hit can be attributed to.

    Round 1's four, each of which a substring scan for `("rmtree",
    "os.remove(", "os.unlink(", ".unlink(", "os.rmdir(")` misses entirely:
    `Path.rmdir()`, `os.removedirs(...)`, a `getattr`-obscured
    `shutil.rmtree`, and a `subprocess.run(["rm", "-rf", ...])`.

    Round 2's own AST walk lost two shapes the substring scan it replaced
    had caught (both still present as text, so a substring scan for
    `"rmtree"` would have found them, but neither is a `Call` node, so an
    AST walk that only inspects `Call.func` misses both): a bare alias
    assignment of `shutil.rmtree`, and `functools.partial(shutil.rmtree,
    ...)` used without being called at the same syntactic position.

    Round 2's AST walk also admitted five new evasions: `os.system(...)`,
    a `subprocess.run` routed through `/bin/rm` instead of the literal
    `"rm"`, a `subprocess.run` with a shell string and `shell=True`, and
    both a `subprocess.run` and an `os.remove` reached through an
    `ast.ImportFrom` alias (`from ... import ... as ...`) rather than a
    direct attribute access.

    Round 3's name-set guard (blocklist or allowlist) admitted four more,
    all through the two names `adopt.py` legitimately calls: a bare alias
    of `subprocess.run` then called through the alias, the same routed
    through `functools.partial`, a `subprocess.run` whose argv is a
    `git ... clean -xdff` rather than the one pinned `git config` argv, and
    `os.rename` used in place of a removal call. The same two admitted
    names also make `shutil.move` itself an avenue: moving the source
    directory onto a decoy path is observably indistinguishable from
    removing it, and a bare alias of `shutil.move` evades a call-site-only
    check the same way `subprocess.run`'s alias does.

    Round 4's own new hole: Arm B pinned each of the two admitted names'
    argv shape / unparsed call text as a **set**, compared by set equality
    -- a second call site whose shape or text is textually identical to the
    one pinned call site collapses into the same set element and is
    invisible to that comparison. Both duplicates below reuse the exact
    pinned shape (so the shape/text pins alone do not fire) and every name
    they reference is already bound by the real module's own function
    signatures (so Arm A's surface pins do not fire either) -- each is a
    clean catch attributable only to the call-count pins Arm B now also
    carries."""
    # -- round 1 --
    assert _removal_call_names(_planted("import shutil\nshutil.rmtree('x')\n")) != []
    assert _removal_call_names(_planted("target.rmdir()\n")) != []
    assert (
        _removal_call_names(_planted("import os\nos.removedirs(str(target))\n")) != []
    )
    assert (
        _removal_call_names(
            _planted("import shutil\ngetattr(shutil, 'rm' + 'tree')(str(clone))\n")
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "import subprocess\n"
                "subprocess.run(['rm', '-rf', str(clone)], check=True)\n"
            )
        )
        != []
    )
    # -- round 2 regressions: caught by the substring scan round 2 removed --
    assert (
        _removal_call_names(
            _planted(
                "import shutil\n_purge_it = shutil.rmtree\n_purge_it(str(target))\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "import functools\n"
                "import shutil\n"
                "functools.partial(shutil.rmtree, str(target))()\n"
            )
        )
        != []
    )
    # -- round 2 new holes --
    assert (
        _removal_call_names(_planted("import os\nos.system('rm -rf ' + str(target))\n"))
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "import subprocess\n"
                "subprocess.run(['/bin/rm', '-rf', str(target)], check=True)\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "import subprocess\n"
                "subprocess.run(f'rm -rf {target}', shell=True, check=True)\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "from subprocess import run as _srun\n"
                "_srun(['rm', '-rf', str(target)])\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted("from os import remove as _drop\n_drop(str(target))\n")
        )
        != []
    )
    # -- round 3 survivors: the two admitted names, bare-aliased, routed
    #    through functools.partial, called with a destructive argv, or with
    #    a sibling stdlib removal (os.rename) that no round yet named --
    assert (
        _removal_call_names(
            _planted(
                "_sr = subprocess.run\n"
                "_sr(['rm', '-rf', str(source_repo)], check=False)\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "import functools\n"
                "functools.partial(subprocess.run, ['rm', '-rf', str(source_repo)])()\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "subprocess.run(\n"
                "    ['git', '-C', str(source_repo), 'clean', '-xdff'], check=False\n"
                ")\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted("os.rename(str(source_repo), str(source_repo) + '.discarded')\n")
        )
        != []
    )
    # -- round 3's own new holes: shutil.move onto a decoy path, and a bare
    #    alias of shutil.move --
    assert (
        _removal_call_names(
            _planted("shutil.move(str(source_repo), str(source_repo) + '.discarded')\n")
        )
        != []
    )
    assert (
        _removal_call_names(_planted("_mv = shutil.move\n_mv(str(source_repo))\n"))
        != []
    )
    # -- round 4's own new hole: a duplicate call site sharing the pinned
    #    shape exactly, for each of the two admitted names --
    assert (
        _removal_call_names(
            _planted(
                "def discard_source_repository(clone: Path, target: Path) -> None:\n"
                "    shutil.move(str(clone), str(target))\n"
            )
        )
        != []
    )
    assert (
        _removal_call_names(
            _planted(
                "subprocess.run(\n"
                "    ['git', '-C', str(repo_root), 'config', scope, 'user.email']\n"
                ")\n"
            )
        )
        != []
    )


def test_module_source_contains_no_directory_removal_call() -> None:
    """`adopt.py` still has no code path that removes a directory, at task
    7.3 exactly as it did at task 5.5. An AST walk over the module's own
    source text for calls that would remove a directory, vacate it onto a
    decoy path, or reach either of `adopt.py`'s two legitimate effectful
    names (`subprocess.run`, `shutil.move`) other than at their one pinned
    call site each -- see `_removal_call_names` for the exact shapes
    covered -- finds none in `scripts/purge/adopt.py` as it stands at task
    7.3. See the module-level scope note above `_bound_names`."""
    import scripts.purge.adopt as adopt_module

    source = Path(inspect.getfile(adopt_module)).read_text(encoding="utf-8")
    assert source, "the walk is looking at the wrong file"
    hits = _removal_call_names(source)
    assert hits == [], (
        "adopt.py's effectful surface or call sites changed -- re-verify by "
        "hand and update the pin"
    )


# ---------------------------------------------------------------------------
# vacuity controls: one per arm, each showing the arm's pin is load-bearing
# rather than a no-op that would report the same thing regardless of its
# content
# ---------------------------------------------------------------------------


def test_arm_a_vacuity_emptying_pinned_attrs_reds_the_clean_module_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_removal_call_names` against the real module's own source is `[]`
    before the mutation (the precondition this control needs to be false
    beforehand). Emptying `_PINNED_ATTRS` makes every one of the module's
    genuinely legitimate attribute accesses (`.run`, `.move`, `.exists`,
    ...) read as "not in the pinned set" -- Arm A's surface check reports
    them all -- which is exactly what proves the pin was doing real work
    and not standing in as an always-empty placeholder."""
    source = _real_module_source()
    assert _removal_call_names(source) == []  # false precondition confirmed

    monkeypatch.setattr(sys.modules[__name__], "_PINNED_ATTRS", frozenset())

    assert _removal_call_names(source) != []


def test_arm_b_vacuity_blanking_the_pinned_argv_shape_reds_the_clean_module_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mirror of the Arm A control, for the argv-shape pin: blanking
    `_PINNED_RUN_ARGV_SHAPES` to the empty set makes the module's own
    single, legitimate `subprocess.run(["git", ..., "config", ...,
    "user.email"])` call read as an unrecognised argv shape."""
    source = _real_module_source()
    assert _removal_call_names(source) == []  # false precondition confirmed

    monkeypatch.setattr(sys.modules[__name__], "_PINNED_RUN_ARGV_SHAPES", frozenset())

    assert _removal_call_names(source) != []


def test_arm_b_vacuity_dropping_the_pinned_move_call_count_reds_the_clean_module_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mirror of the two controls above, for the call-count pins
    that close the duplicate-call-site hole: the real module's source has
    exactly one `shutil.move(...)` call, so `_PINNED_MOVE_CALL_COUNT` (1)
    matches it and the clean check is `[]` before the mutation. Setting the
    pin to a count the module's real single call cannot satisfy (0) makes
    the real module's own legitimate call read as a call-count mismatch --
    proving the count pin is load-bearing and not an always-passing
    placeholder that could never distinguish one call site from two."""
    source = _real_module_source()
    assert _removal_call_names(source) == []  # false precondition confirmed

    monkeypatch.setattr(sys.modules[__name__], "_PINNED_MOVE_CALL_COUNT", 0)

    assert _removal_call_names(source) != []


def test_arm_c_vacuity_emptying_effectful_attrs_undetects_a_bare_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare rebinding of `subprocess.run` (`os` and `subprocess` are
    already imported by the real module, and `run` is a pinned attribute),
    planted after a full copy of the real module's own source (`_planted`)
    so Arm A's surface check reports nothing on it -- every name it uses is
    already part of the real module's pinned baseline, so this fixture is a
    shape only Arm C reports. Confirmed false-before-mutation below (with
    all three arms live it already reports non-empty). Emptying
    `_EFFECTFUL_ATTRS` removes `run` from the set Arm C inspects, and the
    same fixture goes undetected -- exactly the loss of coverage that would
    let `_sr = subprocess.run; _sr([...])` (round 3's own survivor) through
    a version of this guard where Arm C's set was accidentally left empty
    or never populated."""
    fixture = _planted("_run = subprocess.run\n")
    assert _removal_call_names(fixture) != []  # true before the mutation

    monkeypatch.setattr(sys.modules[__name__], "_EFFECTFUL_ATTRS", frozenset())

    assert _removal_call_names(fixture) == []
