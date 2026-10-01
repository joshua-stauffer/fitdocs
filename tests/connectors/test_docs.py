"""Pins for the connectors documentation page (design.md "ConnectorsDoc",
"NeutralScan"; Req 14.6, 15.5).

Two independent things are pinned here:

* **ConnectorsDoc** -- individual facts ``docs/connectors.md`` states that
  have a real code or design source are checked against that source: the
  look-back default and its upper bound
  (:data:`fitdocs.connectors.settings.DEFAULT_LOOKBACK_DAYS`,
  :data:`~fitdocs.connectors.settings.MAX_LOOKBACK_DAYS`); the
  ``FITDOCS_CONNECTOR_*`` examples, recomputed through
  :func:`fitdocs.connectors.credentials.env_var_name`; the credentials
  directory order (the real environment-variable names, in the real
  precedence order); the directory-to-``0700``/file-to-``0600`` mode
  *pairing*, observed on a real
  :class:`~fitdocs.connectors.credentials.CredentialStore` write; the
  instance-table key column (``connector``, ``lookback_days``), parsed from
  the page's own fenced example and compared against the real reader's
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
* **NeutralScan** (design.md "NeutralScan") -- the service-neutral scan
  design.md describes for the connectors package, its tests, and this page's
  own ``##`` sections (plus its preamble, treated as its own section).
  :data:`NEUTRAL_SCAN_EXEMPTIONS` ships **empty** in this spec (no
  online-service connector); ``intervals-connector`` appends its own entry
  later, by design a pure append -- nothing here asserts the table is empty.
  :func:`scan_for_unadmitted_hosts` is pinned on synthetic inputs,
  independent of the real tree, and then run once for real. "The project's
  own" is decided by URL prefix against a declared ``[project.urls]`` value
  (not by hostname alone), matched case-insensitively on the scheme.
"""

from __future__ import annotations

import re
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pytest

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
from fitdocs.connectors.settings import (
    _CONNECTOR_KEY,
    _LOOKBACK_KEY,
    DEFAULT_LOOKBACK_DAYS,
    MAX_LOOKBACK_DAYS,
    load_connectors_settings,
)
from fitdocs.layout import connector_ledger_path

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
# Headings
# --------------------------------------------------------------------------

_EXPECTED_HEADINGS = [
    "# Connectors",
    "## Configuring an instance",
    "## The folder connector",
    "## Connecting",
    "## Credentials",
    "## Pulling",
    "### Reading the report",
    "## Delivery and removal",
    "## The ledger",
    "## What leaves your machine",
    "## The terms-first policy",
    "## Regenerating before a first pull",
    "## Running on a schedule",
]


def test_page_headings_match_expected() -> None:
    """Every ``#``/``##``/``###`` heading, in order, matches exactly.

    Mutation: renaming, reordering, or dropping any heading reds this test.
    """
    found = re.findall(r"^(#{1,3} .+)$", _connectors_doc_text(), re.M)
    assert found == _EXPECTED_HEADINGS


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

# The exact (instance, field) pairs docs/connectors.md illustrates the naming
# rule with -- one plain instance name, one with a hyphen (proving the
# hyphen-to-underscore rule is shown, not only the upper-casing rule).
_DOCUMENTED_ENV_VAR_EXAMPLES: list[tuple[str, str]] = [
    ("myservice", "api_key"),
    ("another-service", "client_secret"),
]


def test_documented_environment_variable_examples_match_env_var_name() -> None:
    """Every ``FITDOCS_CONNECTOR_*`` string on the page is exactly what
    :func:`env_var_name` produces for one of the documented (instance,
    field) pairs -- no more, no fewer."""
    text = _connectors_doc_text()
    found = set(re.findall(r"FITDOCS_CONNECTOR_[A-Z0-9_]+", text))
    expected = {
        env_var_name(instance, field)
        for instance, field in _DOCUMENTED_ENV_VAR_EXAMPLES
    }
    assert found, "docs/connectors.md shows no FITDOCS_CONNECTOR_* example"
    assert found == expected


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
    real reader reserves (:data:`fitdocs.connectors.settings._CONNECTOR_KEY`,
    :data:`~fitdocs.connectors.settings._LOOKBACK_KEY`) -- not a hand-typed
    copy that could drift from the reader's own literal."""
    rows = _instance_table_rows()
    page_keys = {key for key, _default in rows}
    assert page_keys, "docs/connectors.md's instance table has no key column"
    assert page_keys == {_CONNECTOR_KEY, _LOOKBACK_KEY}


