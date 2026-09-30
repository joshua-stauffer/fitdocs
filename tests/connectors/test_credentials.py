"""Pins for the credential store: location order, refusal, modes, resolution.

Every location-order test builds its own ``environ`` mapping and ``home``
path and calls :func:`resolve_credentials_dir` directly -- it does not rely
on the autouse ``FITDOCS_CREDENTIALS_DIR``/``HOME`` isolation from
``conftest.py``, since the function under test takes both as explicit
arguments. The mode tests set a deliberately permissive ``os.umask`` before
calling :meth:`CredentialStore.save` so a mode that merely inherits from
``mkdir``/``open`` defaults (rather than being forced with ``os.chmod``)
would leave extra bits set and fail the pin.
"""

from __future__ import annotations

import os
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
import tomli_w

from fitdocs.connectors.credentials import (
    CredentialsLocationError,
    CredentialStore,
    CredentialStoreError,
    StoredCredentials,
    check_outside_data_root,
    env_var_name,
    resolve_credentials,
    resolve_credentials_dir,
)
from fitdocs.connectors.errors import ConnectorError, NotConnectedError
from fitdocs.connectors.protocol import AuthStyle, Capability, CredentialField, TokenSet
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret


@dataclass(frozen=True)
class _FakeConnector:
    connector_id: str
    auth_style: AuthStyle
    credential_fields: tuple[CredentialField, ...] = ()
    display_name: str = "Fake"
    capabilities: frozenset[Capability] = field(default_factory=frozenset)

    def parse_settings(self, table: Mapping[str, object], context: object) -> object:
        return None


def _stored(
    *,
    connector_id: str = "fake",
    auth_style: AuthStyle = AuthStyle.API_KEY,
    values: Mapping[str, str] | None = None,
    expires_at: datetime | None = None,
    scopes: tuple[str, ...] | None = None,
) -> StoredCredentials:
    return StoredCredentials(
        connector_id=connector_id,
        auth_style=auth_style,
        values={k: Secret(v) for k, v in (values or {}).items()},
        expires_at=expires_at,
        scopes=scopes,
    )


def _write_raw_document(
    directory: Path, instance: str, document: Mapping[str, object]
) -> Path:
    """Write ``document`` as raw TOML, owner-only, bypassing ``CredentialStore.save``."""  # noqa: E501
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory / f"{instance}.toml"
    path.write_bytes(tomli_w.dumps(dict(document)).encode("utf-8"))
    os.chmod(path, 0o600)
    return path


def _valid_raw_document(**overrides: object) -> dict[str, object]:
    """A minimal otherwise-valid document, one field overridable per case."""
    document: dict[str, object] = {
        "credentials_version": 1,
        "connector": "fake",
        "auth_style": "api-key",
        "values": {"api_key": "x"},
    }
    document.update(overrides)
    return document


# Each entry is a document that violates exactly one shape rule; every case
# is otherwise valid (a 0o600 file with the other three required keys
# present and well-typed) so the parametrized test below isolates the one
# violation. `missing_connector` is the only case that removes a key instead
# of overriding it.
MALFORMED_SHAPE_CASES: dict[str, dict[str, object]] = {
    "missing_connector": {
        k: v for k, v in _valid_raw_document().items() if k != "connector"
    },
    "version_true": _valid_raw_document(credentials_version=True),
    "version_zero": _valid_raw_document(credentials_version=0),
    "connector_int": _valid_raw_document(connector=5),
    "auth_style_bogus": _valid_raw_document(auth_style="bogus"),
    "values_string": _valid_raw_document(values="x"),
    "values_api_key_int": _valid_raw_document(values={"api_key": 918273645}),
    "scopes_int_list": _valid_raw_document(scopes=[1]),
    "expires_at_string": _valid_raw_document(expires_at="soon"),
}


# --- Location order (4.1) ------------------------------------------------


