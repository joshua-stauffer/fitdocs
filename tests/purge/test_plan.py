"""`scripts/purge/plan.py`: `RedactionPlan` (task 5.2, design.md `####
RedactionPlan`, Req 5.1, 7.1, 9.3, 11.1, 11.2).

Every fixture here builds a synthetic git repository under `tmp_path` with
`git init`. Nothing here runs a mutating git command against this
repository's own working tree or history -- every enumeration and every
would-be-pruned check is exercised against a throwaway fixture repository,
never against `fitdocs-purge` itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.purge.plan import (
    SYMBOLIC_PROBES,
    ContentMatch,
    PathMatch,
    RedactionPlan,
    WouldBePrunedError,
    build_content_plan,
    build_path_plan,
    build_redaction_plan,
    classify_blob_content,
    classify_path,
    commit_changed_paths,
    enumerate_blob_ids,
    enumerate_paths,
    parse_content_plan_tsv,
    read_blob_text,
    read_redaction_plan,
    render_content_plan_tsv,
    render_path_plan_tsv,
    would_be_pruned_commits,
    write_redaction_plan,
)

from tests._content_oracle import digest, tokens, windows
from tests._forbidden_strings import ForbiddenStrings


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
    return root


def _commit_files(repo: Path, files: dict[str, str], message: str = "fixture") -> str:
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _commit_bytes(
    repo: Path, relative: str, content: bytes, message: str = "fixture"
) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _delete_and_commit(repo: Path, relative: str, message: str = "delete") -> str:
    _git(repo, "rm", "-q", relative)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _forbidden(*values: str) -> ForbiddenStrings:
    return ForbiddenStrings(values=values, source=Path("/nonexistent"))


def _fingerprint_corpus(
    text: str, salt: bytes, floor: float = 96.0
) -> tuple[frozenset[str], frozenset[int]]:
    toks = tokens(text)
    fps: set[str] = set()
    lengths: set[int] = set()
    for offset, length in windows(toks, floor):
        fps.add(digest(toks[offset : offset + length], salt))
        lengths.add(length)
    return frozenset(fps), frozenset(lengths)


# ---------------------------------------------------------------------------
# enumerate_blob_ids -- blob identifiers, never basenames, never tree/commit
# ---------------------------------------------------------------------------


def test_enumerate_blob_ids_returns_blob_objects_not_trees_or_commits(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    commit = _commit_files(
        repo, {"alpha.txt": "alpha content\n", "beta.txt": "beta content\n"}
    )
    tree = _git(repo, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    blob_alpha = _git(repo, "rev-parse", f"{commit}:alpha.txt").stdout.strip()
    blob_beta = _git(repo, "rev-parse", f"{commit}:beta.txt").stdout.strip()

    blob_ids = enumerate_blob_ids(repo)

    # Equality on the full set -- a truncating mutation (e.g. `[:1]`) cannot
    # pass this with two distinct blobs present, and the commit/tree ids
    # would only appear under a dropped type filter.
    assert set(blob_ids) == {blob_alpha, blob_beta}
    assert commit not in blob_ids
    assert tree not in blob_ids


def test_enumerate_blob_ids_reports_distinct_ids_for_same_basename_different_content(
    tmp_path: Path,
) -> None:
    """The four-blobs-not-two scenario design.md names directly: two files
    sharing a basename but differing in content (one carrying a prepended
    line) must enumerate as two distinct blob ids -- nothing here
    de-duplicates by basename, because nothing here even reads a path."""
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "docs/reference/table.csv": "reference,table\n1,2\n",
            "pkg/table.csv": "COPYRIGHT NOTICE\nreference,table\n1,2\n",
        },
    )
    blob_reference = _git(
        repo, "rev-parse", "HEAD:docs/reference/table.csv"
    ).stdout.strip()
    blob_package = _git(repo, "rev-parse", "HEAD:pkg/table.csv").stdout.strip()

    blob_ids = enumerate_blob_ids(repo)

    assert blob_reference != blob_package
    assert blob_reference in blob_ids
    assert blob_package in blob_ids


def test_enumerate_blob_ids_reaches_a_blob_that_exists_only_on_a_second_branch(
    tmp_path: Path,
) -> None:
    """Same `--all`-vs-`HEAD` concern as `enumerate_paths`' own second-branch
    test, at the blob level: a blob that exists only on a branch other than
    the checked-out one must still be reachable from `--all`."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"main-only.txt": "main\n"}, "main commit")
    _git(repo, "checkout", "-q", "-b", "peer")
    _commit_files(repo, {"peer-only.txt": "peer content unique\n"}, "peer commit")
    peer_blob = _git(repo, "rev-parse", "HEAD:peer-only.txt").stdout.strip()
    _git(repo, "checkout", "-q", "main")

    blob_ids = enumerate_blob_ids(repo)

    assert peer_blob in blob_ids


# ---------------------------------------------------------------------------
# read_blob_text -- undecodable bytes handled, never skipped
# ---------------------------------------------------------------------------