def test_instance_table_connector_default_cell_states_the_instance_name_rule() -> None:
    """The ``connector`` row's Default cell is the literal sentence the page
    uses for "falls back to the instance's own name", not a different
    default (such as a hard-coded connector id)."""
    rows = dict(_instance_table_rows())
    assert rows[_CONNECTOR_KEY] == "the instance's own name"


def test_documented_settings_keys_are_accepted_by_the_real_reader(
    tmp_path: Path,
) -> None:
    """Every ``[connectors.<name>]`` key the page documents (``connector``,
    ``lookback_days``) is exercised through the real
    :func:`load_connectors_settings`, not merely asserted as prose.

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
# NeutralScan (design.md "NeutralScan", Req 14.6)
# --------------------------------------------------------------------------

# Ships empty: this spec adds no online-service connector. `intervals-connector`
# appends its own entry later (cross-spec ruling 2026-09-29) -- a pure append,
# so nothing here asserts this table is empty.
NEUTRAL_SCAN_EXEMPTIONS: dict[str, frozenset[str]] = {}

_URL_PATTERN = re.compile(r"https?://[^\s\"')>\]]+", re.IGNORECASE)
_RESERVED_EXACT_HOSTS = frozenset(
    {"example.com", "example.org", "example.net", "localhost"}
)
# RFC 2606 reserved: example.com/.org/.net and any of their subdomains
# (leading-dot boundary -- "notexample.com" must NOT match), plus the
# .example/.test/.invalid reserved suffixes for any host.
_RESERVED_SUFFIXES = (
    ".example.com",
    ".example.org",
    ".example.net",
    ".example",
    ".test",
    ".invalid",
)


def _extract_hosts(text: str) -> list[str]:
    hosts = []
    for match in _URL_PATTERN.finditer(text):
        host = urlparse(match.group(0)).hostname
        if host:
            hosts.append(host.lower())
    return hosts


def _is_reserved(host: str) -> bool:
    return host in _RESERVED_EXACT_HOSTS or host.endswith(_RESERVED_SUFFIXES)


def _url(host: str, path: str = "/api", scheme: str = "https") -> str:
    """Build a syntactically valid URL at runtime for a *fixture* (never a
    real service), without this file's own source text ever spelling a
    scheme and host contiguously -- the real-tree NeutralScan test below
    reads this very file's literal text, and a fixture host is deliberately
    unreserved and unadmitted so the scan can find it at all."""
    return f"{scheme}{'://'}{host}{path}"


def _own_url_prefixes() -> frozenset[str]:
    """Every declared ``[project.urls]`` value, verbatim -- "the project's
    own" is decided by URL *prefix* against one of these, not by comparing
    hostnames alone (design.md: "must be the project's own (under a
    declared [project.urls] value)")."""
    document = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    urls = document["project"]["urls"]
    return frozenset(urls.values())


def test_project_urls_declares_the_connectors_page_entry() -> None:
    """``[project.urls]`` names ``docs/connectors.md`` under the key
    "Connectors". No other test in this module notices the entry's
    deletion: the page links itself relatively, so the real-tree scan never
    needs this prefix."""
    document = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    urls = document["project"]["urls"]
    assert urls["Connectors"] == (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md"
    )


_OWN_URL_BOUNDARY_CHARS = ("/", "?", "#")


def _is_own_url(url: str, own_url_prefixes: frozenset[str]) -> bool:
    """A case-insensitive prefix match against a declared ``[project.urls]``
    value, requiring a boundary right after the matched prefix -- the end of
    the URL, or ``/``/``?``/``#`` -- so a sibling path that merely *starts
    with* the same characters (``.../fitdocs-other/x`` against the prefix
    ``.../fitdocs``) is not wrongly admitted."""
    lowered = url.lower()
    for prefix in own_url_prefixes:
        prefix_lowered = prefix.lower()
        if not lowered.startswith(prefix_lowered):
            continue
        remainder = lowered[len(prefix_lowered) :]
        if remainder == "" or remainder[0] in _OWN_URL_BOUNDARY_CHARS:
            return True
    return False