def test_dedicated_env_var_wins_when_absolute(tmp_path: Path) -> None:
    dedicated = tmp_path / "dedicated-creds"
    environ = {
        "FITDOCS_CREDENTIALS_DIR": str(dedicated),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }
    result = resolve_credentials_dir(environ, home=tmp_path / "home")
    assert result == dedicated


def test_dedicated_env_var_relative_raises_location_error(tmp_path: Path) -> None:
    environ = {"FITDOCS_CREDENTIALS_DIR": "relative/creds"}
    with pytest.raises(CredentialsLocationError):
        resolve_credentials_dir(environ, home=tmp_path / "home")


def test_dedicated_env_var_unset_falls_back_to_xdg(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg-home"
    environ = {"XDG_CONFIG_HOME": str(xdg)}
    result = resolve_credentials_dir(environ, home=tmp_path / "home")
    assert result == xdg / "fitdocs" / "credentials"


def test_dedicated_env_var_empty_string_falls_back_to_xdg(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg-home"
    environ = {"FITDOCS_CREDENTIALS_DIR": "", "XDG_CONFIG_HOME": str(xdg)}
    result = resolve_credentials_dir(environ, home=tmp_path / "home")
    assert result == xdg / "fitdocs" / "credentials"


def test_xdg_relative_falls_back_to_home_default_not_an_error(tmp_path: Path) -> None:
    home = tmp_path / "home"
    environ = {"XDG_CONFIG_HOME": "relative/xdg"}
    result = resolve_credentials_dir(environ, home=home)
    assert result == home / ".config" / "fitdocs" / "credentials"


def test_xdg_unset_falls_back_to_home_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = resolve_credentials_dir({}, home=home)
    assert result == home / ".config" / "fitdocs" / "credentials"


def test_xdg_empty_string_falls_back_to_home_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    environ = {"XDG_CONFIG_HOME": ""}
    result = resolve_credentials_dir(environ, home=home)
    assert result == home / ".config" / "fitdocs" / "credentials"


def test_all_three_locations_are_mutually_distinct(tmp_path: Path) -> None:
    # A sweep in one test: each branch of the order produces a path distinct
    # from the other two, so no branch could be silently substituting for
    # another and passing by coincidence.
    home = tmp_path / "home"
    dedicated = resolve_credentials_dir(
        {"FITDOCS_CREDENTIALS_DIR": str(tmp_path / "d")}, home
    )
    xdg = resolve_credentials_dir({"XDG_CONFIG_HOME": str(tmp_path / "x")}, home)
    default = resolve_credentials_dir({}, home)
    assert len({dedicated, xdg, default}) == 3


# --- Data-root refusal (4.2) ----------------------------------------------


def test_credentials_dir_equal_to_data_root_is_refused(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    with pytest.raises(CredentialsLocationError):
        check_outside_data_root(data_root, data_root)


def test_credentials_dir_inside_data_root_is_refused(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    nested = data_root / ".fitdocs" / "credentials"
    with pytest.raises(CredentialsLocationError):
        check_outside_data_root(nested, data_root)


def test_credentials_dir_outside_data_root_is_accepted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    outside = tmp_path / "elsewhere" / "credentials"
    check_outside_data_root(outside, data_root)  # must not raise


def test_credentials_dir_sibling_with_shared_prefix_is_accepted(tmp_path: Path) -> None:
    # Defeats a naive string-prefix check: "root-other" starts with "root"
    # but is not inside it.
    data_root = tmp_path / "root"
    data_root.mkdir()
    sibling = tmp_path / "root-other" / "credentials"
    check_outside_data_root(sibling, data_root)  # must not raise


def test_data_root_refusal_names_the_directory(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    nested = data_root / "creds"
    with pytest.raises(CredentialsLocationError) as excinfo:
        check_outside_data_root(nested, data_root)
    assert str(nested.resolve()) in str(excinfo.value)


def test_credentials_dir_inside_data_root_reached_through_a_symlink_is_refused(
    tmp_path: Path,
) -> None:
    # The credentials directory is given via a symlinked path whose string
    # form shares no prefix with the (real, unsymlinked) data root -- a
    # naive string or unresolved-path comparison would accept this as
    # "outside", but the symlink physically resolves to inside the data
    # root and must be refused.
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    link_root = tmp_path / "link-root"
    link_root.symlink_to(real_root)
    nested_via_symlink = link_root / "creds"
    assert not str(nested_via_symlink).startswith(str(real_root))
    with pytest.raises(CredentialsLocationError):
        check_outside_data_root(nested_via_symlink, real_root)


def test_data_root_given_as_a_symlink_is_still_resolved_for_containment(
    tmp_path: Path,
) -> None:
    # Mirror of the test above with the symlink on the *other* argument: the
    # credentials directory is already a real (unsymlinked) path, and only
    # ``data_root`` needs resolving for the containment check to see they are
    # the same directory. A check that resolves ``directory`` but not
    # ``data_root`` would miss exactly this case; the test above covers the
    # other direction.
    real_root = tmp_path / "real-root2"
    real_root.mkdir()
    link_root = tmp_path / "link-root2"
    link_root.symlink_to(real_root)
    nested = real_root / "creds"
    assert not str(nested).startswith(str(link_root))
    with pytest.raises(CredentialsLocationError):
        check_outside_data_root(nested, link_root)


def test_relative_arguments_are_resolved_against_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "root3"
    (data_root / "sub").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CredentialsLocationError):
        check_outside_data_root(Path("root3") / "sub", Path("root3"))


# --- env_var_name (4.5) ----------------------------------------------------


def test_env_var_name_shape() -> None:
    assert (
        env_var_name("my-service", "api_key") == "FITDOCS_CONNECTOR_MY_SERVICE_API_KEY"
    )


def test_env_var_name_varies_with_both_instance_and_field() -> None:
    # Confounded-fixture guard: instance and field must each independently
    # affect the output, not just one of them.
    base = env_var_name("alpha", "token")
    diff_instance = env_var_name("beta", "token")
    diff_field = env_var_name("alpha", "secret")
    assert base != diff_instance
    assert base != diff_field
    assert diff_instance != diff_field


# --- Save/load modes and atomicity (4.3, 4.4) ------------------------------


def test_save_creates_missing_directory_owner_only_under_permissive_umask(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "creds"
    store = CredentialStore(directory)
    old_umask = os.umask(0o000)
    try:
        store.save("inst", _stored())
    finally:
        os.umask(old_umask)
    mode = stat.S_IMODE(directory.stat().st_mode)
    assert mode == 0o700


def test_save_leaves_an_existing_directorys_mode_unchanged(tmp_path: Path) -> None:
    # (R1) save() creates the directory owner-only only when it is missing;
    # an existing directory's mode -- even one a user deliberately shared --
    # is never repaired on every save.
    directory = tmp_path / "creds"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o755)
    store = CredentialStore(directory)
    store.save("inst", _stored())
    mode = stat.S_IMODE(directory.stat().st_mode)
    assert mode == 0o755


def test_save_writes_file_owner_only_under_permissive_umask(tmp_path: Path) -> None:
    directory = tmp_path / "creds"
    store = CredentialStore(directory)
    old_umask = os.umask(0o000)
    try:
        path = store.save("inst", _stored())
    finally:
        os.umask(old_umask)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_load_absent_file_returns_none(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    assert store.load("nope") is None


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o620, 0o602])
def test_load_refuses_any_group_or_other_accessible_mode(
    tmp_path: Path, mode: int
) -> None:
    # 0o640/0o604 isolate read-only group/other bits; 0o620/0o602 isolate
    # write-only group/other bits -- a check that only looks at read bits
    # (or only at "other", ignoring "group") passes some of these by
    # mistake while still catching 0o644.
    directory = tmp_path / "creds"
    store = CredentialStore(directory)
    store.save("inst", _stored())
    path = store.path_for("inst")
    os.chmod(path, mode)
    with pytest.raises(CredentialStoreError) as excinfo:
        store.load("inst")
    message = str(excinfo.value)
    assert "chmod 600" in message
    assert str(path) in message


def test_load_accepts_strict_owner_only_file(tmp_path: Path) -> None:
    directory = tmp_path / "creds"
    store = CredentialStore(directory)
    store.save("inst", _stored(values={"api_key": "abc123"}))
    loaded = store.load("inst")
    assert loaded is not None
    assert loaded.values["api_key"].reveal() == "abc123"


def test_save_then_load_round_trips_all_fields(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    expires_at = datetime(2026, 10, 1, tzinfo=UTC)
    stored = _stored(
        connector_id="intervals",
        auth_style=AuthStyle.LOGIN,
        values={"access_token": "tok-1", "refresh_token": "tok-2"},
        expires_at=expires_at,
        scopes=("ACTIVITY:READ",),
    )
    store.save("inst", stored)
    loaded = store.load("inst")
    assert loaded is not None
    assert loaded.connector_id == "intervals"
    assert loaded.auth_style is AuthStyle.LOGIN
    assert loaded.values["access_token"].reveal() == "tok-1"
    assert loaded.values["refresh_token"].reveal() == "tok-2"
    assert loaded.expires_at == expires_at
    assert loaded.scopes == ("ACTIVITY:READ",)


def test_absent_scopes_stay_absent_not_empty_tuple(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(scopes=None))
    loaded = store.load("inst")
    assert loaded is not None
    assert loaded.scopes is None


def test_saved_empty_scopes_round_trip_as_an_empty_tuple_not_none(
    tmp_path: Path,
) -> None:
    # None and () are distinct: None means "the service reported no scopes
    # at all", () means "the service reported an explicit, empty grant". A
    # writer that omits an empty tuple the same way it omits None, or a
    # reader that treats an empty list the same as an absent key, collapses
    # that distinction.
    store = CredentialStore(tmp_path / "creds")
    path = store.save("inst", _stored(values={"api_key": "x"}, scopes=()))
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    assert raw["scopes"] == []
    loaded = store.load("inst")
    assert loaded is not None
    assert loaded.scopes == ()


def test_absent_expires_at_stays_none(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(expires_at=None))
    loaded = store.load("inst")
    assert loaded is not None
    assert loaded.expires_at is None


def test_load_refuses_newer_credentials_version(tmp_path: Path) -> None:
    # The literal 2 (design's next version), not `CREDENTIALS_VERSION + 1`:
    # a self-referential fixture would silently track a change to the
    # constant instead of pinning the design's actual literal 1.
    directory = tmp_path / "creds"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o700)
    path = directory / "inst.toml"
    document = {
        "credentials_version": 2,
        "connector": "fake",
        "auth_style": "api-key",
        "values": {},
    }
    path.write_bytes(tomli_w.dumps(document).encode("utf-8"))
    os.chmod(path, 0o600)
    with pytest.raises(CredentialStoreError) as excinfo:
        CredentialStore(directory).load("inst")
    message = str(excinfo.value)
    # Strip the leading path before checking for "newer": pytest's own
    # per-test tmp_path directory name embeds this test's function name,
    # which itself contains the substring "newer" -- checking the whole
    # message would pass even if the code's own wording never said it.
    assert message.startswith(str(path))
    detail = message.removeprefix(str(path))
    assert "newer" in detail


def test_load_refuses_malformed_toml(tmp_path: Path) -> None:
    directory = tmp_path / "creds"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o700)
    path = directory / "inst.toml"
    path.write_bytes(b"this is not [ valid toml")
    os.chmod(path, 0o600)
    with pytest.raises(CredentialStoreError):
        CredentialStore(directory).load("inst")


@pytest.mark.parametrize("case", sorted(MALFORMED_SHAPE_CASES))
def test_load_refuses_every_malformed_shape_with_credentialstoreerror(
    tmp_path: Path, case: str
) -> None:
    # Each case is a document that violates exactly one shape rule; the
    # production code must convert every one of them to CredentialStoreError
    # -- never let a raw KeyError/ValueError/AttributeError/TypeError leak
    # out of tomllib's permissive parsing or a downstream Secret()/AuthStyle()
    # constructor.
    directory = tmp_path / "creds"
    path = _write_raw_document(directory, "inst", MALFORMED_SHAPE_CASES[case])
    with pytest.raises(CredentialStoreError) as excinfo:
        CredentialStore(directory).load("inst")
    assert str(path) in str(excinfo.value)


def test_load_refuses_a_credentials_file_that_is_actually_a_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "creds"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o700)
    path = directory / "inst.toml"
    path.mkdir()
    os.chmod(path, 0o700)
    with pytest.raises(CredentialStoreError):
        CredentialStore(directory).load("inst")


def test_load_malformed_value_error_does_not_leak_the_value(tmp_path: Path) -> None:
    directory = tmp_path / "creds"
    _write_raw_document(
        directory, "inst", _valid_raw_document(values={"api_key": 918273645})
    )
    with pytest.raises(CredentialStoreError) as excinfo:
        CredentialStore(directory).load("inst")
    assert "918273645" not in str(excinfo.value)


def test_load_malformed_toml_error_does_not_leak_file_contents(tmp_path: Path) -> None:
    directory = tmp_path / "creds"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o700)
    path = directory / "inst.toml"
    secret_looking_value = "sk_live_super_secret_value_12345"
    path.write_bytes(f"this is not [ valid toml {secret_looking_value}".encode())
    os.chmod(path, 0o600)
    with pytest.raises(CredentialStoreError) as excinfo:
        CredentialStore(directory).load("inst")
    assert secret_looking_value not in str(excinfo.value)


