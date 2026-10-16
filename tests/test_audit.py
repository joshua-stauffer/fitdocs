"""The read-only contract audit (Req 5.3, 5.7, 8.1-8.6, 8.8).

Covers :mod:`fitdocs.audit`'s single entry point, :func:`audit`: every
:class:`~fitdocs.audit.FindingKind` produced from a purpose-built fixture tree,
a clean tree yielding no findings, deterministic ordering, a missing
``workouts/`` directory, unreadable documents, and -- the Observable this task
is graded on -- a before/after directory snapshot (bytes *and* mtimes) proving
the pass writes nothing at all.
"""

from __future__ import annotations

import builtins
import os
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path
from unittest import mock

import pytest

from fitdocs.audit import AuditReport, Finding, FindingKind, audit
from fitdocs.benchmarks import Benchmark
from fitdocs.contract import DOC_VERSION
from fitdocs.declaration import ensure_declarations
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.identity.holds import HeldSource, HoldRecord, save_holds
from fitdocs.layout import ARCHIVE_DIR, WORKOUTS_DIR, held_path, source_ref
from tests.fixtures import builder
from tests.test_determinism import _no_socket

_WORKOUTS = f"{WORKOUTS_DIR}/"


# --- fixture builders ----------------------------------------------------------


def _region(region_id: str, content: str = "hello") -> str:
    return f"{begin_marker(region_id)}\n{content}\n{end_marker(region_id)}\n"


def _doc_text(
    *,
    doc_version: object = DOC_VERSION,
    extra_frontmatter: str = "",
    regions: str = "",
    omit_doc_version: bool = False,
) -> str:
    """A minimal, syntactically valid fitdocs workout document."""
    version_line = "" if omit_doc_version else f"doc_version: {doc_version!r}\n"
    return (
        "---\n"
        "title: Test Workout\n"
        "type: workout\n"
        f"{version_line}"
        f"{extra_frontmatter}"
        "---\n\n"
        "# Test Workout\n\n"
        f"{regions}"
    )


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _clean_doc_text() -> str:
    return _doc_text(regions=_region("notes"))


