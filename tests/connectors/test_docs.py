"""Pins for the connectors documentation page (design.md "ConnectorsDoc";
Req 15.5).

Individual facts ``docs/connectors.md`` states that have a real code or
design source are checked against that source: the
look-back default and its upper bound
(:data:`fitdocs.connectors.settings.DEFAULT_LOOKBACK_DAYS`,
:data:`~fitdocs.connectors.settings.MAX_LOOKBACK_DAYS`); the
hyphenated ``FITDOCS_CONNECTOR_*`` example, recomputed through
:func:`fitdocs.connectors.credentials.env_var_name`; the credentials
directory order (the real environment-variable names, in the real
precedence order); the directory-to-``0700``/file-to-``0600`` mode
*pairing*, observed on a real
:class:`~fitdocs.connectors.credentials.CredentialStore` write; the
instance-table key column (``connector``, ``lookback_days``, ``wellness``),
parsed from the page's own table and compared against the real reader's
reserved key literals, and the ``connector`` row's stated default,
compared both as a literal and by exercising the real
default-to-instance-name behavior through a connector registered under a
name other than ``folder``; the folder connector's
example keys, parsed from the page's own fenced block and threaded through
the real :class:`~fitdocs.connectors.folder.FolderConnector`; the ledger
path shape, against :func:`fitdocs.layout.connector_ledger_path`; and the
``cron`` example's data-root variable, against
:data:`fitdocs.config.DATA_ROOT_ENV`. Not every sentence on the page has a
code source (delivery/removal semantics, the report's per-row wording, and
similar are pinned by reading, not by a test here) -- this module does not
claim to check the whole page.
"""

from __future__ import annotations

import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app as cli_app
from fitdocs.config import DATA_ROOT_ENV
from fitdocs.connectors import registry
from fitdocs.connectors.credentials import (
    CREDENTIALS_DIR_ENV,
    XDG_CONFIG_HOME_ENV,
    CredentialStore,
    StoredCredentials,
    env_var_name,
)
from fitdocs.connectors.folder import FolderConnector
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    CredentialField,
    SettingsContext,
)
from fitdocs.connectors.relay import DEFAULT_RELAY_URL
from fitdocs.connectors.settings import (
    _CONNECTOR_KEY,
    _RESERVED_KEYS,
    DEFAULT_LOOKBACK_DAYS,
    MAX_LOOKBACK_DAYS,
    load_connectors_settings,
)
from fitdocs.layout import connector_ledger_path
from tests._changelog_view import V0_2_0, read_unreleased_since

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONNECTORS_DOC = _REPO_ROOT / "docs" / "connectors.md"


def _connectors_doc_text() -> str:
    return _CONNECTORS_DOC.read_text(encoding="utf-8")


def _section_text(heading: str) -> str:
    """The body text of the ``## <heading>`` section (up to, but excluding,
    the next ``## `` heading or end of file)."""
    text = _connectors_doc_text()
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.S | re.M)
    assert match, f"section {heading!r} not found in docs/connectors.md"
    return match.group(1)


# --------------------------------------------------------------------------
# The look-back default and its upper bound
# --------------------------------------------------------------------------


def test_every_stated_lookback_default_equals_the_code_constant() -> None:
    """Every number the page states as ``lookback_days``'s default --
    the table's last column, and every ``defaults to N`` phrase in the
    fenced example -- equals :data:`DEFAULT_LOOKBACK_DAYS`.

    Positive control: the page states this default more than once today (the
    table cell and the ``toml`` comment), so a loop with no hits would be
    silently vacuous; requiring at least two occurrences catches that.
    """
    text = _connectors_doc_text()
    table_match = re.search(r"\| `lookback_days` \|.*\| `(\d+)` \|", text)
    assert table_match, "docs/connectors.md's lookback_days row has no default column"
    prose_matches = re.findall(r"defaults to (\d+)", text)
    assert prose_matches, "docs/connectors.md has no 'defaults to N' prose"

    stated = [int(table_match.group(1))] + [int(value) for value in prose_matches]
    assert len(stated) >= 2, (
        f"only one stated default found, expected the table cell plus at "
        f"least one 'defaults to N' phrase: {stated}"
    )
    assert all(value == DEFAULT_LOOKBACK_DAYS for value in stated), stated