def test_save_refuses_timezone_naive_expires_at(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    naive = datetime(2026, 10, 1)  # noqa: DTZ001 -- deliberately naive
    with pytest.raises(CredentialStoreError):
        store.save("inst", _stored(expires_at=naive))


def test_save_refusing_a_naive_expires_at_leaves_an_existing_file_untouched(
    tmp_path: Path,
) -> None:
    # (R2d) The check must happen before any write: save a valid credential
    # first, then attempt a naive-``expires_at`` save for the same instance,
    # and confirm the file on disk is byte-for-byte the original -- a check
    # that ran only after ``write_atomic`` would have already replaced it.
    store = CredentialStore(tmp_path / "creds")
    path = store.save("inst", _stored(values={"api_key": "original-value"}))
    before = path.read_bytes()
    naive = datetime(2026, 10, 1)  # noqa: DTZ001 -- deliberately naive
    with pytest.raises(CredentialStoreError):
        store.save("inst", _stored(values={"api_key": "new-value"}, expires_at=naive))
    after = path.read_bytes()
    assert after == before


def test_load_refuses_timezone_naive_expires_at_naming_the_file(tmp_path: Path) -> None:
    directory = tmp_path / "creds"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o700)
    path = directory / "inst.toml"
    document = {
        "credentials_version": 1,
        "connector": "fake",
        "auth_style": "api-key",
        "expires_at": datetime(2026, 10, 1),  # naive, no offset written
        "values": {},
    }
    path.write_bytes(tomli_w.dumps(document).encode("utf-8"))
    os.chmod(path, 0o600)
    with pytest.raises(CredentialStoreError) as excinfo:
        CredentialStore(directory).load("inst")
    assert str(path) in str(excinfo.value)


