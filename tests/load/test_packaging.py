"""Packaging guards for the load layer.

Two things must hold now that the third-party methodology has been withdrawn
(Amendment 2, Req 13.1):

* the TOML *write* companion to stdlib ``tomllib`` -- ``tomli_w`` -- is a
  declared runtime dependency, so profile writes work from a clean install
  (the profile store's writer outlives the withdrawn methodology and still
  needs it); and
* no methodology path and no bundled lookup table ships under the load layer
  -- a built wheel contains no non-``.py`` file of any kind under
  ``fitdocs/load/`` (a bundled table can ship as ``.json``, ``.toml``,
  ``.parquet``, ... just as easily as ``.csv``), and no ``.py`` file under
  ``fitdocs/load/`` outside an explicit, reviewed allowlist of the modules
  that legitimately live there.

The directory-membership check (an allowlist of what *may* be present, rather
than a denylist of withdrawn names) is deliberately scoped to
``fitdocs/load/`` alone: a *new* module appearing there under any name --
``methodology_a.py``, ``methodology_b.py``, anything -- is exactly the shape
a rename-to-evade attempt takes, and the allowlist catches it whatever it is
called. A denylist of withdrawn *names* cannot do that by construction:
matching one withdrawn calculator's class name says nothing about a module
shipping the same calculator under a different name in a differently named
file. The justification is not that this directory is small and stable -- it
is not: three specs already queued behind ``training-load`` (``load-channels``,
``threshold-load``, ``activity-qa-flags``) between them add roughly twenty new
modules under ``fitdocs/load/`` on top of the dozen here today, so the
allowlist is heading toward three times its current size, not holding steady.
The justification is that each addition is a deliberate, reviewed act -- a
module lands under ``fitdocs/load/`` only via a spec task that a reviewer
signs off, and the allowlist edit rides in the same change as the module it
allows, so the guard's own failure message (below) says exactly that: add the
entry only alongside the module it names. A run of one-line "add it to the
allowlist" edits carries its own risk -- it can train an agent that the
add-it branch is the routine, low-scrutiny response to this guard failing,
which is precisely the opening a phantom entry (an allowlisted name with no
module behind it, added in a change that touches no module) would need to
pass unnoticed. That is why the membership check below is an equality
comparison, not a one-directional subset check: a phantom entry reds the
suite immediately, the same as a genuine reintroduction would, rather than
sitting invisible until something ships to fill it. A directory-wide
allowlist across the whole of ``src/fitdocs`` (rather than just
``fitdocs/load/``) was considered and rejected as too brittle: it would need
editing for every legitimate new module anywhere in the package, which is far
too broad and fast-moving a surface to keep current without becoming noise
the guard trains people to ignore.

The wheel-inclusion guard builds a real wheel from this checkout (sub-second
with hatchling) and inspects its file list, proving the absence in a
*distribution* -- not merely in the source tree.

A second guard does the same for the **sdist**. The two artifacts `uv build`
produces are materially different: hatchling's default wheel target is
scoped to ``packages = ["src/fitdocs"]`` (declared above), but its default
sdist target has no such scope and includes the working tree minus whatever
``.gitignore`` excludes -- not "whatever git tracks": an untracked-but-
unignored file ships too (verified by probe: an untracked file placed under
``src/fitdocs/`` appeared in the built archive).

Historically that meant, absent an explicit exclude, the sdist redistributed
the withdrawn methodology's writeup and both of its extracted tables verbatim
even though the wheel never had -- the source workbook carried a
redistribution restriction that the repository never obtained permission to
clear, so a ``[tool.hatch.build.targets.sdist]`` exclude in ``pyproject.toml``
carried the licensing fix. encumbered-content-purge task 3.1 (Req 1.1, 2.1)
deleted the writeup and both extracted tables from the working tree entirely
and deleted that exclude section along with them (nothing left to exclude,
and no exclude entry left whose only effect was excluding a removed path,
Req 2.1) -- the guards below now prove the stronger absence directly, by
value, rather than proving an exclude config still does its job.

**Re-based onto the shared value oracle** (``tests._content_oracle``,
``tests._content_fingerprints``; encumbered-content-purge task 4.1, Req 3.1,
3.2). Both the source-tree scan and the built-sdist scan below digest
overlapping windows of numeric and clock-time tokens. Both compare those
digests against a precomputed set rather than matching plaintext values by
substring. Neither scan holds a value from the withdrawn methodology's
tables anywhere in this repository (Req 3.7). Each scan holds only opaque
digests.

**The detection data is unverifiable by construction from this commit
forward** (Req 3.6). The digest set and window-length set
``tests/_content_fingerprints.py`` supplies were measured against the
withdrawn methodology's source files before task 3.1 deleted them from the
working tree. Those source files are gone from the working tree. They
remain reachable in history until the Major 7 history rewrite this spec
also plans (see ``docs/reference/history-rewrites.md``). This guard cannot
regenerate or re-check those digests against their source from the working
tree alone, and does not read history to do so.

**A lone pasted constant of the size these tables' values carry is not
detected by either scan below** (Req 3.6, restated here at the guard site
rather than left only in ``tests/_content_oracle.py``). Those values supply
roughly 19.9 bits of guessing entropy each, under the oracle's conservative
per-digit estimate. That is far short of the 96-bit floor a window must
clear before the oracle will fingerprint it. Detecting one of these values
alone needs several consecutive tokens together clearing the floor. This is
a property of values this short, not a guarantee over every possible
numeric token: ``tests/_content_oracle.py``'s own ``ENTROPY_FLOOR_BITS``
documents that a single token carrying around 29 or more digit characters
clears the floor unaided.

**Four token-literal detections this module used to make are retired here,
not re-based** (Req 11.7, 11.9). They are: a substring scan for the
withdrawn calculator's class name and dotted module path over every shipped
``.py`` file; an assertion that the withdrawn calculator package's
directory no longer exists under ``src/fitdocs``; a substring scan for the
withdrawn methodology's name over the built wheel's member names; and the
matching substring scan over the built sdist's member names. None of the
four is re-based onto the value oracle above. None of the four detects a
*value*. Each matched an identifying token literally. Req 11.7 forbids
retaining that token in this repository in any form from which it can be
read back. This is a genuine loss of detection, stated here rather than
left implicit (Req 11.9): as of this commit, reintroducing any of the four
retired spellings under ``src/fitdocs`` is caught by nothing in this test
suite. ``tests/_forbidden_strings.py`` (Req 11.7, 11.8) supplies the
loader and the tree-scanning mechanism this loss is meant to move to, but
no test yet drives that mechanism against the whole of ``src/fitdocs`` for
these four spellings. encumbered-content-purge task 4.3 is the scheduled
standing guard that closes this gap.

The self-exemption the sdist scan used to need for its own source file is
also removed here. This module's own source used to carry the withdrawn
methodology's plaintext values; that is why the exemption existed. After
this re-basing, this module's own text tokenises to nothing that digests
into the fingerprint set below. No exemption is needed to keep this file's
own content clean of a hit.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests._content_fingerprints import FINGERPRINTS, SALT, WINDOW_LENGTHS
from tests._content_oracle import ENTROPY_FLOOR_BITS, digest, scan, tokens, windows

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_FITDOCS = _PROJECT_ROOT / "src" / "fitdocs"
_BUILD_TIMEOUT_S = 120

# The complete, reviewed set of ``.py`` modules that may ship under
# ``fitdocs/load/`` in a built wheel (Req 13.1). Deliberately an allowlist,
# not a denylist -- see the module docstring for why the right shape here is
# not "the directory stays small" (it will roughly triple across specs
# already queued) but "every addition is a reviewed act, made in the same
# change as the module it allows". This set is compared for *equality*
# against the wheel's actual membership below, not just checked as a
# superset: an entry with no module behind it (a phantom, added without its
# module) is exactly as wrong as a module with no entry, and must fail the
# same way.
_LOAD_MODULE_ALLOWLIST = frozenset(
    {
        "fitdocs/load/__init__.py",
        "fitdocs/load/arbitrate.py",
        "fitdocs/load/docedit.py",
        "fitdocs/load/engine.py",
        "fitdocs/load/priority.py",
        "fitdocs/load/profile.py",
        "fitdocs/load/prompts.py",
        "fitdocs/load/registry.py",
        "fitdocs/load/render.py",
        "fitdocs/load/settings.py",
        "fitdocs/load/threshold/__init__.py",
        "fitdocs/load/threshold/anchors.py",
        "fitdocs/load/threshold/calculator.py",
        "fitdocs/load/threshold/discipline.py",
        "fitdocs/load/threshold/selection.py",
        "fitdocs/load/types.py",
        "fitdocs/load/channels/__init__.py",
        "fitdocs/load/channels/grade.py",
        "fitdocs/load/channels/heart_rate.py",
        "fitdocs/load/channels/pace.py",
        "fitdocs/load/channels/power.py",
        "fitdocs/load/channels/sources.py",
        "fitdocs/load/channels/sufficiency.py",
        "fitdocs/load/channels/types.py",
        "fitdocs/load/channels/weighting.py",
        "fitdocs/load/qa/__init__.py",
        "fitdocs/load/qa/types.py",
        "fitdocs/load/qa/sources.py",
        "fitdocs/load/qa/cadence.py",
    }
)


def test_tomli_w_importable() -> None:
    """The TOML write dependency is installed (the profile store's writer).

    ``tomllib`` (read) is stdlib; ``tomli_w`` (write) is the runtime
    dependency the profile store needs regardless of which methodology, if
    any, is registered.
    """
    import tomli_w  # noqa: F401  -- import is the assertion


def test_no_shipped_module_carries_a_withdrawn_value() -> None:
    """No ``.py`` file under ``src/fitdocs`` holds a numeric-token window
    that digests into the withdrawn methodology's retained-table fingerprint
    set (Req 3.1, 3.2).

    A test with this scan half existed before encumbered-content-purge task
    3.1 deleted the source workbook and its extracted tables. That prior
    test also verified its own detection constants by reading those source
    files before scanning. Task 3.1 retired it whole rather than leave it
    crashing, because the source-verification half could no longer run at
    all once the files it read were gone. This test re-introduces the
    scanning half only, re-based onto the shared value oracle rather than
    onto a literal read of the deleted source. See the module docstring for
    what the lost source-verification means going forward (Req 3.6).
    """
    assert FINGERPRINTS, (
        "the fingerprint set must not be emptied -- an empty set makes this "
        "scan vacuously pass with nothing actually checked"
    )
    assert WINDOW_LENGTHS, (
        "the window-length set must not be emptied -- an empty set makes "
        "windows() emit nothing and this scan vacuously pass"
    )

    scanned = 0
    offenders: list[str] = []
    for path in _SRC_FITDOCS.rglob("*.py"):
        scanned += 1
        text = path.read_text(encoding="utf-8")
        if scan(text, FINGERPRINTS, WINDOW_LENGTHS, SALT):
            offenders.append(str(path.relative_to(_PROJECT_ROOT)))

    assert scanned > 0, (
        "this walk scanned zero .py files under src/fitdocs -- the walk is "
        "looking at the wrong directory, not proving the tree is clean"
    )
    assert not offenders, (
        f"shipped source under src/fitdocs holds a value matching the "
        f"withdrawn methodology's retained tables: {offenders}"
    )


def test_value_oracle_control_flags_invented_values_not_a_clean_sibling(
    tmp_path: Path,
) -> None:
    """Synthetic positive control for the value-oracle re-basing above and
    below (Req 3.3, 3.4): the fingerprint set the guards in this module
    consult holds no independently re-verifiable subject after task 3.1, so
    this control proves the SCAN MECHANISM ITSELF still discriminates, using
    invented values that never appeared in any withdrawn table rather than
    the real (now-unverifiable) one.

    Builds a throwaway digest set from an invented sentence, generates its
    windows with the oracle's own ``windows``/``digest`` functions exactly as
    ``tests/_content_fingerprints.py`` was generated, and asserts ``scan``
    flags a file carrying that sentence and does not flag a sibling file
    that does not -- the sibling half is what stops this control from
    passing by matching everything.
    """
    invented_text = (
        "471.928635 kJ over 3:41:52 at a factor of 0.837291605 across "
        "219384756 repetitions"
    )
    toks = tokens(invented_text)
    emitted = windows(toks, ENTROPY_FLOOR_BITS)
    assert emitted, (
        "the invented control sentence does not clear the entropy floor -- "
        "strengthen the fixture rather than weakening the assertion below"
    )
    control_fingerprints = frozenset(
        digest(toks[start : start + length], SALT) for start, length in emitted
    )
    control_lengths = frozenset(length for _, length in emitted)

    planted = tmp_path / "planted.py"
    planted.write_text(f"# {invented_text}\n")
    clean_sibling = tmp_path / "clean_sibling.py"
    clean_sibling.write_text("# nothing related to any invented value here\n")

    assert scan(planted.read_text(), control_fingerprints, control_lengths, SALT), (
        "the synthetic control's own planted file was not flagged -- the "
        "control cannot prove anything if it does not first prove itself"
    )
    assert not scan(
        clean_sibling.read_text(), control_fingerprints, control_lengths, SALT
    ), "the clean sibling was flagged -- the control passes by matching everything"


def test_fresh_interpreter_registry_holds_exactly_the_threshold_built_in() -> None:
    """Importing the load layer in a fresh interpreter leaves the calculator
    registry holding exactly one calculator, ``threshold`` -- never more, never
    fewer (``threshold-load``, Req 1.1-1.3; supersedes this test's own former
    ``Req 13.2`` reading of an empty registry, a recorded revalidation trigger
    there).

    A *declining* built-in registered at ``fitdocs.load`` import time is
    behaviourally identical to no built-in at all for most of the suite (1837
    tests once passed with exactly such a fixture present, task 6.3's
    finding) -- so the guard must assert the registry's *contents*, in a
    subprocess: an in-process re-import of an already-imported ``fitdocs.load``
    is a ``sys.modules`` cache hit that runs no module-level code a second time
    and proves nothing about a cold import.
    """
    code = "import fitdocs.load as load; print(f'REGISTRY={load.available()!r}')"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert (
        "REGISTRY=(ThresholdCalculator(calculator_id='threshold'," in result.stdout
    ), result.stdout
    # Exactly one entry, not two: a second calculator_id=... substring would
    # mean a duplicate or an extra built-in crept in.
    assert result.stdout.count("calculator_id=") == 1, result.stdout


def test_wheel_contains_no_stray_data_or_module_under_load(
    tmp_path: Path,
) -> None:
    """A wheel built from this checkout ships no methodology data (Req 13.1).

    Builds a real wheel and inspects its member list directly, proving the
    absence in a *distribution* -- not merely that the files are gone from
    the source tree. A wheel is a zip, so its contents are read with
    :mod:`zipfile`.

    Two independent checks over the member list:

    * no non-``.py`` member at all under ``fitdocs/load/`` -- a bundled
      table shipped under a neutral extension (``.json``, ``.toml``,
      ``.parquet``, ...) is exactly as prohibited as a ``.csv`` one, so the
      check is extension-agnostic rather than naming ``.csv`` specifically;
      and
    * the ``.py`` members under ``fitdocs/load/`` are exactly
      ``_LOAD_MODULE_ALLOWLIST`` -- checked in both directions, so a module
      reintroduced under any name is caught here, and so is a phantom
      allowlist entry that names no module the wheel actually ships.

    A third check -- a substring scan of every member's path for the
    withdrawn methodology's name -- used to live here. It is retired, not
    re-based (Req 11.7, 11.9): it matched an identifying token literally,
    and its coverage moves to the standing forbidden-string guard described
    in the module docstring.
    """
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required to build the wheel for this packaging guard but was not "
        "found on PATH; install uv (https://docs.astral.sh/uv/) to run it"
    )

    build = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_S,
        check=False,
    )
    assert build.returncode == 0, (
        f"`uv build --wheel` failed:\n{build.stdout}\n{build.stderr}"
    )

    wheels = sorted(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()

    load_members = [n for n in names if n.startswith("fitdocs/load/")]
    assert load_members, (
        "the wheel contains no member at all under fitdocs/load/ -- this "
        "guard's walk is looking at the wrong prefix, not proving the "
        "directory is clean"
    )

    load_non_py = [
        n for n in load_members if not n.endswith(".py") and not n.endswith("/")
    ]
    assert not load_non_py, (
        f"built wheel contains a bundled data file under fitdocs/load/ (not a "
        f".py module): {load_non_py}"
    )

    load_py = frozenset(n for n in load_members if n.endswith(".py"))
    unexpected = sorted(load_py - _LOAD_MODULE_ALLOWLIST)
    missing = sorted(_LOAD_MODULE_ALLOWLIST - load_py)
    assert not unexpected, (
        f"built wheel contains .py module(s) under fitdocs/load/ not in "
        f"_LOAD_MODULE_ALLOWLIST: {unexpected} -- if this is a legitimate "
        f"new module, add it to the allowlist deliberately; if it is not, "
        f"a withdrawn methodology has been reintroduced under a new name"
    )
    assert not missing, (
        f"_LOAD_MODULE_ALLOWLIST names module(s) the built wheel does not "
        f"contain: {missing} -- either the module was deleted and the "
        f"allowlist entry is stale (remove it), or the entry was added "
        f"without the module it claims to allow (a phantom entry that "
        f"widens what a future reintroduction could pass through "
        f"unnoticed -- remove it and add the entry only alongside the "
        f"module it names)"
    )


# The only research-record members the sdist may legitimately still carry,
# keyed by archive member NAME. Value-keying (below) is what detects the
# retained research record wherever it moves; this allowlist is a narrow,
# separate exemption mechanism for a specific, reviewed member that is
# expected to legitimately trip the value scan -- it does not weaken the
# scan itself, since an entry here still has to name an exact archive
# member. training-load task 5.2 / design.md's Out-of-Boundary list used to
# require the writeup and its extracted tables stay in the source tree as a
# retained
# research record of a withdrawn methodology (design.md was explicit that
# record was "not shipped data", so it belonged in the checkout, not in the
# packaged sdist artifact) -- reversed by encumbered-content-purge (Req 4.1,
# 4.2): all three paths (the writeup and its two tables) are now deleted
# from the working tree entirely (Req 1.1), and the
# ``[tool.hatch.build.targets.sdist]`` exclude that used to keep them out of
# the sdist specifically is deleted with them (Req 2.1) -- there is nothing
# left to exclude. This allowlist is deliberately empty for the stronger
# reason now: none of the three paths exist anywhere in the tree to be a
# candidate for it. If a future change legitimately needs a research-record
# file in the sdist, add it here alongside the change that reintroduces the
# file -- do not let this list grow to explain away a build that ships
# something it should not. Entries must carry the archive's top-level
# ``fitdocs-X.Y.Z/`` prefix (matching ``tarfile.getnames()`` below, e.g.
# ``"fitdocs-0.1.0/docs/reference/some_table.csv"``), not a bare
# repo-relative path -- a plain path would never match a member name and
# would silently fail to exempt anything. That prefix embeds the project
# version, so an entry added here would also need updating at every version
# bump -- one more reason to keep this set empty rather than lean on it.
_SDIST_WITHDRAWN_ALLOWLIST: frozenset[str] = frozenset()


def _decode_and_scan(
    content: bytes,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
) -> bool:
    """True if `content`, decoded permissively, holds a value-oracle match.

    Decodes with ``errors="replace"`` rather than raising or skipping
    content that is not valid UTF-8. A byte that cannot decode becomes one
    U+FFFD replacement character. That replacement character is never a
    digit. It does not join a digit run on either side of it. A numeric-
    token window elsewhere in otherwise-undecodable content therefore still
    tokenises intact and still scans.
    """
    text = content.decode("utf-8", errors="replace")
    return scan(text, fingerprints, window_lengths, salt)


def test_decode_and_scan_flags_a_value_beside_an_undecodable_byte() -> None:
    """A numeric-token window is still detected when it sits beside a byte
    that is not valid UTF-8 (Req 3.2).

    Regression fixture for a defect a review round of this task found: an
    earlier version of ``_decode_and_scan`` skipped a member's content
    outright on ``UnicodeDecodeError``, so a single stray non-UTF-8 byte
    anywhere in an otherwise plaintext member (a realistic shape for an
    exported CSV) made that member's entire content invisible to the sdist
    scan below -- a wider exemption than the single-file self-exemption
    this task removed elsewhere in this module. Builds a throwaway digest
    set from an invented sentence, the same technique
    ``test_value_oracle_control_flags_invented_values_not_a_clean_sibling``
    uses, then prefixes the encoded bytes with one byte that is not valid
    UTF-8 on its own.
    """
    invented_text = (
        "582.049371 kJ over 2:18:56 at a factor of 0.194837265 across "
        "573920184 repetitions"
    )
    toks = tokens(invented_text)
    emitted = windows(toks, ENTROPY_FLOOR_BITS)
    assert emitted, (
        "the invented control sentence does not clear the entropy floor -- "
        "strengthen the fixture rather than weakening the assertion below"
    )
    control_fingerprints = frozenset(
        digest(toks[start : start + length], SALT) for start, length in emitted
    )
    control_lengths = frozenset(length for _, length in emitted)

    # 0xB0 alone is not a valid UTF-8 byte sequence (it is a continuation
    # byte with no leading byte before it) -- confirmed below rather than
    # merely asserted, so this fixture is proven to exercise the decode
    # failure it claims to.
    undecodable_content = b"\xb0" + invented_text.encode("utf-8")
    with pytest.raises(UnicodeDecodeError):
        undecodable_content.decode("utf-8")

    assert _decode_and_scan(
        undecodable_content, control_fingerprints, control_lengths, SALT
    ), (
        "a genuinely present value beside one byte that is not valid UTF-8 "
        "was not flagged -- decoding must not skip content on a decode "
        "failure"
    )


def test_sdist_contains_no_withdrawn_research_record(
    tmp_path: Path,
) -> None:
    """A built sdist ships no value from the withdrawn methodology's
    retained tables (Req 3.1, 3.2).

    The wheel guard above proves ``fitdocs/load/`` is clean, but the wheel
    and the sdist are different artifacts with different default hatchling
    scoping: the wheel target above is scoped to ``packages =
    ["src/fitdocs"]``, while hatchling's default sdist target has no such
    scope and includes the working tree minus whatever ``.gitignore``
    excludes -- not "whatever git tracks": an untracked-but-unignored file
    ships too. Before the ``[tool.hatch.build.targets.sdist]`` exclude
    landed, ``uv build --sdist`` on this checkout included the withdrawn
    methodology's writeup and both extracted tables verbatim -- the source
    workbook carried a redistribution restriction the repository never
    obtained permission to clear, so shipping it in a published sdist would
    be a licensing exposure, not merely defence-in-depth.

    This check is VALUE-keyed, via the shared oracle (``tests._content_oracle``,
    ``tests._content_fingerprints``), not path-keyed and not a plaintext
    substring match (queue item 2026-07-29-sdist-guard-rename-evadable): a
    bare ``git mv`` of the withdrawn methodology's extracted-table directory
    defeated the prior path-literal version of this guard (and the matching
    ``pyproject.toml`` exclude) at once, shipping both tables in a published
    sdist with the rest of the suite green. Every regular archive member's
    bytes -- other than symlink members, which ``member.isfile()`` already
    excludes and which hatchling stores as zero-size (nothing to
    redistribute) -- are scanned for a value matching the withdrawn
    methodology's retained tables, so this fires wherever the retained
    record moves, not only at the paths it lives at today. This module's own
    source is no longer exempted from the scan (the self-exemption that used
    to live here is removed, see the module docstring): after re-basing onto
    the value oracle, this file's own text tokenises to nothing that digests
    into the fingerprint set, so no exemption is needed to keep it clean.

    A positive control (the package's own source module) guards against the
    "vacuous walk" failure mode: if the build silently produced an empty or
    truncated archive, that assertion catches it before the absence checks
    below could pass having inspected nothing. Two further, DIFFERENT
    positive controls guard the value scan itself:

    * ``scanned > 0`` asserts the loop reached at least one regular member
      -- it catches only a scan that opened *zero* members (e.g. an
      ``isfile()`` bug that skips every member); it says nothing about how
      much of any opened member was read.
    * ``bytes_inspected == expected_bytes`` asserts the *total number of
      bytes actually read* across every scanned member equals the *sum of
      each member's own reported size* in the archive. This is the
      assertion that catches a partial read: ``fileobj.read(0)`` in place of
      ``fileobj.read()`` opens every member (satisfying ``scanned > 0``) and
      reads zero bytes from all of them; ``fileobj.read(1)`` and
      ``fileobj.readline()`` each open every member and read some but not
      all of most of them. All three leave ``bytes_inspected <
      expected_bytes`` while still reading a nonzero, easy-to-mistake-for-
      sufficient number of bytes overall -- which is why the check is an
      exact equality against each member's declared size, not merely
      ``bytes_inspected > 0``. Reproduced: each of the three mutations above
      left both extracted tables shipping in the sdist with
      ``uv run pytest`` reporting a passing run under the weaker check.

    A member whose bytes are not valid UTF-8 is decoded with
    ``errors="replace"`` rather than skipped. A skip would exempt the whole
    member's content from the scan on one stray non-UTF-8 byte, and an
    undecodable member can still carry an intact ASCII digit run this
    oracle tokenises normally on either side of the replacement character.
    The byte-count equality below counts every scanned member's bytes
    toward ``bytes_inspected`` regardless of decodability. That equality
    exists to catch a partial *read*, not a decode failure.

    Separately, the digest set and the window-length set this scan consults
    are asserted non-empty above. An emptied set would make the absence
    check below pass vacuously. That non-empty assertion is restated here
    rather than left only in the source-tree guard above. Each guard in
    this module stands on its own.
    """
    assert FINGERPRINTS, (
        "the fingerprint set must not be emptied -- an empty set makes the "
        "content scan below vacuously pass with nothing actually checked"
    )
    assert WINDOW_LENGTHS, (
        "the window-length set must not be emptied -- an empty set makes "
        "windows() emit nothing and the content scan below vacuously pass"
    )

    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required to build the sdist for this packaging guard but was "
        "not found on PATH; install uv (https://docs.astral.sh/uv/) to run it"
    )

    build = subprocess.run(
        [uv, "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_S,
        check=False,
    )
    assert build.returncode == 0, (
        f"`uv build --sdist` failed:\n{build.stdout}\n{build.stderr}"
    )

    sdists = sorted(tmp_path.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected exactly one built sdist, got {sdists}"

    with tarfile.open(sdists[0]) as sdist:
        names = sdist.getnames()

    # Positive control: prove the walk actually inspected a non-empty,
    # correctly-built archive before trusting any absence check below.
    source_members = [n for n in names if n.endswith("src/fitdocs/__init__.py")]
    assert source_members, (
        "the built sdist contains no src/fitdocs/__init__.py -- this guard's "
        "archive is empty or malformed, so the absence checks below would "
        "otherwise pass having inspected nothing"
    )

    scanned = 0
    bytes_inspected = 0
    expected_bytes = 0
    withdrawn_members: list[str] = []
    with tarfile.open(sdists[0]) as sdist:
        for member in sdist.getmembers():
            if not member.isfile() or member.name in _SDIST_WITHDRAWN_ALLOWLIST:
                continue
            expected_bytes += member.size
            fileobj = sdist.extractfile(member)
            if fileobj is None:
                continue
            content = fileobj.read()
            scanned += 1
            bytes_inspected += len(content)
            if _decode_and_scan(content, FINGERPRINTS, WINDOW_LENGTHS, SALT):
                withdrawn_members.append(member.name)

    assert scanned > 0, (
        "the sdist content scan opened zero regular members -- this guard's "
        "walk is inspecting nothing, not proving the archive is clean"
    )
    assert bytes_inspected == expected_bytes, (
        f"the sdist content scan read {bytes_inspected} bytes but scanned "
        f"members total {expected_bytes} bytes by their own declared size "
        f"-- a partial read (e.g. fileobj.read(N) for some N, or "
        f"fileobj.readline()) leaves scanned > 0 satisfied while a value "
        f"occurring after the read cutoff in any member is never seen"
    )
    assert not withdrawn_members, (
        f"built sdist contains a value matching the withdrawn methodology's "
        f"retained research record: {sorted(withdrawn_members)} -- this is "
        f"a licensing exposure, not defence-in-depth; add a matching "
        f"exclude to [tool.hatch.build.targets.sdist] in pyproject.toml. If "
        f"one of these paths legitimately belongs in the sdist, add it to "
        f"_SDIST_WITHDRAWN_ALLOWLIST in the same change that makes it true"
    )
