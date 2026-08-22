"""The single CLI entry point (`scripts/purge/__main__.py`) lists all ten
subcommands (task 1 observable, `_Requirements: 4.4, 10.3_`).

Registration is one line per subcommand in `__main__.py`; the mutation this
pins is dropping any one of those lines, which drops exactly that name from
`--help` and none of the others -- the sole-failure property the fixture
discrimination gate asks for.
"""

from __future__ import annotations

import re

import pytest
import typer
from scripts.purge import (
    adopt,
    fingerprints,
    pins,
    plan,
    preflight,
    replace,
    rewrite,
    verify,
)
from scripts.purge import manifest as manifest_module
from scripts.purge.__main__ import app
from typer.testing import CliRunner

runner = CliRunner()

_COMMAND_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

_SUBCOMMANDS = (
    "manifest",
    "preflight",
    "fingerprints",
    "plan",
    "rewrite",
    "verify-local",
    "adopt",
    "verify-remote",
    "pins",
    "replace",
)


def test_help_lists_all_ten_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert _SUBCOMMANDS, (
        "positive control: the expected-name list is empty, so the walk below "
        "would scan nothing and pass vacuously"
    )
    found = [name for name in _SUBCOMMANDS if name in result.output]
    assert found == list(_SUBCOMMANDS), (
        f"missing from --help output: {sorted(set(_SUBCOMMANDS) - set(found))}"
    )


def _registered_command_names(help_output: str) -> list[str]:
    """Extract the command-name column from the rich `Commands` panel.

    Rich lays the panel out as a fixed-width table: every row is `"│ "`
    plus the name padded to a fixed column width, and a wrapped continuation
    line of a long help string repeats that same padding with the name
    column left blank (`"│ " + " " * name_width + ...`). So the
    character immediately after the row's leading `"│ "` is the row's
    own signal: non-blank on a real command row, blank on a continuation
    line -- regardless of what word the help text happens to wrap on. This
    is anchored on that fixed column, not on the punctuation a particular
    wrap point happens to produce, so a benign reword of `manifest.app`'s
    `help=` string that shifts the wrap onto a lowercase word (verified by
    execution, see DISCRIMINATION) still leaves the continuation line's name
    column blank and still excludes it.

    Every row's first whitespace-delimited token that looks like a command
    name (``^[a-z][a-z0-9-]*$``) is counted -- not filtered against the known
    set -- so an unexpected eleventh entry actually reaches the caller instead of
    being discarded before it can be compared.
    """
    names = []
    in_commands = False
    for line in help_output.splitlines():
        stripped = line.strip()
        if "Commands" in stripped and stripped.startswith("╭"):
            in_commands = True
            continue
        if not in_commands:
            continue
        if stripped.startswith("╰"):
            break
        if not line.startswith("│"):
            continue
        inner = line[1:]
        if inner.endswith("│"):
            inner = inner[:-1]
        # `inner[0]` is the panel's fixed one-space left padding; `inner[1]`
        # is the first character of the name column proper. A continuation
        # line pads the whole name-column width with spaces, so it is blank
        # there too.
        if len(inner) < 2 or inner[1] == " ":
            continue
        content = inner.strip()
        first_token = content.split(None, 1)[0] if content else ""
        if _COMMAND_NAME.match(first_token):
            names.append(first_token)
    return names


def test_help_lists_exactly_ten_subcommands() -> None:
    """Guards the other direction: an eleventh stray entry (a leftover manual
    registration, a typo'd duplicate) is as wrong as a missing one.

    The set comparison subsumes a count check, so no literal `9` is asserted
    here (the plan's "no task rests on a count" rule) -- `_SUBCOMMANDS`
    itself is the enumerated class.
    """
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    registered = _registered_command_names(result.output)
    assert sorted(registered) == sorted(_SUBCOMMANDS)


def test_registered_command_names_survives_a_benign_reword_that_wraps_on_a_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A help-text reword that has nothing to do with registration must not
    flip this guard: rewording only `manifest.app`'s `help=` string so its
    wrapped continuation line starts with a lowercase word (not the digit/
    punctuation the current text happens to wrap on) must still extract
    exactly the ten real names, with no phantom entry for that word.

    Confirmed by execution against the *old*, punctuation-anchored
    extraction: the same reword there admits a phantom ``"nicely"`` entry
    (see DISCRIMINATION in the status report).
    """
    monkeypatch.setattr(
        manifest_module.app.info,
        "help",
        "Tree manifests and the spec status baseline lands wrapped nicely "
        "across lines here today okay",
    )

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    registered = _registered_command_names(result.output)
    assert sorted(registered) == sorted(_SUBCOMMANDS)


def _build_app(*, with_stray_extra_command: bool) -> typer.Typer:
    """Rebuild `__main__.py`'s registration from scratch (rather than
    mutating the shared `app`), optionally with one extra command wired on
    top, so this test cannot contaminate any other test's `app` instance."""
    fresh = typer.Typer(no_args_is_help=True, add_completion=False)
    fresh.add_typer(manifest_module.app, name="manifest")
    fresh.command("preflight")(preflight.run)
    fresh.command("fingerprints")(fingerprints.run)
    fresh.command("plan")(plan.run)
    fresh.command("rewrite")(rewrite.run)
    fresh.command("verify-local")(verify.verify_local)
    fresh.command("adopt")(adopt.run)
    fresh.command("verify-remote")(verify.verify_remote)
    fresh.command("pins")(pins.run)
    fresh.command("replace")(replace.run)
    if with_stray_extra_command:
        fresh.command("extra-command")(pins.run)
    return fresh


