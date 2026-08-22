"""One-shot fingerprint generator for `ContentOracle` (design.md `####
ContentOracle`, Req 3.2, 3.7) -- task 2.4.

Imports `tests._content_oracle` for every piece of the mechanism
(tokenising, windowing, digesting, scanning); writes no second definition of
any of it. Produces two things, both only ever generated once, both
irreproducible after task 3.1 deletes the source material:

1. `tests/_content_fingerprints.py` -- the generated data module beside the
   matcher (`render_data_module` / `write_data_module` below): a salt, the
   entropy floor and digest length recorded at generation time, the digest
   set, and the window-length set. Holds no value from the removed
   material -- only the mechanism's output.
2. A durable, out-of-repository record (`write_results` below) of the
   one-shot evasion-acceptance run: a pass/fail line per evasion catalogued
   in tasks.md 2.4 and design.md, plus the baseline liveness checks the
   task's observable states (the writeup flagged, both tables flagged, a
   control file not flagged). This is the last moment the oracle can be
   tested against its real subject; task 3.4 consumes the recorded results,
   never the values.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer
from tests._content_oracle import DIGEST_HEX_LENGTH as _ORACLE_DIGEST_HEX_LENGTH
from tests._content_oracle import ENTROPY_FLOOR_BITS as _ORACLE_ENTROPY_FLOOR_BITS
from tests._content_oracle import digest, scan, tokens, windows
from tests._forbidden_strings import ENV_VAR as _FORBIDDEN_STRINGS_ENV_VAR

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_DATA_MODULE = _PROJECT_ROOT / "tests" / "_content_fingerprints.py"


def _default_sources() -> tuple[Path, ...]:
    """The tracked-file paths this generator fingerprinted once, before task
    3.1 deleted them (module docstring: this generation cannot be
    repeated). Resolved from the file `FITDOCS_FORBIDDEN_STRINGS` names --
    the ``path``-category entries ending `.md` or `.csv` -- rather than
    hard-coded, so this module holds none of the removed paths itself.
    Returns an empty tuple when the variable is unset, which makes `run()`'s
    CLI default an empty source list; that is already the practical state,
    since the source material this generator fingerprinted no longer exists
    on disk and the generation cannot be repeated regardless.
    """
    raw = os.environ.get(_FORBIDDEN_STRINGS_ENV_VAR)
    if raw is None:
        return ()
    from scripts.purge.sweep import entries_by_category, load_categorized_entries

    entries = load_categorized_entries(Path(raw))
    path_fragments = entries_by_category(entries).get("path", ())
    return tuple(
        _PROJECT_ROOT / fragment
        for fragment in path_fragments
        if fragment.endswith((".md", ".csv"))
    )


# Invented for the acceptance control -- no relation to any retained table.
# This is the negative half of the task's stated observable: "a control file
# without them is not [flagged]".
_CONTROL_TEXT = (
    "Invented training log, for the acceptance control only: easy run, "
    "5.2 km in 32:10 at an average heart rate of 145 bpm, elevation gain "
    "210 m, cadence 168 spm, temperature 18.4 C. None of these values are "
    "drawn from any retained research table."
)


# --- salt --------------------------------------------------------------------


def generate_salt(num_bytes: int = 32) -> bytes:
    """A fresh random salt. Durable and published once generated (design.md
    `#### ContentOracle`): it defeats precomputed tables only -- the window
    entropy floor carries the security, not the salt's secrecy."""
    return secrets.token_bytes(num_bytes)


# --- fingerprint collection ---------------------------------------------------


def collect_fingerprints(
    texts: Sequence[str], *, salt: bytes, floor: float = _ORACLE_ENTROPY_FLOOR_BITS
) -> tuple[frozenset[str], frozenset[int]]:
    """Tokenise, window and digest every text in `texts` independently,
    returning the combined digest set and the combined window-length set.

    Each text is windowed on its own token list -- a window never spans two
    source texts, so a partial match cannot straddle a boundary that would
    not exist in any single re-introduced copy of one file.
    """
    fingerprints: set[str] = set()
    lengths: set[int] = set()
    for text in texts:
        toks = tokens(text)
        for offset, length in windows(toks, floor):
            fingerprints.add(digest(toks[offset : offset + length], salt))
            lengths.add(length)
    return frozenset(fingerprints), frozenset(lengths)


# --- generated data module -----------------------------------------------------