def test_read_blob_text_decodes_a_blob_with_an_invalid_utf8_byte_without_raising(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    payload = b"\xff" + b"secret-token-xyz trailing text\n"
    _commit_bytes(repo, "weird.bin", payload)
    blob_id = _git(repo, "rev-parse", "HEAD:weird.bin").stdout.strip()

    text = read_blob_text(repo, blob_id)

    # The invalid leading byte does not swallow what follows it.
    assert "secret-token-xyz" in text


# ---------------------------------------------------------------------------
# classify_blob_content -- one row per pass that fires, none for a clean blob
# ---------------------------------------------------------------------------


def test_classify_blob_content_flags_value_matcher_and_not_others(
    tmp_path: Path,
) -> None:
    salt = b"fixed-test-salt"
    dense_text = "Zone factors: 118.42837, 204.99123, 337.55019, 441.20876, 552.68231\n"
    fps, lengths = _fingerprint_corpus(dense_text, salt)
    assert fps and lengths, (
        "fixture corpus must clear the entropy floor to be a real test"
    )
    forbidden = _forbidden("unrelated-token")

    hits = classify_blob_content(
        "blob1",
        dense_text,
        fingerprints=fps,
        window_lengths=lengths,
        salt=salt,
        forbidden=forbidden,
    )

    assert hits == (
        ContentMatch(
            blob_id="blob1",
            pass_name="value_matcher",
            disposition="not_pattern_tractable",
        ),
    )


def test_classify_blob_content_flags_forbidden_strings_case_insensitively(
    tmp_path: Path,
) -> None:
    forbidden = _forbidden("Secret-Token-XYZ")

    hits = classify_blob_content(
        "blob2",
        "this text contains secret-token-xyz in lower case\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert hits == (
        ContentMatch(
            blob_id="blob2",
            pass_name="forbidden_strings",
            disposition="literal_replaceable",
        ),
    )


def test_classify_blob_content_flags_a_forbidden_value_wrapped_across_a_line(
    tmp_path: Path,
) -> None:
    """A multi-word forbidden value whose ONLY occurrence in a blob is split
    by a line break must still make that blob `literal_replaceable`.

    This is the consequence that made the flat matcher urgent rather than
    untidy: task 7.2's rewrite is driven by this plan, so a blob classified
    as carrying nothing to replace is a blob the rewrite does not attempt to
    redact -- while `build_rules`, which IS wrap-tolerant, would have
    redacted the wrapped occurrence had the blob been listed at all.

    The whole fixture is a wrapped occurrence and nothing else: a fixture
    that also spelled the value unwrapped somewhere would be classified
    identically by the flat matcher, and would pin nothing.
    """
    forbidden = _forbidden("Secret Token Phrase")

    hits = classify_blob_content(
        "blob2b",
        "a paragraph of markdown prose naming the Secret\nToken Phrase midway\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert hits == (
        ContentMatch(
            blob_id="blob2b",
            pass_name="forbidden_strings",
            disposition="literal_replaceable",
        ),
    )


def test_classify_blob_content_does_not_flag_a_value_split_by_other_text(
    tmp_path: Path,
) -> None:
    """The counterpart to the wrap fixture above: tolerance of a line break
    must not become tolerance of arbitrary intervening text. Over-flagging
    here does not merely add noise -- it puts a blob carrying nothing to
    replace into the rewrite's `literal_replaceable` set."""
    forbidden = _forbidden("Secret Token Phrase")

    hits = classify_blob_content(
        "blob2c",
        "a paragraph naming the Secret, and elsewhere a Token Phrase\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert hits == ()


def test_classify_blob_content_flags_symbolic_probe(tmp_path: Path) -> None:
    """Anchored on the LAST needle, deliberately not `SYMBOLIC_PROBES[0]`:
    a fixture built from the first element cannot defeat a truncation that
    keeps only the first element (the exact trap this needle-set is prone
    to, restated for probe sets by `change-protocol.md`'s "vacuous walk"
    anti-pattern)."""
    label, needle = SYMBOLIC_PROBES[-1]
    assert needle  # sanity: real probe data
    forbidden = _forbidden("unrelated-token")

    hits = classify_blob_content(
        "blob3",
        f"prose mentioning the {needle} in passing\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert hits == (
        ContentMatch(
            blob_id="blob3",
            pass_name="symbolic_probe",
            disposition="literal_replaceable",
        ),
    )


def test_classify_blob_content_flags_every_symbolic_probe_needle_individually(
    tmp_path: Path,
) -> None:
    """A control over the whole probe set, not a sample of it: every needle
    in `SYMBOLIC_PROBES` must, on its own, trigger the `symbolic_probe`
    pass -- so dropping ANY single needle from the set is visible here.

    The `for` loop alone iterates over whatever `SYMBOLIC_PROBES` currently
    is, so it cannot by itself catch the set having been silently shrunk --
    the exact vacuous-walk shape (measured: dropping the tuple's last entry
    left every remaining iteration green). The `len(...) == 9` line is the
    independent anchor that closes that gap; it is the count measured at
    authoring time (`scripts/purge/sweep.py`'s own `SYMBOLIC_PROBES`) and
    must move if a later task legitimately changes the probe count."""
    assert len(SYMBOLIC_PROBES) == 9, (
        "SYMBOLIC_PROBES' count has changed -- update this anchor deliberately "
        "if the probe set genuinely grew or shrank"
    )
    forbidden = _forbidden("unrelated-token")

    for index, (_label, needle) in enumerate(SYMBOLIC_PROBES):
        hits = classify_blob_content(
            f"probe-blob-{index}",
            f"prose containing only {needle} and nothing else notable\n",
            fingerprints=frozenset(),
            window_lengths=frozenset(),
            salt=b"salt",
            forbidden=forbidden,
        )
        assert any(hit.pass_name == "symbolic_probe" for hit in hits), (
            f"needle {needle!r} (index {index}) did not trigger the symbolic probe pass"
        )


def test_classify_blob_content_flags_identity_probe_on_email_shape(
    tmp_path: Path,
) -> None:
    forbidden = _forbidden("unrelated-token")

    hits = classify_blob_content(
        "blob4",
        "contact person@example-domain.test for details\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert hits == (
        ContentMatch(
            blob_id="blob4",
            pass_name="identity_probe",
            disposition="literal_replaceable",
        ),
    )


def test_classify_blob_content_returns_nothing_for_genuinely_clean_text(
    tmp_path: Path,
) -> None:
    """Falsity-in-the-starting-state / pre-satisfied-fixture guard: a control
    text that superficially resembles the trigger content (numbers, prose,
    no @-sign) but clears none of the four passes must yield an empty tuple,
    not merely "not the pass under test"."""
    forbidden = _forbidden("unrelated-token")

    hits = classify_blob_content(
        "blob5",
        "Ordinary prose with a couple of numbers like 12 and 34, nothing else.\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert hits == ()


def test_classify_blob_content_reports_multiple_passes_independently(
    tmp_path: Path,
) -> None:
    """Sole-failure control in the other direction: a blob that trips two
    passes at once must report both, not collapse to one."""
    label, needle = SYMBOLIC_PROBES[len(SYMBOLIC_PROBES) // 2]
    forbidden = _forbidden("forbidden-marker")

    hits = classify_blob_content(
        "blob6",
        f"forbidden-marker alongside the {needle}\n",
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert {hit.pass_name for hit in hits} == {"forbidden_strings", "symbolic_probe"}


def test_content_match_rejects_unknown_disposition() -> None:
    with pytest.raises(ValueError):
        ContentMatch(blob_id="x", pass_name="value_matcher", disposition="bogus")


# ---------------------------------------------------------------------------
# build_content_plan -- end to end over a real repo, undecodable blob included
# ---------------------------------------------------------------------------


def test_build_content_plan_flags_an_undecodable_blob_rather_than_skipping_it(
    tmp_path: Path,
) -> None:
    """The 4.1 hazard restated at blob granularity: a `try`/`except` that
    decodes and skips what will not decode would leave this repository's
    only forbidden-string-bearing blob unscanned. `build_content_plan` must
    still flag it."""
    repo = _repo(tmp_path)
    payload = b"\xff" + b"forbidden-marker after an invalid byte\n"
    _commit_bytes(repo, "weird.bin", payload)
    blob_id = _git(repo, "rev-parse", "HEAD:weird.bin").stdout.strip()
    forbidden = _forbidden("forbidden-marker")

    plan = build_content_plan(
        repo,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert (
        ContentMatch(
            blob_id=blob_id,
            pass_name="forbidden_strings",
            disposition="literal_replaceable",
        )
        in plan
    )


def test_build_content_plan_over_clean_repo_is_empty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"clean.txt": "nothing of interest here\n"})
    forbidden = _forbidden("never-appears-token")

    plan = build_content_plan(
        repo,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert plan == ()


def test_build_content_plan_scans_every_blob_not_just_the_first(tmp_path: Path) -> None:
    """A truncation inside `build_content_plan`'s own loop over
    `enumerate_blob_ids` (as opposed to inside `enumerate_blob_ids` itself,
    which has its own dedicated test) needs a fixture with two blobs that
    EACH produce a hit, so dropping either one is visible regardless of
    which blob id sorts first."""
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {"first.txt": "carries alpha-marker\n", "second.txt": "carries beta-marker\n"},
    )
    blob_first = _git(repo, "rev-parse", "HEAD:first.txt").stdout.strip()
    blob_second = _git(repo, "rev-parse", "HEAD:second.txt").stdout.strip()
    forbidden = _forbidden("alpha-marker", "beta-marker")

    plan = build_content_plan(
        repo,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
    )

    assert {m.blob_id for m in plan} == {blob_first, blob_second}


# ---------------------------------------------------------------------------
# enumerate_paths -- the complete form, not a tip-only ls-files view
# ---------------------------------------------------------------------------


def test_enumerate_paths_includes_a_path_deleted_before_head(tmp_path: Path) -> None:
    """The discriminating fixture: a path introduced at the root commit and
    removed by a later commit is absent from HEAD's tree (a naive
    `git ls-files` / current-tree-only implementation would miss it) but
    still existed at a commit reachable from `main`, so the complete
    enumeration must still report it."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"root-file.txt": "root\n", "shared.txt": "shared\n"}, "root")
    _delete_and_commit(repo, "root-file.txt", "delete root-file")
    _commit_files(repo, {"second-file.txt": "second\n"}, "second")

    paths = enumerate_paths(repo)

    # Equality over three pairwise-distinct, non-adjacent (by history
    # position) paths of different kinds (survives at HEAD / deleted before
    # HEAD / added last) -- a `[:1]`- or tip-only-truncating implementation
    # cannot satisfy this.
    assert set(paths) == {"root-file.txt", "shared.txt", "second-file.txt"}


def test_enumerate_paths_over_a_repo_with_one_commit_matches_git_ls_files(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"only.txt": "only\n"})

    paths = enumerate_paths(repo)

    assert paths == ("only.txt",)


def test_enumerate_paths_reaches_a_path_that_exists_only_on_a_second_branch(
    tmp_path: Path,
) -> None:
    """Req 7.1/11.2 say "any ref", not "HEAD" -- a fixture with a second,
    UNMERGED branch is the only way to tell `--all` from a silently-narrowed
    `HEAD`. Other fixtures in this module do have a second branch (the
    merge tests, and `would_be_pruned`'s mid-history fixture with its `peer`
    branch) -- what is true, and what a `rev-list --all` -> `HEAD` mutation
    on `enumerate_paths` confirms, is that no other `enumerate_paths`
    fixture leaves a second branch UNMERGED, still holding a path `HEAD`
    can never reach."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"main-only.txt": "main\n"}, "main commit")
    _git(repo, "checkout", "-q", "-b", "peer")
    _commit_files(repo, {"peer-only-path.csv": "peer\n"}, "peer commit")
    _git(repo, "checkout", "-q", "main")

    paths = enumerate_paths(repo)

    assert "peer-only-path.csv" in paths


def test_enumerate_paths_reaches_a_path_introduced_only_at_a_merge_commit(
    tmp_path: Path,
) -> None:
    """`git rev-list --all` reaches merge commits by default -- but nothing
    proves that until a fixture has a path that exists ONLY in a merge
    commit's own tree (added during conflict resolution, present in neither
    parent), so an `--no-merges` addition to the `rev-list` call inside
    `enumerate_paths` would silently skip walking it."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"base.txt": "base\n"}, "base")
    _git(repo, "checkout", "-q", "-b", "branch-a")
    _commit_files(repo, {"a.txt": "a\n"}, "a")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "--no-commit", "branch-a")
    (repo / "merge-resolution-only.txt").write_text("only at the merge\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "merge with a path added during resolution")

    paths = enumerate_paths(repo)

    assert "merge-resolution-only.txt" in paths


# ---------------------------------------------------------------------------
# classify_path -- removed / renamed / unmatched
# ---------------------------------------------------------------------------


def test_classify_path_removed_when_only_forbidden_matches(tmp_path: Path) -> None:
    forbidden = _forbidden("removed-fragment")

    result = classify_path("some/removed-fragment/file.csv", forbidden, {})

    assert result == PathMatch(
        path="some/removed-fragment/file.csv", disposition="removed", target_stem=None
    )


def test_classify_path_renamed_when_in_rename_targets_even_if_also_forbidden(
    tmp_path: Path,
) -> None:
    """Precedence control: a path that is BOTH a rename target AND matches a
    forbidden fragment (true of every real rename -- the old name carries
    the very token being erased) must classify as renamed, not removed. A
    fixture where only one of the two conditions holds cannot defeat an
    implementation that checked them in the wrong order."""
    forbidden = _forbidden("old-token-name")
    rename_targets = {".kiro/queue/old-token-name-item.md": "2026-07-26-neutral-stem"}

    result = classify_path(
        ".kiro/queue/old-token-name-item.md", forbidden, rename_targets
    )

    assert result == PathMatch(
        path=".kiro/queue/old-token-name-item.md",
        disposition="renamed",
        target_stem="2026-07-26-neutral-stem",
    )


def test_classify_path_unmatched_path_returns_none(tmp_path: Path) -> None:
    forbidden = _forbidden("removed-fragment")

    result = classify_path("ordinary/file.txt", forbidden, {})

    assert result is None


def test_path_match_renamed_requires_target_stem() -> None:
    with pytest.raises(ValueError):
        PathMatch(path="x", disposition="renamed", target_stem=None)


def test_path_match_removed_forbids_target_stem() -> None:
    with pytest.raises(ValueError):
        PathMatch(path="x", disposition="removed", target_stem="stem")


# ---------------------------------------------------------------------------
# build_path_plan
# ---------------------------------------------------------------------------


def test_build_path_plan_only_emits_matched_paths(tmp_path: Path) -> None:
    """Two matched paths (of the two different removed-fragment names) and
    one unmatched path -- both matches must survive, and the unmatched one
    must not, so a `[:1]` truncation inside `build_path_plan`'s own loop
    (over `enumerate_paths`, which has its own separate truncation test) is
    caught regardless of which matched path sorts first."""
    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "removed-fragment-a/table.csv": "x\n",
            "removed-fragment-b/other.csv": "y\n",
            "ordinary/file.txt": "z\n",
        },
    )
    forbidden = _forbidden("removed-fragment-a", "removed-fragment-b")

    plan = build_path_plan(repo, forbidden, {})

    assert set(plan) == {
        PathMatch(
            path="removed-fragment-a/table.csv", disposition="removed", target_stem=None
        ),
        PathMatch(
            path="removed-fragment-b/other.csv", disposition="removed", target_stem=None
        ),
    }


def test_build_path_plan_includes_a_renamed_row_with_its_target_stem(
    tmp_path: Path,
) -> None:
    """`build_path_plan` is exercised here with a non-empty `rename_targets`
    for the first time in this module -- every other `build_path_plan` test
    passes `{}`, so nothing before this test could tell a `renamed` row
    reaching the emitted plan from one silently dropped (e.g. a mutation
    that filters `build_path_plan`'s output to `disposition == "removed"`
    only)."""
    repo = _repo(tmp_path)
    _commit_files(repo, {".kiro/queue/old-token-name-item.md": "body\n"})
    forbidden = _forbidden("old-token-name")
    rename_targets = {".kiro/queue/old-token-name-item.md": "2026-07-26-neutral-stem"}

    plan = build_path_plan(repo, forbidden, rename_targets)

    assert plan == (
        PathMatch(
            path=".kiro/queue/old-token-name-item.md",
            disposition="renamed",
            target_stem="2026-07-26-neutral-stem",
        ),
    )


def test_build_redaction_plan_includes_a_renamed_row_and_does_not_halt_on_it(
    tmp_path: Path,
) -> None:
    """End to end: `rename_targets` flows from `build_redaction_plan` through
    to `build_path_plan` (the renamed row appears in the emitted plan) AND
    to `would_be_pruned_commits` (a commit touching only the renamed path
    does not halt the run) -- a mutation that drops `rename_targets` on
    either internal call is caught here even though each callee has its own
    dedicated test, because this is the only test that exercises the
    argument actually being threaded through `build_redaction_plan` itself."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep.txt": "keep\n"}, "base")
    _commit_files(
        repo,
        {".kiro/queue/old-token-name-item.md": "body\n"},
        "rename target commit",
    )
    forbidden = _forbidden("old-token-name")
    rename_targets = {".kiro/queue/old-token-name-item.md": "2026-07-26-neutral-stem"}

    plan = build_redaction_plan(
        repo,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
        rename_targets=rename_targets,
    )

    assert (
        PathMatch(
            path=".kiro/queue/old-token-name-item.md",
            disposition="renamed",
            target_stem="2026-07-26-neutral-stem",
        )
        in plan.path_matches
    )


def test_would_be_pruned_commits_does_not_flag_a_commit_touching_only_a_renamed_path(
    tmp_path: Path,
) -> None:
    """Defeats dropping `_is_removed`'s `== "removed"` clause: a renamed
    path also matches `forbidden` (its old name carries the very token being
    erased -- true of every real rename), so if `_is_removed` treated
    "classified at all" as "removed", this commit's sole changed path would
    wrongly count toward emptying its diff and the commit would be flagged.
    It must not be: the renamed path survives under its new name, so the
    commit genuinely is not prunable."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep.txt": "keep\n"}, "base")
    _commit_files(
        repo,
        {".kiro/queue/old-token-name-item.md": "body\n"},
        "rename target commit",
    )
    forbidden = _forbidden("old-token-name")
    rename_targets = {".kiro/queue/old-token-name-item.md": "2026-07-26-neutral-stem"}

    pruned = would_be_pruned_commits(repo, forbidden, rename_targets)

    assert pruned == ()


# ---------------------------------------------------------------------------
# commit_changed_paths -- --root and -m are load-bearing
# ---------------------------------------------------------------------------


def test_commit_changed_paths_reports_the_root_commits_own_files(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    commit = _commit_files(repo, {"root-a.txt": "a\n", "root-b.txt": "b\n"})

    changed = commit_changed_paths(repo, commit)

    assert changed == ("root-a.txt", "root-b.txt")


def test_commit_changed_paths_reports_a_merge_commits_paths_from_both_parents(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"base.txt": "base\n"}, "base")
    _git(repo, "checkout", "-q", "-b", "branch-a")
    _commit_files(repo, {"a.txt": "a\n"}, "a")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "branch-b")
    _commit_files(repo, {"b.txt": "b\n"}, "b")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "branch-a", "-m", "merge-a")
    _git(repo, "merge", "-q", "--no-ff", "branch-b", "-m", "merge-b")
    merge_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    changed = commit_changed_paths(repo, merge_commit)

    # Without `-m` a merge commit's diff-tree reports nothing at all --
    # confirmed both files are visible, not just one (sole-truncation guard).
    assert set(changed) == {"a.txt", "b.txt"}


# ---------------------------------------------------------------------------
# would_be_pruned_commits -- halts on a commit fully inside the removal set
# ---------------------------------------------------------------------------


def test_would_be_pruned_commits_flags_a_commit_whose_entire_diff_is_removed(
    tmp_path: Path,
) -> None:
    """Anchored so neither target commit is the walk's own first element and
    neither is reachable from `HEAD` alone -- both traps `4.3` already hit
    once (a pin on the first member of a walk defeated by exactly the
    truncation it exists to catch; a `--all`-scoped requirement silently
    narrowed to `HEAD`).

    Layout, in commit order: `commit_a` (keep) on `main`; branch `peer`
    forked from `commit_a`, carrying `commit_d` (removed-fragment only,
    reachable ONLY from `peer`, never from `main`'s `HEAD`); back on `main`,
    `commit_b` (removed-fragment only -- the in-history target, sandwiched
    between two survivors); `commit_c` (keep) on `main`, created last so it
    -- not `commit_b` or `commit_d` -- is the most recent commit overall and
    therefore first in `git rev-list --all`'s own output. `HEAD` stays on
    `main` (at `commit_c`) throughout, so `commit_d` is reachable only
    through `--all`, never through `HEAD`.
    """
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep-a.txt": "keep\n"}, "commit_a")
    _git(repo, "checkout", "-q", "-b", "peer")
    commit_d = _commit_files(
        repo, {"removed-fragment/branch-only.csv": "d\n"}, "commit_d (peer only)"
    )
    _git(repo, "checkout", "-q", "main")
    commit_b = _commit_files(
        repo, {"removed-fragment/mid.csv": "b\n"}, "commit_b (mid, removed)"
    )
    _commit_files(repo, {"keep-c.txt": "keep\n"}, "commit_c (tip)")
    forbidden = _forbidden("removed-fragment")

    revisions = _git(repo, "rev-list", "--all").stdout.split()
    assert revisions[0] not in (commit_b, commit_d), (
        "fixture is broken: a target commit sorts first in `rev-list --all`, "
        "which would let a `[:1]` truncation pass this test by accident"
    )
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert (
        commit_d != head
        and commit_d not in _git(repo, "rev-list", "HEAD").stdout.split()
    ), "fixture is broken: commit_d must be unreachable from HEAD"

    pruned = would_be_pruned_commits(repo, forbidden, {})

    assert set(pruned) == {commit_b, commit_d}


def test_would_be_pruned_commits_does_not_flag_a_commit_with_a_surviving_path(
    tmp_path: Path,
) -> None:
    """The fixture that genuinely defeats a vacuous "any match" reading: this
    commit touches one removed path and one surviving path. If the check
    only asked "does any changed path match the removal set" (rather than
    "do ALL of them"), this commit would be wrongly flagged."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep.txt": "keep\n"}, "base")
    _commit_files(
        repo,
        {"removed-fragment/only.csv": "x\n", "surviving.txt": "still here\n"},
        "mixed commit",
    )
    forbidden = _forbidden("removed-fragment")

    pruned = would_be_pruned_commits(repo, forbidden, {})

    assert pruned == ()


def test_would_be_pruned_commits_over_an_all_surviving_history_is_empty(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"a.txt": "a\n"}, "first")
    _commit_files(repo, {"b.txt": "b\n"}, "second")
    forbidden = _forbidden("removed-fragment")

    pruned = would_be_pruned_commits(repo, forbidden, {})

    assert pruned == ()