def test_documented_lookback_upper_bound_equals_the_code_constant() -> None:
    """The page's stated whole-days range upper bound equals
    :data:`MAX_LOOKBACK_DAYS`."""
    text = _connectors_doc_text()
    match = re.search(r"whole days, 0-(\d+)", text)
    assert match, "docs/connectors.md does not state lookback_days's range"
    assert int(match.group(1)) == MAX_LOOKBACK_DAYS


# --------------------------------------------------------------------------
# Environment-variable examples
# --------------------------------------------------------------------------

# The page's naming-rule example whose instance name contains a hyphen (proving
# the hyphen-to-underscore rule is shown, not only the upper-casing rule).
_DOCUMENTED_ENV_VAR_EXAMPLES: list[tuple[str, str]] = [
    ("another-service", "client_secret"),
]


def test_hyphenated_documented_example_uses_the_hyphen_substitution() -> None:
    """The one documented (instance, field) pair whose instance name
    contains a hyphen is used to prove the hyphen-to-underscore rule --
    pulled from :data:`_DOCUMENTED_ENV_VAR_EXAMPLES` itself, not a separate
    hard-coded pair that could silently drift from what the page shows."""
    hyphenated = [
        (instance, field)
        for instance, field in _DOCUMENTED_ENV_VAR_EXAMPLES
        if "-" in instance
    ]
    assert hyphenated, "no documented example instance name contains a hyphen"
    instance, field = hyphenated[0]
    naive = f"FITDOCS_CONNECTOR_{instance.upper()}_{field.upper()}"
    real = env_var_name(instance, field)
    assert real != naive
    assert real in _connectors_doc_text()


# --------------------------------------------------------------------------
# Credentials directory order and mode pairing
# --------------------------------------------------------------------------


def test_documented_credentials_directory_order_matches_the_real_env_vars() -> None:
    """The page names the real environment-variable constants, in the real
    precedence order (dedicated variable, then XDG, then the home
    fallback) -- not paraphrases or a different order.

    The precedence *behavior* itself is pinned exhaustively in
    ``tests/connectors/test_credentials.py`` (PRESERVED-ONLY here); this
    test only pins that the page's prose matches those real names and
    orders them the same way.
    """
    text = _connectors_doc_text()
    assert CREDENTIALS_DIR_ENV in text
    assert XDG_CONFIG_HOME_ENV in text
    assert ".config/fitdocs/credentials" in text
    positions = [
        text.index(CREDENTIALS_DIR_ENV),
        text.index(XDG_CONFIG_HOME_ENV),
        text.index(".config/fitdocs/credentials"),
    ]
    assert positions == sorted(positions)


def test_documented_directory_and_file_mode_pairing_matches_real_behavior(
    tmp_path: Path,
) -> None:
    """The page's directory-mode sentence and file-mode sentence each name
    the mode observed on a real :class:`CredentialStore` write, matched to
    the *correct* one of the pair (not merely "both numbers appear
    somewhere")."""
    text = _connectors_doc_text()
    dir_match = re.search(
        r"directory is created accessible only to you \(`(\d{3,4})`\)", text
    )
    file_match = re.search(
        r"own file, written atomically and\s+readable and writable only by "
        r"you \(`(\d{3,4})`\)",
        text,
    )
    assert dir_match, "directory-mode sentence not found"
    assert file_match, "file-mode sentence not found"

    directory = tmp_path / "credentials"
    store = CredentialStore(directory)
    store.save(
        "inst",
        StoredCredentials(
            connector_id="folder",
            auth_style=AuthStyle.NONE,
            values={},
            expires_at=None,
            scopes=None,
        ),
    )
    real_dir_mode = f"{stat.S_IMODE(directory.stat().st_mode):04o}"
    real_file_mode = f"{stat.S_IMODE(store.path_for('inst').stat().st_mode):04o}"

    assert dir_match.group(1) == real_dir_mode
    assert file_match.group(1) == real_file_mode
    # Falsity in the starting state / sole-failure guard: the two real modes
    # actually differ, so a pairing bug (reading the file's mode for the
    # directory sentence, or vice versa) cannot pass by the two numbers
    # coincidentally matching each other.
    assert real_dir_mode != real_file_mode