def test_registered_command_names_flags_a_stray_extra_command() -> None:
    """The other direction of the same guard: an unwired-for extra
    registration (a leftover manual `app.command(...)` call, a typo'd
    duplicate) must actually surface as a name the fixture didn't expect,
    not be silently absorbed."""
    fresh = _build_app(with_stray_extra_command=True)

    result = runner.invoke(fresh, ["--help"])

    assert result.exit_code == 0
    registered = _registered_command_names(result.output)
    assert sorted(registered) != sorted(_SUBCOMMANDS)
    assert "extra-command" in registered


# One entry per stub subcommand (excluding `manifest` and `fingerprints`,
# which are implemented and have their own functional tests in
# test_manifest.py and test_fingerprints.py respectively), each paired with a
# substring that names only that module's own task and design-doc component
# -- so a row wired to the *wrong* module's callable (a mis-copied
# registration line: `app.command("adopt")(pins.run)`,
# `app.command("verify-local")(verify.verify_remote)`) surfaces the wrong
# substring under the right command name, instead of passing unnoticed
# because both tests only ever asserted the `--help` name column.
_STUB_COMMAND_SIGNATURES = {
    "preflight": "QuiescenceGate",
    "plan": "RedactionPlan",
    "rewrite": "HistoryRewrite",
    "verify-local": "ReplacementVerification",
    "adopt": "CloneAdoption",
    "verify-remote": "RemoteReconciliation",
    "pins": "ReferenceRepair",
    "replace": "HistoryReplacement",
}


@pytest.mark.parametrize(
    ("command_name", "signature"), sorted(_STUB_COMMAND_SIGNATURES.items())
)
def test_each_stub_subcommand_dispatches_to_its_own_module_and_exits_nonzero(
    command_name: str, signature: str
) -> None:
    """Invoking each stub subcommand by name must reach *that* module's own
    `run`/`verify_local`/`verify_remote` callable (not some other module's,
    wired in by mistake) and must exit non-zero -- a stub that silently
    dropped its `raise typer.Exit(code=1)` would exit 0 and go undetected by
    a test that only checked stdout text.
    """
    result = runner.invoke(app, [command_name])

    assert result.exit_code == 1
    assert signature in result.output


# Every subcommand's expected callback, keyed by its registered name -- the
# direct pin `--help`-text and stub-signature tests above do not provide: a
# mis-wired registration (e.g. `app.command("fingerprints")(pins.run)`) still
# produces a working `fingerprints` command name in `--help` and could still
# exit non-zero for reasons unrelated to which module actually ran, so this
# compares the registered *callable itself*. Covers all ten subcommands (the
# nine `app.command(...)` registrations plus the one `add_typer` group), so
# no future task can drop or swap a module's registration line by deleting a
# row from `_STUB_COMMAND_SIGNATURES` alone.
_EXPECTED_COMMAND_CALLBACKS = {
    "preflight": preflight.run,
    "fingerprints": fingerprints.run,
    "plan": plan.run,
    "rewrite": rewrite.run,
    "verify-local": verify.verify_local,
    "adopt": adopt.run,
    "verify-remote": verify.verify_remote,
    "pins": pins.run,
    "replace": replace.run,
}


def test_registered_commands_dispatch_to_their_own_modules_callable() -> None:
    """Directly pins `scripts.purge.__main__.app`'s command registrations,
    name-to-callback, for all nine non-group subcommands.

    `typer.Typer.registered_commands` is a list of `CommandInfo` objects
    (each with a `.name` and a `.callback`), not `(name, callback)` tuples --
    verified by inspecting the installed typer at test-authoring time (typer
    0.27.0), not assumed.
    """
    registered = {info.name: info.callback for info in app.registered_commands}

    assert registered == _EXPECTED_COMMAND_CALLBACKS


def test_registered_groups_wires_manifest_to_its_own_sub_app() -> None:
    """Pins the tenth subcommand -- `manifest`, registered via `add_typer`
    rather than `command` -- separately, since it does not appear in
    `registered_commands`."""
    groups = {info.name: info.typer_instance for info in app.registered_groups}

    assert groups == {"manifest": manifest_module.app}