def test_would_be_pruned_commits_flags_a_merge_commit_whose_diff_is_entirely_removed(
    tmp_path: Path,
) -> None:
    """A positive control that a merge commit reaches and is correctly
    evaluated by this check at all -- no other fixture in this module puts
    a merge commit through `would_be_pruned_commits`, so an `--no-merges`
    addition to its `rev-list --all` call would silently drop every merge
    commit from consideration with every other test here still green.

    `branch-x` adds only a removed-fragment path; merging it into `main`
    (which has not changed since the branches diverged) makes the merge
    commit's `-m` diff against `main` show the one removed-fragment
    addition and its diff against `branch-x` show nothing -- so the
    (deduplicated) changed-path set is exactly the one removed-fragment
    path, and the merge commit is correctly flagged."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep.txt": "keep\n"}, "base")
    _git(repo, "checkout", "-q", "-b", "branch-x")
    _commit_files(repo, {"removed-fragment/only.csv": "x\n"}, "removed on branch-x")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "branch-x", "-m", "merge removed-only branch")
    merge_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    forbidden = _forbidden("removed-fragment")

    pruned = would_be_pruned_commits(repo, forbidden, {})

    assert merge_commit in pruned


def test_would_be_pruned_commits_does_not_flag_a_commit_with_no_changed_paths(
    tmp_path: Path,
) -> None:
    """An already-empty commit (`git commit --allow-empty`) has nothing this
    plan could remove -- `all()` over an empty changed-path set is vacuously
    true, which is exactly the trap `if not changed: continue` exists to
    avoid. A fixture without this commit cannot tell the guard from its
    absence: dropping the `continue` only changes behaviour when `changed`
    is genuinely empty."""
    repo = _repo(tmp_path)
    _commit_files(repo, {"a.txt": "a\n"}, "first")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "empty")
    forbidden = _forbidden("removed-fragment")

    pruned = would_be_pruned_commits(repo, forbidden, {})

    assert pruned == ()


# ---------------------------------------------------------------------------
# build_redaction_plan -- halts before building anything, on a real violation
# ---------------------------------------------------------------------------


def test_build_redaction_plan_raises_on_a_would_be_pruned_commit(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep.txt": "keep\n"}, "base")
    pruned_commit = _commit_files(
        repo, {"removed-fragment/only.csv": "x\n"}, "only removed file"
    )
    forbidden = _forbidden("removed-fragment")

    with pytest.raises(WouldBePrunedError) as excinfo:
        build_redaction_plan(
            repo,
            fingerprints=frozenset(),
            window_lengths=frozenset(),
            salt=b"salt",
            forbidden=forbidden,
            rename_targets={},
        )

    assert pruned_commit in str(excinfo.value)


def test_build_redaction_plan_returns_a_plan_over_a_clean_history(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _commit_files(repo, {"keep.txt": "keep\n"}, "base")
    _commit_files(
        repo,
        {"removed-fragment/only.csv": "x\n", "surviving.txt": "here\n"},
        "mixed",
    )
    forbidden = _forbidden("removed-fragment")

    plan = build_redaction_plan(
        repo,
        fingerprints=frozenset(),
        window_lengths=frozenset(),
        salt=b"salt",
        forbidden=forbidden,
        rename_targets={},
    )

    assert isinstance(plan, RedactionPlan)
    assert any(m.disposition == "removed" for m in plan.path_matches)


# ---------------------------------------------------------------------------
# render_*_plan_tsv -- identifiers and dispositions only, never content
# ---------------------------------------------------------------------------


def test_render_content_plan_tsv_carries_no_matched_substring() -> None:
    """`ContentMatch` today has no content-bearing field, so a check that
    never puts any of the material INTO the input cannot fail if a future
    change adds one back -- true before the call, unfalsifiable regardless
    of `render_content_plan_tsv`'s own behaviour. See the end-to-end version
    below, which plants real material in a synthetic history and would
    catch exactly that regression."""
    content = (
        ContentMatch(
            blob_id="deadbeef",
            pass_name="forbidden_strings",
            disposition="literal_replaceable",
        ),
    )

    rendered = render_content_plan_tsv(content)

    assert "deadbeef" in rendered
    assert "forbidden_strings" in rendered
    assert "literal_replaceable" in rendered


def test_build_and_render_content_plan_carries_none_of_the_planted_material(
    tmp_path: Path,
) -> None:
    """The end-to-end version: plant a forbidden string, an email and a
    symbolic needle, and a numeric corpus dense enough for the value
    matcher, in one blob; build the real plan through `build_redaction_plan`
    and render it; assert NONE of the planted values survive into the
    rendered text. Unlike the unit-level test above, this fails if
    `ContentMatch` or its renderer ever start carrying the matched
    substring, because the substring genuinely was the function's input."""
    salt = b"fixed-test-salt"
    dense_text = "Zone factors: 118.42837, 204.99123, 337.55019, 441.20876, 552.68231\n"
    fps, lengths = _fingerprint_corpus(dense_text, salt)
    assert fps and lengths, "fixture corpus must clear the entropy floor"
    symbolic_label, symbolic_needle = SYMBOLIC_PROBES[-1]
    planted_email = "person@example-domain.test"
    planted_forbidden = "Secret-Token-XYZ"

    repo = _repo(tmp_path)
    _commit_files(
        repo,
        {
            "planted.txt": (
                f"{dense_text}\ncontains {planted_forbidden} literally, "
                f"mentions {symbolic_needle}, and reaches {planted_email}\n"
            )
        },
    )
    forbidden = _forbidden(planted_forbidden)

    plan = build_redaction_plan(
        repo,
        fingerprints=fps,
        window_lengths=lengths,
        salt=salt,
        forbidden=forbidden,
        rename_targets={},
    )
    assert len(plan.content_matches) == 4, (
        "fixture must trip all four content passes to be a real test of "
        "what the render omits"
    )

    rendered = render_content_plan_tsv(plan.content_matches)

    assert planted_forbidden not in rendered
    assert planted_forbidden.lower() not in rendered.lower()
    assert symbolic_needle not in rendered
    assert planted_email not in rendered
    assert "118.42837" not in rendered
    # Positive control: the render is not simply empty.
    assert "value_matcher" in rendered
    assert "forbidden_strings" in rendered
    assert "symbolic_probe" in rendered
    assert "identity_probe" in rendered