def test_saved_file_matches_the_design_literal_toml_shape(tmp_path: Path) -> None:
    # Parses the raw file with tomllib and compares to design.md's literal
    # shape directly -- bypassing this module's own load() so a mutation
    # that renames a key or changes an enum's serialized form the same way
    # on both sides (round-tripping through our own read/write) cannot hide.
    store = CredentialStore(tmp_path / "creds")
    expires_at = datetime(2026, 10, 1, tzinfo=UTC)
    stored = _stored(
        connector_id="intervals",
        auth_style=AuthStyle.API_KEY,
        values={"api_key": "abc123"},
        expires_at=expires_at,
        scopes=("ACTIVITY:READ",),
    )
    path = store.save("inst", stored)
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    assert raw == {
        "credentials_version": 1,
        "connector": "intervals",
        "auth_style": "api-key",
        "scopes": ["ACTIVITY:READ"],
        "expires_at": expires_at,
        "values": {"api_key": "abc123"},
    }


def test_saved_file_omits_scopes_and_expires_at_keys_when_absent(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    stored = _stored(values={"api_key": "abc123"}, scopes=None, expires_at=None)
    path = store.save("inst", stored)
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    assert "scopes" not in raw
    assert "expires_at" not in raw


def test_save_writes_file_atomically_via_dot_prefixed_tempfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    seen_prefixes: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def _spy_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,  # noqa: A002
        text: bool = False,
    ) -> tuple[int, str]:
        assert isinstance(prefix, str)
        seen_prefixes.append(prefix)
        return real_mkstemp(suffix=suffix, prefix=prefix, dir=dir, text=text)

    monkeypatch.setattr(tempfile, "mkstemp", _spy_mkstemp)
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored())
    assert len(seen_prefixes) == 1
    assert seen_prefixes[0].startswith(".inst-")