def render_data_module(
    *,
    salt: bytes,
    entropy_floor_bits: float,
    digest_hex_length: int,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    source_count: int,
    generated_at: str,
) -> str:
    """Render `tests/_content_fingerprints.py`'s source text.

    Holds no value from the removed material -- only the salt, the entropy
    floor and digest length recorded at generation time, the digest set, the
    window-length set, and a count of how many sources were measured (design.md
    `#### ContentOracle`, Req 3.7). Earlier revisions also recorded the
    sources' relative paths (`SOURCE_PATHS`); that field was dropped because a
    path fragment naming the removed material's location is itself an
    identifying token this module must not retain (Req 3.7) -- `source_count`
    keeps the shape guard meaningful (a truncation still shows up as a wrong
    count) without carrying any identity.
    """
    fingerprint_lines = ",\n".join(
        f'    "{fingerprint}"' for fingerprint in sorted(fingerprints)
    )
    window_length_lines = ",\n".join(
        f"    {length}" for length in sorted(window_lengths)
    )
    docstring = (
        "Generated data for `ContentOracle` (design.md `#### ContentOracle`,\n"
        "Req 3.2, 3.7).\n\n"
        "Produced once, by `scripts/purge/fingerprints.py`'s one-shot\n"
        "generator (task 2.4), measured against `SOURCE_COUNT` real files\n"
        "before their deletion in task 3.1. Holds no value from the removed\n"
        "material -- only a salt, the entropy floor and digest length\n"
        "recorded at generation time, a set of truncated digests, a set of\n"
        "window lengths, and a count of sources measured. No source path or\n"
        "other identifying token is recorded here (Req 3.7).\n\n"
        "Do not hand-edit: every field here is generated, and the\n"
        "generation cannot be repeated once the source files it measured\n"
        "are gone."
    )
    return (
        f'"""{docstring}\n"""\n\n'
        "from __future__ import annotations\n\n"
        f"SALT: bytes = bytes.fromhex(\n    {salt.hex()!r}\n)\n"
        f"ENTROPY_FLOOR_BITS: float = {entropy_floor_bits!r}\n"
        f"DIGEST_HEX_LENGTH: int = {digest_hex_length!r}\n"
        f"GENERATED_AT: str = {generated_at!r}\n"
        f"SOURCE_COUNT: int = {source_count!r}\n"
        f"WINDOW_LENGTHS: frozenset[int] = frozenset(\n"
        f"    {{\n{window_length_lines},\n    }}\n)\n"
        f"FINGERPRINTS: frozenset[str] = frozenset(\n"
        f"    {{\n{fingerprint_lines},\n    }}\n)\n"
    )