def test_render_path_plan_tsv_round_trips_the_path_and_target_stem() -> None:
    paths = (
        PathMatch(path="removed/file.csv", disposition="removed", target_stem=None),
        PathMatch(
            path=".kiro/queue/old-name.md",
            disposition="renamed",
            target_stem="2026-07-26-neutral",
        ),
    )

    rendered = render_path_plan_tsv(paths)

    assert "removed/file.csv\tremoved\t" in rendered
    assert ".kiro/queue/old-name.md\trenamed\t2026-07-26-neutral" in rendered


def test_render_content_plan_tsv_rejects_a_tab_in_a_field() -> None:
    content = (
        ContentMatch(
            blob_id="a\tb",
            pass_name="forbidden_strings",
            disposition="literal_replaceable",
        ),
    )

    with pytest.raises(ValueError):
        render_content_plan_tsv(content)


def test_render_content_plan_tsv_rejects_a_newline_in_a_field() -> None:
    """The tab check alone cannot catch this: a git path CAN legally
    contain a literal newline, so a field with a newline and no tab is a
    real hazard `_check_no_tab_or_newline`'s `or "\\n" in field` clause
    exists for -- and nothing above pinned that clause on its own."""
    content = (
        ContentMatch(
            blob_id="a\nb",
            pass_name="forbidden_strings",
            disposition="literal_replaceable",
        ),
    )

    with pytest.raises(ValueError):
        render_content_plan_tsv(content)