# --- resolve_credentials (4.5, 4.6, 4.7, 4.8, 4.9) -------------------------


def test_none_style_access_raises_for_any_field(tmp_path: Path) -> None:
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.NONE)
    access = resolve_credentials("inst", connector, None, {}, Redactor())
    with pytest.raises(ConnectorError):
        access.value("anything")
    assert access.scopes is None
    assert access.expires_at is None


def test_reserved_oauth_browser_style_is_not_connected_not_no_auth(
    tmp_path: Path,
) -> None:
    # (Controller ruling) OAUTH_BROWSER is reserved: resolving it must raise
    # NotConnectedError, never silently resolve like NONE (which has no
    # values at all but is a *supported*, intentional style).
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.OAUTH_BROWSER)
    with pytest.raises(NotConnectedError):
        resolve_credentials("inst", connector, None, {}, Redactor())


def test_api_key_environment_beats_store_when_both_set_and_differ(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(values={"api_key": "stored-value"}))
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    environ = {"FITDOCS_CONNECTOR_INST_API_KEY": "env-value"}
    access = resolve_credentials("inst", connector, store, environ, Redactor())
    assert access.value("api_key").reveal() == "env-value"


def test_api_key_falls_back_to_store_when_env_unset(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(values={"api_key": "stored-value"}))
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    assert access.value("api_key").reveal() == "stored-value"