def scan_for_unadmitted_hosts(
    sources: Mapping[str, str],
    *,
    own_url_prefixes: frozenset[str],
    exemptions: Mapping[str, frozenset[str]],
) -> list[tuple[str, str]]:
    """Every ``(location, host)`` pair found in *sources* whose URL is
    neither the project's own (a case-insensitive prefix match against a
    declared ``[project.urls]`` value), nor on a reserved example host, nor
    admitted for that exact *location* by *exemptions*.

    *location* is a plain repo-relative file path, or
    ``"docs/connectors.md#<heading>"`` for one ``##`` section of the page
    (``"docs/connectors.md#"`` for its preamble before the first heading) --
    an exemption keyed by that exact string admits only that section, never
    the whole page (design.md: "a host admitted for one ``##`` section of a
    page and named in another section is [a violation]").
    """
    violations: list[tuple[str, str]] = []
    for location, text in sources.items():
        for match in _URL_PATTERN.finditer(text):
            url = match.group(0)
            if _is_own_url(url, own_url_prefixes):
                continue
            host = urlparse(url).hostname
            if host is None:
                continue
            host = host.lower()
            if _is_reserved(host):
                continue
            admitted_files = exemptions.get(host, frozenset())
            if location in admitted_files:
                continue
            violations.append((location, host))
    return violations


def _unexercised_exemptions(
    sources: Mapping[str, str], exemptions: Mapping[str, frozenset[str]]
) -> list[str]:
    """Hosts in *exemptions* that are not actually named in any of their own
    admitted files -- the conditional positive control design.md calls for
    ("so an exemption is exercised, never vacuous")."""
    unexercised = []
    for host, admitted_files in exemptions.items():
        found = any(
            host in _extract_hosts(sources.get(loc, "")) for loc in admitted_files
        )
        if not found:
            unexercised.append(host)
    return unexercised


def _read_for_scan(path: Path) -> str:
    """A file's text for the URL scan. Bytes that are not valid UTF-8 (a
    ``.DS_Store``, an image, a Latin-1 resource) become U+FFFD instead of
    raising, so no file is ever left out of the scan: a URL is ASCII and
    survives the replacement unchanged."""
    return path.read_bytes().decode("utf-8", errors="replace")


def _collect_text_sources(
    bases: tuple[Path, ...], *, relative_to: Path
) -> dict[str, str]:
    """Every regular, non-bytecode file under *bases*, keyed by its path
    relative to *relative_to*, read through :func:`_read_for_scan`."""
    texts: dict[str, str] = {}
    for base in bases:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            texts[str(path.relative_to(relative_to))] = _read_for_scan(path)
    return texts


# Every file under both directories, filtered only to skip bytecode caches --
# not just ``*.py`` -- so a non-Python resource under either tree is scanned
# too.
def _package_and_test_sources() -> dict[str, str]:
    return _collect_text_sources(
        (
            _REPO_ROOT / "src" / "fitdocs" / "connectors",
            _REPO_ROOT / "tests" / "connectors",
        ),
        relative_to=_REPO_ROOT,
    )


def _page_sections() -> dict[str, str]:
    """Every ``##`` section of the page, keyed by
    ``"docs/connectors.md#<heading>"``, plus the preamble before the first
    ``##`` heading (which includes the top-level ``# Connectors`` title),
    keyed by ``"docs/connectors.md#"`` (the empty heading)."""
    text = _connectors_doc_text()
    parts = re.split(r"(?m)^## (.+)$", text)
    sections: dict[str, str] = {"docs/connectors.md#": parts[0]}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[f"docs/connectors.md#{heading}"] = body
    return sections


def _real_sources() -> dict[str, str]:
    sources = _package_and_test_sources()
    sources.update(_page_sections())
    return sources