# --- snapshot helper, mirroring tests/test_declaration.py -----------------------


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    state: dict[str, tuple[bytes, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            state[path.relative_to(root).as_posix()] = (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
    return state


def _age(path: Path) -> None:
    old = time.time() - 3600
    os.utime(path, (old, old))


# --- clean tree ------------------------------------------------------------


def test_clean_tree_yields_no_findings(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _clean_doc_text())
    ensure_declarations(tmp_path)

    report = audit(tmp_path)

    assert report.findings == ()
    assert report.documents == 1


# --- missing workouts/ directory -------------------------------------------


def test_missing_workouts_directory_yields_zero_documents_not_an_error(
    tmp_path: Path,
) -> None:
    report = audit(tmp_path)

    assert report.documents == 0
    # Declarations are still missing and reported -- this is not "no findings".
    assert any(
        finding.kind == FindingKind.DECLARATION_MISSING for finding in report.findings
    )


def test_missing_workouts_directory_creates_nothing(tmp_path: Path) -> None:
    audit(tmp_path)

    assert not (tmp_path / WORKOUTS_DIR).exists()


# --- documents count only recognized workout documents ----------------------


def test_documents_counts_only_real_workout_documents(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/real.md", _clean_doc_text())
    _write(tmp_path, f"{WORKOUTS_DIR}/stray.md", "# Just a stray markdown file\n")
    ensure_declarations(tmp_path)  # writes workouts/AGENTS.md

    report = audit(tmp_path)

    assert report.documents == 1


def test_ordinary_frontmatter_without_a_workout_type_is_not_a_document(
    tmp_path: Path,
) -> None:
    # A user's own workouts/index.md, with real YAML frontmatter but no
    # `type: workout` -- must not be treated as a fitdocs document at all,
    # or a user's own index page would start reporting spurious
    # outdated_version findings and a bogus `fitdocs regen` remedy.
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/index.md",
        "---\ntitle: My Index\ntags: [a]\n---\n\n# My Index\n",
    )

    report = audit(tmp_path)

    assert report.documents == 0
    assert not any(finding.subject.endswith("index.md") for finding in report.findings)


def test_declaration_file_is_never_counted_or_flagged_as_a_document(
    tmp_path: Path,
) -> None:
    ensure_declarations(tmp_path)  # only AGENTS.md files exist, no workout docs

    report = audit(tmp_path)

    assert report.documents == 0
    # No OUTDATED_VERSION/DAMAGED_REGIONS/etc finding names an AGENTS.md path
    # as a *document* finding (declaration findings use a different kind).
    document_kinds = {
        FindingKind.OUTDATED_VERSION,
        FindingKind.NEWER_VERSION,
        FindingKind.DAMAGED_REGIONS,
        FindingKind.UNMANAGED_KEYS,
    }
    assert not any(
        finding.kind in document_kinds and finding.subject.endswith("AGENTS.md")
        for finding in report.findings
    )


# --- Req 3.7: an *unreadable* declaration is still never a document scan target
#
# Regression coverage for the ordering bug where `audit()` produced an
# unreadable-document finding (OUTDATED_VERSION) for `workouts/AGENTS.md`
# *before* the declaration-filename exclusion was ever reached. Each variant
# below asserts the same two things: exactly one finding whose kind is a
# `DECLARATION_*` kind for the declaration's own path, and no
# `OUTDATED_VERSION`/`NEWER_VERSION`/`DAMAGED_REGIONS`/`UNMANAGED_KEYS` finding
# ever names it.


_DOCUMENT_FINDING_KINDS = {
    FindingKind.OUTDATED_VERSION,
    FindingKind.NEWER_VERSION,
    FindingKind.DAMAGED_REGIONS,
    FindingKind.UNMANAGED_KEYS,
}
_DECLARATION_FINDING_KINDS = {
    FindingKind.DECLARATION_MISSING,
    FindingKind.DECLARATION_STALE,
    FindingKind.DECLARATION_FOREIGN,
}


def _assert_only_a_declaration_finding_for_agents_md(report: AuditReport) -> None:
    subject = f"{_WORKOUTS}AGENTS.md"
    agents_findings = [f for f in report.findings if f.subject == subject]
    assert len(agents_findings) == 1
    assert agents_findings[0].kind in _DECLARATION_FINDING_KINDS
    assert not any(f.kind in _DOCUMENT_FINDING_KINDS for f in agents_findings)


def test_a_symlinked_declaration_is_never_scanned_as_an_unreadable_document(
    tmp_path: Path,
) -> None:
    outside_root = tmp_path.parent / "escaped-agents.md"
    outside_root.write_text("# hands off\n", encoding="utf-8")
    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    link_path = tmp_path / WORKOUTS_DIR / "AGENTS.md"
    link_path.symlink_to(outside_root)

    report = audit(tmp_path)  # must not raise

    _assert_only_a_declaration_finding_for_agents_md(report)


def test_a_non_utf8_declaration_is_never_scanned_as_an_unreadable_document(
    tmp_path: Path,
) -> None:
    path = tmp_path / WORKOUTS_DIR / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00 not utf-8 at all")

    report = audit(tmp_path)  # must not raise

    _assert_only_a_declaration_finding_for_agents_md(report)


def test_a_permission_denied_declaration_is_never_scanned_as_an_unreadable_document(
    tmp_path: Path,
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    path = tmp_path / WORKOUTS_DIR / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text("# hands off\n", encoding="utf-8")
    path.chmod(0o000)
    try:
        report = audit(tmp_path)  # must not raise
    finally:
        path.chmod(0o644)

    _assert_only_a_declaration_finding_for_agents_md(report)


def test_a_directory_at_the_declaration_path_is_never_scanned_as_an_unreadable_document(
    tmp_path: Path,
) -> None:
    (tmp_path / WORKOUTS_DIR / "AGENTS.md").mkdir(parents=True)

    report = audit(tmp_path)  # must not raise

    _assert_only_a_declaration_finding_for_agents_md(report)


# --- every FindingKind, from purpose-built fixtures -------------------------


def test_outdated_version_below_current(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/old.md", _doc_text(doc_version=DOC_VERSION - 1))

    report = audit(tmp_path)

    finding = next(f for f in report.findings if f.kind == FindingKind.OUTDATED_VERSION)
    assert finding.subject == f"{WORKOUTS_DIR}/old.md"
    assert finding.detail
    assert finding.remedy


def test_outdated_version_missing_doc_version_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/no-version.md",
        _doc_text(omit_doc_version=True),
    )

    report = audit(tmp_path)

    kinds = {f.kind for f in report.findings if f.subject.endswith("no-version.md")}
    assert kinds == {FindingKind.OUTDATED_VERSION}
    assert FindingKind.NEWER_VERSION not in kinds  # Req 5.7's trap, stated twice


def test_outdated_version_unusable_doc_version_value(tmp_path: Path) -> None:
    # A string value is not a genuine integer -- unusable, not newer (Req 5.7).
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/bad-version.md",
        _doc_text(doc_version="not-a-number"),
    )

    report = audit(tmp_path)

    kinds = {f.kind for f in report.findings if f.subject.endswith("bad-version.md")}
    assert kinds == {FindingKind.OUTDATED_VERSION}


def test_newer_version_above_current(tmp_path: Path) -> None:
    _write(
        tmp_path, f"{WORKOUTS_DIR}/future.md", _doc_text(doc_version=DOC_VERSION + 1)
    )

    report = audit(tmp_path)

    finding = next(f for f in report.findings if f.kind == FindingKind.NEWER_VERSION)
    assert finding.subject == f"{WORKOUTS_DIR}/future.md"
    assert finding.detail
    assert finding.remedy


def test_damaged_regions(tmp_path: Path) -> None:
    damaged = _doc_text(regions=f"{begin_marker('notes')}\nno end marker\n")
    _write(tmp_path, f"{WORKOUTS_DIR}/damaged.md", damaged)

    report = audit(tmp_path)

    finding = next(f for f in report.findings if f.kind == FindingKind.DAMAGED_REGIONS)
    assert finding.subject == f"{WORKOUTS_DIR}/damaged.md"
    assert finding.detail
    assert finding.remedy


def test_unmanaged_keys(tmp_path: Path) -> None:
    doc = _doc_text(extra_frontmatter="tags: foo\n", regions=_region("notes"))
    _write(tmp_path, f"{WORKOUTS_DIR}/tagged.md", doc)

    report = audit(tmp_path)

    finding = next(f for f in report.findings if f.kind == FindingKind.UNMANAGED_KEYS)
    assert finding.subject == f"{WORKOUTS_DIR}/tagged.md"
    assert "tags" in finding.detail
    assert finding.remedy


def test_invalid_effort_tag(tmp_path: Path) -> None:
    doc = _doc_text(
        extra_frontmatter="effort: race\neffort_time_s: abc\n",
        regions=_region("notes"),
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/malformed.md", doc)

    report = audit(tmp_path)

    finding = next(
        f for f in report.findings if f.kind == FindingKind.INVALID_EFFORT_TAG
    )
    assert finding.subject == f"{WORKOUTS_DIR}/malformed.md"
    assert finding.detail == (
        "malformed effort tag: effort_time_s: must be a positive number of "
        "seconds; got 'abc'"
    )
    assert "not in effect" in finding.remedy


def test_valid_effort_tag_yields_no_finding(tmp_path: Path) -> None:
    """A well-formed tag yields no finding of either kind (Req 3.6)."""
    doc = _doc_text(extra_frontmatter="effort: race\n", regions=_region("notes"))
    _write(tmp_path, f"{WORKOUTS_DIR}/valid.md", doc)

    report = audit(tmp_path)

    kinds = {f.kind for f in report.findings if f.subject.endswith("valid.md")}
    assert FindingKind.INVALID_EFFORT_TAG not in kinds
    assert FindingKind.UNMANAGED_KEYS not in kinds


def test_effort_key_is_exempt_from_the_unmanaged_key_finding(
    tmp_path: Path,
) -> None:
    doc = _doc_text(
        extra_frontmatter="effort: race\ntags: foo\n", regions=_region("notes")
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/effort_and_tags.md", doc)

    report = audit(tmp_path)

    finding = next(
        f
        for f in report.findings
        if f.kind == FindingKind.UNMANAGED_KEYS
        and f.subject.endswith("effort_and_tags.md")
    )
    assert finding.detail == "unmanaged frontmatter keys: tags"


def test_unmanaged_key_and_malformed_tag_findings_are_independent(
    tmp_path: Path,
) -> None:
    """A document can carry both an unmanaged key and a malformed effort tag;
    neither finding suppresses the other (Req 1.4, 3.5, 4.7)."""
    doc = _doc_text(
        extra_frontmatter="tags: foo\neffort: race\neffort_time_s: abc\n",
        regions=_region("notes"),
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/both.md", doc)

    report = audit(tmp_path)

    kinds = {f.kind for f in report.findings if f.subject.endswith("both.md")}
    assert kinds == {FindingKind.UNMANAGED_KEYS, FindingKind.INVALID_EFFORT_TAG}

    unmanaged = next(
        f
        for f in report.findings
        if f.kind == FindingKind.UNMANAGED_KEYS and f.subject.endswith("both.md")
    )
    assert unmanaged.detail == "unmanaged frontmatter keys: tags"


def test_declaration_missing(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _clean_doc_text())
    # No ensure_declarations call: AGENTS.md is absent everywhere.

    report = audit(tmp_path)

    finding = next(
        f
        for f in report.findings
        if f.kind == FindingKind.DECLARATION_MISSING
        and f.subject == f"{_WORKOUTS}AGENTS.md"
    )
    assert finding.subject == f"{_WORKOUTS}AGENTS.md"
    assert finding.detail
    assert finding.remedy


def test_declaration_stale(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _clean_doc_text())
    ensure_declarations(tmp_path)
    from fitdocs import contract

    stale_path = tmp_path / WORKOUTS_DIR / "AGENTS.md"
    stale_path.write_text(
        contract.GENERATED_PREFIX + ": stale -->\nold\n", encoding="utf-8"
    )

    report = audit(tmp_path)

    finding = next(
        f for f in report.findings if f.kind == FindingKind.DECLARATION_STALE
    )
    assert finding.subject == f"{_WORKOUTS}AGENTS.md"
    assert finding.detail
    assert finding.remedy


def test_declaration_foreign(tmp_path: Path) -> None:
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    foreign_path = tmp_path / ARCHIVE_DIR / "AGENTS.md"
    foreign_path.parent.mkdir(parents=True, exist_ok=True)
    foreign_path.write_text("# hands off\n", encoding="utf-8")

    report = audit(tmp_path)

    finding = next(
        f for f in report.findings if f.kind == FindingKind.DECLARATION_FOREIGN
    )
    assert finding.subject == f"{ARCHIVE_DIR}/AGENTS.md"
    assert finding.detail
    assert finding.remedy


# --- a document yielding multiple findings at once --------------------------


def test_a_document_can_yield_multiple_findings(tmp_path: Path) -> None:
    doc = _doc_text(
        doc_version=DOC_VERSION - 1,
        extra_frontmatter="tags: foo\n",
        regions=_region("notes"),
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/multi.md", doc)

    report = audit(tmp_path)

    kinds = {f.kind for f in report.findings if f.subject.endswith("multi.md")}
    assert kinds == {FindingKind.OUTDATED_VERSION, FindingKind.UNMANAGED_KEYS}


# --- unreadable documents: a finding, never a raise -------------------------


def test_a_directory_named_like_a_document_is_a_finding_not_a_raise(
    tmp_path: Path,
) -> None:
    (tmp_path / WORKOUTS_DIR / "oops.md").mkdir(parents=True)

    report = audit(tmp_path)  # must not raise

    finding = next(f for f in report.findings if f.subject.endswith("oops.md"))
    assert finding.kind == FindingKind.OUTDATED_VERSION
    assert report.documents == 0
    # A directory was never UTF-8 decoded and `regen` cannot fix it: the
    # detail names the true cause, and the remedy is not "run fitdocs regen".
    assert "directory" in finding.detail
    # Distinctive per cause: collapsing all four remedies to one
    # shared string must fail here.
    assert "directory" in finding.remedy.lower()
    assert "regen" not in finding.remedy


def test_a_symlink_escaping_the_data_root_is_treated_as_unreadable(
    tmp_path: Path,
) -> None:
    # A symlink is refused *before* any read is attempted -- read_text follows
    # it -- so a symlink pointing at a real, well-formed document outside the
    # data root is never read through: it is a finding, not a counted document.
    outside_root = tmp_path.parent / "escaped-document.md"
    outside_root.write_text(_clean_doc_text(), encoding="utf-8")
    link_path = tmp_path / WORKOUTS_DIR / "escape.md"
    link_path.parent.mkdir(parents=True)
    link_path.symlink_to(outside_root)

    report = audit(tmp_path)  # must not raise

    finding = next(f for f in report.findings if f.subject.endswith("escape.md"))
    assert finding.kind == FindingKind.OUTDATED_VERSION
    assert report.documents == 0
    # The symlink is valid, readable UTF-8 on the other end -- `regen` would
    # happily read through it -- so the detail must name the symlink itself,
    # and the remedy must not point at `regen`.
    assert "symlink" in finding.detail
    # Distinctive per cause: collapsing all four remedies to one
    # shared string must fail here.
    assert "symlink" in finding.remedy.lower()
    assert "regen" not in finding.remedy


def test_non_utf8_bytes_are_a_finding_not_a_raise(tmp_path: Path) -> None:
    path = tmp_path / WORKOUTS_DIR / "binary.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00 not utf-8 at all")

    report = audit(tmp_path)  # must not raise

    finding = next(f for f in report.findings if f.subject.endswith("binary.md"))
    assert finding.kind == FindingKind.OUTDATED_VERSION
    assert report.documents == 0
    assert "UTF-8" in finding.detail
    # Distinctive per cause: collapsing all four remedies to one
    # shared string must fail here.
    assert "corrupt" in finding.remedy.lower()
    # The remedy may *mention* that regeneration skips this file (an honest
    # caveat), but must never instruct the maintainer to run it as the fix.
    assert "run `fitdocs regen`" not in finding.remedy


def test_permission_denied_document_is_a_finding_not_a_raise(tmp_path: Path) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    path = tmp_path / WORKOUTS_DIR / "locked.md"
    path.parent.mkdir(parents=True)
    path.write_text(_clean_doc_text(), encoding="utf-8")
    path.chmod(0o000)
    try:
        report = audit(tmp_path)  # must not raise
    finally:
        path.chmod(0o644)

    finding = next(f for f in report.findings if f.subject.endswith("locked.md"))
    assert finding.kind == FindingKind.OUTDATED_VERSION
    assert report.documents == 0
    # The file is valid UTF-8 -- `regen` fails to even reach the permission
    # error the same way audit does -- so the detail must name the real
    # failure (an EACCES-flavored message), not a UTF-8 decode failure.
    assert "could not be opened" in finding.detail
    # Distinctive per cause: collapsing all four remedies to one
    # shared string must fail here.
    assert "permission" in finding.remedy.lower()
    assert "regen" not in finding.remedy


# --- deterministic ordering --------------------------------------------------


def test_findings_are_sorted_by_subject_then_kind(tmp_path: Path) -> None:
    # Non-monotonic insertion order: neither ascending nor descending by
    # subject, so a test that only reverses insertion order cannot pass.
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/mmm.md",
        _doc_text(doc_version=DOC_VERSION - 1, extra_frontmatter="tags: x\n"),
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/aaa.md", _doc_text(doc_version=DOC_VERSION + 1))
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/zzz.md",
        _doc_text(doc_version=DOC_VERSION - 1, extra_frontmatter="tags: y\n"),
    )

    report = audit(tmp_path)

    subjects_and_kinds = [(f.subject, f.kind) for f in report.findings]
    assert subjects_and_kinds == sorted(subjects_and_kinds)
    # And it is a genuine sort, not an accident of insertion order:
    assert [s for s, _ in subjects_and_kinds] != [
        f"{WORKOUTS_DIR}/mmm.md",
        f"{WORKOUTS_DIR}/mmm.md",
        f"{WORKOUTS_DIR}/aaa.md",
        f"{WORKOUTS_DIR}/zzz.md",
        f"{WORKOUTS_DIR}/zzz.md",
    ]


# --- the pass writes nothing at all: before/after snapshot with mtimes ------


def test_audit_writes_nothing_at_all(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _clean_doc_text())
    _write(tmp_path, f"{WORKOUTS_DIR}/old.md", _doc_text(doc_version=DOC_VERSION - 1))
    _write(
        tmp_path, f"{WORKOUTS_DIR}/future.md", _doc_text(doc_version=DOC_VERSION + 1)
    )
    damaged = _doc_text(regions=f"{begin_marker('notes')}\nno end\n")
    _write(tmp_path, f"{WORKOUTS_DIR}/damaged.md", damaged)
    ensure_declarations(tmp_path)

    for path in sorted(tmp_path.rglob("*")):
        if path.is_file():
            _age(path)
    before = _snapshot(tmp_path)
    assert before  # sanity: there really is something to protect

    report = audit(tmp_path)

    after = _snapshot(tmp_path)
    assert after == before  # every byte AND every mtime, completely untouched
    assert report.findings != ()  # a non-trivial run, not a vacuous one


# --- Req 8.8: offline, and never opens a `.fit` source ----------------------


def test_audit_completes_without_network_access_or_reading_any_fit_file(
    tmp_path: Path,
) -> None:
    """The inspection never opens a network socket and never opens a ``.fit``
    file (Req 8.8), proven mechanically over a data root holding a REAL
    archived source -- not merely asserted by reading the module's docstring.

    Reuses ``tests.test_determinism``'s ``_no_socket`` guard (rather than a
    second copy) for the network half; the ``.fit``-read half is a dedicated
    instrumentation of ``builtins.open``, ``Path.read_bytes``, and
    ``Path.read_text`` that raises the moment any of them is asked to open a
    path ending in ``.fit`` -- ``read_text``/``read_bytes`` bypass
    ``builtins.open`` entirely (they call the lower-level ``io`` machinery
    directly), so all three surfaces must be guarded for the assertion to be
    load-bearing rather than accidentally vacuous.

    Mutation caught: making ``audit`` read the archived ``.fit`` source (e.g.
    to sniff its sport for a friendlier finding) trips this guard immediately.
    """
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/one.md",
        _doc_text(
            extra_frontmatter=f"sources:\n  - {ARCHIVE_DIR}/{'0' * 8}.fit\n",
            regions=_region("notes"),
        ),
    )
    ensure_declarations(tmp_path)
    archive_dir = tmp_path / ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / ("0" * 8 + ".fit")).write_bytes(builder.run_fit_bytes())

    opened_fit_paths: list[str] = []
    real_open = builtins.open
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text

    def _guarded_open(
        file: object, mode: str = "r", *args: object, **kwargs: object
    ) -> object:
        if str(file).endswith(".fit"):
            opened_fit_paths.append(str(file))
            raise AssertionError(f".fit file opened via open(): {file!r}")
        return real_open(file, mode, *args, **kwargs)  # type: ignore[arg-type]

    def _guarded_read_bytes(self: Path, *args: object, **kwargs: object) -> bytes:
        if str(self).endswith(".fit"):
            opened_fit_paths.append(str(self))
            raise AssertionError(f".fit file opened via Path.read_bytes: {self}")
        return real_read_bytes(self, *args, **kwargs)  # type: ignore[arg-type]

    def _guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if str(self).endswith(".fit"):
            opened_fit_paths.append(str(self))
            raise AssertionError(f".fit file opened via Path.read_text: {self}")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    with (
        mock.patch("builtins.open", _guarded_open),
        mock.patch.object(Path, "read_bytes", _guarded_read_bytes),
        mock.patch.object(Path, "read_text", _guarded_read_text),
        mock.patch("socket.socket", _no_socket),
    ):
        report = audit(tmp_path)  # must not raise

    assert opened_fit_paths == []
    assert report.documents == 1
    assert report.findings == ()


def test_audit_creates_no_directory_on_a_bare_data_root(tmp_path: Path) -> None:
    before = sorted(p for p in tmp_path.rglob("*"))
    assert before == []

    audit(tmp_path)

    after = sorted(p for p in tmp_path.rglob("*"))
    assert after == []


# --- AuditReport / Finding / FindingKind shape ------------------------------


def test_finding_and_report_are_frozen_dataclasses() -> None:
    finding = Finding(
        kind=FindingKind.OUTDATED_VERSION,
        subject="workouts/x.md",
        detail="d",
        remedy="r",
    )
    with pytest.raises(AttributeError):
        finding.detail = "changed"  # type: ignore[misc]

    report = AuditReport(findings=(finding,), documents=1)
    with pytest.raises(AttributeError):
        report.documents = 2  # type: ignore[misc]


def test_every_finding_kind_is_a_str() -> None:
    for kind in FindingKind:
        assert isinstance(kind.value, str)
        assert str(kind) == kind.value


# --- activity-identity 8.1-8.5: held, orphaned and duplicated sources --------

_SHA_HELD = "b" * 64
_SHA_ORPHAN = "c" * 64
_SHA_LISTED = "a" * 64
_SHA_UNREADABLE_PAGE = "d" * 64
_SHA_EXTRA = "e" * 64
_SHA_BASE = "f" * 64
_UUID_TWO = "99999999-8888-7777-6666-555555555555"
_UUID = "11111111-2222-3333-4444-555555555555"
_REMEDY_ONE_WORKOUT = (
    "if the candidate pages are one workout, keep one (move anything worth "
    "keeping out of the other's notes first), delete the other, and run "
    "`fitdocs regen`; fitdocs never merges pages or picks one"
)
_REMEDY_ORPHAN = (
    "run `fitdocs regen` to render it, or delete it if its page was removed on purpose"
)
_REMEDY_HOLD_RECORD = "run `fitdocs regen`, which rebuilds it"


def _page(root: Path, name: str, *, sources: list[str], extra: str = "") -> str:
    """Write a workout page listing ``sources``; returns its subject."""
    listing = "".join(f"  - {ref}\n" for ref in sources)
    _write(
        root,
        f"{WORKOUTS_DIR}/{name}.md",
        _doc_text(
            extra_frontmatter=f"sources:\n{listing}{extra}",
            regions=_region("notes"),
        ),
    )
    return f"{WORKOUTS_DIR}/{name}.md"


def _archive(root: Path, *shas: str) -> None:
    for sha in shas:
        target = root / ARCHIVE_DIR / f"{sha}.fit"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(builder.run_fit_bytes())


def _kind(report: AuditReport, kind: FindingKind) -> list[Finding]:
    return [f for f in report.findings if f.kind == kind]


def _stage_identity_tree(root: Path) -> None:
    """One held entry, one orphan, a shared-source pair, a UUID-only triple, a
    rule-tier pair, a clean page, a page listing two archived sources, and a
    triple linked by two tiers."""
    ensure_declarations(root)
    _archive(root, _SHA_HELD, _SHA_ORPHAN, _SHA_LISTED)
    # shared source (evidence: source)
    _page(root, "s1", sources=[source_ref(_SHA_LISTED)])
    _page(root, "s2", sources=[source_ref(_SHA_LISTED)])
    # UUID-only triple: pairwise-disjoint sources, no start, so no rule tier
    for name, sha in (("u1", "1"), ("u2", "2"), ("u3", "3")):
        _page(
            root,
            name,
            sources=[source_ref(sha * 64)],
            extra=f"uuid: {_UUID}\n",
        )
    # rule-tier pair (evidence: strict): different sources, no uuid
    for name, sha in (("r1", "4"), ("r2", "5")):
        _page(
            root,
            name,
            sources=[source_ref(sha * 64)],
            extra=(
                "sport: running\nstart_time: '2026-07-12T07:30:00-06:00'\n"
                "source_elapsed_s: 1800\nsource_distance_m: 5000\n"
            ),
        )
    _page(root, "clean", sources=[source_ref("6" * 64)])
    # extra + base, neither held, pairwise-distinct from every other sha
    _archive(root, _SHA_EXTRA, _SHA_BASE)
    _page(root, "multi", sources=[source_ref(_SHA_EXTRA), source_ref(_SHA_BASE)])
    # two tiers in one set: m1-m2 share a source, m2-m3 share a uuid
    _page(root, "m1", sources=[source_ref("7" * 64)])
    _page(
        root,
        "m2",
        sources=[source_ref("7" * 64), source_ref("8" * 64)],
        extra=f"uuid: {_UUID_TWO}\n",
    )
    _page(root, "m3", sources=[source_ref("9" * 64)], extra=f"uuid: {_UUID_TWO}\n")
    save_holds(
        root,
        HoldRecord(
            (
                HeldSource(
                    sha256=_SHA_HELD,
                    name="held.fit",
                    candidates=(f"{WORKOUTS_DIR}/s1.md", f"{WORKOUTS_DIR}/r1.md"),
                    evidence=("strict", "device"),
                ),
            )
        ),
    )


def test_held_entry_is_one_finding_with_subject_candidates_evidence_and_remedy(
    tmp_path: Path,
) -> None:
    _stage_identity_tree(tmp_path)

    found = _kind(audit(tmp_path), FindingKind.AMBIGUOUS_SOURCE)

    assert len(found) == 1
    finding = found[0]
    assert finding.subject == source_ref(_SHA_HELD)
    assert f"{WORKOUTS_DIR}/s1.md" in finding.detail
    assert f"{WORKOUTS_DIR}/r1.md" in finding.detail
    assert "strict, device" in finding.detail
    assert finding.remedy == _REMEDY_ONE_WORKOUT


def test_a_held_archive_is_not_also_orphaned_but_an_unheld_unlisted_one_is(
    tmp_path: Path,
) -> None:
    _stage_identity_tree(tmp_path)

    orphans = _kind(audit(tmp_path), FindingKind.ORPHANED_SOURCE)

    # _SHA_HELD is archived, unlisted by every page, and named by the hold.
    # (the multi-source page's two archives are listed, so not orphans)
    assert [f.subject for f in orphans] == [source_ref(_SHA_ORPHAN)]
    assert orphans[0].remedy == _REMEDY_ORPHAN
    assert orphans[0].detail  # non-empty, names why


def test_orphan_check_ignores_pages_the_audit_could_not_read(tmp_path: Path) -> None:
    _stage_identity_tree(tmp_path)
    _archive(tmp_path, _SHA_UNREADABLE_PAGE)
    # A page listing the archive but not valid UTF-8, and a non-workout note
    # that mentions it: neither is a readable workout page.
    bad = tmp_path / WORKOUTS_DIR / "bad.md"
    bad.write_bytes(
        b"---\ntype: workout\nsources:\n  - "
        + source_ref(_SHA_UNREADABLE_PAGE).encode()
        + b"\n---\n\xff\xfe\n"
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/stray.md",
        f"---\ntitle: n\nsources:\n  - {source_ref(_SHA_UNREADABLE_PAGE)}\n---\n",
    )

    orphans = _kind(audit(tmp_path), FindingKind.ORPHANED_SOURCE)

    assert source_ref(_SHA_UNREADABLE_PAGE) in [f.subject for f in orphans]


def test_archive_entries_that_are_not_hex_named_fit_files_are_not_orphans(
    tmp_path: Path,
) -> None:
    ensure_declarations(tmp_path)
    (tmp_path / ARCHIVE_DIR).mkdir(exist_ok=True)
    (tmp_path / ARCHIVE_DIR / "notes.fit").write_bytes(b"x")
    (tmp_path / ARCHIVE_DIR / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / ARCHIVE_DIR / f"{_SHA_ORPHAN}.fit").mkdir()

    assert _kind(audit(tmp_path), FindingKind.ORPHANED_SOURCE) == []


def test_duplicate_sets_yield_one_finding_per_page_naming_the_others(
    tmp_path: Path,
) -> None:
    _stage_identity_tree(tmp_path)

    report = audit(tmp_path)
    dups = {f.subject: f for f in _kind(report, FindingKind.DUPLICATE_SESSION)}

    w = f"{WORKOUTS_DIR}/"
    assert sorted(dups) == [
        f"{w}{n}.md"
        for n in ("m1", "m2", "m3", "r1", "r2", "s1", "s2", "u1", "u2", "u3")
    ]
    # two tiers link this set: both named, strongest first (duplicate_sets order)
    assert (
        dups[f"{w}m2.md"].detail
        == f"the same session as {w}m1.md, {w}m3.md; evidence: source, uuid"
    )
    assert dups[f"{w}s1.md"].detail == f"the same session as {w}s2.md; evidence: source"
    assert dups[f"{w}r2.md"].detail == f"the same session as {w}r1.md; evidence: strict"
    # UUID-only set of three: each names both others, and the link is the uuid.
    assert (
        dups[f"{w}u2.md"].detail
        == f"the same session as {w}u1.md, {w}u3.md; evidence: uuid"
    )
    assert {f.remedy for f in dups.values()} == {_REMEDY_ONE_WORKOUT}
    assert f"{w}clean.md" not in dups


def test_unreadable_hold_record_is_one_finding_naming_the_file(
    tmp_path: Path,
) -> None:
    _stage_identity_tree(tmp_path)
    _write(tmp_path, ".fitdocs/held.toml", "held = [ not toml")

    report = audit(tmp_path)
    found = _kind(report, FindingKind.AMBIGUOUS_SOURCE)

    # The scan continues past the bad record (Req 8.4): the formerly held
    # archive is now unnamed, so it is orphaned too.
    orphans = {f.subject for f in _kind(report, FindingKind.ORPHANED_SOURCE)}
    assert orphans == {source_ref(_SHA_ORPHAN), source_ref(_SHA_HELD)}
    assert len(_kind(report, FindingKind.DUPLICATE_SESSION)) == 10
    assert len(found) == 1
    assert found[0].subject == ".fitdocs/held.toml"
    assert "held.toml" in found[0].detail
    assert found[0].remedy == _REMEDY_HOLD_RECORD


def test_absent_hold_record_means_no_held_findings_and_creates_nothing(
    tmp_path: Path,
) -> None:
    ensure_declarations(tmp_path)
    _page(tmp_path, "one", sources=[source_ref(_SHA_LISTED)])
    _archive(tmp_path, _SHA_LISTED)

    assert audit(tmp_path).findings == ()
    assert not held_path(tmp_path).parent.exists()


def test_identity_findings_open_no_fit_file_and_write_nothing(
    tmp_path: Path,
) -> None:
    _stage_identity_tree(tmp_path)
    for path in sorted(tmp_path.rglob("*")):
        if path.is_file():
            _age(path)
    before = _snapshot(tmp_path)

    opened: list[str] = []
    real_open = builtins.open
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text
    real_path_open = Path.open

    def _note(target: object) -> None:
        if str(target).endswith(".fit"):
            opened.append(str(target))
            raise AssertionError(f".fit opened: {target}")

    def _open(file: object, *args: object, **kwargs: object) -> object:
        _note(file)
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

    def _rb(self: Path) -> bytes:
        _note(self)
        return real_read_bytes(self)

    def _rt(self: Path, *args: object, **kwargs: object) -> str:
        _note(self)
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    def _po(self: Path, *args: object, **kwargs: object) -> object:
        _note(self)
        return real_path_open(self, *args, **kwargs)  # type: ignore[call-overload]

    with (
        mock.patch("builtins.open", _open),
        mock.patch.object(Path, "read_bytes", _rb),
        mock.patch.object(Path, "read_text", _rt),
        mock.patch.object(Path, "open", _po),
    ):
        report = audit(tmp_path)

    assert opened == []
    # A non-vacuous run: every identity kind was reached.
    assert {f.kind for f in report.findings} >= {
        FindingKind.AMBIGUOUS_SOURCE,
        FindingKind.ORPHANED_SOURCE,
        FindingKind.DUPLICATE_SESSION,
    }
    assert _snapshot(tmp_path) == before


def test_check_cli_prints_the_three_kinds_and_exits_one(tmp_path: Path) -> None:
    _stage_identity_tree(tmp_path)

    fitdocs = Path(sys.executable).parent / "fitdocs"
    result = subprocess.run(
        [str(fitdocs), "check", "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    # The listing prints subject, detail and remedy, not the kind name.
    for fragment in (
        source_ref(_SHA_HELD),  # held
        source_ref(_SHA_ORPHAN),  # orphaned
        _REMEDY_ORPHAN,
        "the same session as",  # duplicate
        _REMEDY_ONE_WORKOUT,
    ):
        assert fragment in result.stdout, fragment


# --- wellness-store 4.3 -------------------------------------------------------

_WELLNESS_CASES = (
    "orphan",
    "stale",
    "occupied",
    "conflict",
    "conflict-other",
    "settings",
)
_WELLNESS_ENUMS = (
    ("WELLNESS_ORPHANED_ENTRY", "wellness_orphaned_entry"),
    ("WELLNESS_SERIES_STALE", "wellness_series_stale"),
    ("WELLNESS_SERIES_OCCUPIED", "wellness_series_occupied"),
    ("WELLNESS_CONFLICT", "wellness_conflict"),
)
_WELLNESS_REMEDIES = {
    "orphan": (
        "move it out of `wellness-archive/`: fitdocs never reads it; "
        "if it is a wellness file, drop it into the inbox instead"
    ),
    "stale": "run `fitdocs sync` or `fitdocs regen` to rebuild the wellness series",
    "occupied": (
        "move or remove it: fitdocs never overwrites a file it did not write, "
        "and rebuilds the series once the path is free"
    ),
    "conflict": (
        "if one of the entries is wrong, delete it from `wellness-archive/` "
        "and from the inbox, then run `fitdocs regen`; otherwise fitdocs "
        "keeps the value named here"
    ),
    "settings": "fix `fitdocs.toml`; sync and regen refuse to run until it is valid",
}


def _wellness_archive(
    root: Path, value: int, day: str = "2028-03-17", *, garmin: bool = False
) -> str:
    from fitdocs.wellness.archive import Committed, commit_original
    from fitdocs.wellness.registry import format_named
    from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record

    if garmin:
        from tests.wellness.builders_garmin import garmin_file_bytes, garmin_uds_record

        payload = garmin_file_bytes([garmin_uds_record(day, totalSteps=value)])
    else:
        payload = intervals_list_bytes([intervals_record(day, restingHR=value)])
    candidate = root / f"synthetic-{value}.json"
    candidate.write_bytes(payload)
    format = format_named("garmin-uds" if garmin else "intervals-icu")
    if format is None:
        raise AssertionError("missing published wellness format")
    result = commit_original(root, format, candidate, sha256(payload).hexdigest())
    if not isinstance(result, Committed):
        raise AssertionError(result)
    return result.entry.ref


def _wellness_build(root: Path) -> None:
    from fitdocs.wellness import DEFAULT_WELLNESS_SETTINGS
    from fitdocs.wellness.engine import SeriesStatus, rebuild_series

    result = rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=False)
    if result.status not in (SeriesStatus.REBUILT, SeriesStatus.UNCHANGED):
        raise AssertionError(result)


def _stage_wellness(root: Path, case: str) -> dict[str, str]:
    ensure_declarations(root)
    subject = "wellness/manifest.toml"
    detail = "series manifest is missing"
    kind = "wellness_series_stale"
    if case == "orphan":
        subject = "wellness-archive/intervals-icu/stray.json"
        _write(root, subject, "synthetic orphan")
        detail = (
            "not a regular entry with the format's sha256 name and suffix; "
            "fitdocs never reads it"
        )
        kind = "wellness_orphaned_entry"
    elif case == "occupied":
        subject = "wellness/2024.csv"
        _wellness_archive(root, 48)
        _wellness_build(root)
        (root / subject).mkdir()
        detail = "occupied series path"
        kind = "wellness_series_occupied"
    elif case == "settings":
        _write(root, "fitdocs.toml", '[wellness]\nprecedence="invalid"\n')
        detail = (
            f"series cannot be judged: {root / 'fitdocs.toml'}: "
            "[wellness] precedence must be a list of source identifiers"
        )
    elif case in ("conflict", "conflict-other"):
        other = case == "conflict-other"
        day = "2031-09-06" if other else "2028-03-17"
        metric = "steps" if other else "resting_hr_bpm"
        source = "garmin-export" if other else "intervals-icu"
        low, high = (8310, 9201) if other else (61, 78)
        first = _wellness_archive(root, low, day, garmin=other)
        second = _wellness_archive(root, high, day, garmin=other)
        _wellness_build(root)
        kept = max(first, second)
        value = low if kept == first else high
        subject = f"wellness/{day[:4]}.csv"
        detail = (
            f"{day} {metric} {source}: "
            f"kept {value} from {kept}; conflicting entries: "
            + ", ".join(sorted((first, second)))
        )
        kind = "wellness_conflict"
    elif case == "stale":
        _wellness_archive(root, 56)
    elif case == "clean":
        _wellness_archive(root, 53)
        _wellness_build(root)
        return {}
    else:
        raise ValueError(case)
    return {
        "kind": kind,
        "subject": subject,
        "detail": detail,
        "remedy": _WELLNESS_REMEDIES["conflict" if case == "conflict-other" else case],
    }


@pytest.mark.parametrize("name,value", _WELLNESS_ENUMS)
def test_wellness_enum(name: str, value: str) -> None:
    assert FindingKind.__members__[name].value == value


@pytest.mark.parametrize("case", _WELLNESS_CASES)
@pytest.mark.parametrize("field", ("kind", "subject", "detail", "remedy"))
def test_wellness_finding_field(tmp_path: Path, case: str, field: str) -> None:
    expected = _stage_wellness(tmp_path, case)
    finding = audit(tmp_path).findings[0]
    assert getattr(finding, field) == expected[field]


@pytest.mark.parametrize("case", _WELLNESS_CASES)
def test_wellness_cardinality(tmp_path: Path, case: str) -> None:
    _stage_wellness(tmp_path, case)
    assert len(audit(tmp_path).findings) == 1


@pytest.mark.parametrize("directory", ("wellness", "wellness-archive"))
def test_wellness_missing_declaration(tmp_path: Path, directory: str) -> None:
    ensure_declarations(tmp_path)
    (tmp_path / directory / "AGENTS.md").unlink()
    assert [(f.subject, f.kind.value) for f in audit(tmp_path).findings] == [
        (f"{directory}/AGENTS.md", "declaration_missing")
    ]


def test_wellness_sorted_with_existing_findings(tmp_path: Path) -> None:
    _stage_wellness(tmp_path, "conflict")
    _write(tmp_path, "wellness/2028.csv", "foreign")
    _write(tmp_path, "wellness-archive/intervals-icu/z.txt", "orphan")
    _write(tmp_path, "wellness-archive/intervals-icu/a.txt", "orphan")
    _write(tmp_path, "workouts/z.md", _doc_text(doc_version=1))
    _write(tmp_path, "workouts/a.md", _doc_text(doc_version=1))
    (tmp_path / "fit-archive/AGENTS.md").unlink()
    assert [(f.subject, f.kind.value) for f in audit(tmp_path).findings] == [
        ("fit-archive/AGENTS.md", "declaration_missing"),
        ("wellness-archive/intervals-icu/a.txt", "wellness_orphaned_entry"),
        ("wellness-archive/intervals-icu/z.txt", "wellness_orphaned_entry"),
        ("wellness/2028.csv", "wellness_conflict"),
        ("wellness/2028.csv", "wellness_series_occupied"),
        ("wellness/manifest.toml", "wellness_series_stale"),
        ("workouts/a.md", "outdated_version"),
        ("workouts/z.md", "outdated_version"),
    ]


def test_wellness_audit_opens_no_archive_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_wellness(tmp_path, "clean")
    opened: list[Path] = []
    real_open = Path.open

    def record(path: Path, *args: object, **kwargs: object) -> object:
        if (
            path.is_relative_to(tmp_path / "wellness-archive")
            and path.name != "AGENTS.md"
        ):
            opened.append(path)
        return real_open(path, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", record)
    audit(tmp_path)
    assert opened == []


def test_wellness_audit_preserves_files(tmp_path: Path) -> None:
    _stage_wellness(tmp_path, "clean")
    before = _snapshot(tmp_path)
    audit(tmp_path)
    assert _snapshot(tmp_path) == before


def test_wellness_audit_creates_no_directories(tmp_path: Path) -> None:
    ensure_declarations(tmp_path)
    (tmp_path / "wellness/AGENTS.md").unlink()
    (tmp_path / "wellness").rmdir()
    (tmp_path / "wellness-archive/AGENTS.md").unlink()
    (tmp_path / "wellness-archive").rmdir()
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()}
    audit(tmp_path)
    assert {
        p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()
    } == before


def test_wellness_reports_each_conflict(tmp_path: Path) -> None:
    _stage_wellness(tmp_path, "conflict")
    _stage_wellness(tmp_path, "conflict-other")
    assert (
        len([f for f in audit(tmp_path).findings if f.kind == "wellness_conflict"]) == 2
    )


# --- heart-rate profile findings (hr-derivation 3.4) ---------------------------


def _hr_entry(
    kind: str,
    day: str,
    value: float,
    *,
    origin: str = "hand",
    discipline: str | None = None,
    applies: str | None = None,
) -> Benchmark:
    from datetime import date

    from fitdocs.benchmarks import BenchmarkKind
    from fitdocs.hr_benchmarks.types import HrMethod
    from fitdocs.model import Sport
    from tests.hr_benchmarks.builders import derived_benchmark, hand_benchmark

    scope = Sport(discipline) if discipline is not None else None
    start = date.fromisoformat(applies) if applies is not None else None
    if origin == "derived":
        resting = kind == "resting_hr_bpm"
        return derived_benchmark(
            BenchmarkKind(kind),
            date.fromisoformat(day),
            value,
            method=HrMethod.RESTING_HR_SERIES_MEDIAN
            if resting
            else HrMethod.MAX_HR_SUSTAINED_PEAK,
            document="wellness/2031.csv" if resting else "workouts/2031-01-08-hill.md",
            inputs=(
                "source garmin-export; window 2030-12-19 to 2031-01-15; 18 "
                "days; 7 confirmation days"
            )
            if resting
            else (
                "window 2030-01-09 to 2031-01-08; 23 sessions; peaks 198.4, "
                "193.2, 191.1 bpm"
            ),
            citation="synthetic-rhr" if resting else "synthetic-max",
            series="garmin-export/resting_hr_bpm" if resting else None,
            discipline=scope,
            applies_from=start,
        )
    return hand_benchmark(
        BenchmarkKind(kind),
        date.fromisoformat(day),
        value,
        discipline=scope,
        applies_from=start,
        measured=origin == "measured",
    )


def _hr_root(root: Path, entries: list[Benchmark]) -> None:
    from tests.hr_benchmarks.builders import make_data_root

    make_data_root(root, entries)
    ensure_declarations(root)


def _hr_records(root: Path) -> list[tuple[str, str, str, str]]:
    return [(f.kind.value, f.subject, f.detail, f.remedy) for f in audit(root).findings]


_HR_TAKEOVER_REMEDY = (
    "to keep your own value, record a new {kind} entry by hand "
    "(it wins from its date); "
    "to accept the derived value, leave it — this listing ends "
    "when a later {kind} entry exists"
)
_HR_INCONSISTENT_REMEDY = (
    "heart-rate load is not computed in this period; record the "
    "correct value by hand for the one that is wrong"
)
_HR_UNREADABLE_REMEDY = (
    "fix `athlete.toml`; load and derive-benchmarks refuse to run until it is valid"
)


def _stage_hr_takeover(root: Path, case: str) -> list[tuple[str, str, str, str]]:
    hand = _hr_entry(
        "max_hr_bpm",
        "2031-01-02",
        181,
        origin="measured" if case == "measured" else "hand",
        applies="2031-01-02"
        if case == "equal-applies"
        else "2030-11-01"
        if case == "early-applies"
        else None,
    )
    derived = _hr_entry("max_hr_bpm", "2031-01-08", 193, origin="derived")
    entries = [derived, hand]
    expected = [
        (
            "hr_benchmark_takeover",
            "athlete.toml",
            (
                "max_hr_bpm: derived 193 bpm from 2031-01-08 takes over from "
                "your hand-recorded 181 bpm of 2031-01-02 (applied by "
                "measurement date); evidence: window 2030-01-09 to "
                "2031-01-08; 23 sessions; peaks 198.4, 193.2, 191.1 bpm; "
                "document: workouts/2031-01-08-hill.md"
            ),
            _HR_TAKEOVER_REMEDY.format(kind="max_hr_bpm"),
        )
    ]
    if case == "dual":
        entries += [
            _hr_entry("resting_hr_bpm", "2031-01-04", 63),
            _hr_entry("resting_hr_bpm", "2031-01-15", 57, origin="derived"),
        ]
        expected += [
            (
                "hr_benchmark_takeover",
                "athlete.toml",
                (
                    "resting_hr_bpm: derived 57 bpm from 2031-01-15 takes over "
                    "from your hand-recorded 63 bpm of 2031-01-04 (applied by "
                    "measurement date); evidence: source garmin-export; window "
                    "2030-12-19 to 2031-01-15; 18 days; 7 confirmation days; "
                    "document: wellness/2031.csv; series: "
                    "garmin-export/resting_hr_bpm"
                ),
                _HR_TAKEOVER_REMEDY.format(kind="resting_hr_bpm"),
            )
        ]
    elif case in ("later-hand", "later-derived"):
        entries += [
            _hr_entry(
                "max_hr_bpm",
                "2031-02-10",
                197,
                origin="derived" if case == "later-derived" else "hand",
            )
        ]
        expected = []
    elif case == "back-reach":
        entries = [
            derived,
            _hr_entry("max_hr_bpm", "2031-02-10", 179, applies="2030-12-01"),
        ]
        expected = []
    _hr_root(root, entries)
    return expected


@pytest.mark.parametrize(
    "name,value",
    [
        ("HR_BENCHMARK_TAKEOVER", "hr_benchmark_takeover"),
        ("HR_BENCHMARK_INCONSISTENT", "hr_benchmark_inconsistent"),
        ("ATHLETE_PROFILE_UNREADABLE", "athlete_profile_unreadable"),
    ],
)
def test_hr_enum(name: str, value: str) -> None:
    assert FindingKind.__members__.get(name) == value


@pytest.mark.parametrize(
    "case",
    [
        "dual",
        "measured",
        "equal-applies",
        "early-applies",
        "later-hand",
        "later-derived",
        "back-reach",
    ],
)
def test_hr_current_takeover_records(tmp_path: Path, case: str) -> None:
    expected = _stage_hr_takeover(tmp_path, case)
    assert _hr_records(tmp_path) == expected


def _stage_hr_inconsistent(root: Path, case: str) -> list[tuple[str, str, str, str]]:
    max_origin, rest_origin = (
        ("hand", "derived")
        if case == "rest-derived"
        else ("derived", "derived")
        if case == "both-derived"
        else ("derived", "hand")
    )
    mx = 61 if case == "equal" else 53
    entries = [
        _hr_entry("max_hr_bpm", "2031-01-03", mx, origin=max_origin),
        _hr_entry("resting_hr_bpm", "2031-01-05", 61, origin=rest_origin),
        _hr_entry("lthr_bpm", "2031-01-01", 55, discipline="Run"),
        _hr_entry("lthr_bpm", "2031-01-02", 71, discipline="Ride"),
    ]
    expected = [
        (
            "hr_benchmark_inconsistent",
            "athlete.toml",
            (
                f"max_not_above_rest [2031-01-05, open): max_hr_bpm {mx} bpm "
                f"of 2031-01-03 "
                f"({'derived' if max_origin == 'derived' else 'hand-recorded'}); "
                f"resting_hr_bpm 61 bpm of 2031-01-05 "
                f"({'derived' if rest_origin == 'derived' else 'hand-recorded'})"
            ),
            _HR_INCONSISTENT_REMEDY,
        )
    ]
    if case == "hand-only":
        entries[0] = _hr_entry("max_hr_bpm", "2031-01-03", mx)
        expected = []
    elif case == "missing-max":
        entries = entries[1:]
        expected = []
    elif case == "missing-rest":
        entries.pop(1)
        expected = []
    _hr_root(root, entries)
    return expected


@pytest.mark.parametrize(
    "case",
    [
        "lower",
        "equal",
        "rest-derived",
        "both-derived",
        "hand-only",
        "missing-max",
        "missing-rest",
    ],
)
def test_hr_underlying_inconsistency_records(tmp_path: Path, case: str) -> None:
    expected = _stage_hr_inconsistent(tmp_path, case)
    assert _hr_records(tmp_path) == expected


@pytest.mark.parametrize("lt", [59, 61, 151, 183, 185])
@pytest.mark.parametrize("discipline", ["Run", "Ride"])
@pytest.mark.parametrize("origin", ["max", "rest", "threshold-only"])
def test_hr_threshold_bound_records(
    tmp_path: Path, lt: int, discipline: str, origin: str
) -> None:
    _hr_root(
        tmp_path,
        [
            _hr_entry(
                "max_hr_bpm",
                "2031-01-03",
                183,
                origin="derived" if origin == "max" else "hand",
            ),
            _hr_entry(
                "resting_hr_bpm",
                "2031-01-01",
                61,
                origin="derived" if origin == "rest" else "hand",
            ),
            _hr_entry(
                "lthr_bpm",
                "2031-01-06",
                lt,
                discipline=discipline,
                origin="derived" if origin == "threshold-only" else "hand",
            ),
        ],
    )
    expected = (
        []
        if origin == "threshold-only" or 61 < lt <= 183
        else [
            (
                "hr_benchmark_inconsistent",
                "athlete.toml",
                (
                    f"threshold_outside_reserve [2031-01-06, open) {discipline}: "
                    f"max_hr_bpm 183 bpm of 2031-01-03 "
                    f"({'derived' if origin == 'max' else 'hand-recorded'}); "
                    f"resting_hr_bpm 61 bpm of 2031-01-01 "
                    f"({'derived' if origin == 'rest' else 'hand-recorded'}); "
                    f"lthr_bpm {lt} bpm of 2031-01-06 (hand-recorded)"
                ),
                _HR_INCONSISTENT_REMEDY,
            )
        ]
    )
    assert _hr_records(tmp_path) == expected


def _stage_hr_periods(tmp_path: Path) -> list[tuple[str, str, str, str]]:
    _hr_root(
        tmp_path,
        [
            _hr_entry(
                "lthr_bpm", "2031-01-09", 187, discipline="Run", origin="derived"
            ),
            _hr_entry("max_hr_bpm", "2031-01-03", 183, origin="derived"),
            _hr_entry("resting_hr_bpm", "2031-01-01", 61),
            _hr_entry("lthr_bpm", "2031-01-04", 59, discipline="Run"),
            _hr_entry("lthr_bpm", "2031-01-02", 185, discipline="Ride"),
            _hr_entry("lthr_bpm", "2031-01-07", 59, discipline="Run"),
            _hr_entry("lthr_bpm", "2031-01-11", 151, discipline="Ride"),
        ],
    )
    expected = [
        (
            "threshold_outside_reserve [2031-01-03, 2031-01-11) Ride: "
            "max_hr_bpm 183 bpm of 2031-01-03 (derived); resting_hr_bpm "
            "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 185 bpm of "
            "2031-01-02 (hand-recorded)"
        ),
        (
            "threshold_outside_reserve [2031-01-04, 2031-01-07) Run: "
            "max_hr_bpm 183 bpm of 2031-01-03 (derived); resting_hr_bpm "
            "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 59 bpm of "
            "2031-01-04 (hand-recorded)"
        ),
        (
            "threshold_outside_reserve [2031-01-07, 2031-01-09) Run: "
            "max_hr_bpm 183 bpm of 2031-01-03 (derived); resting_hr_bpm "
            "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 59 bpm of "
            "2031-01-07 (hand-recorded)"
        ),
        (
            "threshold_outside_reserve [2031-01-09, open) Run: "
            "max_hr_bpm 183 bpm of 2031-01-03 (derived); resting_hr_bpm "
            "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 187 bpm of "
            "2031-01-09 (derived)"
        ),
    ]
    return [
        ("hr_benchmark_inconsistent", "athlete.toml", text, _HR_INCONSISTENT_REMEDY)
        for text in expected
    ]


def test_hr_periods_and_associations(tmp_path: Path) -> None:
    expected = _stage_hr_periods(tmp_path)
    assert _hr_records(tmp_path) == expected


@pytest.mark.parametrize(
    "case", ["malformed", "newer", "profile", "athlete", "permission", "os"]
)
def test_hr_unreadable_profile_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    import importlib

    from fitdocs.athlete import AthleteFileError

    module = importlib.import_module("fitdocs.audit")
    _hr_root(tmp_path, [])
    if case == "malformed":
        _write(tmp_path, "athlete.toml", "[")
        reason = (
            f"{tmp_path / 'athlete.toml'} is not valid TOML: Invalid "
            f"initial character for a key part (at end of document)"
        )
    elif case == "newer":
        _write(tmp_path, "athlete.toml", "profile_version=999\n")
        reason = (
            "athlete.toml declares profile_version = 999, which is newer "
            "than the schema version this fitdocs supports (2); install "
            "a newer fitdocs to read it"
        )
    elif case == "profile":
        _write(tmp_path, "athlete.toml", "[benchmarks]\nathlete=1\n")
        reason = "athlete.toml: benchmarks.athlete must be a table, got 1 (int)"
    elif case == "athlete":
        reason = "athlete.toml: synthetic athlete error"

        def fail(_root: Path) -> object:
            raise AthleteFileError(reason)

        monkeypatch.setattr(module, "load_profile", fail)
    else:
        reason = (
            "synthetic permission denied"
            if case == "permission"
            else "synthetic I/O failure"
        )
        real_open = Path.open

        def fail_open(path: Path, *args: object, **kwargs: object) -> object:
            if path == tmp_path / "athlete.toml":
                raise (
                    PermissionError(reason) if case == "permission" else OSError(reason)
                )
            return real_open(path, *args, **kwargs)  # type: ignore[call-overload]

        monkeypatch.setattr(Path, "open", fail_open)
    _write(tmp_path, "workouts/z.md", _doc_text(doc_version=1))
    (tmp_path / "fit-archive/AGENTS.md").unlink()
    _write(tmp_path, "wellness-archive/intervals-icu/stray.json", "synthetic orphan")
    _write(tmp_path, "fit-archive/" + "a" * 64 + ".fit", "synthetic archive")
    try:
        report: object = audit(tmp_path)
    except Exception as exc:
        report = exc
    expected = [
        ("athlete.toml", "athlete_profile_unreadable", reason, _HR_UNREADABLE_REMEDY),
        ("fit-archive/AGENTS.md", "declaration_missing", None, None),
        ("fit-archive/" + "a" * 64 + ".fit", "orphaned_source", None, None),
        (
            "wellness-archive/intervals-icu/stray.json",
            "wellness_orphaned_entry",
            None,
            None,
        ),
        ("workouts/z.md", "outdated_version", None, None),
    ]
    observed = (
        [
            (
                f.subject,
                f.kind.value,
                f.detail if f.subject == "athlete.toml" else None,
                f.remedy if f.subject == "athlete.toml" else None,
            )
            for f in report.findings
        ]
        if isinstance(report, AuditReport)
        else report
    )
    assert observed == expected


def test_hr_loads_profile_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    module = importlib.import_module("fitdocs.audit")
    _stage_hr_takeover(tmp_path, "dual")
    roots: list[Path] = []
    load = module.load_profile

    def record(root: Path) -> object:
        roots.append(root)
        return load(root)

    monkeypatch.setattr(module, "load_profile", record)
    module._benchmark_findings(tmp_path)
    assert roots == [tmp_path]


@pytest.mark.parametrize("case", ["present", "absent"])
def test_hr_helper_open_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    import importlib
    import io

    module = importlib.import_module("fitdocs.audit")
    if case == "present":
        _stage_hr_takeover(tmp_path, "dual")
    for path in (
        "fit-archive/decoy.fit",
        "wellness/2031.csv",
        "wellness/manifest.toml",
        "wellness-archive/decoy.json",
    ):
        _write(tmp_path, path, "synthetic decoy")
    opened: list[tuple[str, object]] = []
    real_io_open, real_open = io.open, builtins.open

    def record_io(path: object, *args: object, **kwargs: object) -> object:
        if isinstance(path, (str, Path)):
            opened.append(
                (
                    Path(path).relative_to(tmp_path).as_posix(),
                    args[0] if args else kwargs.get("mode", "r"),
                )
            )
        return real_io_open(path, *args, **kwargs)  # type: ignore[call-overload]

    def record_builtin(path: object, *args: object, **kwargs: object) -> object:
        if isinstance(path, (str, Path)):
            opened.append(
                (
                    Path(path).relative_to(tmp_path).as_posix(),
                    args[0] if args else kwargs.get("mode", "r"),
                )
            )
        return real_open(path, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(io, "open", record_io)
    monkeypatch.setattr(builtins, "open", record_builtin)
    module._benchmark_findings(tmp_path)
    assert opened == ([("athlete.toml", "rb")] if case == "present" else [])


@pytest.mark.parametrize(
    "case", ["dual", "later-hand", "later-derived", "back-reach", "absent"]
)
def test_hr_preserves_tree(tmp_path: Path, case: str) -> None:
    if case != "absent":
        _stage_hr_takeover(tmp_path, case)
    before = _snapshot(tmp_path)
    directories = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()}
    audit(tmp_path)
    assert (
        _snapshot(tmp_path),
        {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()},
    ) == (before, directories)


def test_hr_absent_profile_has_no_findings(tmp_path: Path) -> None:
    ensure_declarations(tmp_path)
    assert _hr_records(tmp_path) == []


def test_hr_unrelated_error_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    module = importlib.import_module("fitdocs.audit")

    def fail(_root: Path) -> object:
        raise ValueError("unrelated implementation error")

    monkeypatch.setattr(module, "load_profile", fail)
    try:
        observed: object = audit(tmp_path)
    except ValueError as exc:
        observed = str(exc)
    assert observed == "unrelated implementation error"


@pytest.mark.parametrize("violation", ["maximum", "threshold"])
def test_hr_recurring_periods(tmp_path: Path, violation: str) -> None:
    if violation == "maximum":
        entries = [
            _hr_entry("max_hr_bpm", "2031-01-20", 53, applies="2031-01-01"),
            _hr_entry("max_hr_bpm", "2031-01-10", 183, applies="2031-01-05"),
            _hr_entry("resting_hr_bpm", "2031-01-01", 61, origin="derived"),
        ]
        descriptions = [
            (
                "max_not_above_rest [2031-01-01, 2031-01-05): max_hr_bpm 53 "
                "bpm of 2031-01-20 (hand-recorded); resting_hr_bpm 61 bpm of "
                "2031-01-01 (derived)"
            ),
            (
                "max_not_above_rest [2031-01-20, open): max_hr_bpm 53 bpm of "
                "2031-01-20 (hand-recorded); resting_hr_bpm 61 bpm of "
                "2031-01-01 (derived)"
            ),
        ]
    else:
        entries = [
            _hr_entry(
                "lthr_bpm", "2031-01-20", 187, discipline="Run", applies="2031-01-01"
            ),
            _hr_entry(
                "lthr_bpm", "2031-01-10", 151, discipline="Run", applies="2031-01-05"
            ),
            _hr_entry("max_hr_bpm", "2031-01-01", 183, origin="derived"),
            _hr_entry("resting_hr_bpm", "2031-01-01", 61),
        ]
        descriptions = [
            (
                "threshold_outside_reserve [2031-01-01, 2031-01-05) Run: "
                "max_hr_bpm 183 bpm of 2031-01-01 (derived); resting_hr_bpm "
                "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 187 bpm of "
                "2031-01-20 (hand-recorded)"
            ),
            (
                "threshold_outside_reserve [2031-01-20, open) Run: "
                "max_hr_bpm 183 bpm of 2031-01-01 (derived); resting_hr_bpm "
                "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 187 bpm of "
                "2031-01-20 (hand-recorded)"
            ),
        ]
    _hr_root(tmp_path, entries)
    assert _hr_records(tmp_path) == [
        ("hr_benchmark_inconsistent", "athlete.toml", text, _HR_INCONSISTENT_REMEDY)
        for text in descriptions
    ]


@pytest.mark.parametrize("changed", ["max", "rest"])
def test_hr_same_value_new_entry_periods(tmp_path: Path, changed: str) -> None:
    entries = [
        _hr_entry("max_hr_bpm", "2031-01-02", 53, origin="derived"),
        _hr_entry("resting_hr_bpm", "2031-01-03", 61),
        _hr_entry(
            "max_hr_bpm" if changed == "max" else "resting_hr_bpm",
            "2031-01-08",
            53 if changed == "max" else 61,
            origin="derived" if changed == "max" else "hand",
        ),
    ]
    _hr_root(tmp_path, entries)
    expected = [
        (
            "max_not_above_rest [2031-01-03, 2031-01-08): max_hr_bpm 53 "
            "bpm of 2031-01-02 (derived); resting_hr_bpm 61 bpm of "
            "2031-01-03 (hand-recorded)"
        ),
        (
            "max_not_above_rest [2031-01-08, open): max_hr_bpm 53 bpm of "
            "2031-01-08 (derived); resting_hr_bpm 61 bpm of 2031-01-03 "
            "(hand-recorded)"
        )
        if changed == "max"
        else (
            "max_not_above_rest [2031-01-08, open): max_hr_bpm 53 bpm of "
            "2031-01-02 (derived); resting_hr_bpm 61 bpm of 2031-01-08 "
            "(hand-recorded)"
        ),
    ]
    assert _hr_records(tmp_path) == [
        ("hr_benchmark_inconsistent", "athlete.toml", text, _HR_INCONSISTENT_REMEDY)
        for text in expected
    ]


def test_hr_composes_with_existing_checks(tmp_path: Path) -> None:
    takeovers = _stage_hr_takeover(tmp_path, "dual")
    with (tmp_path / "athlete.toml").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n[[benchmarks.Run.lthr_bpm]]\nvalue=194\nmeasured_on=2031-01-09\n"
        )
    _write(tmp_path, "workouts/a.md", _doc_text(doc_version=1))
    _write(tmp_path, "wellness-archive/intervals-icu/stray.json", "synthetic orphan")
    expected = [
        (
            "hr_benchmark_inconsistent",
            "athlete.toml",
            "threshold_outside_reserve [2031-01-09, 2031-01-15) Run: "
            "max_hr_bpm 193 bpm of 2031-01-08 (derived); "
            "resting_hr_bpm 63 bpm of 2031-01-04 (hand-recorded); "
            "lthr_bpm 194 bpm of 2031-01-09 (hand-recorded)",
            _HR_INCONSISTENT_REMEDY,
        ),
        (
            "hr_benchmark_inconsistent",
            "athlete.toml",
            "threshold_outside_reserve [2031-01-15, open) Run: "
            "max_hr_bpm 193 bpm of 2031-01-08 (derived); "
            "resting_hr_bpm 57 bpm of 2031-01-15 (derived); "
            "lthr_bpm 194 bpm of 2031-01-09 (hand-recorded)",
            _HR_INCONSISTENT_REMEDY,
        ),
        *takeovers,
    ]
    records = _hr_records(tmp_path)
    assert (records[:4], [(r[0], r[1]) for r in records[4:]]) == (
        expected,
        [
            ("wellness_orphaned_entry", "wellness-archive/intervals-icu/stray.json"),
            ("outdated_version", "workouts/a.md"),
        ],
    )


def _hr_decode_fixture(root: Path) -> str:
    ensure_declarations(root)
    payload = b"profile_version = 2\n# synthetic athlete comment: caf\xe9\n"
    (root / "athlete.toml").write_bytes(payload)
    _write(root, "workouts/old.md", _doc_text(doc_version=1))
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return str(exc)
    raise RuntimeError("fixture must contain invalid UTF-8")


def test_hr_decode_failure_continues(tmp_path: Path) -> None:
    reason = _hr_decode_fixture(tmp_path)
    try:
        report: object = audit(tmp_path)
    except Exception as exc:
        report = exc
    observed = (
        [
            (f.kind.value, f.subject, f.detail, f.remedy)
            if f.subject == "athlete.toml"
            else (f.kind.value, f.subject, None, None)
            for f in report.findings
        ]
        if isinstance(report, AuditReport)
        else (type(report).__name__, str(report))
    )
    assert observed == [
        ("athlete_profile_unreadable", "athlete.toml", reason, _HR_UNREADABLE_REMEDY),
        ("outdated_version", "workouts/old.md", None, None),
    ]


@pytest.mark.parametrize(
    "violation,measured",
    [
        ("maximum", "max"),
        ("maximum", "rest"),
        ("threshold", "max"),
        ("threshold", "rest"),
        ("threshold", "threshold"),
    ],
)
def test_hr_explicit_measured_inconsistency_origins(
    tmp_path: Path, violation: str, measured: str
) -> None:
    maximum = 53 if violation == "maximum" else 183
    entries = [
        _hr_entry(
            "max_hr_bpm",
            "2031-01-01",
            maximum,
            origin="measured" if measured == "max" else "derived",
        ),
        _hr_entry(
            "resting_hr_bpm",
            "2031-01-02",
            61,
            origin="derived"
            if measured == "max"
            else "measured"
            if measured == "rest"
            else "hand",
        ),
    ]
    max_origin = "hand-recorded" if measured == "max" else "derived"
    rest_origin = "derived" if measured == "max" else "hand-recorded"
    if violation == "maximum":
        text = (
            "max_not_above_rest [2031-01-02, open): max_hr_bpm 53 bpm of "
            f"2031-01-01 ({max_origin}); resting_hr_bpm 61 bpm of "
            f"2031-01-02 ({rest_origin})"
        )
    else:
        entries.append(
            _hr_entry(
                "lthr_bpm",
                "2031-01-03",
                187,
                discipline="Run",
                origin="measured" if measured == "threshold" else "hand",
            )
        )
        text = (
            "threshold_outside_reserve [2031-01-03, open) Run: max_hr_bpm "
            f"183 bpm of 2031-01-01 ({max_origin}); resting_hr_bpm 61 bpm "
            f"of 2031-01-02 ({rest_origin}); lthr_bpm 187 bpm of "
            "2031-01-03 (hand-recorded)"
        )
    _hr_root(tmp_path, entries)
    assert _hr_records(tmp_path) == [
        ("hr_benchmark_inconsistent", "athlete.toml", text, _HR_INCONSISTENT_REMEDY)
    ]


def test_hr_mixed_violation_inspect_tie_order(tmp_path: Path) -> None:
    _hr_root(
        tmp_path,
        [
            _hr_entry("max_hr_bpm", "2031-01-01", 183, origin="derived"),
            _hr_entry("resting_hr_bpm", "2031-01-01", 61),
            _hr_entry("lthr_bpm", "2031-01-02", 187, discipline="Run"),
            _hr_entry("lthr_bpm", "2031-01-02", 59, discipline="Ride"),
            _hr_entry("max_hr_bpm", "2031-01-05", 53, origin="derived"),
        ],
    )
    assert _hr_records(tmp_path) == [
        (
            "hr_benchmark_inconsistent",
            "athlete.toml",
            "threshold_outside_reserve [2031-01-02, 2031-01-05) Ride: "
            "max_hr_bpm 183 bpm of 2031-01-01 (derived); resting_hr_bpm "
            "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 59 bpm of "
            "2031-01-02 (hand-recorded)",
            _HR_INCONSISTENT_REMEDY,
        ),
        (
            "hr_benchmark_inconsistent",
            "athlete.toml",
            "threshold_outside_reserve [2031-01-02, 2031-01-05) Run: "
            "max_hr_bpm 183 bpm of 2031-01-01 (derived); resting_hr_bpm "
            "61 bpm of 2031-01-01 (hand-recorded); lthr_bpm 187 bpm of "
            "2031-01-02 (hand-recorded)",
            _HR_INCONSISTENT_REMEDY,
        ),
        (
            "hr_benchmark_inconsistent",
            "athlete.toml",
            "max_not_above_rest [2031-01-05, open): max_hr_bpm 53 bpm "
            "of 2031-01-05 (derived); resting_hr_bpm 61 bpm of "
            "2031-01-01 (hand-recorded)",
            _HR_INCONSISTENT_REMEDY,
        ),
    ]


@pytest.mark.parametrize(
    "state",
    [
        "absent",
        "empty",
        "hand-only",
        "takeover",
        "period",
        "mixed",
        "malformed",
        "newer",
        "profile",
        "athlete",
        "permission",
        "os",
        "unicode",
    ],
)
@pytest.mark.parametrize(
    "field", ["calls", "opens", "bytes", "mtimes", "directories", "findings"]
)
def test_hr_helper_state_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str, field: str
) -> None:
    import importlib
    import io

    from fitdocs.athlete import AthleteFileError

    module = importlib.import_module("fitdocs.audit")
    errors = {"malformed", "newer", "profile", "athlete", "permission", "os", "unicode"}
    injected = {"athlete", "permission", "os"}
    if state in ("takeover", "mixed"):
        _stage_hr_takeover(tmp_path, "dual")
        if state == "mixed":
            with (tmp_path / "athlete.toml").open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n[[benchmarks.Run.lthr_bpm]]\nvalue=194\nmeasured_on=2031-01-09\n"
                )
    elif state == "period":
        _hr_root(
            tmp_path,
            [
                _hr_entry("max_hr_bpm", "2031-01-01", 53, origin="derived"),
                _hr_entry("resting_hr_bpm", "2031-01-02", 61),
            ],
        )
    elif state == "hand-only":
        _hr_root(tmp_path, [_hr_entry("max_hr_bpm", "2031-01-01", 183)])
    elif state == "unicode":
        _hr_decode_fixture(tmp_path)
    else:
        ensure_declarations(tmp_path)
        if state != "absent":
            _hr_root(tmp_path, [])
        if state in ("malformed", "newer", "profile"):
            _write(
                tmp_path,
                "athlete.toml",
                {
                    "malformed": "[",
                    "newer": "profile_version=999\n",
                    "profile": "[benchmarks]\nathlete=1\n",
                }[state],
            )
    for relative in (
        "fit-archive/decoy.fit",
        "wellness/2031.csv",
        "wellness/manifest.toml",
        "wellness-archive/decoy.json",
    ):
        _write(tmp_path, relative, "synthetic decoy")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            _age(path)
    before = _snapshot(tmp_path)
    directories = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()}
    calls: list[Path] = []
    opened: list[tuple[str, object]] = []
    found: object = None
    real_load, helper = module.load_profile, module._benchmark_findings
    real_io, real_builtin = io.open, builtins.open

    def load(root: Path) -> object:
        calls.append(root)
        if state == "athlete":
            raise AthleteFileError("synthetic athlete error")
        if state == "permission":
            raise PermissionError("synthetic permission denied")
        if state == "os":
            raise OSError("synthetic I/O failure")
        return real_load(root)

    def record_io(path: object, *args: object, **kwargs: object) -> object:
        if isinstance(path, (str, Path)):
            opened.append(
                (
                    Path(path).relative_to(tmp_path).as_posix(),
                    args[0] if args else kwargs.get("mode", "r"),
                )
            )
        return real_io(path, *args, **kwargs)  # type: ignore[call-overload]

    def record_builtin(path: object, *args: object, **kwargs: object) -> object:
        if isinstance(path, (str, Path)):
            opened.append(
                (
                    Path(path).relative_to(tmp_path).as_posix(),
                    args[0] if args else kwargs.get("mode", "r"),
                )
            )
        return real_builtin(path, *args, **kwargs)  # type: ignore[call-overload]

    def recorded_helper(root: Path) -> tuple[Finding, ...]:
        nonlocal found
        with monkeypatch.context() as patch:
            patch.setattr(module, "load_profile", load)
            patch.setattr(io, "open", record_io)
            patch.setattr(builtins, "open", record_builtin)
            try:
                result = helper(root)
            except Exception as exc:
                found = (type(exc).__name__, str(exc))
                return ()
            found = tuple(f.kind.value for f in result)
            return result

    monkeypatch.setattr(module, "_benchmark_findings", recorded_helper)
    audit(tmp_path)
    after = _snapshot(tmp_path)
    observed = {
        "calls": calls,
        "opens": opened,
        "bytes": {p: value[0] for p, value in after.items()},
        "mtimes": {p: value[1] for p, value in after.items()},
        "directories": {
            p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()
        },
        "findings": found,
    }
    expected = {
        "calls": [tmp_path],
        "opens": []
        if state == "absent" or state in injected
        else [("athlete.toml", "rb")],
        "bytes": {p: value[0] for p, value in before.items()},
        "mtimes": {p: value[1] for p, value in before.items()},
        "directories": directories,
        "findings": ("athlete_profile_unreadable",)
        if state in errors
        else {
            "absent": (),
            "empty": (),
            "hand-only": (),
            "takeover": ("hr_benchmark_takeover", "hr_benchmark_takeover"),
            "period": ("hr_benchmark_inconsistent",),
            "mixed": (
                "hr_benchmark_takeover",
                "hr_benchmark_takeover",
                "hr_benchmark_inconsistent",
                "hr_benchmark_inconsistent",
            ),
        }.get(state),
    }
    assert observed[field] == expected[field]


