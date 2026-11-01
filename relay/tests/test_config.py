"""The configuration reader: every rule, both bound sides, no secret in an error."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from tests.test_contract import PINNED_ENVIRONMENT

from fitdocs_relay.config import (
    ConfigError,
    PostgresTarget,
    RelayConfig,
    SqliteTarget,
    load_config,
)
from fitdocs_relay.contract import ENV_PREFIX, ENVIRONMENT

URL = "FITDOCS_RELAY_DATABASE_URL"
PASSWORD = "FITDOCS_RELAY_DATABASE_PASSWORD"
PEPPER = "FITDOCS_RELAY_TOKEN_PEPPER"
HOST = "FITDOCS_RELAY_HOST"
PORT = "FITDOCS_RELAY_PORT"
FORWARDED = "FITDOCS_RELAY_FORWARDED_ALLOW_IPS"
TOKEN_LIMIT = "FITDOCS_RELAY_TOKEN_RATE_LIMIT_PER_MINUTE"
CLIENT_LIMIT = "FITDOCS_RELAY_CLIENT_RATE_LIMIT_PER_MINUTE"
GRACE = "FITDOCS_RELAY_SHUTDOWN_GRACE_SECONDS"
LEVEL = "FITDOCS_RELAY_LOG_LEVEL"
EXTENSIONS = "FITDOCS_RELAY_EXTENSIONS"

GOOD_PEPPER = "p" * 43
SECRET = "Zq9-planted-secret-value-7f3"

URL_REASON = (
    "must be a sqlite:/// or sqlite://// file path, "
    + "or a postgresql:// or postgres:// URL"
)


def env(**changes: str | None) -> dict[str, str]:
    """A valid minimal environment, with `NAME=value` overrides (None removes)."""
    base = {URL: "sqlite:///relay.db", PEPPER: GOOD_PEPPER}
    for key, value in changes.items():
        name = key if key.startswith(ENV_PREFIX) else ENV_PREFIX + key
        if value is None:
            base.pop(name, None)
        else:
            base[name] = value
    return base


def with_vars(base: Mapping[str, str], **named: str) -> dict[str, str]:
    merged = dict(base)
    merged.update(named)
    return merged


def refusal(environ: Mapping[str, str]) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        load_config(environ)
    return caught.value


# --- defaults and the happy path ------------------------------------------


def test_defaults_when_only_required_variables_are_set() -> None:
    cfg = load_config(env())
    assert cfg == RelayConfig(
        database=SqliteTarget(Path("relay.db")),
        pepper=GOOD_PEPPER.encode(),
        host="127.0.0.1",
        port=8080,
        forwarded_allow_ips=(),
        token_limit_per_minute=60,
        client_limit_per_minute=20,
        shutdown_grace_s=20,
        log_level="info",
        extensions=(),
    )


def test_every_setting_lands_in_its_own_field() -> None:
    environ = env(
        **{
            HOST: "10.1.2.3",
            PORT: "9101",
            FORWARDED: "10.0.0.1, 192.168.0.0/16",
            TOKEN_LIMIT: "301",
            CLIENT_LIMIT: "402",
            GRACE: "503",
            LEVEL: "warning",
            EXTENSIONS: "pkg.mod:ext, other:thing",
        }
    )
    cfg = load_config(environ)
    assert cfg.host == "10.1.2.3"
    assert cfg.port == 9101
    assert cfg.forwarded_allow_ips == ("10.0.0.1", "192.168.0.0/16")
    assert cfg.token_limit_per_minute == 301
    assert cfg.client_limit_per_minute == 402
    assert cfg.shutdown_grace_s == 503
    assert cfg.log_level == "warning"
    assert cfg.extensions == ("pkg.mod:ext", "other:thing")


def test_reads_the_process_environment_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [k for k in os.environ if k.startswith(ENV_PREFIX)]:
        monkeypatch.delenv(name)
    monkeypatch.setenv(URL, "sqlite:///from-process.db")
    monkeypatch.setenv(PEPPER, GOOD_PEPPER)
    monkeypatch.setenv(PORT, "9999")
    cfg = load_config()
    assert cfg.database == SqliteTarget(Path("from-process.db"))
    assert cfg.port == 9999


def test_variables_without_the_prefix_are_ignored() -> None:
    environ = env()
    environ["FITDOCS_RELAYX"] = "1"
    environ["PORT"] = "not a port"
    environ["fitdocs_relay_port"] = "also ignored"
    assert load_config(environ).port == 8080


# --- required, empty and unknown -----------------------------------------


@pytest.mark.parametrize("name", [URL, PEPPER])
def test_a_required_variable_absent_is_refused(name: str) -> None:
    error = refusal(env(**{name: None}))
    assert str(error) == f"{name}: is required"
    assert error.variable == name


@pytest.mark.parametrize(
    "name", [URL, PEPPER, PASSWORD, HOST, PORT, TOKEN_LIMIT, CLIENT_LIMIT, GRACE, LEVEL]
)
def test_an_empty_value_is_refused_where_empty_is_no_default(name: str) -> None:
    environ = env(**{URL: "postgresql://u@h/db", name: ""})
    error = refusal(environ)
    assert str(error) == f"{name}: must not be empty"
    assert error.variable == name


@pytest.mark.parametrize("name", [FORWARDED, EXTENSIONS])
def test_an_empty_list_variable_is_the_empty_list(name: str) -> None:
    cfg = load_config(env(**{name: ""}))
    field_name = "forwarded_allow_ips" if name == FORWARDED else "extensions"
    assert getattr(cfg, field_name) == ()


@pytest.mark.parametrize(
    "name",
    [
        "FITDOCS_RELAY_BOGUS",
        "FITDOCS_RELAY_",
        "FITDOCS_RELAY_TEST_POSTGRES_URL",
        "FITDOCS_RELAY_PORT2",
    ],
)
def test_an_unknown_prefixed_variable_is_refused_by_name(name: str) -> None:
    error = refusal(with_vars(env(), **{name: SECRET}))
    assert (
        str(error)
        == f"{name}: unknown variable with the reserved prefix FITDOCS_RELAY_"
    )
    assert error.variable == name
    assert SECRET not in str(error)


def test_unknown_variables_are_refused_in_a_fixed_order() -> None:
    environ = with_vars(env(), FITDOCS_RELAY_ZZZ="1", FITDOCS_RELAY_AAA="1")
    assert refusal(environ).variable == "FITDOCS_RELAY_AAA"


# --- the database URL and the separate password ---------------------------


@pytest.mark.parametrize(
    ("url", "path"),
    [
        ("sqlite:///relay.db", Path("relay.db")),
        ("sqlite:///data/sub/relay.db", Path("data/sub/relay.db")),
        ("sqlite:////var/lib/relay.db", Path("/var/lib/relay.db")),
    ],
)
def test_sqlite_urls_give_relative_and_absolute_paths(url: str, path: Path) -> None:
    target = load_config(env(**{URL: url})).database
    assert target == SqliteTarget(path)
    assert isinstance(target, SqliteTarget)
    assert target.path.is_absolute() == path.is_absolute()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///:memory:",
        "sqlite:///",
        "sqlite://",
        "sqlite://:memory:",
        "sqlite:///:memory:?cache=shared",
        "sqlite:///relay.db?mode=memory",
        "sqlite:///relay.db#frag",
        "sqlite:///file::memory:",
        "sqlite:///./:memory:",
        "sqlite:///:memory:/",
        "sqlite:///.//:memory:",
        "sqlite:///./file::memory:",
        "sqlite:///data/:memory:",
        "sqlite:///data/",
        "sqlite:///.",
        "sqlite:///./",
        "sqlite:///..",
        "sqlite:///:memory:/relay.db",
        "sqlite:///data/file:x/relay.db",
        "sqlite:///relay\x00.db",
        "sqlite://host/relay.db",
        "sqlite:",
        "mysql://u@h/db",
        "http://example.com/db",
        "postgresql",
        "postgresql:/db",
        "/var/lib/relay.db",
        "relay.db",
    ],
)
def test_unsupported_database_urls_are_refused(url: str) -> None:
    error = refusal(env(**{URL: url}))
    assert str(error) == f"{URL}: {URL_REASON}"
    assert error.variable == URL


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u@h:5432/db?sslmode=require",
        "postgres://u@h/db",
        "postgresql:///db",
        "postgresql://u:pw@h/db",
    ],
)
def test_postgres_urls_are_kept_as_given(url: str) -> None:
    target = load_config(env(**{URL: url})).database
    assert target == PostgresTarget(conninfo=url, password=None)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u@h:99999/db",
        "postgresql://u@h:abc/db",
        "postgres://u@h/db with space",
        "postgres://u@h/db\n",
        "postgres://u@h/db#frag",
        "postgresql://u@[::1/db",
    ],
)
def test_malformed_postgres_urls_are_refused(url: str) -> None:
    error = refusal(env(**{URL: url}))
    assert str(error) == f"{URL}: {URL_REASON}"


def test_the_password_variable_joins_a_postgres_url() -> None:
    target = load_config(
        env(**{URL: "postgres://u@h:5432/db", PASSWORD: SECRET})
    ).database
    assert target == PostgresTarget(conninfo="postgres://u@h:5432/db", password=SECRET)


def test_the_password_variable_is_refused_with_a_sqlite_url() -> None:
    error = refusal(env(**{PASSWORD: SECRET}))
    assert str(error) == f"{PASSWORD}: is only valid with a PostgreSQL {URL}"
    assert error.variable == PASSWORD


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:inline@h/db",
        "postgresql://u:@h/db",
        "postgresql://u@h/db?password=inline",
        "postgresql://u@h/db?sslmode=require&PASSWORD=inline",
    ],
)
def test_the_password_variable_is_refused_when_the_url_carries_a_password(
    url: str,
) -> None:
    error = refusal(env(**{URL: url, PASSWORD: SECRET}))
    assert str(error) == f"{PASSWORD}: is not allowed when {URL} carries a password"
    assert error.variable == PASSWORD


# --- pepper ---------------------------------------------------------------


def test_the_pepper_minimum_is_43_characters() -> None:
    assert load_config(env(**{PEPPER: "a" * 43})).pepper == b"a" * 43
    error = refusal(env(**{PEPPER: "a" * 42}))
    assert str(error) == f"{PEPPER}: must be at least 43 characters"
    assert error.variable == PEPPER


def test_the_pepper_minimum_counts_characters_not_bytes() -> None:
    assert load_config(env(**{PEPPER: "é" * 43})).pepper == ("é" * 43).encode("utf-8")
    assert (
        str(refusal(env(**{PEPPER: "é" * 42})))
        == f"{PEPPER}: must be at least 43 characters"
    )


# --- ranges ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "low", "high", "attr"),
    [
        (PORT, 1, 65535, "port"),
        (TOKEN_LIMIT, 1, 100000, "token_limit_per_minute"),
        (CLIENT_LIMIT, 1, 100000, "client_limit_per_minute"),
        (GRACE, 0, 600, "shutdown_grace_s"),
    ],
)
def test_integer_ranges_accept_both_bounds_and_refuse_just_outside(
    name: str, low: int, high: int, attr: str
) -> None:
    assert getattr(load_config(env(**{name: str(low)})), attr) == low
    assert getattr(load_config(env(**{name: str(high)})), attr) == high
    expected = f"{name}: must be an integer from {low} to {high}"
    for bad in (str(low - 1), str(high + 1)):
        error = refusal(env(**{name: bad}))
        assert str(error) == expected
        assert error.variable == name


@pytest.mark.parametrize("name", [PORT, TOKEN_LIMIT, CLIENT_LIMIT, GRACE])
@pytest.mark.parametrize(
    "bad", ["abc", "1.5", "+5", "-1", " 5", "5 ", "0x10", "١٢٣", "5_0"]
)
def test_integers_are_plain_ascii_digits(name: str, bad: str) -> None:
    assert refusal(env(**{name: bad})).variable == name


# --- host, forwarded addresses, log level, extensions ----------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "::1", "localhost", "relay-1.example.com"])
def test_hosts_that_are_addresses_or_names_are_accepted(host: str) -> None:
    assert load_config(env(**{HOST: host})).host == host


LONGEST_HOST = ".".join(["a" * 63] * 3 + ["a" * 61])
TOO_LONG_HOST = ".".join(["a" * 63] * 4)


def test_a_host_name_may_be_253_characters_but_not_255() -> None:
    assert len(LONGEST_HOST) == 253
    assert len(TOO_LONG_HOST) == 255
    just_over = ".".join(["a" * 63] * 3 + ["a" * 62])
    assert len(just_over) == 254
    assert refusal(env(**{HOST: just_over})).variable == HOST
    assert load_config(env(**{HOST: LONGEST_HOST})).host == LONGEST_HOST
    error = refusal(env(**{HOST: TOO_LONG_HOST}))
    assert str(error) == f"{HOST}: must be an IP address or a host name"


@pytest.mark.parametrize(
    "host", ["bad host", "-x", "a..b", "http://x", "x_y", "a" * 64]
)
def test_other_hosts_are_refused(host: str) -> None:
    error = refusal(env(**{HOST: host}))
    assert str(error) == f"{HOST}: must be an IP address or a host name"


def test_forwarded_addresses_are_split_and_stripped() -> None:
    cfg = load_config(env(**{FORWARDED: " 10.0.0.1 ,172.16.0.0/12, ::1 "}))
    assert cfg.forwarded_allow_ips == ("10.0.0.1", "172.16.0.0/12", "::1")


@pytest.mark.parametrize(
    "bad", ["*", "10.0.0.1,", ",10.0.0.1", "10.0.0.1,,::1", "proxy", "10.0.0.256"]
)
def test_bad_forwarded_addresses_are_refused(bad: str) -> None:
    error = refusal(env(**{FORWARDED: bad}))
    assert (
        str(error) == f"{FORWARDED}: must be comma-separated IP addresses or networks"
    )


@pytest.mark.parametrize("level", ["debug", "info", "warning", "error"])
def test_each_log_level_is_accepted(level: str) -> None:
    assert load_config(env(**{LEVEL: level})).log_level == level


@pytest.mark.parametrize("level", ["INFO", "trace", "warn", "critical", " info"])
def test_other_log_levels_are_refused(level: str) -> None:
    error = refusal(env(**{LEVEL: level}))
    assert str(error) == f"{LEVEL}: must be one of debug, info, warning or error"


@pytest.mark.parametrize(
    "bad",
    ["a", "a:", ":b", "a:b:c", "a-b:c", "a:b,", ",a:b", "a:b,,c:d", "1a:b", "a:1b"],
)
def test_bad_extension_references_are_refused(bad: str) -> None:
    error = refusal(env(**{EXTENSIONS: bad}))
    assert (
        str(error)
        == f"{EXTENSIONS}: must be comma-separated module:attribute references"
    )


# --- no secret reaches any error ------------------------------------------

ALL_MESSAGES = frozenset(
    {
        f"{URL}: is required",
        f"{PEPPER}: is required",
        f"{URL}: must not be empty",
        f"{PASSWORD}: must not be empty",
        f"{PEPPER}: must not be empty",
        f"{HOST}: must not be empty",
        f"{PORT}: must not be empty",
        f"{TOKEN_LIMIT}: must not be empty",
        f"{CLIENT_LIMIT}: must not be empty",
        f"{GRACE}: must not be empty",
        f"{LEVEL}: must not be empty",
        f"{URL}: {URL_REASON}",
        f"{PASSWORD}: is only valid with a PostgreSQL {URL}",
        f"{PASSWORD}: is not allowed when {URL} carries a password",
        f"{PEPPER}: must be at least 43 characters",
        f"{HOST}: must be an IP address or a host name",
        f"{PORT}: must be an integer from 1 to 65535",
        f"{TOKEN_LIMIT}: must be an integer from 1 to 100000",
        f"{CLIENT_LIMIT}: must be an integer from 1 to 100000",
        f"{GRACE}: must be an integer from 0 to 600",
        f"{FORWARDED}: must be comma-separated IP addresses or networks",
        f"{LEVEL}: must be one of debug, info, warning or error",
        f"{EXTENSIONS}: must be comma-separated module:attribute references",
    }
)

PG = "postgresql://u@h/db"
PG_WITH_SECRET = f"postgresql://u:{SECRET}@h/db"
BAD = f"not valid {SECRET}"

# Every case plants SECRET in at least one secret variable or malformed value.
SECRET_CASES: list[tuple[str, dict[str, str]]] = [
    ("url-unsupported-scheme", {URL: f"mysql://u:{SECRET}@h/db"}),
    ("url-sqlite-memory", {URL: f"sqlite:///:memory:?{SECRET}"}),
    ("url-sqlite-query", {URL: f"sqlite:///{SECRET}.db?mode=memory"}),
    ("url-bad-port", {URL: f"postgresql://u:{SECRET}@h:abc/db"}),
    ("url-whitespace", {URL: f"postgresql://u:{SECRET}@h/d b"}),
    ("password-with-sqlite", {PASSWORD: SECRET}),
    ("password-url-carries", {URL: PG_WITH_SECRET, PASSWORD: SECRET}),
    ("password-query-carries", {URL: f"{PG}?password={SECRET}", PASSWORD: SECRET}),
    ("password-empty-with-url-secret", {URL: PG_WITH_SECRET, PASSWORD: ""}),
    ("pepper-short", {PEPPER: SECRET}),
    ("pepper-empty-with-secret-url", {URL: PG_WITH_SECRET, PEPPER: ""}),
    ("url-secret-port-bad", {URL: PG_WITH_SECRET, PORT: BAD}),
    ("url-secret-host-bad", {URL: PG_WITH_SECRET, HOST: BAD}),
    ("url-secret-token-limit-bad", {URL: PG_WITH_SECRET, TOKEN_LIMIT: BAD}),
    ("url-secret-client-limit-bad", {URL: PG_WITH_SECRET, CLIENT_LIMIT: BAD}),
    ("url-secret-grace-bad", {URL: PG_WITH_SECRET, GRACE: BAD}),
    ("url-secret-forwarded-bad", {URL: PG_WITH_SECRET, FORWARDED: BAD}),
    ("url-secret-level-bad", {URL: PG_WITH_SECRET, LEVEL: BAD}),
    ("url-secret-extensions-bad", {URL: PG_WITH_SECRET, EXTENSIONS: BAD}),
    ("pepper-secret-port-bad", {PEPPER: SECRET + "x" * 43, PORT: BAD}),
    ("pepper-secret-level-bad", {PEPPER: SECRET + "x" * 43, LEVEL: BAD}),
    ("password-secret-port-bad", {URL: PG, PASSWORD: SECRET, PORT: BAD}),
    ("password-secret-pepper-short", {URL: PG, PASSWORD: SECRET, PEPPER: "short"}),
    ("password-secret-url-missing", {URL: "", PASSWORD: SECRET}),
]


@pytest.mark.parametrize(
    ("label", "changes"), SECRET_CASES, ids=[c[0] for c in SECRET_CASES]
)
def test_no_error_prints_a_planted_secret(label: str, changes: dict[str, str]) -> None:
    environ = env()
    environ.update(changes)
    assert any(SECRET in value for value in environ.values()), label
    error = refusal(environ)
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in repr(error.args)
    assert SECRET not in error.variable
    assert str(error) in ALL_MESSAGES
    assert str(error).startswith(error.variable + ": ")


def test_the_secret_cases_exercise_every_variable_of_the_table() -> None:
    named = set()
    for _, changes in SECRET_CASES:
        environ = env()
        environ.update(changes)
        named.add(refusal(environ).variable)
    assert named == {var.name for var in ENVIRONMENT}


def test_the_loaded_configuration_hides_its_secrets_in_repr() -> None:
    environ = env(
        **{URL: "postgresql://u@h/db", PASSWORD: SECRET, PEPPER: SECRET + "x" * 43}
    )
    cfg = load_config(environ)
    assert isinstance(cfg.database, PostgresTarget)
    assert cfg.database.password == SECRET
    assert cfg.pepper.startswith(SECRET.encode())
    text = repr(cfg)
    assert SECRET not in text
    assert "postgresql://u@h/db" not in text
    assert "Zq9" not in text


# --- the table the reader is bound to ---------------------------------------


def test_the_names_used_here_are_the_pinned_tables_variables() -> None:
    # The table itself, meanings included, is pinned once, in test_contract.py.
    used = [
        URL,
        PASSWORD,
        PEPPER,
        HOST,
        PORT,
        FORWARDED,
        TOKEN_LIMIT,
        CLIENT_LIMIT,
        GRACE,
        LEVEL,
        EXTENSIONS,
    ]
    assert used == [row[0] for row in PINNED_ENVIRONMENT]
    assert [(v.name, v.required, v.default, v.secret) for v in ENVIRONMENT] == [
        row[:4] for row in PINNED_ENVIRONMENT
    ]
