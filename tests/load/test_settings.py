"""Tests for the ``[load]`` settings reader (Req 10.1, 10.2, 14.1, 14.2, 14.3, 14.6).

This exercises :func:`fitdocs.load.settings.load_load_settings`, the *single*
per-table projection of an already-parsed ``<data-root>/fitdocs.toml`` ``[load]``
table onto the :class:`~fitdocs.load.settings.LoadSettings` contract (design:
"LoadSettings", ``src/fitdocs/load/settings.py``). It is pinned by Amendment 3
of the training-load spec: four sibling specs (``athlete-benchmarks``,
``load-channels``, ``threshold-load``, ``activity-qa-flags``) each extend this
exact module and this exact test file rather than opening a second reader or a
second test module.

Two invariants govern every case:

* *Every field is defaulted, so absent is never an error.* An empty document
  -- what the shared reader returns for an absent ``fitdocs.toml`` -- or a
  document with no ``[load]`` table yields
  :data:`~fitdocs.load.settings.DEFAULT_LOAD_SETTINGS`. Constructing
  :class:`~fitdocs.load.settings.LoadSettings` with no arguments always equals
  that default -- the additivity guard that reddens the moment a sibling spec
  adds an undefaulted field (Req 14.2).
* *Malformed fails loudly, and unknown is tolerated.* A non-table ``[load]``
  value, or a non-string/empty ``default_calculator``, raises
  :class:`~fitdocs.load.settings.LoadSettingsError` naming the settings file
  and the offending key (Req 14.6). Unknown keys inside ``[load]`` *and*
  unknown sub-tables beneath it are ignored (Req 14.3) -- the additivity
  contract that lets ``[load.sufficiency]``, ``[load.priority]`` and
  ``[load.flags]`` land without ever touching this reader.

The reader never opens a file: it validates only the mapping it is handed and
uses ``settings_file`` only to name the file in errors. Whether the configured
identifier is *registered* is deliberately not checked here (that is an
arbitration concern).
"""

from __future__ import annotations

import ast
import subprocess
import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.load import settings as load_settings_module
from fitdocs.load.settings import (
    DEFAULT_LOAD_SETTINGS,
    LoadSettings,
    LoadSettingsError,
    load_load_settings,
)
from fitdocs.settings import SettingsError
from tests.fixtures import builder

# A representative settings-file path; the reader only ever names it in errors
# and never opens it, so it need not (and here does not) exist on disk.
_SETTINGS_FILE = Path("/vault/fitdocs.toml")


# --- The keyless default / additivity guard (Req 14.2) -----------------------


def test_default_load_settings_is_keyless_default_calculator_none() -> None:
    """The keyless default: no default calculator configured."""
    assert LoadSettings(default_calculator=None) == DEFAULT_LOAD_SETTINGS


def test_no_argument_construction_equals_module_default() -> None:
    """``LoadSettings()`` with no arguments equals ``DEFAULT_LOAD_SETTINGS``.

    This is the additivity guard four sibling specs depend on: a sibling
    adding a field must default it, or this assertion reddens.
    """
    assert LoadSettings() == DEFAULT_LOAD_SETTINGS


def test_default_staleness_window_is_84_days() -> None:
    """The documented staleness-window default is pinned to the literal 84."""
    assert DEFAULT_LOAD_SETTINGS.benchmark_staleness_days == 84


# --- Absent file / table -> defaults (never an error) (Req 14.2) -------------


def test_absent_file_returns_defaults() -> None:
    """An empty document (an absent ``fitdocs.toml``) -> the defaults."""
    assert load_load_settings({}, _SETTINGS_FILE) == DEFAULT_LOAD_SETTINGS


def test_absent_load_table_returns_defaults() -> None:
    """A document with other tables but no ``[load]`` -> the defaults."""
    document = {"tiles": {}, "plugins": {"enabled": False}}
    assert load_load_settings(document, _SETTINGS_FILE) == DEFAULT_LOAD_SETTINGS


# --- A valid key resolves (Req 10.1, 10.2) ------------------------------------