def test_path_match_rejects_unknown_disposition() -> None:
    """The same guard `test_content_match_rejects_unknown_disposition` pins
    for `ContentMatch`, mirrored for `PathMatch` -- nothing before this
    exercised `PATH_DISPOSITIONS` membership with a value that is neither
    `removed` nor `renamed`; the two existing `PathMatch` validation tests
    each use a REAL disposition and vary only `target_stem`."""
    with pytest.raises(ValueError):
        PathMatch(path="x", disposition="bogus", target_stem=None)


# ---------------------------------------------------------------------------
# write_redaction_plan / read_redaction_plan -- round trip, and in-repo refusal
# ---------------------------------------------------------------------------


def test_write_then_read_redaction_plan_round_trips_every_row_in_order(
    tmp_path: Path,
) -> None:
    """The artifact-producing-function-must-read-back-what-it-wrote rule
    this spec's own Implementation Notes state, applied here: build a plan
    with at least one `removed` AND one `renamed` path row (so a swapped
    disposition or a dropped `target_stem` is visible) and two distinct
    content rows (so `content_out.write_text("")` or writing the content
    plan into the path file, or vice versa, is visible), write both files,
    read them back, and compare row-for-row and in order against the
    original `RedactionPlan`."""
    plan = RedactionPlan(
        content_matches=(
            ContentMatch(
                blob_id="blob-aaa",
                pass_name="value_matcher",
                disposition="not_pattern_tractable",
            ),
            ContentMatch(
                blob_id="blob-bbb",
                pass_name="forbidden_strings",
                disposition="literal_replaceable",
            ),
        ),
        path_matches=(
            PathMatch(path="removed/file.csv", disposition="removed", target_stem=None),
            PathMatch(
                path=".kiro/queue/old-name.md",
                disposition="renamed",
                target_stem="2026-07-26-neutral-stem",
            ),
        ),
    )
    # Two DIFFERENT non-existent subdirectories, deliberately -- one shared
    # directory (both files' parent already existing after the first
    # `mkdir`) cannot tell `content_out.parent.mkdir(...)` from
    # `path_out.parent.mkdir(...)` apart; dropping either one alone would
    # still leave both writes succeeding.
    content_out = tmp_path / "scratch-content" / "content.tsv"
    path_out = tmp_path / "scratch-paths" / "paths.tsv"

    write_redaction_plan(plan, content_out, path_out, repo_root=tmp_path / "repo")
    read_back = read_redaction_plan(content_out, path_out)

    assert read_back.content_matches == plan.content_matches
    assert read_back.path_matches == plan.path_matches


