"""The targets and Strava configuration: every refusal, no secret in any error."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from tests.test_config import SECRET_CASES
from tests.test_config import env as base_env

from fitdocs_relay.config import ConfigError, RelayConfig, load_config
from fitdocs_relay.contract import ENVIRONMENT
from fitdocs_relay.strava.config import (
    STRAVA_VARIABLES,
    TARGETS_VARIABLES,
    Limits,
)

P = "FITDOCS_RELAY_"
URL = P + "DATABASE_URL"
PEPPER = P + "TOKEN_PEPPER"
PUBLIC_URL = P + "PUBLIC_URL"
KEYS = P + "ENCRYPTION_KEYS"
OPERATOR = P + "OPERATOR_NAME"
CONTACT = P + "SUPPORT_CONTACT"
POLICY = P + "PRIVACY_POLICY_URL"
TERMS = P + "TERMS_URL"
CLIENT_ID = P + "STRAVA_CLIENT_ID"
CLIENT_SECRET = P + "STRAVA_CLIENT_SECRET"
WEBHOOK = P + "STRAVA_WEBHOOK_TOKEN"
API_URL = P + "STRAVA_API_URL"
OAUTH_URL = P + "STRAVA_OAUTH_URL"
WEB_URL = P + "STRAVA_WEB_URL"
RATE = P + "STRAVA_RATE_LIMIT"
READ_RATE = P + "STRAVA_READ_RATE_LIMIT"

SECRET = "Zq9-planted-secret-value-7f3"
KEY_ONE = "k1:" + "A" * 43
KEY_TWO = "k2:" + "B" * 42 + "E"
TOKEN = "t" * 40

BASE = {URL: "sqlite:///relay.db", PEPPER: "p" * 43}
STRAVA = {
    CLIENT_ID: "12345",
    CLIENT_SECRET: "c" * 40,
    WEBHOOK: TOKEN,
    PUBLIC_URL: "https://relay.example.org",
    KEYS: KEY_ONE,
    OPERATOR: "Example Operator",
    CONTACT: "help@example.org",
}


def env(
    changes: Mapping[str, str] | None = None, *, without: tuple[str, ...] = ()
) -> dict[str, str]:
    """A valid Strava-enabled environment, with `changes` applied and the
    `without` names removed."""
    merged = {**BASE, **STRAVA}
    for name in without:
        del merged[name]
    merged.update(changes or {})
    return merged


def refusal(environ: Mapping[str, str]) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        load_config(environ)
    return caught.value


# --- unconfigured and configured -------------------------------------------


def test_an_environment_without_a_target_loads_as_before() -> None:
    cfg = load_config(BASE)
    assert cfg.targets is None
    assert cfg.strava is None
    assert isinstance(cfg, RelayConfig)


def test_the_client_id_enables_the_target_with_every_default() -> None:
    cfg = load_config(env())
    assert cfg.strava is not None
    assert cfg.strava.client_id == "12345"
    assert cfg.strava.client_secret == "c" * 40
    assert cfg.strava.webhook_token == TOKEN
    assert cfg.strava.api_url == "https://www.strava.com/api/v3"
    assert cfg.strava.oauth_url == "https://www.strava.com/oauth"
    assert cfg.strava.web_url == "https://www.strava.com"
    assert cfg.strava.limits == Limits(200, 2000, 100, 1000)
    assert cfg.targets is not None
    assert cfg.targets.public_url == "https://relay.example.org"
    assert [key.key_id for key in cfg.targets.keys] == ["k1"]
    assert cfg.targets.operator_name == "Example Operator"
    assert cfg.targets.support_contact == "help@example.org"
    assert cfg.targets.privacy_policy_url is None
    assert cfg.targets.terms_url is None


def test_every_setting_lands_in_its_own_field() -> None:
    cfg = load_config(
        env(
            {
                PUBLIC_URL: "http://127.0.0.1:8080/",
                KEYS: f"{KEY_TWO},{KEY_ONE}",
                OPERATOR: "Op 2",
                CONTACT: "https://example.org/contact",
                POLICY: "https://example.org/privacy",
                TERMS: "https://example.org/terms/",
                API_URL: "http://localhost:9001/api",
                OAUTH_URL: "https://oauth.example.org/o/",
                WEB_URL: "http://[::1]:9002",
                RATE: "11,22",
                READ_RATE: "3,4",
            }
        )
    )
    assert cfg.targets is not None and cfg.strava is not None
    assert cfg.targets.public_url == "http://127.0.0.1:8080"
    assert [key.key_id for key in cfg.targets.keys] == ["k2", "k1"]
    assert cfg.targets.operator_name == "Op 2"
    assert cfg.targets.support_contact == "https://example.org/contact"
    assert cfg.targets.privacy_policy_url == "https://example.org/privacy"
    assert cfg.targets.terms_url == "https://example.org/terms"
    assert cfg.strava.api_url == "http://localhost:9001/api"
    assert cfg.strava.oauth_url == "https://oauth.example.org/o"
    assert cfg.strava.web_url == "http://[::1]:9002"
    assert cfg.strava.limits == Limits(11, 22, 3, 4)


def test_equal_fifteen_minute_and_daily_limits_are_accepted() -> None:
    cfg = load_config(env({RATE: "5,5", READ_RATE: "6,6"}))
    assert cfg.strava is not None
    assert cfg.strava.limits == Limits(5, 5, 6, 6)


def test_the_loaded_configuration_hides_its_secrets_in_repr() -> None:
    cfg = load_config(env({CLIENT_SECRET: SECRET, WEBHOOK: SECRET + "x" * 20}))
    text = repr(cfg)
    assert cfg.strava is not None and cfg.strava.client_secret == SECRET
    assert SECRET not in text
    assert "Zq9" not in text
    assert "keys=" not in text
    assert "client_secret=" not in text
    assert "webhook_token=" not in text
    assert "client_id='12345'" in text


# --- the refusals -----------------------------------------------------------

BAD = f"bad {SECRET}"
LIMIT_REASON = (
    "must be two comma-separated integers from 1 to 1000000: the limit per 15 "
    "minutes, then the limit per day"
)
ORDER_REASON = "the limit per 15 minutes must not exceed the limit per day"
HTTPS_REASON = "must be an https address"
CONTACT_REASON = "must be an email address or an https address"
LOOPBACK_REASON = HTTPS_REASON + " (or http to a loopback host)"
KEYS_REASON = (
    "must be 1 to 8 comma-separated id:key entries with distinct ids, "
    "each key 32 bytes in unpadded base64url"
)

# (label, environment changes, variable, reason). The cases outside NOT_PLANTED
# carry SECRET in a changed value.
REFUSALS: list[tuple[str, dict[str, str], str, str]] = [
    ("client-id-letters", {CLIENT_ID: f"12{SECRET}"}, CLIENT_ID, "must be digits"),
    ("client-id-empty", {CLIENT_ID: ""}, CLIENT_ID, "must not be empty"),
    (
        "client-secret-space",
        {CLIENT_SECRET: f"a {SECRET}"},
        CLIENT_SECRET,
        "must be at most 256 printable characters without spaces",
    ),
    (
        "client-secret-too-long",
        {CLIENT_SECRET: SECRET + "x" * 300},
        CLIENT_SECRET,
        "must be at most 256 printable characters without spaces",
    ),
    ("client-secret-empty", {CLIENT_SECRET: ""}, CLIENT_SECRET, "must not be empty"),
    (
        "client-secret-control",
        {CLIENT_SECRET: f"{SECRET}\x07"},
        CLIENT_SECRET,
        "must be at most 256 printable characters without spaces",
    ),
    (
        "client-secret-non-ascii",
        {CLIENT_SECRET: f"{SECRET}\u00e9"},
        CLIENT_SECRET,
        "must be at most 256 printable characters without spaces",
    ),
    (
        "webhook-token-short",
        {WEBHOOK: SECRET},
        WEBHOOK,
        "must be 32 to 128 characters of letters, digits, underscore or hyphen",
    ),
    (
        "webhook-token-long",
        {WEBHOOK: SECRET + "x" * 120},
        WEBHOOK,
        "must be 32 to 128 characters of letters, digits, underscore or hyphen",
    ),
    (
        "webhook-token-bad-character",
        {WEBHOOK: SECRET + "/" + "x" * 20},
        WEBHOOK,
        "must be 32 to 128 characters of letters, digits, underscore or hyphen",
    ),
    ("keys-malformed", {KEYS: f"k1:{SECRET}"}, KEYS, KEYS_REASON),
    ("keys-no-colon", {KEYS: SECRET}, KEYS, KEYS_REASON),
    ("keys-duplicate-id", {KEYS: f"{KEY_ONE},k1:{'B' * 42}E"}, KEYS, KEYS_REASON),
    (
        "keys-nine",
        {KEYS: ",".join(f"k{i}:{'A' * 43}" for i in range(9))},
        KEYS,
        KEYS_REASON,
    ),
    ("keys-empty", {KEYS: ""}, KEYS, "must not be empty"),
    (
        "public-url-plain-http",
        {PUBLIC_URL: f"http://example.org/{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-userinfo",
        {PUBLIC_URL: f"https://u:{SECRET}@example.org"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-query",
        {PUBLIC_URL: f"https://example.org/?k={SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-fragment",
        {PUBLIC_URL: f"https://example.org/#{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-space",
        {PUBLIC_URL: f"https://example.org/a b{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-control",
        {PUBLIC_URL: f"https://example.org/\x07{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-non-ascii",
        {PUBLIC_URL: f"https://ex\u00e4mple.org/{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-no-host",
        {PUBLIC_URL: f"https:///{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-bad-port",
        {PUBLIC_URL: f"https://example.org:x{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-ftp",
        {PUBLIC_URL: f"ftp://localhost/{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    ("public-url-empty", {PUBLIC_URL: ""}, PUBLIC_URL, "must not be empty"),
    (
        "operator-too-long",
        {OPERATOR: SECRET + "x" * 100},
        OPERATOR,
        "must be 1 to 100 printable characters",
    ),
    (
        "operator-control",
        {OPERATOR: f"{SECRET}\x07"},
        OPERATOR,
        "must be 1 to 100 printable characters",
    ),
    (
        "operator-blank",
        {OPERATOR: "   "},
        OPERATOR,
        "must be 1 to 100 printable characters",
    ),
    ("operator-empty", {OPERATOR: ""}, OPERATOR, "must not be empty"),
    (
        "contact-no-domain",
        {CONTACT: f"{SECRET}@x"},
        CONTACT,
        "must be an email address or an https address",
    ),
    (
        "contact-http",
        {CONTACT: f"http://example.org/{SECRET}"},
        CONTACT,
        CONTACT_REASON,
    ),
    (
        "contact-two-ats",
        {CONTACT: f"{SECRET}@a@b.org"},
        CONTACT,
        "must be an email address or an https address",
    ),
    (
        "contact-too-long",
        {CONTACT: SECRET + "a" * 250 + "@b.org"},
        CONTACT,
        "must be an email address or an https address",
    ),
    (
        "contact-space",
        {CONTACT: f"{SECRET} x@b.org"},
        CONTACT,
        "must be an email address or an https address",
    ),
    ("contact-control", {CONTACT: f"{SECRET}\x07@b.org"}, CONTACT, CONTACT_REASON),
    ("contact-non-ascii", {CONTACT: f"{SECRET}\u00e9@b.org"}, CONTACT, CONTACT_REASON),
    (
        "contact-loopback-http",
        {CONTACT: f"http://localhost/{SECRET}"},
        CONTACT,
        CONTACT_REASON,
    ),
    ("rate-non-ascii-digits", {RATE: "\u0661,\u0662"}, RATE, LIMIT_REASON),
    (
        "client-id-non-ascii-digits",
        {CLIENT_ID: "\u0661\u0662"},
        CLIENT_ID,
        "must be digits",
    ),
    (
        "webhook-token-non-ascii-word",
        {WEBHOOK: SECRET + "\u00e9" * 10},
        WEBHOOK,
        "must be 32 to 128 characters of letters, digits, underscore or hyphen",
    ),
    (
        "public-url-private-address",
        {PUBLIC_URL: f"http://10.0.0.1/{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-localhost-suffix",
        {PUBLIC_URL: f"http://notlocalhost/{SECRET}"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-empty-query",
        {PUBLIC_URL: f"https://example.org/{SECRET}?"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    (
        "public-url-empty-fragment",
        {PUBLIC_URL: f"https://example.org/{SECRET}#"},
        PUBLIC_URL,
        LOOPBACK_REASON,
    ),
    ("contact-no-local", {CONTACT: "@b.org"}, CONTACT, CONTACT_REASON),
    ("contact-empty-domain-label", {CONTACT: "x@.org"}, CONTACT, CONTACT_REASON),
    ("contact-trailing-dot", {CONTACT: "x@a."}, CONTACT, CONTACT_REASON),
    ("contact-empty-middle-label", {CONTACT: "x@a..b"}, CONTACT, CONTACT_REASON),
    (
        "contact-trailing-text",
        {CONTACT: f"x@b.org {SECRET}"},
        CONTACT,
        CONTACT_REASON,
    ),
    (
        "contact-space-in-domain",
        {CONTACT: f"x@{SECRET} b.org"},
        CONTACT,
        CONTACT_REASON,
    ),
    (
        "contact-at-in-last-label",
        {CONTACT: f"x@a.{SECRET}@c"},
        CONTACT,
        CONTACT_REASON,
    ),
    ("rate-one-number-digits", {RATE: "5"}, RATE, LIMIT_REASON),
    ("rate-short-above-range", {RATE: "1000001,5"}, RATE, LIMIT_REASON),
    ("rate-day-zero", {RATE: "1,0"}, RATE, LIMIT_REASON),
    ("client-id-hex-letters", {CLIENT_ID: "12abcdef"}, CLIENT_ID, "must be digits"),
    (
        "webhook-token-dot",
        {WEBHOOK: SECRET + "." + "x" * 20},
        WEBHOOK,
        "must be 32 to 128 characters of letters, digits, underscore or hyphen",
    ),
    (
        "webhook-token-plus",
        {WEBHOOK: SECRET + "+" + "x" * 20},
        WEBHOOK,
        "must be 32 to 128 characters of letters, digits, underscore or hyphen",
    ),
    ("policy-http", {POLICY: f"http://example.org/{SECRET}"}, POLICY, HTTPS_REASON),
    (
        "policy-loopback-http",
        {POLICY: f"http://localhost/{SECRET}"},
        POLICY,
        HTTPS_REASON,
    ),
    ("policy-empty", {POLICY: ""}, POLICY, "must not be empty"),
    ("terms-http", {TERMS: f"http://example.org/{SECRET}"}, TERMS, HTTPS_REASON),
    (
        "terms-loopback-http",
        {TERMS: f"http://localhost/{SECRET}"},
        TERMS,
        HTTPS_REASON,
    ),
    ("terms-empty", {TERMS: ""}, TERMS, "must not be empty"),
    (
        "api-url-http",
        {API_URL: f"http://example.org/{SECRET}"},
        API_URL,
        LOOPBACK_REASON,
    ),
    (
        "oauth-url-query",
        {OAUTH_URL: f"https://example.org/?{SECRET}"},
        OAUTH_URL,
        LOOPBACK_REASON,
    ),
    (
        "web-url-userinfo",
        {WEB_URL: f"https://{SECRET}@example.org"},
        WEB_URL,
        LOOPBACK_REASON,
    ),
    ("web-url-empty", {WEB_URL: ""}, WEB_URL, "must not be empty"),
    ("rate-one-number", {RATE: f"{SECRET}"}, RATE, LIMIT_REASON),
    ("rate-three-numbers", {RATE: "1,2,3"}, RATE, LIMIT_REASON),
    ("rate-letters", {RATE: f"1,{SECRET}"}, RATE, LIMIT_REASON),
    ("rate-space", {RATE: "1, 2"}, RATE, LIMIT_REASON),
    ("rate-zero", {RATE: "0,5"}, RATE, LIMIT_REASON),
    ("rate-negative", {RATE: "-1,5"}, RATE, LIMIT_REASON),
    ("rate-too-big", {RATE: "1,1000001"}, RATE, LIMIT_REASON),
    ("rate-short-above-day", {RATE: "6,5"}, RATE, ORDER_REASON),
    ("read-rate-letters", {READ_RATE: f"{SECRET},1"}, READ_RATE, LIMIT_REASON),
    ("read-rate-short-above-day", {READ_RATE: "1001,1000"}, READ_RATE, ORDER_REASON),
    ("rate-empty", {RATE: ""}, RATE, "must not be empty"),
]


# The cases whose changed value carries no SECRET, by kind: an emptiness
# (the *-empty cases), a blank (operator-blank), a count (keys-nine,
# rate-three-numbers), a range or an order (rate-zero, rate-negative,
# rate-too-big, rate-short-above-day, read-rate-short-above-day), a repeated id
# (keys-duplicate-id), a near-miss literal whose fault is its exact text
# (rate-space), a non-ASCII digit lookalike
# (rate-non-ascii-digits, client-id-non-ascii-digits), and a value that is
# malformed by its shape alone (contact-no-local, contact-empty-domain-label,
# contact-trailing-dot, contact-empty-middle-label, rate-one-number-digits,
# rate-short-above-range, rate-day-zero, client-id-hex-letters).
NOT_PLANTED = frozenset(
    {
        "client-id-empty",
        "keys-nine",
        "keys-duplicate-id",
        "keys-empty",
        "public-url-empty",
        "operator-blank",
        "operator-empty",
        "client-secret-empty",
        "policy-empty",
        "terms-empty",
        "web-url-empty",
        "rate-three-numbers",
        "rate-space",
        "rate-zero",
        "rate-negative",
        "rate-too-big",
        "rate-short-above-day",
        "read-rate-short-above-day",
        "rate-empty",
        "rate-non-ascii-digits",
        "client-id-non-ascii-digits",
        "contact-no-local",
        "contact-empty-domain-label",
        "contact-trailing-dot",
        "contact-empty-middle-label",
        "rate-one-number-digits",
        "rate-short-above-range",
        "rate-day-zero",
        "client-id-hex-letters",
    }
)


@pytest.mark.parametrize(
    ("label", "changes", "variable", "reason"), REFUSALS, ids=[r[0] for r in REFUSALS]
)
def test_each_refusal_names_the_variable_and_never_a_planted_value(
    label: str, changes: dict[str, str], variable: str, reason: str
) -> None:
    environ = env(changes)
    assert (label in NOT_PLANTED) != any(SECRET in v for v in changes.values()), label
    error = refusal(environ)
    assert error.variable == variable
    assert str(error) == f"{variable}: {reason}"
    assert SECRET not in repr(error) + repr(error.args) + error.variable


def test_the_refusal_table_exercises_every_target_and_strava_variable() -> None:
    assert {r[2] for r in REFUSALS} == set(TARGETS_VARIABLES + STRAVA_VARIABLES)


MISSING = [KEYS, PUBLIC_URL, OPERATOR, CONTACT, CLIENT_SECRET, WEBHOOK]


def test_every_variable_of_the_table_has_a_refusal_case() -> None:
    """The union of every refusal in this file and in test_config.py is the table,
    so a row appended later without a refusal case reds here."""
    refused = {r[2] for r in REFUSALS} | set(MISSING)
    for _, changes in SECRET_CASES:
        environ = base_env()
        environ.update(changes)
        refused.add(refusal(environ).variable)
    assert refused == {v.name for v in ENVIRONMENT}


@pytest.mark.parametrize("name", MISSING)
def test_a_missing_required_variable_is_refused_once_the_client_id_is_set(
    name: str,
) -> None:
    error = refusal(env(without=(name,)))
    assert str(error) == f"{name}: is required"
    assert error.variable == name


def test_the_missing_variables_are_the_contracts_required_with_rows() -> None:
    declared = [v.name for v in ENVIRONMENT if v.required_with == (CLIENT_ID,)]
    assert sorted(declared) == sorted(MISSING)


LITERAL_GROUP = [
    "FITDOCS_RELAY_PUBLIC_URL",
    "FITDOCS_RELAY_ENCRYPTION_KEYS",
    "FITDOCS_RELAY_OPERATOR_NAME",
    "FITDOCS_RELAY_SUPPORT_CONTACT",
    "FITDOCS_RELAY_PRIVACY_POLICY_URL",
    "FITDOCS_RELAY_TERMS_URL",
    "FITDOCS_RELAY_STRAVA_CLIENT_SECRET",
    "FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN",
    "FITDOCS_RELAY_STRAVA_API_URL",
    "FITDOCS_RELAY_STRAVA_OAUTH_URL",
    "FITDOCS_RELAY_STRAVA_WEB_URL",
    "FITDOCS_RELAY_STRAVA_RATE_LIMIT",
    "FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT",
]


def test_the_group_constants_are_the_literal_group_and_the_client_id() -> None:
    assert set(TARGETS_VARIABLES + STRAVA_VARIABLES) == {
        *LITERAL_GROUP,
        "FITDOCS_RELAY_STRAVA_CLIENT_ID",
    }
    assert len(TARGETS_VARIABLES + STRAVA_VARIABLES) == 14


@pytest.mark.parametrize("name", LITERAL_GROUP)
def test_any_other_variable_without_the_client_id_is_refused(name: str) -> None:
    environ = {**BASE, name: f"{SECRET}"}
    error = refusal(environ)
    assert error.variable == name
    assert str(error).startswith(f"{name}: is only valid with ")
    assert SECRET not in str(error)
    assert CLIENT_ID in str(error)


def test_a_valid_looking_variable_alone_is_still_refused_without_the_client_id() -> (
    None
):
    environ = {**BASE, RATE: "11,22"}
    assert str(refusal(environ)) == f"{RATE}: is only valid with {CLIENT_ID}"


def test_the_whole_strava_set_minus_the_client_id_is_refused_on_the_first_name() -> (
    None
):
    environ = {**BASE, **{k: v for k, v in STRAVA.items() if k != CLIENT_ID}}
    assert refusal(environ).variable == PUBLIC_URL


def test_existing_refusals_come_before_the_strava_ones() -> None:
    environ = env({PEPPER: "short", CLIENT_ID: BAD})
    assert refusal(environ).variable == PEPPER


def test_every_variable_of_the_group_is_a_contract_row() -> None:
    names = {v.name for v in ENVIRONMENT}
    assert set(TARGETS_VARIABLES + STRAVA_VARIABLES) <= names
    assert len(TARGETS_VARIABLES + STRAVA_VARIABLES) == 14


# --- both sides of every bound ---------------------------------------------


def _eight_keys() -> str:
    return ",".join(f"k{i}:{'A' * 43}" for i in range(8))


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({WEBHOOK: "w" * 32}, lambda c: len(c.strava.webhook_token) == 32),
        ({WEBHOOK: "w" * 128}, lambda c: len(c.strava.webhook_token) == 128),
        ({OPERATOR: "o"}, lambda c: c.targets.operator_name == "o"),
        ({OPERATOR: "o" * 100}, lambda c: len(c.targets.operator_name) == 100),
        ({CLIENT_SECRET: "s" * 256}, lambda c: len(c.strava.client_secret) == 256),
        ({CLIENT_ID: "9" * 20}, lambda c: c.strava.client_id == "9" * 20),
        ({KEYS: _eight_keys()}, lambda c: len(c.targets.keys) == 8),
        ({RATE: "1,1"}, lambda c: c.strava.limits.overall_day == 1),
        ({RATE: "1000000,1000000"}, lambda c: c.strava.limits.overall_day == 10**6),
        (
            {CONTACT: "a" * 242 + "@example.org"},
            lambda c: len(c.targets.support_contact) == 254,
        ),
    ],
    ids=[
        "webhook-32",
        "webhook-128",
        "operator-1",
        "operator-100",
        "secret-256",
        "client-id-20",
        "keys-8",
        "limit-1",
        "limit-1000000",
        "contact-254",
    ],
)
def test_the_last_accepted_value_of_each_bound_loads(
    changes: dict[str, str], field: object
) -> None:
    cfg = load_config(env(changes))
    assert cfg.strava is not None and cfg.targets is not None
    assert field(cfg)  # type: ignore[operator]


@pytest.mark.parametrize(
    ("changes", "variable"),
    [
        ({WEBHOOK: "w" * 31}, WEBHOOK),
        ({WEBHOOK: "w" * 129}, WEBHOOK),
        ({OPERATOR: "o" * 101}, OPERATOR),
        ({CLIENT_SECRET: "s" * 257}, CLIENT_SECRET),
        ({CLIENT_ID: "9" * 21}, CLIENT_ID),
        ({CONTACT: "a" * 243 + "@example.org"}, CONTACT),
        ({RATE: "1000001,1000001"}, RATE),
    ],
    ids=[
        "webhook-31",
        "webhook-129",
        "operator-101",
        "secret-257",
        "client-id-21",
        "contact-255",
        "limit-1000001",
    ],
)
def test_the_first_refused_value_of_each_bound_is_refused(
    changes: dict[str, str], variable: str
) -> None:
    assert refusal(env(changes)).variable == variable


# --- behaviour the refusal table does not pin ---------------------------------


def test_a_target_variable_without_the_client_id_names_the_configured_target() -> None:
    error = refusal({**BASE, PUBLIC_URL: "https://relay.example.org"})
    assert str(error) == (
        f"{PUBLIC_URL}: is only valid with a configured target ({CLIENT_ID})"
    )


@pytest.mark.parametrize(
    "token",
    ["A" * 32, "a" * 32, "0" * 32, "_" * 32, "-" * 32, "Az09_-" * 6],
    ids=["upper", "lower", "digit", "underscore", "hyphen", "mixed"],
)
def test_each_class_of_the_webhook_alphabet_is_accepted(token: str) -> None:
    cfg = load_config(env({WEBHOOK: token}))
    assert cfg.strava is not None and cfg.strava.webhook_token == token


def test_every_trailing_slash_of_a_base_address_is_dropped() -> None:
    cfg = load_config(env({PUBLIC_URL: "https://relay.example.org/a//"}))
    assert cfg.targets is not None
    assert cfg.targets.public_url == "https://relay.example.org/a"


def test_all_bad_values_are_refused_one_at_a_time_in_the_contract_tables_order() -> (
    None
):
    valid = env(
        {POLICY: "https://example.org/privacy", TERMS: "https://example.org/terms"}
    )
    bad = {name: "a b" for name in valid if name not in BASE}
    bad[OPERATOR] = "\x07"
    environ = {**BASE, **bad}
    order = []
    for _ in range(len(bad)):
        name = refusal(environ).variable
        order.append(name)
        environ[name] = valid[name]
    assert order == [v.name for v in ENVIRONMENT if v.name in bad]
    assert load_config(environ).strava is not None


REMOVED_LINKS = P + "STRAVA_LINKS"  # the link setting, in no released relay


@pytest.mark.parametrize("value", ["activity", "relay", ""])
@pytest.mark.parametrize("enabled", [True, False])
def test_the_removed_link_setting_is_an_unknown_reserved_variable(
    value: str, enabled: bool
) -> None:
    environ = {**(env() if enabled else BASE), REMOVED_LINKS: value}
    error = refusal(environ)
    assert error.variable == REMOVED_LINKS
    assert str(error) == (
        f"{REMOVED_LINKS}: unknown variable with the reserved prefix {P}"
    )
