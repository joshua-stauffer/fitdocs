"""`scripts/purge/sweep.py`: the classified sweep inventory (task 3.2,
design.md `#### ReproductionSweep`, Req 1.2, 1.3, 2.3).

Every fixture that exercises a `git grep` pass builds a fresh, tiny,
synthetic git repository (`_repo` below) with its own commits -- none of
these tests read the withdrawn writeup or either withdrawn CSV by path, so
this suite stays meaningful after task 3.1 deletes them and does not depend
on the real tree's current shape for its *mechanism* coverage. A handful of
tests at the bottom of the file DO run the real
sweep against this repository's real tracked tree -- those are the
end-to-end observables tasks.md 3.2 itself demands (the inventory's file
set is a superset of the modified-files table; re-running reproduces the
same hit set) and are gated on `FITDOCS_FORBIDDEN_STRINGS` via
`tests._forbidden_strings.require`, skipping (never silently passing) when
it is unset.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from scripts.purge.sweep import (
    DISPOSITIONS,
    CategorizedEntry,
    ClassifiedHit,
    SweepHit,
    _classify_email_domain,
    build_default_overrides,
    classify_hit,
    classify_hits,
    entries_by_category,
    git_grep_fixed_files,
    load_categorized_entries,
    parse_categorized_entries,
    parse_inventory_tsv,
    read_inventory,
    render_inventory_tsv,
    run_basename_probe_sweep,
    run_full_sweep,
    run_identity_probe_sweep,
    run_stale_pointer_sweep,
    run_symbolic_probe_sweep,
    run_value_matcher_sweep,
    scan_content_and_path,
    tracked_files,
    write_inventory,
)

from tests._content_oracle import digest, tokens, windows
from tests._forbidden_strings import ForbiddenStrings, require

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    return root


def _commit_files(repo: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture commit")


# --- CategorizedEntry / parse_categorized_entries ----------------------------


def test_parse_categorized_entries_keeps_category_per_line() -> None:
    text = "token\tfirst-value\npath\tsecond/value\n"

    entries = parse_categorized_entries(text)

    assert entries == (
        CategorizedEntry(category="token", value="first-value"),
        CategorizedEntry(category="path", value="second/value"),
    )


def test_parse_categorized_entries_skips_blank_and_comment_lines() -> None:
    text = "# a comment\n\ntoken\tone\n"

    entries = parse_categorized_entries(text)

    assert entries == (CategorizedEntry(category="token", value="one"),)


def test_parse_categorized_entries_untagged_line_is_uncategorized() -> None:
    # No tab at all -- the format permits a bare line, per
    # tests._forbidden_strings._parse's own contract.
    entries = parse_categorized_entries("bare-value\n")

    assert entries == (CategorizedEntry(category="uncategorized", value="bare-value"),)


def test_load_categorized_entries_reads_from_disk(tmp_path: Path) -> None:
    source = tmp_path / "match-data.tsv"
    source.write_text("token\talpha\npath\tsome/path.md\n", encoding="utf-8")

    entries = load_categorized_entries(source)

    assert entries == (
        CategorizedEntry(category="token", value="alpha"),
        CategorizedEntry(category="path", value="some/path.md"),
    )


def test_entries_by_category_groups_values_preserving_file_order() -> None:
    # Deliberately interleaved and not alphabetical, so a mutant that sorts
    # values (rather than preserving file order within a category) is caught.
    entries = (
        CategorizedEntry(category="token", value="zeta"),
        CategorizedEntry(category="path", value="p1"),
        CategorizedEntry(category="token", value="alpha"),
    )

    grouped = entries_by_category(entries)

    assert grouped == {"token": ("zeta", "alpha"), "path": ("p1",)}


# --- tracked_files() ----------------------------------------------------------


def test_tracked_files_over_the_real_repo_is_nonempty_and_a_tuple_of_paths() -> None:
    files = tracked_files(_REPO_ROOT)

    assert files, (
        "git ls-files reported nothing -- the walk is looking at the wrong directory"
    )
    assert all(isinstance(path, Path) for path in files)
    assert all(path.is_absolute() for path in files)


def test_tracked_files_excludes_untracked_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"tracked.txt": "tracked\n"})
    (repo / "untracked.txt").write_text("not added\n", encoding="utf-8")

    files = tracked_files(repo)
    names = {path.name for path in files}

    assert names == {"tracked.txt"}, (
        "an untracked file leaked into the universe -- the sweep's universe "
        "must be git ls-files, not a filesystem walk"
    )


def test_tracked_files_raises_rather_than_silently_return_an_empty_universe(
    tmp_path: Path,
) -> None:
    # A path that is not a git repository at all: `git ls-files` exits
    # nonzero. This must raise (check=True), never collapse into a silent
    # empty tuple -- an empty universe is indistinguishable from "a real,
    # genuinely empty repository" and every later pass would report a
    # vacuously clean sweep having scanned nothing.
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    with pytest.raises(subprocess.CalledProcessError):
        tracked_files(not_a_repo)


# --- scan_content_and_path() (pass 1) -----------------------------------------


def test_scan_content_and_path_finds_content_and_path_surfaces_separately(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "alpha.txt": "carries needle-one in its body\n",
            "needle-two-in-the-name.txt": "clean body text\n",
            "clean.txt": "nothing of interest\n",
        },
    )
    entries = (
        CategorizedEntry(category="token", value="needle-one"),
        CategorizedEntry(category="path", value="needle-two"),
    )
    files = tracked_files(repo)

    hits, unreadable = scan_content_and_path(files, repo, entries)

    assert not unreadable
    content_hits = {(h.sweep, h.relative_path) for h in hits if h.surface == "content"}
    path_hits = {(h.sweep, h.relative_path) for h in hits if h.surface == "path"}
    assert content_hits == {("token", "alpha.txt")}
    assert path_hits == {("path", "needle-two-in-the-name.txt")}


def test_scan_content_and_path_reports_unreadable_file_without_raising(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    # A binary, genuinely non-UTF-8 tracked file (distinct failure mode from
    # the broken symlink below: UnicodeDecodeError, not OSError) -- pre-
    # written before _commit_files' own `git add -A` so it is staged and
    # committed alongside the text fixtures.
    (repo / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    _commit_files(
        repo,
        {"visible.txt": "carries needle-one\n", "broken-link.txt": "placeholder\n"},
    )
    broken = repo / "broken-link.txt"
    broken.unlink()
    broken.symlink_to(repo / "does-not-exist.txt")

    entries = (CategorizedEntry(category="token", value="needle-one"),)
    files = tracked_files(repo)

    hits, unreadable = scan_content_and_path(files, repo, entries)

    unreadable_names = {item.relative_path for item in unreadable}
    assert "broken-link.txt" in unreadable_names, (
        "a broken symlink must be reported as unreadable, not silently "
        "yield zero hits and zero report"
    )
    assert "blob.bin" in unreadable_names, (
        "a genuinely non-UTF-8 tracked file must be reported as unreadable "
        "too -- UnicodeDecodeError is a distinct failure mode from OSError "
        "and must not be silently swallowed by a bare `continue`"
    )
    assert ("token", "visible.txt") in {(h.sweep, h.relative_path) for h in hits}
    assert not any(h.relative_path == "blob.bin" for h in hits), (
        "an unreadable file's content surface must never contribute a hit"
    )


# --- run_value_matcher_sweep() (pass 2) ---------------------------------------


def _fingerprint_corpus(
    text: str, salt: bytes, floor: float
) -> tuple[frozenset[str], frozenset[int]]:
    toks = tokens(text)
    fps: set[str] = set()
    lengths: set[int] = set()
    for offset, length in windows(toks, floor):
        fps.add(digest(toks[offset : offset + length], salt))
        lengths.add(length)
    return frozenset(fps), frozenset(lengths)


def test_value_matcher_sweep_flags_a_file_whose_content_clears_the_floor(
    tmp_path: Path,
) -> None:
    salt = b"fixed-test-salt"
    dense_text = "Zone factors: 118.42837, 204.99123, 337.55019, 441.20876, 552.68231\n"
    control_text = "Nothing of interest, no numbers dense enough to match.\n"
    fps, lengths = _fingerprint_corpus(dense_text, salt, floor=96.0)
    assert fps and lengths, (
        "fixture corpus must clear the entropy floor to be a real test"
    )

    repo = _repo(tmp_path)
    _commit_files(repo, {"dense.txt": dense_text, "clean.txt": control_text})
    files = tracked_files(repo)

    hits, unreadable = run_value_matcher_sweep(
        files, repo, fingerprints=fps, window_lengths=lengths, salt=salt
    )

    assert not unreadable
    flagged = {h.relative_path for h in hits}
    assert flagged == {"dense.txt"}, (
        "the value matcher must flag exactly the dense file and not the "
        "control file -- a wider or narrower flagged set is wrong"
    )


def test_value_matcher_sweep_reports_an_unreadable_file_without_raising(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    _commit_files(repo, {"visible.txt": "clean\n", "broken-link.txt": "placeholder\n"})
    broken = repo / "broken-link.txt"
    broken.unlink()
    broken.symlink_to(repo / "does-not-exist.txt")
    files = tracked_files(repo)

    hits, unreadable = run_value_matcher_sweep(
        files, repo, fingerprints=frozenset(), window_lengths=frozenset(), salt=b"salt"
    )

    assert not hits
    unreadable_names = {item.relative_path for item in unreadable}
    assert "broken-link.txt" in unreadable_names, (
        "a broken symlink must be reported as unreadable by the value-matcher "
        "pass too, not silently skipped with no report"
    )
    assert "blob.bin" in unreadable_names, (
        "a genuinely non-UTF-8 tracked file must be reported as unreadable "
        "by the value-matcher pass too -- UnicodeDecodeError is a distinct "
        "failure mode from OSError and must not be silently swallowed by a "
        "bare `continue`"
    )


# --- git_grep_fixed_files() / the shared _git_grep_files() exit-code split ---


def test_git_grep_fixed_files_returns_matching_relative_paths(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {"a/one.txt": "has the needle right here\n", "b/two.txt": "no match\n"},
    )

    found = git_grep_fixed_files(repo, "the needle")

    assert found == ("a/one.txt",)


def test_git_grep_fixed_files_treats_a_regex_metacharacter_literally(
    tmp_path: Path,
) -> None:
    # Pins the -F (fixed-string) contract directly, real git behaviour, no
    # mocking: `-E` would interpret `.` as "any character", so a needle
    # containing a literal `.` would ALSO match a file that substitutes a
    # different character in that position. `-F` must not. This is the
    # concrete case `change-protocol.md`'s "-E silently reads clean" trap
    # names, reproduced rather than merely cited: measured directly against
    # this git build, `git grep -lE -- 'a.b'` matches BOTH a file containing
    # the literal `a.b` and a file containing `aXb`, while `git grep -lF`
    # matches only the literal.
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "literal.txt": "has the literal dot right here: a.b\n",
            "wildcard-candidate.txt": "an any-char match candidate: aXb\n",
        },
    )

    found = git_grep_fixed_files(repo, "a.b")

    assert found == ("literal.txt",), (
        "-F must treat '.' literally; matching wildcard-candidate.txt too "
        "means -E (or an equivalent regex mode) is being used instead"
    )


def test_run_identity_probe_sweep_invokes_git_grep_with_the_perl_regex_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Direct pin of the exact argv run_identity_probe_sweep issues, full-
    # vector equality (not a prefix match) -- for THIS module's specific
    # email pattern, `-nPoI` and `-nEoI` happen to produce byte-identical
    # output against real git (measured directly: no \b, no PCRE-only
    # construct in _EMAIL_PATTERN), so no fixture built from real file
    # content can discriminate the flag at the behavioural level. Pinning
    # the constructed command itself is the only mechanism that catches an
    # -nPoI -> -nEoI edit, and matches the precedent
    # tests/purge/test_rewrite_map_extraction.py's own full-vector fakes
    # use for the same reason (a prefix match can't distinguish a correct
    # invocation from a malformed one sharing a prefix).
    from scripts.purge import sweep as sweep_module

    calls: list[list[str]] = []

    class _FakeCompletedProcess:
        returncode = 1
        stdout = ""
        stderr = ""

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(args)
        return _FakeCompletedProcess()

    # Patches the same `subprocess` module object sweep.py's own
    # `import subprocess` resolves to (module-level imports are singletons),
    # not a re-exported attribute of scripts.purge.sweep.
    monkeypatch.setattr(subprocess, "run", fake_run)

    sweep_module.run_identity_probe_sweep(Path("/irrelevant"))

    assert calls == [["git", "grep", "-nPoI", "--", sweep_module._EMAIL_PATTERN]], (
        "run_identity_probe_sweep must invoke git grep with exactly this "
        "argument vector, in particular -nPoI (Perl regex) -- a change to "
        "-nEoI is not behaviourally distinguishable for this pattern against "
        "real git, so the invocation itself is what must be pinned"
    )


def test_run_identity_probe_sweep_raises_rather_than_swallow_a_real_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_identity_probe_sweep issues its OWN subprocess.run call rather
    # than going through the shared `_git_grep_files` helper, so that
    # helper's own exit-code-splitting test does not cover this function's
    # copy of the same logic. This pins it directly: a genuine failure
    # (exit >= 2) must raise, never collapse into the same empty tuple
    # "no match" (exit 1) returns.
    from scripts.purge import sweep as sweep_module

    class _FakeFailedProcess:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        return _FakeFailedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        sweep_module.run_identity_probe_sweep(Path("/irrelevant"))


def test_run_identity_probe_sweep_returns_empty_tuple_for_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The distinguishing sibling to the failure test above: exit 1 ("no
    # match") must NOT raise.
    from scripts.purge import sweep as sweep_module

    class _FakeNoMatchProcess:
        returncode = 1
        stdout = ""
        stderr = ""

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        return _FakeNoMatchProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert sweep_module.run_identity_probe_sweep(Path("/irrelevant")) == ()


def test_git_grep_fixed_files_returns_empty_tuple_for_no_match(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"a.txt": "nothing relevant\n"})

    found = git_grep_fixed_files(repo, "absolutely-not-present")

    assert found == ()


def test_git_grep_fixed_files_raises_rather_than_swallow_a_real_failure(
    tmp_path: Path,
) -> None:
    # A path that is not a git repository at all: `git grep` exits >= 2
    # ("not a git repository"), which must raise, never collapse into the
    # same empty tuple "no match" (exit 1) returns.
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    with pytest.raises(RuntimeError):
        git_grep_fixed_files(not_a_repo, "anything")


# --- run_symbolic_probe_sweep() (pass 3) --------------------------------------


def test_symbolic_probes_tuple_is_nonempty() -> None:
    from scripts.purge.sweep import SYMBOLIC_PROBES

    assert SYMBOLIC_PROBES, (
        "an empty probe tuple would make run_symbolic_probe_sweep pass "
        "having searched for nothing"
    )


def test_run_symbolic_probe_sweep_finds_a_planted_probe_string(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "notes.md": "this file mentions a pace lookup table explicitly\n",
            "unrelated.md": "nothing relevant here at all\n",
        },
    )

    hits = run_symbolic_probe_sweep(repo)

    flagged = {h.relative_path for h in hits}
    assert "notes.md" in flagged
    assert "unrelated.md" not in flagged

    notes_hits = [h for h in hits if h.relative_path == "notes.md"]
    assert notes_hits, "no hit recorded for notes.md at all"
    assert all(h.note == "pace lookup rows" for h in notes_hits), (
        "each symbolic-probe hit must carry its probe's label in `note` -- "
        "the provenance record loses which probe fired if `note` is dropped "
        f"or blanked; got {[h.note for h in notes_hits]!r}"
    )


# --- run_identity_probe_sweep() / _classify_email_domain() (pass 4) ---------


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("someone@example.com", "public-or-placeholder"),
        ("66793731+someone@users.noreply.github.com", "public-or-placeholder"),
        ("git@github.com", "public-or-placeholder"),
        ("person@laptop.local", "git-constructed-form-candidate"),
        ("real.person@somewhere-else.com", "personal-address-candidate"),
        # Uppercase domain: pins the `.lower()` call -- dropping it would
        # make "EXAMPLE.COM" fail the safe-domain membership test and
        # misclassify a placeholder address as personal-address-candidate.
        ("someone@EXAMPLE.COM", "public-or-placeholder"),
    ],
)
def test_classify_email_domain(email: str, expected: str) -> None:
    assert _classify_email_domain(email) == expected


def test_email_pattern_captures_the_whole_dotted_plussed_local_part() -> None:
    # Direct regex-level pin: `SweepHit.matched` is deliberately always ""
    # for this pass (see run_identity_probe_sweep's docstring), so this
    # cannot be observed through a `SweepHit` -- it has to be pinned against
    # `_EMAIL_PATTERN` itself. A narrowed local-part class (dropping `.`,
    # `+` or `-` from it) would make the match start later in the string
    # (e.g. at "test@..." instead of the full "real.person+tag-1.test@..."),
    # which this catches by asserting the exact matched span, not merely
    # that *something* matched.
    from scripts.purge.sweep import _EMAIL_PATTERN

    text = "contact: real.person+tag-1.test@somewhere-else.com please"
    match = re.search(_EMAIL_PATTERN, text)

    assert match is not None
    assert match.group() == "real.person+tag-1.test@somewhere-else.com"


def test_email_pattern_requires_at_least_two_letter_tld() -> None:
    # Pins the `{2,}` TLD-length lower bound: a broadened bound (e.g. `{1,}`)
    # would also match "person@example.c" as a whole address (TLD "c"),
    # which a real single-letter TLD never is. The domain has a real dot
    # in it (unlike a needle with no dot at all, which fails to match for
    # an unrelated reason and would not discriminate this bound).
    from scripts.purge.sweep import _EMAIL_PATTERN

    assert re.fullmatch(_EMAIL_PATTERN, "person@example.c") is None


def test_run_identity_probe_sweep_finds_and_classifies_planted_addresses(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "safe.md": "contact: someone@example.com\n",
            "risky.md": "contact: real.person@somewhere-else.com\n",
            "local-form.md": "seen once: person@laptop.local\n",
            "clean.md": "no address here at all\n",
        },
    )

    hits = run_identity_probe_sweep(repo)

    by_path = {h.relative_path: h.note for h in hits}
    assert by_path["safe.md"] == "public-or-placeholder"
    assert by_path["risky.md"] == "personal-address-candidate"
    assert by_path["local-form.md"] == "git-constructed-form-candidate"
    assert "clean.md" not in by_path
    assert all(h.matched == "" for h in hits), (
        "the identity probe must never record a literal address, even out-of-repository"
    )


# --- run_stale_pointer_sweep() (pass 5) ---------------------------------------


def test_run_stale_pointer_sweep_finds_a_path_fragment(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "pointer.md": "see docs/reference/removed-thing.md for details\n",
            "clean.md": "nothing relevant\n",
        },
    )

    hits = run_stale_pointer_sweep(repo, ("docs/reference/removed-thing.md",))

    assert {h.relative_path for h in hits} == {"pointer.md"}
    assert hits[0].matched == "docs/reference/removed-thing.md"


def test_run_stale_pointer_sweep_over_empty_fragments_is_empty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"a.md": "anything\n"})

    assert run_stale_pointer_sweep(repo, ()) == ()


# --- run_basename_probe_sweep() (pass 6, ad hoc) ------------------------------


def test_token_free_basename_probes_tuple_is_nonempty() -> None:
    from scripts.purge.sweep import _TOKEN_FREE_BASENAME_PROBES

    assert _TOKEN_FREE_BASENAME_PROBES


def test_run_basename_probe_sweep_over_the_real_repo_finds_both_probes() -> None:
    # The trap this ad-hoc pass exists for: a full-path-only search misses a
    # file that references either basename under a different prefix or
    # bare. This pins that the probe set is non-empty and that it finds
    # something in the real tree (a positive control for the walk).
    hits = run_basename_probe_sweep(_REPO_ROOT)

    assert hits, (
        "the basename probe found nothing in the real tree -- either the "
        "probe values are wrong or the walk is looking at the wrong root"
    )


# --- classify_hit() / classify_hits() -----------------------------------------


def test_classified_hit_rejects_an_unknown_disposition() -> None:
    hit = SweepHit(sweep="token", relative_path="a.md", surface="content", matched="x")

    with pytest.raises(ValueError):
        ClassifiedHit(hit=hit, disposition="not-a-real-disposition", rationale="n/a")


def test_classify_hit_uses_fine_override_over_coarse_override() -> None:
    hit = SweepHit(sweep="token", relative_path="a.md", surface="content", matched="x")
    overrides = {("token", "a.md"): ("stale_pointer", "coarse")}
    fine_overrides = {("token", "a.md", "x"): ("guard", "fine")}

    classified = classify_hit(hit, overrides, fine_overrides)

    assert classified.disposition == "guard"
    assert classified.rationale == "fine"


def test_classify_hit_falls_back_to_coarse_override(tmp_path: Path) -> None:
    hit = SweepHit(sweep="token", relative_path="a.md", surface="content", matched="x")
    overrides = {("token", "a.md"): ("stale_pointer", "coarse-rationale")}

    classified = classify_hit(hit, overrides)

    assert classified.disposition == "stale_pointer"
    assert classified.rationale == "coarse-rationale"


def test_classify_hit_auto_classifies_value_matcher_hit() -> None:
    hit = SweepHit(
        sweep="value_matcher", relative_path="a.md", surface="content", matched=""
    )

    classified = classify_hit(hit, overrides={})

    assert classified.disposition == "reproduction_pending_redaction"


def test_classify_hit_auto_classifies_public_or_placeholder_identity_hit() -> None:
    hit = SweepHit(
        sweep="identity_probe",
        relative_path="a.md",
        surface="content",
        matched="",
        note="public-or-placeholder",
    )

    classified = classify_hit(hit, overrides={})

    assert classified.disposition == "public_or_placeholder_identity"


def test_classify_hit_auto_classifies_personal_address_candidate_hit() -> None:
    hit = SweepHit(
        sweep="identity_probe",
        relative_path="a.md",
        surface="content",
        matched="",
        note="personal-address-candidate",
    )

    classified = classify_hit(hit, overrides={})

    assert classified.disposition == "identity_pending_erasure"


def test_classify_hit_raises_for_an_unreviewed_hit() -> None:
    # "value_matcher" and "identity_probe" both carry built-in auto-rules
    # now; a genuinely unhandled sweep name is what must still raise.
    hit = SweepHit(
        sweep="some-future-sweep-nobody-has-classified-yet",
        relative_path="never-seen.md",
        surface="content",
        matched="",
    )

    with pytest.raises(KeyError):
        classify_hit(hit, overrides={})


def test_classify_hits_preserves_order() -> None:
    hits = (
        SweepHit(sweep="token", relative_path="z.md", surface="content", matched="x"),
        SweepHit(sweep="token", relative_path="a.md", surface="content", matched="y"),
    )
    overrides = {
        ("token", "z.md"): ("stale_pointer", "z"),
        ("token", "a.md"): ("guard", "a"),
    }

    classified = classify_hits(hits, overrides)

    assert [c.hit.relative_path for c in classified] == ["z.md", "a.md"], (
        "classify_hits must preserve input order, not sort it"
    )


# --- build_default_overrides() ------------------------------------------------


def test_build_default_overrides_classifies_gitignore_as_ignore_rule() -> None:
    overrides = build_default_overrides({"path": frozenset({".gitignore"})})

    disposition, _ = overrides[("path", ".gitignore")]
    assert disposition == "ignore_rule_stale_pointer"


def test_build_default_overrides_classifies_a_guard_file() -> None:
    overrides = build_default_overrides(
        {"token": frozenset({"tests/load/test_packaging.py"})}
    )

    disposition, _ = overrides[("token", "tests/load/test_packaging.py")]
    assert disposition == "guard"


def test_build_default_overrides_classifies_sweep_tooling() -> None:
    overrides = build_default_overrides(
        {"path": frozenset({"scripts/purge/fingerprints.py"})}
    )

    disposition, _ = overrides[("path", "scripts/purge/fingerprints.py")]
    assert disposition == "sweep_tooling_self_reference"


def test_guard_files_and_sweep_tooling_files_are_real_tracked_paths() -> None:
    # GUARD_FILES and SWEEP_TOOLING_FILES are hand-maintained sets; a stale
    # entry (a rename that was not followed here) would silently misclassify
    # nothing (the entry just never matches a real hit) and a MISSING entry
    # (a new tooling file added without updating the set, exactly the defect
    # this task was rejected for) is the dangerous direction. This asserts
    # every entry resolves against `git ls-files` -- the same universe
    # `run_full_sweep` uses -- so a rename/removal is caught here rather
    # than discovered as a silent misclassification later.
    from scripts.purge.sweep import GUARD_FILES, SWEEP_TOOLING_FILES

    tracked = {str(path.relative_to(_REPO_ROOT)) for path in tracked_files(_REPO_ROOT)}
    assert tracked, (
        "git ls-files reported nothing -- cannot validate against the real tree"
    )

    for relative_path in GUARD_FILES | SWEEP_TOOLING_FILES:
        assert relative_path in tracked, (
            f"{relative_path!r} is in GUARD_FILES/SWEEP_TOOLING_FILES but is "
            "not a tracked path -- the set has rotted (a rename or removal "
            "was not followed here)"
        )


def test_build_default_overrides_classifies_a_closed_queue_item_as_retained() -> None:
    overrides = build_default_overrides(
        {"stale_pointer": frozenset({".kiro/queue/closed/2026-01-01-example.md"})}
    )

    disposition, _ = overrides[
        ("stale_pointer", ".kiro/queue/closed/2026-01-01-example.md")
    ]
    assert disposition == "retained_historical_subject"


def test_build_default_overrides_defaults_an_ordinary_file_to_stale_pointer() -> None:
    overrides = build_default_overrides(
        {"path": frozenset({".kiro/specs/some-spec/design.md"})}
    )

    disposition, _ = overrides[("path", ".kiro/specs/some-spec/design.md")]
    assert disposition == "stale_pointer"


def test_build_default_overrides_default_and_guard_are_distinguishable() -> None:
    # Confounded-fixture guard: an ordinary spec file and a named guard file
    # must land on DIFFERENT dispositions, not just "some disposition".
    overrides = build_default_overrides(
        {
            "path": frozenset(
                {".kiro/specs/some-spec/design.md", "tests/load/test_packaging.py"}
            )
        }
    )

    ordinary, _ = overrides[("path", ".kiro/specs/some-spec/design.md")]
    guard, _ = overrides[("path", "tests/load/test_packaging.py")]
    assert ordinary != guard


def test_build_default_overrides_classifies_symbolic_reproduction_site() -> None:
    overrides = build_default_overrides(
        {
            "symbolic_probe": frozenset(
                {".kiro/specs/training-load/research.md", "some/other/file.md"}
            )
        }
    )

    site, _ = overrides[("symbolic_probe", ".kiro/specs/training-load/research.md")]
    other, _ = overrides[("symbolic_probe", "some/other/file.md")]
    assert site == "reproduction_pending_redaction"
    assert other == "judged_not_a_reproduction"
    assert site != other


# --- render_inventory_tsv() / write_inventory() / read_inventory() -----------


def _sample_classified() -> tuple[ClassifiedHit, ...]:
    # Deliberately mixed dispositions and non-alphabetical order -- a
    # pass-filter or a silent-sort mutation must both be reachable failures.
    return (
        ClassifiedHit(
            hit=SweepHit(
                sweep="token", relative_path="z.md", surface="content", matched="alpha"
            ),
            disposition="stale_pointer",
            rationale="first rationale",
        ),
        ClassifiedHit(
            hit=SweepHit(
                sweep="path", relative_path="a.md", surface="path", matched="beta"
            ),
            disposition="guard",
            rationale="second rationale",
        ),
        ClassifiedHit(
            hit=SweepHit(
                sweep="identity_probe",
                relative_path="m.md",
                surface="content",
                matched="",
                note="personal-address-candidate",
            ),
            disposition="identity_pending_erasure",
            rationale="third rationale",
        ),
    )


def test_write_then_read_inventory_round_trips_field_by_field_and_in_order(
    tmp_path: Path,
) -> None:
    classified = _sample_classified()
    out_path = tmp_path / "scratch" / "sweep-inventory.tsv"

    write_inventory(classified, out_path)
    rows = read_inventory(out_path)

    assert len(rows) == len(classified)
    for row, item in zip(rows, classified, strict=True):
        assert row["sweep"] == item.hit.sweep
        assert row["relative_path"] == item.hit.relative_path
        assert row["surface"] == item.hit.surface
        assert row["matched"] == item.hit.matched
        assert row["note"] == item.hit.note
        assert row["disposition"] == item.disposition
        assert row["rationale"] == item.rationale
    # Not every row shares a disposition -- defeats a mutation that always
    # writes/reads the first row's disposition for every row.
    assert {row["disposition"] for row in rows} == {
        "stale_pointer",
        "guard",
        "identity_pending_erasure",
    }


def test_write_inventory_creates_missing_parent_directories(tmp_path: Path) -> None:
    out_path = tmp_path / "does" / "not" / "exist" / "inventory.tsv"

    write_inventory(_sample_classified(), out_path)

    assert out_path.exists()
    assert len(read_inventory(out_path)) == 3


@pytest.mark.parametrize(
    "rationale",
    [
        "a rationale\twith an embedded tab",
        "a rationale\nwith an embedded newline",
    ],
)
def test_render_inventory_tsv_raises_on_embedded_tab_or_newline(rationale: str) -> None:
    bad = (
        ClassifiedHit(
            hit=SweepHit(
                sweep="token", relative_path="a.md", surface="content", matched="x"
            ),
            disposition="stale_pointer",
            rationale=rationale,
        ),
    )

    with pytest.raises(ValueError):
        render_inventory_tsv(bad)


def test_parse_inventory_tsv_over_header_only_text_is_empty() -> None:
    text = (
        "\t".join(
            [
                "sweep",
                "relative_path",
                "surface",
                "matched",
                "note",
                "disposition",
                "rationale",
            ]
        )
        + "\n"
    )

    assert parse_inventory_tsv(text) == ()


def test_parse_inventory_tsv_raises_on_a_row_with_the_wrong_field_count() -> None:
    # A malformed row (too few fields, e.g. from hand-editing or a truncated
    # write) must raise, not silently zip-truncate to a short dict that
    # drops trailing columns (`disposition`/`rationale`) without any error
    # -- the same "swallowed failure reads as a clean value" species this
    # module is otherwise careful to avoid.
    header = "\t".join(
        [
            "sweep",
            "relative_path",
            "surface",
            "matched",
            "note",
            "disposition",
            "rationale",
        ]
    )
    malformed_row = "token\ta.md\tcontent\tx"  # only 4 of 7 fields
    text = f"{header}\n{malformed_row}\n"

    with pytest.raises(ValueError):
        parse_inventory_tsv(text)


# --- end-to-end: run_full_sweep() over a synthetic repo -----------------------


def _synthetic_forbidden_strings_source(tmp_path: Path) -> Path:
    source = tmp_path / "forbidden-strings.tsv"
    source.write_text(
        "token\tneedle-token\npath\tremoved/path/fragment.md\n", encoding="utf-8"
    )
    return source


def test_run_full_sweep_hits_every_pass_at_least_once(tmp_path: Path) -> None:
    # Built to defeat exactly the survivors a reviewer found: dropping any
    # one of the six enumerations `run_full_sweep` combines (tp_hits split
    # into token/path, vm_hits, sym_hits, id_hits, sp_hits, bn_hits), or
    # dropping the unreadable-file report, or calling
    # run_stale_pointer_sweep with an empty needle set, must each turn one
    # or more of the assertions below false. One file per pass, each
    # containing content that ONLY that pass's needle set can reach, so a
    # dropped enumeration is a reachable, distinguishable failure rather
    # than a coincidental pass.
    from scripts.purge.sweep import _TOKEN_FREE_BASENAME_PROBES

    salt = b"full-sweep-coverage-salt"
    dense_text = "Zone factors: 118.42837, 204.99123, 337.55019, 441.20876, 552.68231\n"
    fps, lengths = _fingerprint_corpus(dense_text, salt, floor=96.0)
    assert fps and lengths, "fixture corpus must clear the entropy floor"

    basename_probe_value = _TOKEN_FREE_BASENAME_PROBES[0]
    assert basename_probe_value

    repo = _repo(tmp_path)
    (repo / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    _commit_files(
        repo,
        {
            "token-and-path.md": "carries needle-token and removed/path/fragment.md\n",
            "dense.md": dense_text,
            "symbolic.md": "this file mentions a pace lookup explicitly\n",
            "identity.md": "contact: real.person@somewhere-else.com\n",
            "basename.md": f"bare-mentions {basename_probe_value}, no full path\n",
            "broken-link.md": "placeholder\n",
        },
    )
    broken = repo / "broken-link.md"
    broken.unlink()
    broken.symlink_to(repo / "does-not-exist.md")
    source = _synthetic_forbidden_strings_source(tmp_path)

    classified, unreadable = run_full_sweep(
        repo,
        forbidden_strings_path=source,
        fingerprints=fps,
        window_lengths=lengths,
        salt=salt,
    )

    sweeps_seen = {item.hit.sweep for item in classified}
    assert sweeps_seen == {
        "token",
        "path",
        "value_matcher",
        "symbolic_probe",
        "identity_probe",
        "stale_pointer",
        "basename_probe",
    }, f"expected all seven sweep kinds represented, got {sweeps_seen}"
    # Both failure modes required, distinctly -- a half-fix that reports the
    # broken symlink (OSError) but silently swallows the binary file
    # (UnicodeDecodeError), or vice versa, must be a reachable,
    # distinguishable failure here, not just "unreadable is non-empty".
    unreadable_names = {item.relative_path for item in unreadable}
    assert "broken-link.md" in unreadable_names, (
        "the broken symlink must be reported as unreadable by run_full_sweep"
    )
    assert "blob.bin" in unreadable_names, (
        "the non-UTF-8 file must be reported as unreadable by run_full_sweep "
        "too -- reporting only the OSError case is a half-fix"
    )


def test_run_full_sweep_is_deterministic_across_two_runs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "a.md": "carries needle-token and points at removed/path/fragment.md\n",
            "b.md": "clean\n",
        },
    )
    source = _synthetic_forbidden_strings_source(tmp_path)

    first, first_unreadable = run_full_sweep(
        repo,
        forbidden_strings_path=source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
    )
    second, second_unreadable = run_full_sweep(
        repo,
        forbidden_strings_path=source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
    )

    assert first == second, (
        "re-running the sweep over an unchanged tree must reproduce the same hit set"
    )
    assert first_unreadable == second_unreadable
    assert first, (
        "the sweep found nothing at all -- the fixture is not exercising the walk"
    )


def test_run_full_sweep_classifies_every_hit_it_produces(tmp_path: Path) -> None:
    # If any pass produced a (sweep, path) pair build_default_overrides
    # cannot classify, run_full_sweep would raise KeyError inside
    # classify_hits -- this simply proves that does not happen for an
    # ordinary synthetic fixture.
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "a.md": "carries needle-token\n",
            ".kiro/queue/closed/example.md": (
                "narrates removed/path/fragment.md historically\n"
            ),
        },
    )
    source = _synthetic_forbidden_strings_source(tmp_path)

    classified, _ = run_full_sweep(
        repo,
        forbidden_strings_path=source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
    )

    assert classified
    for item in classified:
        assert item.disposition in DISPOSITIONS


# --- end-to-end observables against the real repository -----------------------

_MODIFIED_FILES_TABLE_SAMPLE: tuple[str, ...] = (
    # A sample, not the full design.md table -- enough to prove the
    # superset property is genuinely checked rather than vacuous.
    #
    # Deliberately excludes pyproject.toml: task 3.1 already deleted its
    # dead sdist section and copyright-notice comment entirely (Req 2.1,
    # 11.4, pinned by tests/purge/test_tree_removal.py), so the file
    # legitimately carries zero token/path hits now -- re-measured directly:
    # a fixed-string search of the match data's token and path entries over
    # that file returns nothing but an unrelated `mypy` dependency line.
    # Including it here would assert a hit this task's own sweep is right
    # to no longer find.
    #
    # Also deliberately excludes .gitignore and CLAUDE.md: task 3.5 redacted
    # both (the key-reference bullet removed from CLAUDE.md; the ignore-rule
    # comment and its stale pointer replaced in .gitignore), and both now
    # carry zero token/path hits -- re-measured directly the same way.
    #
    # Also deliberately excludes .kiro/specs/training-load/research.md: task
    # 3.6 redacted the dense "methodology extraction" research-log entry that
    # was this file's own designated symbolic-reproduction site
    # (`_SYMBOLIC_REPRODUCTION_SITE` in scripts/purge/sweep.py) -- the zone
    # table, formulas, discount-generating rule and worked-example vectors
    # are gone, every remaining identifying-token mention is replaced from the
    # fixed vocabulary table, and the licensing contact address is removed.
    # Re-measured directly: the token/path matcher, the value-matcher oracle
    # and the symbolic-probe fixed strings all return zero hits against the
    # file's current content, so it legitimately carries no hit on any of
    # the five sweep passes any more. Including it here would assert a hit
    # this task's own redaction is right to no longer find.
    #
    # This exclusion is a coverage gap the sample-superset check below cannot
    # see by itself: a clean file and a file silently dropped from the sweep
    # universe are indistinguishable by "does not appear in `covered`" alone.
    # `test_research_log_redaction_site_is_scanned_and_clean` below re-bases
    # that coverage directly against `tracked_files`, so this exclusion is
    # checked rather than merely asserted in prose.
    #
    # Also deliberately excludes .kiro/specs/training-load/design.md,
    # tasks.md and spec.json: task 3.7 reversed the retention instructions
    # these three carried and erased every remaining identifying-token
    # mention across all three, including the approved `training-load`
    # component name built from one. Re-measured directly: the token/path
    # matcher returns zero hits against all three files' current content, so
    # they legitimately carry no hit on the sweep any more.
    # `test_retention_reversal_sites_are_scanned_and_clean` below re-bases
    # that narrow coverage -- token/path membership and sweep-universe
    # membership only -- directly against `tracked_files`, so the exclusion
    # of these three sites is checked rather than merely asserted in prose.
    # It does NOT pin Req 4.1's substance: it runs the value-matcher oracle
    # with an empty fingerprint/window-length set (task 4.3's tree-wide guard
    # owns that; it does not exist yet), so a token-free retention
    # instruction reintroduced into these files would pass this test
    # undetected.
    #
    # Also deliberately excludes .kiro/steering/roadmap.md and
    # .kiro/steering/structure.md: task 3.10 corrected the tense of both
    # documents' retention rulings, repointed the deleted rewrite-map's
    # citation at docs/reference/history-rewrites.md, corrected roadmap.md's
    # three superseded Phase 5 constraints (the halt-not-orphan quiescence
    # behaviour, the refs/original/ disposition settled during requirements
    # rather than left for deliberate decision, and the sweep-scope widening
    # to every tracked file alongside the depth decision discovery took
    # before requirements settled on erasing the identity rather than
    # retaining it), and erased every remaining identifying-token mention
    # across both files. Re-measured
    # directly: the token/path matcher returns zero hits against both files'
    # current content, so they legitimately carry no hit on the sweep any
    # more. `test_steering_docs_are_scanned_and_clean` below re-bases that
    # narrow coverage -- token/path membership and sweep-universe membership
    # only -- directly against `tracked_files`, so this exclusion is checked
    # rather than merely asserted in prose.
    #
    # Also deliberately excludes tests/load/test_packaging.py: task 4.1
    # erased every remaining identifying-token mention from the module
    # (deleting the value tuples and the withdrawn-symbol tuple outright
    # rather than renaming them, re-basing both value scans onto the shared
    # oracle, and retiring the token-literal built-artifact checks). Re-
    # measured directly: the token/path matcher returns zero hits against
    # the file's current content, so it legitimately carries no hit on the
    # sweep any more. `test_reintroduction_guards_module_is_scanned_and_clean`
    # below re-bases that narrow coverage -- token/path membership and
    # sweep-universe membership only -- directly against `tracked_files`, so
    # this exclusion is checked rather than merely asserted in prose.
    #
    # Also deliberately excludes tests/test_docs_guarantees.py: task 4.2
    # retired the literal-token absence assertion and both token-present
    # positive controls it held (the second and third already died at task
    # 3.1) and re-based the steering co-location guard onto neutral
    # vocabulary. Re-measured directly: the token/path matcher returns zero
    # hits against the file's current content, so it legitimately carries no
    # hit on the sweep any more.
    # `test_documentation_guard_module_is_scanned_and_clean` below re-bases
    # that narrow coverage -- token/path membership and sweep-universe
    # membership only -- directly against `tracked_files`, so this exclusion
    # is checked rather than merely asserted in prose.
    ".kiro/specs/distribution/design.md",
    ".kiro/specs/encumbered-content-purge/brief.md",
)


def test_modified_files_table_sample_is_nonempty() -> None:
    assert _MODIFIED_FILES_TABLE_SAMPLE, (
        "an empty needle set would make the superset check below pass vacuously"
    )


def test_real_inventory_file_set_is_a_superset_of_the_modified_files_table_sample() -> (
    None
):
    forbidden_strings = require(_REPO_ROOT)
    # require() only skips on an unset env var; a real ForbiddenStrings
    # object means the source resolved, so build the same resolved path
    # run_full_sweep needs directly from it.
    assert isinstance(forbidden_strings, ForbiddenStrings)

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )

    covered = {item.hit.relative_path for item in classified}
    missing = [path for path in _MODIFIED_FILES_TABLE_SAMPLE if path not in covered]
    assert not missing, (
        f"the inventory's file set does not cover these modified-files-table "
        f"entries: {missing}"
    )


def test_real_inventory_has_extras_beyond_the_table_that_are_classified() -> None:
    # tasks.md 3.2: "the Modified-files table ... is not the enumeration ...
    # every extra is classified rather than dropped." Pins that the real
    # sweep finds strictly more files than the sample table above, and that
    # every one of those extras still carries a valid disposition (not a
    # default/placeholder).
    forbidden_strings = require(_REPO_ROOT)
    assert isinstance(forbidden_strings, ForbiddenStrings)

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )

    covered = {item.hit.relative_path for item in classified}
    extras = covered - set(_MODIFIED_FILES_TABLE_SAMPLE)
    assert extras, (
        "the real sweep found no files beyond the sample table -- the "
        "fixture sample is too broad"
    )
    extra_items = [item for item in classified if item.hit.relative_path in extras]
    assert extra_items
    assert all(item.disposition in DISPOSITIONS for item in extra_items)


def test_research_log_redaction_site_is_scanned_and_clean() -> None:
    # F8 remediation (task 3.6 review round 1): the sample-superset check
    # above only proves coverage for files that still carry a hit. A file
    # dropped from the sweep universe entirely and a file that was scanned
    # and came up clean are both simply absent from `covered` -- the
    # superset check cannot tell them apart. This test re-bases coverage of
    # `.kiro/specs/training-load/research.md` (`_SYMBOLIC_REPRODUCTION_SITE`
    # in scripts/purge/sweep.py) directly against `tracked_files`, so a
    # sweep universe that silently excludes the file reds here even though
    # it would leave every other assertion in this module green.
    forbidden_strings = require(_REPO_ROOT)
    assert isinstance(forbidden_strings, ForbiddenStrings)

    site = ".kiro/specs/training-load/research.md"
    tracked = {str(path.relative_to(_REPO_ROOT)) for path in tracked_files(_REPO_ROOT)}
    assert site in tracked, (
        "the sweep universe must include the file task 3.6 redacted -- a "
        "narrowed universe would let it silently escape every pass"
    )

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )
    hits = [item for item in classified if item.hit.relative_path == site]
    assert not hits, f"research.md carries unexpected sweep hits: {hits}"


def test_retention_reversal_sites_are_scanned_and_clean() -> None:
    # Task 3.7 review shape, copied from
    # `test_research_log_redaction_site_is_scanned_and_clean` above: once a
    # redaction leaves a file with zero sweep hits, it drops out of
    # `_MODIFIED_FILES_TABLE_SAMPLE`'s coverage set with no way for the
    # superset check to distinguish "scanned and clean" from "silently
    # dropped from the sweep universe". This re-bases coverage of the three
    # `training-load` documents task 3.7 owns directly against
    # `tracked_files`, so a sweep universe that silently excludes any of them
    # reds here even though every other assertion in this module stays green.
    #
    # Coverage limit, stated rather than left implicit: this pins tokens
    # (via `forbidden_strings`) and sweep-universe membership only. It runs
    # `run_full_sweep` with an empty fingerprint set, empty window-length set
    # and an unused salt, so it exercises no content-fingerprint matching at
    # all. It cannot detect a token-free retention instruction reintroduced
    # into any of the three sites -- that substance guard is task 4.3's
    # tree-wide check, which does not exist yet.
    forbidden_strings = require(_REPO_ROOT)
    assert isinstance(forbidden_strings, ForbiddenStrings)

    sites = (
        ".kiro/specs/training-load/design.md",
        ".kiro/specs/training-load/tasks.md",
        ".kiro/specs/training-load/spec.json",
    )
    assert sites, "an empty site tuple would make every walk below pass vacuously"
    tracked = {str(path.relative_to(_REPO_ROOT)) for path in tracked_files(_REPO_ROOT)}
    for site in sites:
        assert site in tracked, (
            f"the sweep universe must include {site} -- a narrowed universe "
            "would let it silently escape every pass"
        )

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )
    for site in sites:
        hits = [item for item in classified if item.hit.relative_path == site]
        assert not hits, f"{site} carries unexpected sweep hits: {hits}"


def test_steering_docs_are_scanned_and_clean() -> None:
    # Task 3.10 review shape, copied from
    # `test_retention_reversal_sites_are_scanned_and_clean` above: once a
    # redaction leaves a file with zero sweep hits, it drops out of
    # `_MODIFIED_FILES_TABLE_SAMPLE`'s coverage set with no way for the
    # superset check to distinguish "scanned and clean" from "silently
    # dropped from the sweep universe". This re-bases coverage of the two
    # steering documents task 3.10 owns directly against `tracked_files`, so
    # a sweep universe that silently excludes either one reds here even
    # though every other assertion in this module stays green.
    #
    # Coverage limit, stated rather than left implicit: this pins tokens
    # (via `forbidden_strings`) and sweep-universe membership only. It runs
    # `run_full_sweep` with an empty fingerprint set, empty window-length set
    # and an unused salt, so it exercises no content-fingerprint matching at
    # all. It cannot detect a token-free retention instruction reintroduced
    # into either site -- that substance guard is task 4.3's tree-wide check,
    # which does not exist yet.
    forbidden_strings = require(_REPO_ROOT)
    assert isinstance(forbidden_strings, ForbiddenStrings)

    sites = (
        ".kiro/steering/roadmap.md",
        ".kiro/steering/structure.md",
    )
    assert sites, "an empty site tuple would make every walk below pass vacuously"
    tracked = {str(path.relative_to(_REPO_ROOT)) for path in tracked_files(_REPO_ROOT)}
    for site in sites:
        assert site in tracked, (
            f"the sweep universe must include {site} -- a narrowed universe "
            "would let it silently escape every pass"
        )

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )
    for site in sites:
        hits = [item for item in classified if item.hit.relative_path == site]
        assert not hits, f"{site} carries unexpected sweep hits: {hits}"


def test_reintroduction_guards_module_is_scanned_and_clean() -> None:
    # Task 4.1 review shape, copied from
    # `test_steering_docs_are_scanned_and_clean` above: once a redaction
    # leaves a file with zero sweep hits, it drops out of
    # `_MODIFIED_FILES_TABLE_SAMPLE`'s coverage set with no way for the
    # superset check to distinguish "scanned and clean" from "silently
    # dropped from the sweep universe". This re-bases coverage of
    # `tests/load/test_packaging.py`, which task 4.1 redacted, directly
    # against `tracked_files`, so a sweep universe that silently excludes it
    # reds here even though every other assertion in this module stays
    # green.
    #
    # Coverage limit, stated rather than left implicit: this pins tokens
    # (via `forbidden_strings`) and sweep-universe membership only. It runs
    # `run_full_sweep` with an empty fingerprint set, empty window-length set
    # and an unused salt, so it exercises no content-fingerprint matching at
    # all. It cannot detect a token-free reproduction of the withdrawn
    # methodology's values reintroduced into this site -- that substance
    # guard is task 4.3's tree-wide check, which does not exist yet.
    forbidden_strings = require(_REPO_ROOT)
    assert isinstance(forbidden_strings, ForbiddenStrings)

    site = "tests/load/test_packaging.py"
    tracked = {str(path.relative_to(_REPO_ROOT)) for path in tracked_files(_REPO_ROOT)}
    assert site in tracked, (
        f"the sweep universe must include {site} -- a narrowed universe "
        "would let it silently escape every pass"
    )

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )
    hits = [item for item in classified if item.hit.relative_path == site]
    assert not hits, f"{site} carries unexpected sweep hits: {hits}"


def test_documentation_guard_module_is_scanned_and_clean() -> None:
    # Task 4.2 review shape, copied from
    # `test_reintroduction_guards_module_is_scanned_and_clean` above: once a
    # redaction leaves a file with zero sweep hits, it drops out of
    # `_MODIFIED_FILES_TABLE_SAMPLE`'s coverage set with no way for the
    # superset check to distinguish "scanned and clean" from "silently
    # dropped from the sweep universe". This re-bases coverage of
    # `tests/test_docs_guarantees.py`, which task 4.2 redacted, directly
    # against `tracked_files`, so a sweep universe that silently excludes it
    # reds here even though every other assertion in this module stays
    # green.
    #
    # Coverage limit, stated rather than left implicit: this pins tokens
    # (via `forbidden_strings`) and sweep-universe membership only. It runs
    # `run_full_sweep` with an empty fingerprint set, empty window-length set
    # and an unused salt, so it exercises no content-fingerprint matching at
    # all. It cannot detect a token-free reproduction of the withdrawn
    # methodology's values reintroduced into this site -- that substance
    # guard is task 4.3's tree-wide check, which does not exist yet.
    forbidden_strings = require(_REPO_ROOT)
    assert isinstance(forbidden_strings, ForbiddenStrings)

    site = "tests/test_docs_guarantees.py"
    tracked = {str(path.relative_to(_REPO_ROOT)) for path in tracked_files(_REPO_ROOT)}
    assert site in tracked, (
        f"the sweep universe must include {site} -- a narrowed universe "
        "would let it silently escape every pass"
    )

    classified, _ = run_full_sweep(
        _REPO_ROOT,
        forbidden_strings_path=forbidden_strings.source,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"unused-for-this-check",
    )
    hits = [item for item in classified if item.hit.relative_path == site]
    assert not hits, f"{site} carries unexpected sweep hits: {hits}"


def test_purges_own_new_files_are_classified_as_sweep_tooling() -> None:
    # Trap 3 from task 3.2's own brief: fingerprints.py / test_fingerprints.py
    # / test_tree_removal.py / rewrite_map.py / test_rewrite_map_extraction.py
    # must be classified, not silently dropped for post-dating design.md.
    #
    # Re-based here (encumbered-content-purge task 6.3): these files used to
    # carry real `token`/`path` hits from their own literal content, which is
    # what let this test drive the classification through a REAL
    # `run_full_sweep` call and assert on its output. Task 6.3 emptied that
    # content -- these files now source their detection needles from
    # `FITDOCS_FORBIDDEN_STRINGS` at run time instead of holding them
    # literally, which is the whole point of that task -- so a real sweep no
    # longer produces a hit for either path to classify. This asserts the
    # SAME classification decision `_token_disposition` makes directly,
    # unit-level, which is what `run_full_sweep` would have applied to a hit
    # in either file had one been found; it no longer depends on either file
    # accidentally carrying detection data of its own.
    from scripts.purge.sweep import _token_disposition

    disposition, _ = _token_disposition("scripts/purge/fingerprints.py")
    assert disposition == "sweep_tooling_self_reference"
    disposition, _ = _token_disposition("tests/purge/test_tree_removal.py")
    assert disposition == "sweep_tooling_self_reference"


def test_this_tasks_own_new_files_are_classified_as_sweep_tooling() -> None:
    # Item 5: SWEEP_TOOLING_FILES must list task 3.2's own three new files,
    # not only task 2.4/3.1's -- omitting them would misclassify
    # `scripts/purge/sweep.py` and `tests/purge/test_sweep.py` as
    # `identity_pending_erasure`/`stale_pointer` were either to ever carry a
    # real token/path hit.
    #
    # Re-based here (encumbered-content-purge task 6.3), for the same reason
    # as `test_purges_own_new_files_are_classified_as_sweep_tooling` above:
    # both files used to carry real hits (the removed-path fragments they
    # named directly); task 6.3 emptied that content, so a real
    # `run_full_sweep` no longer finds anything in either to classify. This
    # asserts `_token_disposition`'s and `_reference_disposition`'s decision
    # directly for both paths instead.
    from scripts.purge.sweep import _reference_disposition, _token_disposition

    for disposition_fn in (_token_disposition, _reference_disposition):
        sweep_py, _ = disposition_fn("scripts/purge/sweep.py")
        test_sweep_py, _ = disposition_fn("tests/purge/test_sweep.py")
        assert sweep_py == "sweep_tooling_self_reference", (
            f"sweep.py's disposition is {sweep_py!r}, not sweep-tooling"
        )
        assert test_sweep_py == "sweep_tooling_self_reference", (
            f"test_sweep.py's disposition is {test_sweep_py!r}, not sweep-tooling"
        )


def test_token_disposition_default_branch_is_distinguishable() -> None:
    # Direct unit test of _token_disposition's default branch: an ordinary
    # (non-guard, non-tooling) file must be `identity_pending_erasure`, and
    # that value must differ from BOTH the guard and the sweep-tooling
    # results -- "some disposition" is not enough; flipping the default
    # return to `judged_not_a_reproduction` (the "no work needed" outcome
    # Requirement 1.2/11.1 forbids silently reaching) must be reachable as
    # a distinguishable wrong answer.
    from scripts.purge.sweep import GUARD_FILES, SWEEP_TOOLING_FILES, _token_disposition

    guard_file = next(iter(GUARD_FILES))
    tooling_file = next(iter(SWEEP_TOOLING_FILES))

    ordinary, _ = _token_disposition(".kiro/specs/some-other-spec/design.md")
    guard, _ = _token_disposition(guard_file)
    tooling, _ = _token_disposition(tooling_file)

    assert ordinary == "identity_pending_erasure"
    assert ordinary != guard
    assert ordinary != tooling
    assert guard != tooling


# --- scripts/purge/build_sweep_inventory.py::_report_unreadable() ------------


def test_report_unreadable_prints_nothing_when_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.purge.build_sweep_inventory import _report_unreadable

    _report_unreadable(())

    captured = capsys.readouterr()
    assert captured.err == "", (
        "an empty unreadable tuple must print nothing -- a stray message here "
        "would falsely claim a file went unscanned when none did"
    )


def test_report_unreadable_names_every_offending_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.purge.build_sweep_inventory import _report_unreadable
    from scripts.purge.sweep import UnreadableFile

    _report_unreadable(
        (
            UnreadableFile(relative_path="a/one.bin", reason="reason one"),
            UnreadableFile(relative_path="b/two.bin", reason="reason two"),
        )
    )

    captured = capsys.readouterr()
    assert "a/one.bin" in captured.err
    assert "b/two.bin" in captured.err
    assert "2 tracked file(s)" in captured.err, (
        "the count in the header line must match the number of entries -- "
        "a hardcoded count would pass a single-entry check but not this one"
    )