def test_api_key_env_var_satisfies_field_even_with_no_store(tmp_path: Path) -> None:
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    environ = {"FITDOCS_CONNECTOR_INST_API_KEY": "env-only"}
    access = resolve_credentials("inst", connector, None, environ, Redactor())
    assert access.value("api_key").reveal() == "env-only"


def test_api_key_missing_field_raises_not_connected_naming_command_and_variable(
    tmp_path: Path,
) -> None:
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    with pytest.raises(NotConnectedError) as excinfo:
        resolve_credentials("inst", connector, None, {}, Redactor())
    message = str(excinfo.value)
    assert "fitdocs connect inst" in message
    assert "FITDOCS_CONNECTOR_INST_API_KEY" in message


def test_api_key_multiple_missing_fields_names_every_variable(tmp_path: Path) -> None:
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
            CredentialField(name="api_secret", label="API secret", secret=True),
        ),
    )
    with pytest.raises(NotConnectedError) as excinfo:
        resolve_credentials("inst", connector, None, {}, Redactor())
    message = str(excinfo.value)
    assert "FITDOCS_CONNECTOR_INST_API_KEY" in message
    assert "FITDOCS_CONNECTOR_INST_API_SECRET" in message


def test_api_key_env_var_set_to_empty_string_falls_back_to_store(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(values={"api_key": "stored-value"}))
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    environ = {"FITDOCS_CONNECTOR_INST_API_KEY": ""}
    access = resolve_credentials("inst", connector, store, environ, Redactor())
    assert access.value("api_key").reveal() == "stored-value"