def test_configured_default_calculator_is_read() -> None:
    """A valid ``default_calculator`` string resolves onto the dataclass."""
    document = {"load": {"default_calculator": "threshold"}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


def test_absent_staleness_key_returns_documented_default() -> None:
    """A present ``[load]`` table without ``benchmark_staleness_days`` -> 84."""
    document = {"load": {"default_calculator": "threshold"}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.benchmark_staleness_days == 84


def test_configured_staleness_window_is_read() -> None:
    """A valid, non-default ``benchmark_staleness_days`` resolves onto the dataclass."""
    document = {"load": {"benchmark_staleness_days": 30}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(benchmark_staleness_days=30)
    assert result.benchmark_staleness_days == 30


# --- Malformed fails loudly, naming file and key (Req 14.6) ------------------


def test_non_table_load_value_is_rejected() -> None:
    document = {"load": "not-a-table"}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "load" in message


def test_non_string_default_calculator_is_rejected() -> None:
    document = {"load": {"default_calculator": 5}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "default_calculator" in message


def test_empty_string_default_calculator_is_rejected() -> None:
    document = {"load": {"default_calculator": ""}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "default_calculator" in message


def test_non_integer_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": "84"}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "84" in body


def test_float_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": 84.5}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "84.5" in body


def test_boolean_staleness_window_is_rejected() -> None:
    """``bool`` is an ``int`` subclass in Python -- must be rejected on its own."""
    document = {"load": {"benchmark_staleness_days": True}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "True" in body


def test_zero_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": 0}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "0" in body


def test_negative_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": -7}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "-7" in body


# --- Additivity: unknown keys and unknown sub-tables ignored (Req 14.3) ------


def test_unknown_key_in_load_table_is_ignored() -> None:
    document = {"load": {"default_calculator": "threshold", "made_up_key": 42}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


def test_two_unknown_downstream_sub_tables_parse_cleanly() -> None:
    """Two sub-tables not yet owned by this reader parse without error.

    Stands in for ``[load.priority]`` (``threshold-load``) and
    ``[load.flags]`` (``activity-qa-flags``) -- sub-tables this reader does
    not know about yet, landing additively without touching this module.
    """
    document = {
        "load": {
            "default_calculator": "threshold",
            "priority": {"channels": ["hr", "pace"]},
            "flags": {"staleness_days": 30},
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


def test_unknown_sub_table_alongside_configured_staleness_is_ignored() -> None:
    """An unknown ``[load.*]`` sub-table does not shadow the staleness key."""
    document = {
        "load": {
            "benchmark_staleness_days": 30,
            "sufficiency": {"min_days": 14},
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(benchmark_staleness_days=30)


def test_unknown_sibling_table_outside_load_is_ignored() -> None:
    """A sibling top-level table (``[tiles]``) alongside ``[load]`` is ignored."""
    document = {
        "tiles": {"some_tile": {}},
        "load": {"default_calculator": "threshold"},
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


# --- The error is a configuration error the CLI already maps (Req 14.6) -----


def test_load_settings_error_is_a_settings_error() -> None:
    assert issubclass(LoadSettingsError, SettingsError)


# --- Import direction: this module does not import types.py at runtime ------
# (corrected 2026-07-25 by the import-direction ruling; Req 14.7)


def test_settings_module_does_not_import_load_types_at_runtime() -> None:
    """A fresh interpreter proves ``settings.py`` itself imports no ``load.types``.

    ``fitdocs.load.__init__`` already eagerly imports ``registry`` -> ``types``
    today (pre-existing, not owned by this task), so ``import
    fitdocs.load.settings`` alone would trigger that parent-package init and
    pull ``fitdocs.load.types`` into ``sys.modules`` regardless of what this
    module's own source does -- that check would not discriminate. Instead
    this loads ``settings.py`` directly off disk via ``importlib`` under a
    synthetic module name, bypassing ``fitdocs.load``'s package init (whose
    own top-level imports, ``import`` and ``from __future__ import
    annotations`` aside, are just ``fitdocs.settings`` -- a sibling package
    that does not import ``fitdocs.load`` either), and asserts that
    ``fitdocs.load.types`` never lands in ``sys.modules`` as a side effect of
    executing this module's own top-level statements.
    """
    settings_path = (
        Path(__file__).resolve().parents[2] / "src" / "fitdocs" / "load" / "settings.py"
    )
    module_name = "_isolated_load_settings"
    script = (
        "import sys\n"
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location({module_name!r}, "
        f"{str(settings_path)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['_isolated_load_settings'] = module\n"
        "spec.loader.exec_module(module)\n"
        "assert 'fitdocs.load.types' not in sys.modules, "
        "'fitdocs.load.settings must not import fitdocs.load.types at runtime'\n"
        "print('OK')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK" in completed.stdout


# --- Single-reader rule (task 6.4, Req 14.1): package-wide, not just the CLI -
#
# ``tests/test_cli.py::test_cli_module_holds_no_load_settings_type_or_reader``
# already pins this for the command surface specifically (task 4.2). This is
# the module's own docstring obligation stated more broadly: "no second
# reader of ``[load]`` may exist *anywhere in the tool*" -- so the guard below
# scans every module under ``src/fitdocs``, not only ``cli.py``.
#
# A resolution-based AST walk rather than a literal import match, per task
# 4.2's finding that ``ast.ImportFrom`` module-name matching is defeated by
# alternate spellings: this instead looks for a *call site* naming
# ``load_load_settings`` -- as a bare name (``load_load_settings(...)``) or as
# an attribute access (``anything.load_load_settings(...)``) -- and, per task
# 6.4 round 3, any per-file ``from ... import load_load_settings as <alias>``
# binding, matched against that file's own alias set rather than the literal
# string. This is spelling-proof to a plain ``from x import y`` / ``from x
# import y as z`` / ``import x`` then ``x.load_load_settings(...)`` -- but
# not to every spelling; see below.
#
# It is not proof against every spelling, though (corrected 2026-07-26, task
# 6.4 round 2; extended 2026-07-26, task 6.4 round 3): this walk only
# inspects ``ast.Call.func`` and ``ast.ImportFrom`` aliases naming
# ``load_load_settings`` directly, so a call *site* that names something the
# walk cannot trace back to that literal import still defeats it -- e.g.
# ``importlib.import_module`` plus ``getattr`` (the ``func`` is a
# ``getattr(...)`` call, not a ``load_load_settings``-named node), or a
# plain non-import alias (``reader = load_load_settings`` followed by
# ``reader({}, path)``, where the call site names only ``reader`` and no
# ``ImportFrom`` alias exists to resolve it). All three spellings -- the
# ``importlib``/``getattr`` form, the plain-assignment alias, and the
# ``from ... import ... as`` alias this round closes -- were run against
# this guard; the first two still leave it green (and the rest of the
# 1850-test suite green), the third now reddens it directly. The behavioral
# companion below, which spies on the reader itself rather than parsing call
# sites, is what actually closes all three spellings; this walk still catches
# the ordinary cases (a literal second call, or a ``from ... import ...
# as``-aliased one, naming ``load_load_settings``) cheaply and without
# needing to run anything.


def _modules_calling_load_load_settings() -> set[Path]:
    """Files under ``src/fitdocs`` containing a call site that reaches
    ``load_load_settings``, matched against a *per-file* set of matched
    names rather than the literal string ``"load_load_settings"`` (corrected
    task 6.4 round 3, finding 1): a ``from fitdocs.load.settings import
    load_load_settings as _reader`` import binds the reader under a local
    alias, and the previous version of this walk -- comparing the call
    site's own spelling directly against the literal name -- never matched
    ``_reader(...)``. Each module's own ``ast.ImportFrom`` aliases for
    ``load_load_settings`` are collected first (``.asname or .name``), and
    call sites in *that* module are matched against that module's own
    matched-name set, not a single global name.
    """
    src_root = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
    callers: set[Path] = set()
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        matched_names = {"load_load_settings"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if alias.name == "load_load_settings":
                    matched_names.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in matched_names:
                callers.add(path.relative_to(src_root))
                break
    return callers


def test_load_load_settings_is_called_from_exactly_one_module() -> None:
    """Req 14.1: the reader is called from exactly one place in shipped
    source -- the load engine -- and from nowhere else, including the
    command surface, the document editor, the profile store, or any other
    module that might be tempted to read ``[load]`` directly.

    Mutation caught: adding a second, real call site (e.g. a guarded
    ``load_load_settings(...)`` invocation added to ``fitdocs/load/docedit.py``,
    reached only behind an always-false condition so it changes no
    behavior) reddens this test by naming both callers, while leaving the
    rest of the suite green -- the same shape task 4.2's reviewer proved
    against the CLI-specific version of this guard.
    """
    callers = _modules_calling_load_load_settings()
    assert callers == {Path("load/engine.py")}, (
        f"load_load_settings is called from {sorted(str(p) for p in callers)}, "
        "expected exactly ['load/engine.py']"
    )


def _reads_load_table_literally(tree: ast.AST) -> bool:
    """True if ``tree`` contains either of the literal-key spellings this
    guard treats as a second reader of the top-level ``[load]`` table:

    * ``ast.Subscript`` keyed by the constant ``"load"`` (``doc["load"]``);
    * an ``ast.Call`` to an attribute named ``get`` carrying the constant
      ``"load"`` in the one argument position that can actually *be* the
      key: ``args[0]`` for the bound form (``doc.get("load")``), or
      ``args[1]`` -- and only when the receiver is the literal name
      ``dict`` -- for the unbound-method form (``dict.get(document,
      "load")``, queue item
      2026-07-26-second-load-reader-spellings-escape-guards, spelling 2).

    Narrower than the version review round 1 shipped, on two counts, both
    findings from round 2:

    * **Any-positional-argument matching false-positived on the *value*, not
      the key.** ``options.get("mode", "load")`` reads key ``"mode"`` with
      default value ``"load"`` -- the exact opposite of a ``[load]`` read --
      but matched because the check scanned every argument position rather
      than the one that can hold a key. Pinning the key to its own position
      (``args[0]`` bound, ``args[1]`` unbound-and-only-when-the-receiver-is-
      literally-``dict``) removes it: a default value can never land in the
      position this now checks.
    * **``.pop`` and ``ast.Compare(==)`` are dropped, not narrowed, because
      no argument-position fix removes their false positives.** ``"load"``
      is already three unrelated namespaces in this repo:
      :data:`fitdocs.contract.LOAD_REGION` (a rendered document region),
      the ``@app.command("load")`` CLI verb, and this settings table. A
      bound ``X.pop("load")`` is syntactically identical whether ``X`` is a
      settings document (spelling 3, a real second reader) or the
      ``regions`` mapping :func:`fitdocs.load.docedit._load_region_content`
      already legitimately pops/subscripts by this same literal key
      (``src/fitdocs/load/docedit.py``, which reads ``regions[LOAD_REGION]``
      today but is one literal-instead-of-constant edit away from
      ``regions.pop("load")``) -- no receiver-position or argument-position
      rule distinguishes them, because both really are ``X.pop("load")``.
      Likewise ``ast.Compare(==)`` matched ``command_name == "load"`` (CLI
      dispatch) exactly as readily as a settings-document key comparison.
      Measured: both constructs, added as real code, left the full suite,
      ruff and mypy green under the *narrowed* positional check -- proving
      position alone does not save them -- and both are now included as
      negative controls below to keep it that way. The two spellings this
      costs -- (1) dict iteration (``for k, v in doc.items(): if k ==
      "load"``) and (3) ``document.pop("load")`` -- are accepted residuals,
      alongside the pre-existing aliased-key residual below: a guard that
      flags every ``.pop("load")`` and every ``== "load"`` in the tool is
      not a Req 14.1 guard, it is a ban on writing ``"load"`` as a Python
      string literal anywhere in ``src/fitdocs``.

    Deliberately does not chase the aliased-key spelling (``_T = "load"``;
    ``doc.get(_T)``): that is the accepted residual recorded in tasks.md's
    task 6.4 notes (a module-level alias still evades any literal-key AST
    check; only the behavioural companion below, which spies on the real
    reader, closes that spelling).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            index = node.slice
            if isinstance(index, ast.Constant) and index.value == "load":
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get":
                receiver = func.value
                if isinstance(receiver, ast.Name) and receiver.id == "dict":
                    if (
                        len(node.args) >= 2
                        and isinstance(node.args[1], ast.Constant)
                        and node.args[1].value == "load"
                    ):
                        return True
                elif (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "load"
                ):
                    return True
    return False


def _modules_parsing_load_table_literally(src_root: Path | None = None) -> set[Path]:
    """Files under ``src_root`` (every ``*.py``, package-wide -- not just
    ``cli.py``) containing a node :func:`_reads_load_table_literally`
    recognises as a literal read of the ``[load]`` table.

    Defaults to the real ``src/fitdocs`` tree. A caller may pass a synthetic
    tree instead (see
    ``test_literal_load_table_detection_catches_the_reported_spellings``
    below) to exercise the detection logic without touching shipped source;
    the positive-control and allowlist assertions that guard against a
    silently-vacuous walk live in the real-tree test, not here, since they
    only mean something against the real tree.

    ``load/settings.py`` -- the sole legitimate parser, :func:`load_load_settings`
    itself -- is allowlisted when present; every other module's match is a
    second reader Req 14.1 forbids ("no second reader of that table shall
    exist anywhere in the tool"), which is strictly wider than task 4.2's
    CLI-only guard.
    """
    if src_root is None:
        src_root = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
    allowlisted = src_root / "load" / "settings.py"
    scanned = sorted(src_root.rglob("*.py"))
    offenders: set[Path] = set()
    for path in scanned:
        if path == allowlisted:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _reads_load_table_literally(tree):
            offenders.add(path.relative_to(src_root))
    return offenders


def test_no_module_other_than_load_settings_parses_the_load_table_literally() -> None:
    """Req 14.1's other half, package-wide: "no second reader of that table
    shall exist anywhere in the tool" -- not just "the command surface holds
    no reader" (task 4.2's original, narrower scope).

    Every earlier guard in this module keys on the *function*
    ``load_load_settings``; a module that parses ``[load]`` directly off an
    already-loaded settings document, never calling that function, is
    invisible to all of them. Confirmed by the reviewer's exact probe: a
    block added to ``src/fitdocs/audit.py`` that calls
    ``load_settings_document(data_root)``, reads ``.get("load")``, and
    validates ``default_calculator`` itself -- a real second reader with its
    own validation, never touching :func:`fitdocs.load.settings.load_load_settings`
    -- passes the full suite, ruff, and mypy with every other guard in this
    module green. This walk is what catches it.

    Mutation caught: the probe above, added to ``audit.py``, names
    ``audit.py`` as the sole offender here while leaving every other test in
    the suite green (verified by running it, not by inspection).
    """
    src_root = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
    allowlisted = src_root / "load" / "settings.py"
    scanned = sorted(src_root.rglob("*.py"))
    # Positive control. Without it this walk passes green having visited zero
    # files: ``parents[2]`` is depth-sensitive, so moving this test one
    # directory deeper silently points ``src_root`` at ``tests/src/fitdocs``
    # and the guard is permanently vacuous. The sibling steering guard in
    # ``tests/test_docs_guarantees.py`` was rejected for exactly this.
    assert scanned, (
        f"no modules scanned under {src_root} -- the walk is looking at the "
        "wrong directory, so this guard proves nothing"
    )
    assert allowlisted.is_file(), (
        f"the sole legitimate parser {allowlisted} is missing -- the allowlist "
        "has drifted and offenders would be misattributed"
    )
    offenders = _modules_parsing_load_table_literally()
    assert not offenders, (
        f"modules parsing the [load] table by literal key outside "
        f"load/settings.py: {sorted(str(p) for p in offenders)}"
    )


def test_literal_load_table_detection_catches_the_reported_spellings(
    tmp_path: Path,
) -> None:
    """Fixture-discrimination companion for
    :func:`_modules_parsing_load_table_literally`'s detection, run against a
    synthetic source tree rather than by editing real shipped modules -- a
    temporary, reviewable fixture instead of a hand-edit/revert cycle.

    **Closes**, of the four spellings named in queue item
    2026-07-26-second-load-reader-spellings-escape-guards:

    * a direct subscript, ``document["load"]`` (not itself one of the four
      queue spellings, but the walk's oldest and most load-bearing clause --
      pinned here per review round 2, which found no offender for it
      anywhere in this fixture);
    * spelling (2), the mapping passed positionally rather than as the
      receiver: ``dict.get(document, "load")``.

    **Accepted as residual, not closed here** (see
    :func:`_reads_load_table_literally`'s docstring for why, review round 2):

    * spelling (1), dict iteration: ``for k, v in doc.items(): if k ==
      "load"`` -- the ``ast.Compare(==)`` clause that would catch it also
      matched CLI dispatch (``command_name == "load"``), so it was dropped;
    * spelling (3), ``document.pop("load")`` -- syntactically identical to
      the legitimate ``regions.pop("load")`` a rendered-document region
      helper could just as well write, so the ``.pop`` half of the ``get``/
      ``pop`` clause was dropped too;
    * spelling (4), a default-parameter capture -- a different guard's
      concern entirely (the ``sys.modules`` behavioural spy below, not this
      literal-key walk); see that spy's own docstring for how it is closed.

    Three FALSE-POSITIVE constructs, measured against review round 1's wider
    version of this walk and confirmed still real in the repo today (``load``
    is simultaneously the settings table, :data:`fitdocs.contract.LOAD_REGION`,
    and the ``@app.command("load")`` CLI verb), are included as NEGATIVE
    CONTROLS so a future widening cannot silently reintroduce them:

    * ``options.get("mode", "load")`` -- ``"load"`` is the *default value*
      for key ``"mode"``, not a key read, and false-positived under the
      original any-positional-argument ``.get``/``.pop`` check;
    * ``if command_name == "load": ...`` -- ordinary CLI dispatch, false-
      positived under the dropped ``ast.Compare(==)`` clause;
    * ``regions.pop("load")`` -- removing the rendered ``load`` region
      (``src/fitdocs/load/docedit.py`` already reads ``regions[LOAD_REGION]``
      by this same string, one literal-instead-of-constant edit away), false-
      positived under the original ``.pop`` matching and the reason ``.pop``
      is dropped rather than narrowed.

    A fifth, innocent module using ``.get`` for an unrelated key is also
    included: the detection must not start flagging every ``.get`` call in
    the tree.

    Mutation caught: narrowing ``_reads_load_table_literally`` back to
    matching only ``ast.Subscript`` (dropping the ``.get`` clause entirely)
    reddens this test, because the unbound-``.get`` offender no longer
    matches while every negative control still correctly does not appear.
    Widening it back to the original any-positional-argument ``.get``/``.pop``
    plus ``ast.Compare(==)`` shape also reddens this test, because the three
    negative controls then incorrectly appear in ``offenders``.
    """
    src_root = tmp_path / "fitdocs"
    (src_root / "load").mkdir(parents=True)
    (src_root / "load" / "settings.py").write_text(
        "# allowlisted -- the sole legitimate parser\n", encoding="utf-8"
    )
    (src_root / "load" / "__init__.py").write_text("", encoding="utf-8")
    (src_root / "__init__.py").write_text("", encoding="utf-8")

    # --- offenders: still closed ------------------------------------------
    (src_root / "subscript_reader.py").write_text(
        "def scan(doc):\n    return doc['load']['channels']\n",
        encoding="utf-8",
    )
    (src_root / "unbound_get_reader.py").write_text(
        "def scan(doc):\n    return dict.get(doc, 'load')\n",
        encoding="utf-8",
    )
    (src_root / "bound_get_reader.py").write_text(
        "def scan(doc):\n    return doc.get('load')\n",
        encoding="utf-8",
    )

    # --- accepted residuals: not offenders under this walk -----------------
    (src_root / "iter_reader.py").write_text(
        "def scan(doc):\n"
        "    for k, v in doc.items():\n"
        "        if k == 'load':\n"
        "            return v\n"
        "    return None\n",
        encoding="utf-8",
    )
    (src_root / "pop_reader.py").write_text(
        "def scan(doc):\n    return doc.pop('load')\n",
        encoding="utf-8",
    )

    # --- negative controls: real constructs that must never be flagged -----
    (src_root / "default_value_reader.py").write_text(
        "def scan(options):\n    return options.get('mode', 'load')\n",
        encoding="utf-8",
    )
    (src_root / "cli_dispatch.py").write_text(
        "def dispatch(command_name):\n"
        "    if command_name == 'load':\n"
        "        return 'dispatched'\n"
        "    return None\n",
        encoding="utf-8",
    )
    (src_root / "region_pop.py").write_text(
        "def drop_load_region(regions):\n    return regions.pop('load')\n",
        encoding="utf-8",
    )

    # --- innocent: unrelated key ------------------------------------------
    (src_root / "innocent.py").write_text(
        "def unrelated(doc):\n    return doc.get('other')\n",
        encoding="utf-8",
    )

    offenders = _modules_parsing_load_table_literally(src_root)
    assert offenders == {
        Path("subscript_reader.py"),
        Path("unbound_get_reader.py"),
        Path("bound_get_reader.py"),
    }, (
        f"expected exactly the three synthetic offenders (subscript, "
        f"unbound-get, bound-get), got {sorted(str(p) for p in offenders)}"
    )


# --- Package-wide behavioral companion (task 6.4 round 2, Req 14.1) ---------
#
# The AST walk above is a call-*site* check: it can only see a call that its
# own resolution logic can trace back to ``load_load_settings`` (a literal
# name, or a per-file ``ImportFrom`` alias of it). It is provably bypassable
# by spellings that still reach the real reader without ever writing a name
# the walk can resolve -- ``importlib.import_module(...)`` + ``getattr(...)``,
# a plain non-import alias (``reader = load_load_settings`` then
# ``reader(...)``), and a *module-level* ``from x import y as z`` import
# whose call site names only ``z`` -- all of which leave the walk above
# green (the last one only as of task 6.4 round 3; the fix in this module
# closes it for the AST walk directly). This behavioral companion covers
# every *module-level* binding, under any local name, in any ``fitdocs.*``
# module, plus every default-parameter capture (positional or keyword-only)
# reachable from one -- the scope stated at the sweep itself below.
# ``tests/test_cli.py::test_load_command_calls_load_load_settings_exactly_once``
# also spies on the reader, but only for ``fitdocs load`` and only across the
# two binding surfaces it patches by hand -- so it closes every spelling
# *that routes through those two modules*, not every spelling. Measured: a
# module-level ``from fitdocs.load.settings import load_load_settings as _r2``
# in ``src/fitdocs/load/arbitrate.py`` plus a call in ``validate_configured``
# -- a real second read on the ``fitdocs load`` path -- leaves
# ``tests/test_cli.py`` fully green at 36 passed, while the sweep below
# reddens. That is why this sweep is not redundant with it: do not delete
# this in favour of that one.


def test_load_load_settings_is_called_the_documented_number_of_times_per_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 14.1, package-wide: ``load_load_settings`` is called exactly once
    per ``fitdocs sync``, ``fitdocs regen``, and ``fitdocs load`` invocation
    (the single read inside ``apply_load`` itself, task 4.1) and exactly
    zero times for ``fitdocs check`` (the command that runs the read-only
    contract audit, ``src/fitdocs/audit.py``) -- ``audit()`` never touches
    the load engine or the ``[load]`` table at all.

    Sweeps *every* already-imported ``fitdocs.*`` module rather than
    hand-listing the two binding surfaces this test used to spy on
    (corrected task 6.4 round 3, finding 1): a ``from x import y`` binds the
    original function object into the importing module's own namespace, at
    import time, under whatever local name that module chose -- there are as
    many such binding surfaces as there are importing modules, not two, and
    a hand-picked pair (``fitdocs.load.settings`` and ``fitdocs.load.engine``)
    is blind to a binding anywhere else, including an aliased one (``from
    fitdocs.load.settings import load_load_settings as _reader``) added to a
    third module such as ``fitdocs.audit``. This walks ``sys.modules`` for
    every module whose name starts with ``fitdocs.``, and for every
    attribute on it that ``is`` the real (pre-patch) function, patches it to
    the spy -- so any *module-level* binding, under any local name, in any
    module, is caught regardless of where it lives or what it is called
    there. A default-parameter capture -- ``def audit(data_root: Path, _r:
    object = load_load_settings)`` followed by a call to ``_r(...)`` -- is
    never a *module* attribute either, but the binding still lives one
    dereference away: on the function object's own ``__defaults__`` (or
    ``__kwdefaults__`` for a keyword-only parameter, ``def audit(data_root,
    *, _r=load_load_settings)``), both of which are ordinary writable
    attributes. For every already-swept ``fitdocs.*`` module-level function,
    this also inspects its ``__defaults__``/``__kwdefaults__`` for the real
    reader and patches whichever tuple/dict entry holds it, closing that
    spelling too -- no call-time interception or caller-frame instrumentation
    required. A call-time rebinding inside another module (``from
    fitdocs.load.settings import load_load_settings`` executed *inside a
    function body* rather than at module import time, or
    ``getattr(importlib.import_module(...), ...)``) still resolves the
    current, patched module attribute at call time, so this spy catches
    those too -- unlike the AST walk above.

    Mutation caught (verified by running each, not by inspection): adding
    any of the bypass spellings above as a real, reachable call inside
    ``src/fitdocs/audit.py`` -- including a module-level ``from
    fitdocs.load.settings import load_load_settings as _reader`` plus a call
    to ``_reader(...)`` inside ``audit()``, and the two default-parameter
    capture forms (positional and keyword-only) -- so that ``fitdocs check``
    invokes the reader once where zero is documented, reddens this test's
    ``fitdocs check`` assertion as a sole failure in every case (verified by
    running each mutation through the full suite, not by inspection).
    """
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )
    runner = CliRunner()
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())

    calls: list[object] = []
    original = load_settings_module.load_load_settings

    def _spy(document: object, settings_file: object) -> object:
        calls.append(document)
        return original(document, settings_file)  # type: ignore[arg-type]

    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("fitdocs."):
            continue
        for attr_name in list(vars(module)):
            value = getattr(module, attr_name, None)
            if value is original:
                monkeypatch.setattr(module, attr_name, _spy)
                continue
            if not isinstance(value, types.FunctionType):
                continue
            # A default-parameter capture (``def f(..., _r=load_load_settings)``)
            # never becomes a *module* attribute, so the ``vars(module)`` walk
            # above is structurally blind to it -- but the default lives in the
            # function object's own ``__defaults__``/``__kwdefaults__``, one
            # dereference from a module attribute and just as writable. Patch
            # any default (positional or keyword-only) that is the real reader.
            if value.__defaults__ and any(d is original for d in value.__defaults__):
                monkeypatch.setattr(
                    value,
                    "__defaults__",
                    tuple(_spy if d is original else d for d in value.__defaults__),
                )
            if value.__kwdefaults__ and any(
                d is original for d in value.__kwdefaults__.values()
            ):
                monkeypatch.setattr(
                    value,
                    "__kwdefaults__",
                    {
                        k: (_spy if v is original else v)
                        for k, v in value.__kwdefaults__.items()
                    },
                )

    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0, synced.output
    assert len(calls) == 1, (
        f"fitdocs sync called load_load_settings {len(calls)} times, expected 1"
    )
    calls.clear()

    regenerated = runner.invoke(app, ["regen", "--out", str(data_root)])
    assert regenerated.exit_code == 0, regenerated.output
    assert len(calls) == 1, (
        f"fitdocs regen called load_load_settings {len(calls)} times, expected 1"
    )
    calls.clear()

    loaded = runner.invoke(app, ["load", "--out", str(data_root)])
    assert loaded.exit_code == 0, loaded.output
    assert len(calls) == 1, (
        f"fitdocs load called load_load_settings {len(calls)} times, expected 1"
    )
    calls.clear()

    checked = runner.invoke(app, ["check", "--out", str(data_root)])
    assert checked.exit_code == 0, checked.output
    assert len(calls) == 0, (
        f"fitdocs check called load_load_settings {len(calls)} times, expected 0"
    )