@pytest.mark.parametrize(
    "state",
    [
        "absent",
        "empty",
        "hand-only",
        "takeover",
        "period",
        "mixed",
        "malformed",
        "newer",
        "profile",
        "athlete",
        "permission",
        "os",
        "unicode",
    ],
)
def test_hr_helper_preserves_stable_tree_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    import importlib
    import stat

    module = importlib.import_module("fitdocs.audit")
    helper = module._benchmark_findings
    before: object = None
    after: object = None

    def snapshot(root: Path) -> dict[Path, tuple[object, ...]]:
        result = {}
        for path in [root, *sorted(root.rglob("*"))]:
            metadata = path.lstat()
            result[path.relative_to(root)] = (
                metadata.st_mode,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
                metadata.st_size,
                metadata.st_nlink,
                path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None,
            )
        return result

    def recorded_helper(root: Path) -> tuple[Finding, ...]:
        nonlocal before, after
        for path in [root, *root.rglob("*")]:
            if path.is_dir():
                _age(path)
        before = snapshot(root)
        result = helper(root)
        after = snapshot(root)
        return result

    monkeypatch.setattr(module, "_benchmark_findings", recorded_helper)
    test_hr_helper_state_matrix(tmp_path, monkeypatch, state, "findings")
    assert before is not None and after == before
