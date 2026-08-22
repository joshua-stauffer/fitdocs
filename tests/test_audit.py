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
import time
from pathlib import Path
from unittest import mock

import pytest

from fitdocs.audit import AuditReport, Finding, FindingKind, audit
from fitdocs.contract import DOC_VERSION
from fitdocs.declaration import ensure_declarations
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.layout import ARCHIVE_DIR, WORKOUTS_DIR
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
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _clean_doc_text())
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