def test_api_key_env_var_set_to_empty_string_with_no_store_is_not_connected(
    tmp_path: Path,
) -> None:
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    environ = {"FITDOCS_CONNECTOR_INST_API_KEY": ""}
    with pytest.raises(NotConnectedError):
        resolve_credentials("inst", connector, None, environ, Redactor())


def test_api_key_env_sourced_value_is_registered_with_the_redactor(
    tmp_path: Path,
) -> None:
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    environ = {"FITDOCS_CONNECTOR_INST_API_KEY": "env-secret-value"}
    redactor = Redactor()
    resolve_credentials("inst", connector, None, environ, redactor)
    assert (
        redactor.redact("prefix env-secret-value suffix") == f"prefix {REDACTED} suffix"
    )


def test_login_style_stored_token_is_registered_with_the_redactor(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst",
        _stored(
            auth_style=AuthStyle.LOGIN, values={"access_token": "login-secret-value"}
        ),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    redactor = Redactor()
    resolve_credentials("inst", connector, store, {}, redactor)
    assert (
        redactor.redact("prefix login-secret-value suffix")
        == f"prefix {REDACTED} suffix"
    )


def test_api_key_resolved_access_preserves_stored_scopes_and_expiry(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    expires_at = datetime(2026, 10, 1, tzinfo=UTC)
    store.save(
        "inst",
        _stored(
            values={"api_key": "x"}, scopes=("ACTIVITY:READ",), expires_at=expires_at
        ),
    )
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    assert access.scopes == ("ACTIVITY:READ",)
    assert access.expires_at == expires_at


def test_login_style_ignores_environment_override(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst",
        _stored(auth_style=AuthStyle.LOGIN, values={"access_token": "stored-token"}),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    environ = {"FITDOCS_CONNECTOR_INST_ACCESS_TOKEN": "should-be-ignored"}
    access = resolve_credentials("inst", connector, store, environ, Redactor())
    assert access.value("access_token").reveal() == "stored-token"


def test_login_resolved_access_preserves_stored_scopes_and_expiry(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    expires_at = datetime(2026, 10, 1, tzinfo=UTC)
    store.save(
        "inst",
        _stored(
            auth_style=AuthStyle.LOGIN,
            values={"access_token": "x"},
            scopes=("ACTIVITY:READ",),
            expires_at=expires_at,
        ),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    assert access.scopes == ("ACTIVITY:READ",)
    assert access.expires_at == expires_at


def test_login_style_with_no_store_is_not_connected(tmp_path: Path) -> None:
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    with pytest.raises(NotConnectedError) as excinfo:
        resolve_credentials("inst", connector, None, {}, Redactor())
    assert "fitdocs connect inst" in str(excinfo.value)


def test_login_style_with_no_stored_file_is_not_connected(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    with pytest.raises(NotConnectedError) as excinfo:
        resolve_credentials("inst", connector, store, {}, Redactor())
    assert "fitdocs connect inst" in str(excinfo.value)


def test_login_style_replace_persists_new_token_set_before_returning(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst",
        _stored(auth_style=AuthStyle.LOGIN, values={"access_token": "old-token"}),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    new_tokens = TokenSet(
        values={"access_token": Secret("new-token")},
        expires_at=None,
        scopes=None,
    )
    access.replace(new_tokens)
    on_disk = store.load("inst")
    assert on_disk is not None
    assert on_disk.values["access_token"].reveal() == "new-token"


def test_login_style_replace_updates_the_live_access_object_too(tmp_path: Path) -> None:
    # Persisting to disk is not enough: the same access object's own
    # value()/expires_at/scopes must reflect the new token set immediately,
    # without a fresh resolve_credentials() call. Every fixture differs from
    # its "old" counterpart so a mutation that skips the in-memory update
    # cannot coincidentally match.
    store = CredentialStore(tmp_path / "creds")
    old_expires_at = datetime(2026, 1, 1, tzinfo=UTC)
    store.save(
        "inst",
        _stored(
            auth_style=AuthStyle.LOGIN,
            values={"access_token": "old-token"},
            scopes=("OLD:SCOPE",),
            expires_at=old_expires_at,
        ),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    new_expires_at = datetime(2026, 12, 31, tzinfo=UTC)
    new_tokens = TokenSet(
        values={"access_token": Secret("new-token")},
        expires_at=new_expires_at,
        scopes=("NEW:SCOPE",),
    )
    access.replace(new_tokens)
    assert access.value("access_token").reveal() == "new-token"
    assert access.expires_at == new_expires_at
    assert access.scopes == ("NEW:SCOPE",)
    # And the record on disk is the whole new set, still issued for this
    # connector in this style, so the next resolve reads it back.
    on_disk = store.load("inst")
    assert on_disk is not None
    assert on_disk.connector_id == "fake"
    assert on_disk.auth_style is AuthStyle.LOGIN
    assert on_disk.expires_at == new_expires_at
    assert on_disk.scopes == ("NEW:SCOPE",)
    fresh = resolve_credentials("inst", connector, store, {}, Redactor())
    assert fresh.value("access_token").reveal() == "new-token"


def test_login_resolved_access_missing_field_raises_not_connected(
    tmp_path: Path,
) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst", _stored(auth_style=AuthStyle.LOGIN, values={"access_token": "x"})
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    with pytest.raises(NotConnectedError):
        access.value("absent_field")


def test_login_style_replace_never_persists_a_field_not_in_the_new_token_set(
    tmp_path: Path,
) -> None:
    # A login-style store must never hold the typed answers (e.g. a
    # "password" field): after replace(), only the fields the service
    # issued this time are on disk.
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst",
        _stored(
            auth_style=AuthStyle.LOGIN,
            values={"access_token": "old-token", "password": "typed-secret"},
        ),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    new_tokens = TokenSet(
        values={"access_token": Secret("new-token")}, expires_at=None, scopes=None
    )
    access.replace(new_tokens)
    on_disk = store.load("inst")
    assert on_disk is not None
    assert set(on_disk.values.keys()) == {"access_token"}
    assert "password" not in on_disk.values


def test_foreign_connector_id_is_not_connected_for_api_key(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(connector_id="other-connector", values={"api_key": "x"}))
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    with pytest.raises(NotConnectedError) as excinfo:
        resolve_credentials("inst", connector, store, {}, Redactor())
    message = str(excinfo.value)
    assert "other-connector" in message
    assert "fake" in message
    assert "fitdocs connect inst" in message


def test_foreign_connector_id_is_not_connected_for_login(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst",
        _stored(
            connector_id="other-connector",
            auth_style=AuthStyle.LOGIN,
            values={"access_token": "x"},
        ),
    )
    connector = _FakeConnector(connector_id="fake", auth_style=AuthStyle.LOGIN)
    with pytest.raises(NotConnectedError) as excinfo:
        resolve_credentials("inst", connector, store, {}, Redactor())
    message = str(excinfo.value)
    assert "other-connector" in message
    assert "fake" in message
    assert "fitdocs connect inst" in message


def test_resolved_values_are_registered_with_the_redactor(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save("inst", _stored(values={"api_key": "very-secret-value"}))
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    redactor = Redactor()
    resolve_credentials("inst", connector, store, {}, redactor)
    assert (
        redactor.redact("prefix very-secret-value suffix")
        == f"prefix {REDACTED} suffix"
    )


def test_absent_scopes_in_resolved_credentials_stay_absent(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    store.save(
        "inst",
        _stored(values={"api_key": "x"}, scopes=None),
    )
    connector = _FakeConnector(
        connector_id="fake",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField(name="api_key", label="API key", secret=True),
        ),
    )
    access = resolve_credentials("inst", connector, store, {}, Redactor())
    assert access.scopes is None