def write_data_module(path: Path, content: str) -> None:
    """Write the rendered data module's source text to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- evasion transformations --------------------------------------------------

# Matches a comma that IS a thousands separator inside a digit run (a comma
# flanked by a digit on the left and exactly three digits then a non-digit
# on the right), protecting it from the delimiter reformatting below -- so
# reformatting a CSV's field delimiters does not fragment a grouped-integer
# token into two smaller ones. Verified against the real corpus (task 2.4's
# status report): neither withdrawn table nor the writeup contains a
# thousands-grouped integer, so this is a defensive generalisation rather
# than a fixture drawn from what is actually there.
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")


def reformatted_copy(text: str) -> str:
    """A renamed-and-reformatted re-add of `text`: field delimiters and
    heading markup change, but no digit run is touched or reordered, so any
    digest generated over the original still matches. One of the five
    evasion probes catalogued in tasks.md 2.4 and design.md -- not itself
    one of the three entries in the withdrawal-evasions queue item, whose
    "bundled table one level up" entry is a verbatim copy, not a reformatted
    one."""
    protected = _THOUSANDS_COMMA.sub("\0", text)
    reformatted = protected.replace(",", " | ")
    reformatted = reformatted.replace("\0", ",")
    reformatted = re.sub(
        r"^#+\s*", "renamed section: ", reformatted, flags=re.MULTILINE
    )
    return reformatted


def as_python_literal(text: str, constant_name: str = "_PASTED_TABLE") -> str:
    """`text`'s non-blank lines, quoted verbatim as a Python string-tuple
    literal -- evasion 3 from the withdrawal-evasions queue item: a table
    pasted as language literals into an allowlisted module. Quoting does not
    touch digit runs, so `tokens()` finds the same sequence in the same
    order."""
    lines = [line for line in text.splitlines() if line.strip()]
    body = ",\n".join(f"    {line!r}" for line in lines)
    return f"{constant_name}: tuple[str, ...] = (\n{body},\n)\n"


def different_extension_copy(text: str) -> str:
    """A copy of `text` shipped under a different file extension -- one of
    the five evasion probes catalogued in tasks.md 2.4 and design.md (this
    one has no counterpart in the three-entry withdrawal-evasions queue
    item). The value matcher scans text content, never a path or an
    extension, so this transformation is the identity; it is still run and
    recorded as its own probe because extension-keyed guards (Major 4's
    packaging guard) are not identity here, and collapsing this into "same
    as verbatim" would leave that distinction implicit rather than
    demonstrated."""
    return text


# --- evasion probes ------------------------------------------------------------


@dataclass(frozen=True)
class EvasionResult:
    """One probe's outcome: whether the oracle detected `name`'s text, and
    whether that matches what was expected. `passed` is the pass/fail line
    the provenance record (task 3.4) consumes -- never the text itself."""

    name: str
    expected_detected: bool
    detected: bool

    @property
    def passed(self) -> bool:
        return self.detected == self.expected_detected


def run_probe(
    name: str,
    text: str,
    *,
    expected_detected: bool,
    fps: frozenset[str],
    lengths: frozenset[int],
    salt: bytes,
) -> EvasionResult:
    """Scan `text` and record whether the result matches `expected_detected`.

    Used both for the catalogued evasions (mostly `expected_detected=True`)
    and for the single-constant-paste probe and the control file (both
    `expected_detected=False`) -- a declared-limit non-detection is recorded
    as a *pass* here when it is what the oracle is documented to do (Req
    3.7), not silently treated as a failure.
    """
    detected = scan(text, fps, lengths, salt)
    return EvasionResult(
        name=name, expected_detected=expected_detected, detected=detected
    )


# --- durable, out-of-repository results record ---------------------------------


def write_results(
    results: Sequence[EvasionResult],
    out_path: Path,
    *,
    source_count: int,
    fingerprint_count: int,
    window_length_count: int,
) -> None:
    """Write `results` -- pass/fail and shape only, never a value -- to
    `out_path`, outside the repository. Task 3.4 consumes this for the
    provenance record.

    Records `source_count` rather than source paths: task 3.4 folds this
    record into an in-repository provenance record, so a path fragment
    identifying the removed material's location must not be carried here
    even in an out-of-repository file (Req 3.7)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_count": source_count,
        "fingerprint_count": fingerprint_count,
        "window_length_count": window_length_count,
        "probes": [
            {
                "name": result.name,
                "expected_detected": result.expected_detected,
                "detected": result.detected,
                "passed": result.passed,
            }
            for result in results
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# --- one-shot orchestration ------------------------------------------------------


def generate_and_verify(
    sources: Sequence[Path],
    *,
    data_module_out: Path,
    results_out: Path,
    control_text: str = _CONTROL_TEXT,
) -> tuple[frozenset[str], frozenset[int], tuple[EvasionResult, ...]]:
    """The one-shot generation and acceptance run, as a pure-ish function of
    its arguments (all real IO is at its edges) so it is callable from both
    the CLI and a test with synthetic paths.

    Raises `ValueError` if the generated fingerprint or window-length set
    would be empty -- writing a vacuous data module is exactly the failure
    this task must not produce silently.
    """
    texts = [source.read_text(encoding="utf-8") for source in sources]
    salt = generate_salt()
    fps, lengths = collect_fingerprints(texts, salt=salt)
    if not fps or not lengths:
        raise ValueError(
            "generated fingerprint or window-length set is empty -- refusing to "
            "write a vacuous data module (an empty set makes every later absence "
            "assertion vacuous, Req 3.7's own precondition)"
        )

    generated_at = datetime.now(UTC).isoformat()
    rendered = render_data_module(
        salt=salt,
        entropy_floor_bits=_ORACLE_ENTROPY_FLOOR_BITS,
        digest_hex_length=_ORACLE_DIGEST_HEX_LENGTH,
        fingerprints=fps,
        window_lengths=lengths,
        source_count=len(sources),
        generated_at=generated_at,
    )
    write_data_module(data_module_out, rendered)

    results: list[EvasionResult] = []

    # Baseline liveness checks -- the task's stated observable: the writeup
    # and both extracted tables are each individually flagged, and a control
    # file without them is not. Probe names are opaque, index-based labels
    # (never a source's filename) -- Req 3.7 forbids carrying an identifying
    # path fragment even into this out-of-repository record, since task 3.4
    # folds it into an in-repository provenance record.
    for index, text in enumerate(texts, start=1):
        results.append(
            run_probe(
                f"source-{index} flagged",
                text,
                expected_detected=True,
                fps=fps,
                lengths=lengths,
                salt=salt,
            )
        )
    results.append(
        run_probe(
            "control file not flagged",
            control_text,
            expected_detected=False,
            fps=fps,
            lengths=lengths,
            salt=salt,
        )
    )

    # The five evasion probes catalogued in tasks.md 2.4 and design.md, run
    # against the real material while it is still on disk.
    combined_text = "\n\n".join(texts)
    results.append(
        run_probe(
            "verbatim re-add",
            combined_text,
            expected_detected=True,
            fps=fps,
            lengths=lengths,
            salt=salt,
        )
    )
    if texts:
        results.append(
            run_probe(
                "renamed and reformatted re-add",
                reformatted_copy(texts[0]),
                expected_detected=True,
                fps=fps,
                lengths=lengths,
                salt=salt,
            )
        )
        results.append(
            run_probe(
                "table pasted as a language literal into an allowlisted module",
                as_python_literal(texts[-1]),
                expected_detected=True,
                fps=fps,
                lengths=lengths,
                salt=salt,
            )
        )
        results.append(
            run_probe(
                "copy under a different extension",
                different_extension_copy(texts[0]),
                expected_detected=True,
                fps=fps,
                lengths=lengths,
                salt=salt,
            )
        )

    write_results(
        results,
        results_out,
        source_count=len(sources),
        fingerprint_count=len(fps),
        window_length_count=len(lengths),
    )

    return fps, lengths, tuple(results)


# NOTE (encumbered-content-purge, 4.1, elective boundary exception): a
# `_single_known_positive_control_value` helper and a conditional
# "single-constant paste" probe branch in `generate_and_verify` above used to
# sit here. The helper read the first value of `tests/load/test_packaging.py`'s
# own value-tuple constant -- the single table value that guard's mutation
# check recorded as its only positive-detection evidence -- and reused it so
# the probe replicated that guard's own evidence exactly. Task 4.1 deleted
# that constant outright rather than renaming it, so the helper could only
# ever return `None` from that point forward and the conditional branch that
# consumed it became permanently unreachable dead code, not merely
# conditionally absent. Removed here rather than left as a branch that can
# never execute. This edit is outside task 4.1's declared boundary
# (`ReintroductionGuards`, `IdentityErasure`) -- this module belongs to
# `ContentOracle` (task 2.4) per design.md's Component -> file map -- but was
# forced by task 4.1's deletion in `tests/load/test_packaging.py`: reverting
# it alone leaves this module's now-deleted import line type-checking
# against the deleted value-tuple attribute (an `mypy attr-defined` error),
# and this module is in `[tool.mypy].files`.


# --- CLI -----------------------------------------------------------------------

_SOURCES_OPTION = typer.Option(
    None,
    "--source",
    help="Source file to fingerprint (repeatable). Defaults to the paths "
    "named by FITDOCS_FORBIDDEN_STRINGS's path-category entries, if set.",
)
_DATA_MODULE_OUT_OPTION = typer.Option(
    _DEFAULT_DATA_MODULE,
    "--data-module-out",
    help="Where to write the generated data module.",
)
_RESULTS_OUT_OPTION = typer.Option(
    ...,
    "--results-out",
    help="Scratch path (outside the repo) to write the evasion-acceptance results to.",
)


def run(
    source: list[Path] | None = _SOURCES_OPTION,
    data_module_out: Path = _DATA_MODULE_OUT_OPTION,
    results_out: Path = _RESULTS_OUT_OPTION,
) -> None:
    """`purge fingerprints` -- the one-shot generator (Req 3.2, 3.7,
    ContentOracle). Must run while the source material is still on disk;
    task 3.1 deletes it and this cannot be repeated afterward."""
    sources = tuple(source) if source else _default_sources()
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        typer.echo(f"purge fingerprints: source file(s) not found: {missing}", err=True)
        raise typer.Exit(code=1)

    try:
        fps, lengths, results = generate_and_verify(
            sources, data_module_out=data_module_out, results_out=results_out
        )
    except ValueError as exc:
        typer.echo(f"purge fingerprints: {exc}", err=True)
        raise typer.Exit(code=1) from None

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        typer.echo(
            f"{status}: {result.name} (expected_detected={result.expected_detected}, "
            f"detected={result.detected})"
        )
    typer.echo(
        f"wrote {len(fps)} fingerprints and {len(lengths)} window lengths to "
        f"{data_module_out}; evasion-acceptance results at {results_out}"
    )
    if not all(result.passed for result in results):
        typer.echo(
            "purge fingerprints: one or more probes did not match their expected "
            "outcome -- see the results above before proceeding",
            err=True,
        )
        raise typer.Exit(code=1)