def _real_file_listing() -> set[str]:
    """Every regular, non-bytecode file under both scanned directories,
    from a fresh walk of its own (not :func:`_package_and_test_sources`),
    for the positive control to compare against."""
    listing: set[str] = set()
    for base in (
        _REPO_ROOT / "src" / "fitdocs" / "connectors",
        _REPO_ROOT / "tests" / "connectors",
    ):
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            listing.add(str(path.relative_to(_REPO_ROOT)))
    return listing


# --- Always-on positive control: the scan really reads the real tree ------


def test_scan_file_set_matches_directory_listings_and_includes_a_page_section() -> None:
    sources = _real_sources()
    file_keys = {key for key in sources if not key.startswith("docs/connectors.md#")}
    assert file_keys == _real_file_listing()
    assert len(file_keys) > 10, "the walk is looking at the wrong directory"

    page_keys = {key for key in sources if key.startswith("docs/connectors.md#")}
    assert page_keys, "no page section was scanned"
    assert "docs/connectors.md#The ledger" in page_keys
    assert "docs/connectors.md#" in page_keys, "the page's preamble was not scanned"
    assert sources["docs/connectors.md#"].startswith("# Connectors")


def test_a_url_in_an_undecodable_file_is_still_scanned(tmp_path: Path) -> None:
    """A file that is not valid UTF-8 is read, not skipped: an unadmitted
    URL inside a Latin-1 file is still a violation, and a binary file beside
    it does not crash the walk."""
    latin1 = tmp_path / "notes.txt"
    latin1.write_bytes(f"caf\xe9 {_url(_FAKE_HOST)}\n".encode("latin-1"))
    binary_file = tmp_path / ".DS_Store"
    binary_file.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x01, 0x80, 0x81]))
    with pytest.raises(UnicodeDecodeError):
        latin1.read_bytes().decode("utf-8")

    texts = _collect_text_sources((tmp_path,), relative_to=tmp_path)

    assert set(texts) == {".DS_Store", "notes.txt"}
    violations = scan_for_unadmitted_hosts(
        texts, own_url_prefixes=frozenset(), exemptions={}
    )
    assert violations == [("notes.txt", _FAKE_HOST)]


# --- Always-on: the real tree is clean --------------------------------


def test_real_tree_has_no_unadmitted_hosts() -> None:
    sources = _real_sources()
    violations = scan_for_unadmitted_hosts(
        sources,
        own_url_prefixes=_own_url_prefixes(),
        exemptions=NEUTRAL_SCAN_EXEMPTIONS,
    )
    assert violations == []


# --- Conditional control: only when the table is non-empty ----------------
# (zero iterations today -- the table ships empty; `intervals-connector`
# exercises this loop for real when it appends an entry).


def test_every_exemption_entry_is_exercised_in_the_real_tree() -> None:
    sources = _real_sources()
    assert _unexercised_exemptions(sources, NEUTRAL_SCAN_EXEMPTIONS) == []


# --- Synthetic unit tests of the scan function, independent of the real ---
# --- table (design.md: "pinned on synthetic inputs independent of the ----
# --- real table") -----------------------------------------------------


_FAKE_HOST = "sync.fake-vendor.net"
_OWN_URL_PREFIXES = frozenset({"https://github.com/joshua-stauffer/fitdocs"})


def test_scan_flags_an_unreserved_host_with_no_admission() -> None:
    sources = {"pkg/mod.py": f"see {_url(_FAKE_HOST)} for details"}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", _FAKE_HOST)]


def test_scan_flags_a_plain_http_url_too() -> None:
    """The scan is not scheme-specific to ``https``."""
    sources = {"pkg/mod.py": _url(_FAKE_HOST, scheme="http")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", _FAKE_HOST)]


def test_scan_matches_the_scheme_case_insensitively() -> None:
    sources = {"pkg/mod.py": _url(_FAKE_HOST, scheme="HTTPS")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", _FAKE_HOST)]


def test_scan_admits_the_same_host_for_that_exact_file() -> None:
    sources = {"pkg/mod.py": f"see {_url(_FAKE_HOST)} for details"}
    exemptions = {_FAKE_HOST: frozenset({"pkg/mod.py"})}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions=exemptions
    )
    assert violations == []


def test_scan_rejects_a_host_admitted_only_for_a_different_page_section() -> None:
    """A host admitted for one ``##`` section of the page must not be
    treated as admitted for a different section it is also named in."""
    sources = {
        "docs/connectors.md#Section A": _url(_FAKE_HOST),
        "docs/connectors.md#Section B": "nothing relevant here",
    }
    exemptions = {_FAKE_HOST: frozenset({"docs/connectors.md#Section B"})}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=frozenset(), exemptions=exemptions
    )
    assert violations == [("docs/connectors.md#Section A", _FAKE_HOST)]


