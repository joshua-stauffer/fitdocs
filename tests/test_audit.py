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
from pathlib import Path
from unittest import mock

import pytest

from fitdocs.audit import AuditReport, Finding, FindingKind, audit
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
_REMEDY_HOLD_RECORD = "delete it and run `fitdocs regen`, which rebuilds it"


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