def test_write_redaction_plan_refuses_a_content_destination_inside_the_repo_root(
    tmp_path: Path,
) -> None:
    """`content_out` alone is inside `repo_root`; `path_out` is outside.
    Paired with the sibling test below (which puts only `path_out` inside),
    the two conditions no longer co-vary -- reducing the guard's loop to
    check only `content_out` reds THIS test but not the sibling, and
    reducing it to check only `path_out` reds the sibling but not this one.
    Un-confounding these is the point: a rendered PATH plan is the file that
    actually carries forbidden path fragments (every `removed` row IS one),
    so the destination this guard exists to protect is `path_out`, not
    `content_out` -- a single combined fixture could not tell the two
    apart."""
    plan = RedactionPlan(
        content_matches=(),
        path_matches=(
            PathMatch(path="removed/file.csv", disposition="removed", target_stem=None),
        ),
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "scratch"
    inside_content = repo_root / "content.tsv"
    outside_path = outside / "paths.tsv"

    with pytest.raises(ValueError):
        write_redaction_plan(plan, inside_content, outside_path, repo_root=repo_root)


def test_write_redaction_plan_refuses_a_path_destination_inside_the_repo_root(
    tmp_path: Path,
) -> None:
    """`path_out` alone is inside `repo_root`; `content_out` is outside --
    the sibling of the test above, un-confounding the same two conditions
    from the other side. This is the destination that matters most: a
    rendered path plan necessarily carries forbidden path fragments, the
    same reason `tests._forbidden_strings.load` refuses a source path that
    resolves inside the repository working tree."""
    plan = RedactionPlan(
        content_matches=(),
        path_matches=(
            PathMatch(path="removed/file.csv", disposition="removed", target_stem=None),
        ),
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "scratch"
    outside_content = outside / "content.tsv"
    inside_path = repo_root / "paths.tsv"

    with pytest.raises(ValueError):
        write_redaction_plan(plan, outside_content, inside_path, repo_root=repo_root)


def test_write_redaction_plan_refuses_a_symlink_that_resolves_inside_repo_root(
    tmp_path: Path,
) -> None:
    """`path_out` is a symlink living OUTSIDE `repo_root`, textually, but
    pointing AT a file inside it -- a destination `resolved = destination`
    (skipping `.resolve()`) would pass straight through, since the symlink
    itself is not textually under `repo_root`. `.resolve()` is what
    dereferences it back to the real, in-repo target."""
    plan = RedactionPlan(
        content_matches=(),
        path_matches=(
            PathMatch(path="removed/file.csv", disposition="removed", target_stem=None),
        ),
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "scratch"
    outside.mkdir()
    outside_content = outside / "content.tsv"
    real_inside_target = repo_root / "paths.tsv"
    symlinked_path_out = outside / "paths-symlink.tsv"
    symlinked_path_out.symlink_to(real_inside_target)

    with pytest.raises(ValueError):
        write_redaction_plan(
            plan, outside_content, symlinked_path_out, repo_root=repo_root
        )


def test_write_redaction_plan_refuses_when_repo_root_itself_is_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror of the destination-side `.resolve()` test above, on the
    OTHER operand: `repo_root` itself is passed unresolved (`Path(".")`,
    the caller shape task 7.2 will actually use when run from inside the
    repository), and `path_out` is textually inside `repo_root`'s
    RESOLVED form but not inside its unresolved textual form (`"."` has no
    textual containment relationship with anything). `resolved_repo_root =
    repo_root` (skipping `.resolve()` on `repo_root`) would compare
    destinations against the literal string `"."`, which nothing before a
    resolve call is textually "under", so the refusal would silently never
    fire for this caller shape -- every other fixture in this module passes
    an already-resolved absolute `tmp_path`-derived `repo_root`, so none of
    them can distinguish `repo_root.resolve()` from `repo_root` unchanged.
    """
    plan = RedactionPlan(
        content_matches=(),
        path_matches=(
            PathMatch(path="removed/file.csv", disposition="removed", target_stem=None),
        ),
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "scratch"
    outside_content = outside / "content.tsv"
    inside_path = repo_root / "paths.tsv"

    monkeypatch.chdir(repo_root)

    with pytest.raises(ValueError):
        write_redaction_plan(plan, outside_content, inside_path, repo_root=Path("."))


def test_parse_content_plan_tsv_rejects_a_row_with_the_wrong_field_count() -> None:
    """A defensive check over a plan file that was hand-edited or corrupted
    after `write_redaction_plan` wrote it -- a row with too few or too many
    tab-separated fields must raise rather than silently mis-assign a
    disposition to the wrong field.

    `match=` is load-bearing, not decorative: a bare `pytest.raises(
    ValueError)` cannot distinguish `_parse_row`'s own explicit check from
    Python's tuple-unpacking arity error at the immediately following
    `blob_id, pass_name, disposition = _parse_row(...)` line -- both raise
    `ValueError` at the same call site. `_parse_row`'s check is the only one
    that raises with this message."""
    malformed = "blob_id\tpass_name\tdisposition\nonly-two-fields\tvalue_matcher\n"

    with pytest.raises(ValueError, match="malformed plan row"):
        parse_content_plan_tsv(malformed)