def test_scan_treats_the_projects_own_url_as_admitted_everywhere() -> None:
    sources = {"pkg/mod.py": _url("github.com", "/joshua-stauffer/fitdocs")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == []


def test_scan_flags_a_lookalike_host_that_merely_contains_the_own_host_and_path() -> (
    None
):
    """Kills a wrong ``_is_own_url`` shaped as "hostname startswith own
    hostname and path startswith own path" (checked on the two fields
    separately, rather than the full URL as one prefix): under that wrong
    check, ``github.com.fake-vendor.net``'s hostname still starts with
    ``github.com`` and its path still starts with ``/joshua-stauffer/
    fitdocs``, so it would be wrongly admitted. The real, full-URL-prefix
    check never matches this host at all."""
    sources = {
        "pkg/mod.py": _url("github.com.fake-vendor.net", "/joshua-stauffer/fitdocs")
    }
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "github.com.fake-vendor.net")]


def test_scan_flags_a_sibling_repository_with_no_path_boundary() -> None:
    """A sibling repository whose path merely *starts with* the own prefix's
    path, with no separator in between (``.../fitdocs-other/x`` against the
    declared ``.../fitdocs``, which has no trailing slash), must still be
    flagged -- a bare ``str.startswith`` admits it wrongly."""
    sources = {"pkg/mod.py": _url("github.com", "/joshua-stauffer/fitdocs-other/x")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "github.com")]


def test_scan_does_not_admit_a_lookalike_host_sharing_only_a_hostname_substring() -> (
    None
):
    """ "Own" is a URL-prefix match, not a hostname check: a URL on a
    completely different host that merely happens to *contain* the
    project's own repo path as a substring must still be flagged."""
    sources = {"pkg/mod.py": _url("not-github.com", "/joshua-stauffer/fitdocs")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "not-github.com")]


def test_scan_requires_the_full_url_prefix_not_merely_the_same_host() -> None:
    """ "Own" means the URL starts with a declared ``[project.urls]`` value,
    not merely that it shares a host with one: a link to a different
    repository on the *same* host (``github.com``) must still be flagged,
    or a host-only comparison would wrongly admit any URL on that host."""
    sources = {"pkg/mod.py": _url("github.com", "/someone-else/other-repo")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "github.com")]


def test_scan_treats_a_reserved_example_host_as_admitted_everywhere() -> None:
    sources = {
        "pkg/mod.py": (
            f"see {_url('api.example.com', '/v1')} and {_url('localhost:8080', '/x')}"
        )
    }
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=frozenset(), exemptions={}
    )
    assert violations == []


def test_scan_does_not_treat_an_example_lookalike_host_as_reserved() -> None:
    """Leading-dot boundary: ``notexample.com`` merely *contains*
    ``example.com`` as a substring but is not a subdomain of it, so it must
    still be flagged as an unadmitted host."""
    sources = {"pkg/mod.py": _url("notexample.com")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=frozenset(), exemptions={}
    )
    assert violations == [("pkg/mod.py", "notexample.com")]


def test_conditional_control_flags_an_exemption_entry_none_of_its_files_names() -> None:
    """Named mutation target: an exemption table entry for a host that none
    of its own admitted files actually names is caught by
    :func:`_unexercised_exemptions` -- the mechanism the (currently
    zero-iteration) real conditional control above relies on."""
    bad_sources = {"pkg/mod.py": "no urls here at all"}
    bad_exemptions = {_FAKE_HOST: frozenset({"pkg/mod.py"})}
    assert _unexercised_exemptions(bad_sources, bad_exemptions) == [_FAKE_HOST]

    good_sources = {"pkg/mod.py": _url(_FAKE_HOST, "/x")}
    assert _unexercised_exemptions(good_sources, bad_exemptions) == []