# --------------------------------------------------------------------------
# Settings keys, exercised through the real reader
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _StubConnector:
    """A minimal connector registered only so a test instance can be named
    something other than ``folder`` while still resolving through the real
    registry. Registration itself does not call ``parse_settings``,
    ``list_activities``, or ``fetch_activity``; :meth:`parse_settings` below
    is exercised directly by :func:`load_connectors_settings`, so it returns
    a usable value rather than raising."""

    connector_id: str
    display_name: str = "Stub"
    auth_style: AuthStyle = AuthStyle.NONE
    capabilities: frozenset[Capability] = frozenset({Capability.PULL_ACTIVITIES})
    credential_fields: tuple[CredentialField, ...] = ()

    def parse_settings(self, table: Mapping[str, object], context: object) -> object:
        return dict(table)

    def list_activities(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError

    def fetch_activity(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError


def test_regenerate_section_names_the_regen_command() -> None:
    """With cross-source identity shipped, the page tells a data root whose
    pages predate it to run ``fitdocs regen`` before its first pull."""
    assert "`fitdocs regen`" in _section_text("Regenerating before a first pull")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_delivery_section_states_the_same_pull_refetch_and_its_window() -> None:
    """The sweep runs before the listing (``connectors/pull.py``), so a
    forgotten delivery is fetched again by the same pull, and only when that
    pull lists it. The page once promised "a later pull" with no window."""
    section = _flat(_section_text("Delivery and removal"))
    assert "fetched again on a later pull" not in section
    assert "This check runs before the pull lists anything, so the same pull" in (
        section
    )
    assert "An `intervals` activity older than that window is not listed again" in (
        section
    )
    assert "fitdocs pull intervals --since YYYY-MM-DD" in section


def test_delivery_section_reports_changed_bytes_already_held_as_held() -> None:
    """A changed activity whose new bytes the archive or another pending
    delivery already holds is recorded ``ALREADY_HELD`` and reported
    ``held``; nothing is delivered."""
    section = _flat(_section_text("Delivery and removal"))
    assert (
        "the new bytes are delivered in its place, unless the archive, or another "
        "of this instance's pending deliveries, already holds those exact bytes"
    ) in section
    assert "the report lists it as `held`, not `delivered`" in section


def test_intervals_section_does_not_promise_a_plain_pull_resumes_a_backfill() -> None:
    """A plain pull lists from the watermark less ``lookback_days`` and the
    watermark never moves back, so an interrupted ``--since`` backfill into an
    instance that has pulled before is continued only by the same ``--since``."""
    match = re.search(
        r"^### What a pull fetches\n(.*?)(?=\n### |\n## |\Z)",
        _connectors_doc_text(),
        re.S | re.M,
    )
    assert match is not None
    section = _flat(match.group(1))
    assert "the next pull resumes where it stopped" not in section
    assert "the next one resumes" not in section
    assert "the backfill does not move the watermark back" in section
    assert "Run the same `fitdocs pull intervals --since YYYY-MM-DD` again" in section


def _instance_table_rows() -> list[tuple[str, str]]:
    """The ``| Key | Meaning | Default |`` table under "## Configuring an
    instance", parsed from the page's own text: ``(key, default-cell-text)``
    pairs, in row order."""
    section = _section_text("Configuring an instance")
    rows = []
    for line in section.splitlines():
        match = re.match(r"^\| `(\w+)` \| .+? \| (.+) \|$", line)
        if match:
            rows.append((match.group(1), match.group(2)))
    return rows


def _page_connector_key_name() -> str:
    """The instance-table key whose Default cell states the
    default-to-instance-name rule -- found by that cell's text, not by
    position, so a rename of the key itself doesn't break the lookup."""
    candidates = [
        key
        for key, default in _instance_table_rows()
        if "instance's own name" in default
    ]
    assert len(candidates) == 1, (
        f"expected exactly one instance-table row whose default is the "
        f"instance's own name, found {candidates}"
    )
    return candidates[0]


def test_instance_table_keys_match_the_real_readers_reserved_keys() -> None:
    """The page's instance-table key column is exactly the set of keys the
    real reader reserves (:data:`fitdocs.connectors.settings._RESERVED_KEYS`)."""
    rows = _instance_table_rows()
    page_keys = {key for key, _default in rows}
    assert page_keys, "docs/connectors.md's instance table has no key column"
    assert page_keys == _RESERVED_KEYS


def test_instance_table_connector_default_cell_states_the_instance_name_rule() -> None:
    """The ``connector`` row's Default cell is the literal sentence the page
    uses for "falls back to the instance's own name", not a different
    default (such as a hard-coded connector id)."""
    rows = dict(_instance_table_rows())
    assert rows[_CONNECTOR_KEY] == "the instance's own name"


def test_documented_settings_keys_are_accepted_by_the_real_reader(
    tmp_path: Path,
) -> None:
    """The documented ``connector`` and ``lookback_days`` keys are exercised
    through the real :func:`load_connectors_settings`, not merely asserted as prose.

    Falsity in the starting state: the instance is given a *non-default*
    ``lookback_days`` (5, not 30) so the assertion cannot pass merely
    because the reader ignored the key and fell back to its default.
    """
    source = tmp_path / "source"
    source.mkdir()
    document = {
        "connectors": {
            "myinstance": {
                "connector": "folder",
                "lookback_days": 5,
                "path": str(source),
            }
        }
    }
    context = SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")
    instances = load_connectors_settings(
        document, settings_file=tmp_path / "fitdocs.toml", context=context
    )
    assert len(instances) == 1
    instance = instances[0]
    assert instance.name == "myinstance"
    assert instance.connector.connector_id == "folder"
    assert instance.lookback_days == 5


def test_omitting_the_connector_key_defaults_to_the_instance_name() -> None:
    """The page's connector-defaults-to-instance-name rule, exercised
    through the real reader using an instance whose name is a registered
    connector id *other than* ``folder``: a fixture instance named
    ``folder`` cannot tell this rule apart from a bug that hard-codes the
    fallback to the literal ``"folder"``, because the hard-coded value and
    the correct value would coincide."""
    connector_key = _page_connector_key_name()
    stub_id = "page-default-stub"
    registry.register(_StubConnector(connector_id=stub_id))
    try:
        context = SettingsContext(
            data_root=Path("/nonexistent"), inbox=Path("/nonexistent/inbox")
        )
        table: dict[str, object] = {"lookback_days": DEFAULT_LOOKBACK_DAYS}
        assert connector_key not in table
        document = {"connectors": {stub_id: table}}
        instances = load_connectors_settings(
            document, settings_file=Path("/nonexistent/fitdocs.toml"), context=context
        )
    finally:
        registry.unregister(stub_id)
    assert len(instances) == 1
    assert instances[0].connector.connector_id == stub_id


# --------------------------------------------------------------------------
# The folder connector's example keys, parsed from the page itself
# --------------------------------------------------------------------------


def _folder_example_keys() -> list[str]:
    """The ordered ``key = value`` names in the folder connector's own
    fenced ``toml`` example block, parsed from the page's actual text."""
    section = _section_text("The folder connector")
    match = re.search(r"```toml\n(.*?)```", section, re.S)
    assert match, "no toml example found under '## The folder connector'"
    keys = []
    for line in match.group(1).splitlines():
        key_match = re.match(r"(\w+)\s*=", line)
        if key_match:
            keys.append(key_match.group(1))
    return keys


def test_documented_folder_keys_thread_through_the_real_connector(
    tmp_path: Path,
) -> None:
    """The folder connector's example keys, read from the page's own fenced
    block, are used -- under their literal spelled names, not a hard-coded
    table -- to build the settings table fed into the real
    :meth:`FolderConnector.parse_settings`, with a non-default sentinel for
    ``settle_seconds``: a misspelled key on the page reds the key-list
    assertion; the sentinel then proves the parsed keys reach the real
    connector under those spellings.
    """
    keys = _folder_example_keys()
    assert keys == ["connector", "path", "settle_seconds"], (
        f"the folder connector's documented example keys changed: {keys}"
    )

    source = tmp_path / "source"
    source.mkdir()
    sentinel_settle_seconds = 4.5
    known_values: dict[str, object] = {
        "path": str(source),
        "settle_seconds": sentinel_settle_seconds,
    }
    # "connector" is reserved by the generic [connectors] reader and never
    # reaches a connector's own parse_settings (see the settings-keys tests
    # above); every other page-parsed key must have a known fixture value.
    rest_keys = [key for key in keys if key != _CONNECTOR_KEY]
    assert set(rest_keys) <= set(known_values), (
        f"the folder connector's documented example has a key with no "
        f"fixture value mapped here: {set(rest_keys) - set(known_values)}"
    )
    table = {key: known_values[key] for key in rest_keys}

    context = SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")
    settings = FolderConnector().parse_settings(table, context)
    assert settings.source == source
    assert settings.settle_seconds == sentinel_settle_seconds
    assert settings.settle_seconds != 2.0  # the inbox's own unrelated default


# --------------------------------------------------------------------------
# The ledger path shape
# --------------------------------------------------------------------------


def test_documented_ledger_path_shape_matches_layout() -> None:
    """The page's ``<data-root>/.fitdocs/connectors/<name>.toml`` template
    matches the real shape :func:`connector_ledger_path` produces."""
    template = ".fitdocs/connectors/<name>.toml"
    assert template in _connectors_doc_text()

    produced = connector_ledger_path(Path("/does/not/matter"), "name")
    expected_suffix = template.replace("<name>", "name")
    assert str(produced).endswith(expected_suffix)


# --------------------------------------------------------------------------
# The cron example's data-root variable
# --------------------------------------------------------------------------


def test_cron_example_uses_the_real_data_root_env_var() -> None:
    text = _connectors_doc_text()
    assert f"{DATA_ROOT_ENV}=/path/to/data-root" in text


# --------------------------------------------------------------------------
# Inbox carve-out (task 8.2, design.md "InboxDocs"; Req 8.9, 15.4)
# --------------------------------------------------------------------------

_INBOX_DOC = _REPO_ROOT / "docs" / "inbox.md"


def _inbox_doc_text() -> str:
    return _INBOX_DOC.read_text(encoding="utf-8")


def test_inbox_page_names_the_delivery_carve_out_as_the_concern_exception() -> None:
    """The opening bold sentence keeps naming no watching/scheduling, and
    now qualifies "your concern" with the connector exception instead of
    the old unqualified "entirely" (design.md InboxDocs).

    Mutation caught: reverting the qualifying clause back to "entirely your
    concern" reds this; dropping the no-watching clause entirely also reds
    this (checked independently of the never-delete pins below, which neither
    regex here can satisfy).
    """
    text = _inbox_doc_text()
    assert re.search(
        r"your concern, unless you configure a connector\.\s+fitdocs\s+"
        r"performs no watching and no scheduling of any kind",
        text,
    )


def test_inbox_page_states_the_three_carve_out_statements() -> None:
    """The Disposition policy paragraph design.md states: the drain itself
    is unchanged (still never deletes); a connector's own prior delivery is
    removed by the *next* pull once its bytes are archived; and nothing the
    athlete or the athlete's own tools placed in the inbox is ever a
    removal candidate.

    Three independent regexes, each scoped to its own clause, so a mutation
    dropping only one of the three statements (not the whole paragraph)
    still reds exactly one assertion rather than being masked by the other
    two surviving.
    """
    text = _inbox_doc_text()
    assert re.search(r"drain itself\s+never\s+deletes anything", text)
    assert re.search(
        r"\*next\*\s+pull\s+removes it once the archive holds an? "
        r"identical-content copy",
        text,
    )
    assert re.search(
        r"[Nn]othing you or your own tools put in the inbox is ever removed",
        text,
    )


def test_inbox_page_keeps_both_never_delete_pins_verbatim() -> None:
    """The two bold guarantee sentences in the Disposition policy paragraph
    survive the carve-out addition verbatim -- the carve-out is additive,
    not a narrowing of the default-disposition guarantee.

    Mutation caught: deleting either sentence (simulating an edit that
    folded the never-delete guarantee into the new carve-out paragraph
    instead of keeping it standing on its own) reds the corresponding
    assertion.
    """
    text = _inbox_doc_text()
    assert re.search(
        r"No configuration\s+ever deletes an inbox file: deletion is not an "
        r"option fitdocs offers, under\s+any disposition",
        text,
    )
    assert re.search(
        r"it stays in the inbox and is retried on the next drain",
        text,
    )


def test_inbox_page_carve_out_paragraph_is_additive_not_in_place_of_the_pin() -> None:
    """The carve-out is its own paragraph, after the never-delete and
    never-moved sentences -- not a rewrite that replaces "never" with a
    conditional.
    """
    text = _inbox_doc_text()
    never_delete = text.index("deletion is not an")
    never_moved = text.index("it stays in the inbox and is retried")
    carve_out = text.index("drain itself")
    assert never_delete < never_moved < carve_out
    assert (
        "\n\n**Connector deliveries are the one carve-out.** The drain itself never"
        in text
    )


# --------------------------------------------------------------------------
# Relay documentation (relay-server task 8.4; Req 16.3, 16.7)
# --------------------------------------------------------------------------


def _relay_section() -> str:
    return _section_text("The relay connector")


def test_relay_section_states_the_default_url_and_the_override_variable() -> None:
    """Mutation: changing the stated address, or the stated variable, reds."""
    section = _relay_section()
    assert f"defaults to the maintainer's relay ({DEFAULT_RELAY_URL})" in section
    assert f'url = "{DEFAULT_RELAY_URL}"' in section
    assert f"`{env_var_name('relay', 'token')}`" in section


def test_relay_section_names_every_relay_command_form() -> None:
    """Each command form stands as its own whole line of a fenced block.

    Whole-line matching matters: ``fitdocs connect relay`` is a prefix of the
    registration form, and ``fitdocs disconnect relay`` of the local-only one.
    Mutation: deleting any one of these lines reds this.
    """
    section = _relay_section()
    for line in (
        "fitdocs connect relay",
        "fitdocs connect relay --register [--email ADDRESS]",
        "fitdocs disconnect relay",
        "fitdocs disconnect relay --local-only",
    ):
        found = re.findall(rf"^{re.escape(line)}$", section, re.M)
        assert len(found) == 1, line


def test_relay_section_pull_sentence_is_what_the_cli_prints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line the section quotes for a relay-only bare pull is the line a
    relay-only bare pull prints.

    Mutation: rewording the CLI's line, or the section's quote, reds this.
    """
    quoted = re.findall(
        r'prints "(No configured[^"]*)"', " ".join(_relay_section().split())
    )
    assert len(quoted) == 1
    (tmp_path / "fitdocs.toml").write_text(
        '[connectors.my-relay]\nconnector = "relay"\n'
    )
    result = CliRunner().invoke(cli_app, ["pull", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert quoted[0] in " ".join(result.output.split())


def test_relay_section_states_what_leaves_for_each_command() -> None:
    """The "What each command sends" subsection names the request each
    command makes, so a deleted row reds."""
    match = re.search(
        r"^### What each command sends\n(.*?)(?=\n### |\Z)",
        _relay_section(),
        re.S | re.M,
    )
    assert match, "no 'What each command sends' subsection"
    body = " ".join(match.group(1).split())
    for phrase in (
        "pasted token",
        "email address",
        "stored token",
        "nothing leaves your machine",
    ):
        assert phrase in body, phrase


def _added_and_changed() -> tuple[str, str]:
    view = read_unreleased_since(_REPO_ROOT / "CHANGELOG.md", V0_2_0)
    unreleased = view.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    added = unreleased.split("### Added", 1)[1].split("\n### ", 1)[0]
    changed = unreleased.split("### Changed", 1)[1].split("\n### ", 1)[0]
    return " ".join(added.split()), " ".join(changed.split())


def _bullet(text: str, start: str) -> str:
    """The one bullet of *text* (whitespace-collapsed) that begins with *start*."""
    bullets = [
        b
        for b in re.split(r"(?= - )", " " + text)
        if b.strip().startswith(f"- {start}")
    ]
    assert len(bullets) == 1, start
    return bullets[0]


def test_changelog_added_names_connector_register_and_disconnect() -> None:
    """Each Added entry names the action. Mutation: deleting the connector
    entry, `--register`, the disconnect entry, `--local-only`, or either
    action sentence reds."""
    added, _ = _added_and_changed()
    connector = _bullet(added, "The `relay` connector, for a fitdocs relay")
    assert "fitdocs connect NAME --register" in connector
    assert (
        "Action: to use a relay, add the instance table and run "
        "`fitdocs connect NAME`." in connector
    )
    disconnect = _bullet(added, "`fitdocs disconnect NAME [--local-only]`")
    assert "`--local-only` removes the file without contacting the relay" in disconnect
    assert (
        "Action: run `fitdocs disconnect NAME` to retire a token you no longer "
        "want on this machine." in disconnect
    )


def test_changelog_changed_names_bare_pull_and_credentials_style() -> None:
    """Each Changed entry names the action, and the two are adjacent, the bare
    pull then the `auth_style` value (later landers may append after them).
    Mutation: deleting either entry or action sentence, or separating or
    swapping the two entries, reds."""
    _, changed = _added_and_changed()
    bare = _bullet(changed, "A bare `fitdocs pull`")
    assert "Action: none; name the instance to see why it is not pulled." in bare
    style = _bullet(changed, "The credentials file's `auth_style` value set")
    assert f"gains `{AuthStyle.RELAY_TOKEN.value}`" in style
    assert (
        "Action: none for existing files; do not share one credentials "
        "directory with an older fitdocs." in style
    )
    bullets = [b.strip() for b in re.split(r"(?= - )", " " + changed) if b.strip()]
    position = bullets.index(bare.strip())
    assert bullets[position + 1] == style.strip()


def test_relay_section_registration_order_and_token_rules() -> None:
    """Registration order and the override rules, as literal sentences.
    Mutation: reverting any of these sentences reds."""
    flat = " ".join(_relay_section().split())
    assert (
        "checks the address's shape, and only then asks the relay whether it "
        "offers registration" in flat
    )
    assert "to ask its operator for a token" in flat
    assert "revokes only the stored token, never the variable" in flat
    assert (
        "overrides the stored token wherever fitdocs resolves the instance's "
        "credentials" in flat
    )
    assert "`fitdocs connect` prints the variable's name when it is set" in flat
    assert (
        "only when nothing is stored does it say the variable is not revoked "
        "and remains set" in flat
    )
    assert "exits `2` and names the variable, except with `--register --email" in flat
    assert "exactly `localhost`, `127.0.0.1` and `::1`" in flat


def test_framework_pulling_bullet_and_terms_paragraph_cover_the_relay() -> None:
    """Mutation: reverting either edit reds."""
    text = " ".join(_connectors_doc_text().split())
    assert (
        "omit to pull every configured instance whose connector pulls "
        "activities or wellness (see [Pulling a relay instance]"
        "(#pulling-a-relay-instance))" in text
    )
    assert (
        "talks to a fitdocs relay (the maintainer's, or one you or another "
        "operator run), not to a third-party service's API" in text
    )
    assert "([Pulling a relay instance](#pulling-a-relay-instance) below)" in text


_COMPATIBILITY_DOC = _REPO_ROOT / "docs" / "compatibility.md"
_CONFIGURATION_DOC = _REPO_ROOT / "docs" / "configuration.md"


def _collapsed_doc(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_compatibility_inbox_item_names_the_carve_out() -> None:
    text = _collapsed_doc(_COMPATIBILITY_DOC)
    start = text.index("2. **The inbox interface**")
    item = text[start : text.index("3. **The load-calculator plugin API**", start)]
    assert (
        "with one carve-out: a connector's own prior delivery, once archived, "
        "is removed by the next pull"
    ) in item


def test_compatibility_inbox_subsection_names_the_carve_out_as_additive() -> None:
    text = _collapsed_doc(_COMPATIBILITY_DOC)
    start = text.index("**The inbox interface.**")
    subsection = text[start : text.index("**The plugin API.**", start)]
    additive = subsection[subsection.index("Additive:") : subsection.index("Internal:")]
    assert (
        "the delivery-removal carve-out — a connector's own prior delivery, once "
        "its bytes are archived, is removed by that connector's next pull"
    ) in additive
    assert (
        "nothing the athlete or the athlete's own tools place in the inbox is "
        "ever a candidate for removal"
    ) in additive


def test_configuration_data_root_command_list_names_connect_and_pull() -> None:
    text = _collapsed_doc(_CONFIGURATION_DOC)
    assert (
        "`derive-benchmarks`, `connect`, `pull`, and any future one) needs a data root"
    ) in text


def test_configuration_names_the_connectors_table_and_points_at_its_page() -> None:
    markdown = _CONFIGURATION_DOC.read_text(encoding="utf-8")
    rows = [
        line for line in markdown.splitlines() if line.startswith("| `[connectors]` |")
    ]
    assert len(rows) == 1
    assert rows[0].rstrip().endswith("| below |")
    heading = "### `[connectors]`: pulling from a configured source\n"
    assert markdown.count(heading) == 1
    body = re.split(r"\n#{1,3} ", markdown.split(heading, 1)[1], maxsplit=1)[0]
    assert "[`docs/connectors.md`](connectors.md)" in body
