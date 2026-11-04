"""The Strava section of `docs/relay.md` bound to the code (strava-publish 7.2;
Requirements 4.9, 13.6, 16.1, 16.5, 16.6, 17.2, 17.7).

The operator page's `## The Strava target` section carries the policy summary,
the routes and pages table and a set of statements an operator relies on. The
summary's section list is compared with `POLICY_HEADINGS`, the routes table with
the route constants, and each statement is looked up in its own subsection.
Each check is a function over page text, so the mutations at the foot of the
file can feed it an altered page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs_relay.routes import ROUTE_BODY_LIMITS
from fitdocs_relay.shared.relay_targets import (
    ACTION_CONNECT,
    ACTION_CONNECT_POLL,
    ACTION_DISCONNECT,
    ACTION_PUBLISH,
    ACTION_UPLOAD,
    MAX_UPLOAD_REQUEST_BYTES,
    STRAVA,
    target_route,
)
from fitdocs_relay.strava.connect import CALLBACK_PATH
from fitdocs_relay.strava.policy import POLICY_HEADINGS
from fitdocs_relay.strava.routes import (
    CONNECT_PAGE_PATH,
    PRIVACY_PATH,
)
from fitdocs_relay.strava.webhook import WEBHOOK_PATH

PAGE = Path(__file__).resolve().parents[3] / "docs" / "relay.md"
STRAVA_HEADING = "## The Strava target"
ROUTES_HEADER = "| Path | Method | Answers |"

SUBSECTIONS = (
    "### Configuring Strava",
    "### Encryption keys and rotation",
    "### The webhook subscription",
    "### Routes and pages",
    "### What the relay keeps and when it deletes it",
    "### Privacy policy and consent",
    "### Operator obligations",
    "### Running your own Strava application",
)

# Words that name a hosting or an email provider. The page names none.
PROVIDER_WORDS = (
    "amazon",
    "aws",
    "azure",
    "cloudflare",
    "digitalocean",
    "fly.io",
    "gmail",
    "google cloud",
    "heroku",
    "hetzner",
    "mailgun",
    "postmark",
    "railway",
    "render.com",
    "sendgrid",
    "ses.amazonaws",
    "vercel",
)


def page_text() -> str:
    assert PAGE.is_file(), f"the operator page is missing: {PAGE}"
    return PAGE.read_text(encoding="utf-8")


def strava_section(text: str) -> str:
    assert text.count(STRAVA_HEADING + "\n") == 1, f"{STRAVA_HEADING!r} not once"
    rest = text.split(STRAVA_HEADING + "\n", 1)[1]
    return re.split(r"^## ", rest, maxsplit=1, flags=re.MULTILINE)[0]


def subsection(text: str, heading: str) -> str:
    body = strava_section(text)
    assert body.count(heading + "\n") == 1, f"{heading!r} is not exactly once"
    rest = body.split(heading + "\n", 1)[1]
    return re.split(r"^### ", rest, maxsplit=1, flags=re.MULTILINE)[0]


def flat(text: str) -> str:
    return " ".join(text.split())


# --- structure ----------------------------------------------------------------


def heading_problems(text: str) -> list[str]:
    found = re.findall(r"^### .*$", strava_section(text), re.MULTILINE)
    if found != list(SUBSECTIONS):
        return [f"subsections: page has {found}, expected {list(SUBSECTIONS)}"]
    return []


# --- the policy summary ---------------------------------------------------------


def summary_headings(text: str) -> list[str]:
    """The policy sections the summary lists, one `- **Heading**` line each."""
    body = subsection(text, "### Privacy policy and consent")
    return re.findall(r"^- \*\*(.+?)\*\*", body, re.MULTILINE)


def summary_problems(text: str) -> list[str]:
    found = summary_headings(text)
    wanted = list(POLICY_HEADINGS)
    problems = [f"missing section: {name}" for name in wanted if name not in found]
    problems += [f"unexpected section: {name}" for name in found if name not in wanted]
    if not problems and found != wanted:
        problems.append("the sections are not in the policy's order")
    return problems


# --- the routes and pages table -------------------------------------------------


def route_rows(text: str) -> list[list[str]]:
    lines = subsection(text, "### Routes and pages").splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == ROUTES_HEADER]
    if len(starts) != 1:
        return []
    rows: list[list[str]] = []
    for line in lines[starts[0] + 2 :]:
        if not line.startswith("|"):
            break
        cells = re.split(r"(?<!\\)\|", line.strip())[1:-1]
        rows.append([cell.strip() for cell in cells])
    return rows


WANTED_ROUTES = [
    (f"`{target_route(STRAVA, ACTION_CONNECT)}`", "POST"),
    (f"`{target_route(STRAVA, ACTION_CONNECT_POLL)}`", "POST"),
    (f"`{target_route(STRAVA, ACTION_PUBLISH)}`", "POST"),
    (f"`{target_route(STRAVA, ACTION_UPLOAD)}`", "POST"),
    (f"`{target_route(STRAVA, ACTION_DISCONNECT)}`", "POST"),
    (f"`{CONNECT_PAGE_PATH}`", "GET"),
    (f"`{CALLBACK_PATH}`", "GET"),
    (f"`{PRIVACY_PATH}`", "GET"),
    (f"`{WEBHOOK_PATH}/<webhook token>`", "GET, POST"),
]


def route_problems(text: str) -> list[str]:
    found = [(row[0], row[1]) for row in route_rows(text) if len(row) == 3]
    problems = [
        f"missing route: {path}" for path, _ in WANTED_ROUTES if (path, _) not in found
    ]
    problems += [
        f"unexpected route: {path}"
        for path, _ in found
        if (path, _) not in WANTED_ROUTES
    ]
    if not problems and found != WANTED_ROUTES:
        problems.append("the routes are not in the code's order")
    return problems


# --- statements -------------------------------------------------------------------

# name -> (subsection heading, sentence that must appear, whitespace-flattened)
STATEMENTS = {
    "enabled by the client id": (
        "### Configuring Strava",
        "The Strava target is offered exactly when "
        "`FITDOCS_RELAY_STRAVA_CLIENT_ID` is set",
    ),
    "unset target is absent": (
        "### Configuring Strava",
        "every Strava route, page and webhook address answers `not-offered` "
        "like any unknown path",
    ),
    "public url equals instances": (
        "### Routes and pages",
        "`FITDOCS_RELAY_PUBLIC_URL` must be the address fitdocs instances "
        "configure as their relay's `url`",
    ),
    "link setting activity": (
        "### Routes and pages",
        "Under `activity` every posted or uploaded answer carries the "
        "activity's address",
    ),
    "link setting relay": (
        "### Routes and pages",
        "Under `relay` the answer carries no address and the page links to "
        "`/go/<publication id>`",
    ),
    "robots": (
        "### Routes and pages",
        "`/robots.txt` disallows `/go/` for every crawler",
    ),
    "head": (
        "### Routes and pages",
        "answers `405` with `Allow: GET` to HEAD",
    ),
    "webhook size": (
        "### Routes and pages",
        "body over 64 KiB is refused with `request-too-large` (413)",
    ),
    "upload bound": (
        "### Routes and pages",
        "Only while the Strava target is configured does the upload route "
        "accept a request of up to 22 MiB",
    ),
    "rotation steps": (
        "### Encryption keys and rotation",
        "Put the new key first, keep the old keys after it, restart, run "
        "`fitdocs-relay reencrypt`",
    ),
    "rotation removal": (
        "### Encryption keys and rotation",
        "only when it reports no unreadable connection, remove the old key and restart",
    ),
    "unreadable is not connected": (
        "### Encryption keys and rotation",
        "A connection that no configured key opens is treated as not connected",
    ),
    "reencrypt exit codes": (
        "### Encryption keys and rotation",
        "It exits 0 when `m` is zero and 1 otherwise, and 2 when the Strava "
        "target is not configured",
    ),
    "pepper": (
        "### Encryption keys and rotation",
        "Changing `FITDOCS_RELAY_TOKEN_PEPPER` also breaks the match between "
        "deauthorization events and stored connections",
    ),
    "subscription needed": (
        "### The webhook subscription",
        "Without the subscription the relay never learns that an athlete "
        "revoked its access",
    ),
    "subscription command": (
        "### The webhook subscription",
        "`fitdocs-relay strava webhook create`",
    ),
    "subscription elsewhere": (
        "### The webhook subscription",
        "creates nothing and prints `subscribed elsewhere` on standard error, "
        "exiting 1",
    ),
    "connection ends on a refused renewal, not on a failed call": (
        "### The webhook subscription",
        "the relay keeps the connection until Strava refuses to renew its tokens, "
        "the principal is deleted, the same Strava account is connected from "
        "another principal or `fitdocs disconnect` runs",
    ),
    "deletion revokes the relay token": (
        "### What the relay keeps and when it deletes it",
        "revokes the connection's relay token (it stays listed as revoked, and "
        "fitdocs then gets `token-revoked`)",
    ),
    "deauthorization deletes": (
        "### What the relay keeps and when it deletes it",
        "Strava reports a deauthorization through the webhook subscription",
    ),
    "refused refresh deletes": (
        "### What the relay keeps and when it deletes it",
        "Strava refuses to renew a connection's tokens",
    ),
    "transient refresh keeps": (
        "### What the relay keeps and when it deletes it",
        "A redirect, a server error or an unreachable Strava is transient",
    ),
    "proxy": (
        "### Configuring Strava",
        "Requests to Strava honour the standard `HTTPS_PROXY` and `NO_PROXY` variables",
    ),
    "policy address": (
        "### Privacy policy and consent",
        "`<public address>/privacy`",
    ),
    "own policy address": (
        "### Privacy policy and consent",
        "`FITDOCS_RELAY_PRIVACY_POLICY_URL`",
    ),
    "breach": (
        "### Operator obligations",
        "Notify Strava of a breach within 24 hours",
    ),
    "capacity": (
        "### Operator obligations",
        "one athlete at first, up to ten on the owner's request, and more only "
        "after Strava's review",
    ),
    "no charging": (
        "### Operator obligations",
        "Never charge for the feature",
    ),
    "no announcement": (
        "### Operator obligations",
        "Publish no announcement that references Strava",
    ),
    "own application": (
        "### Running your own Strava application",
        "needs its own Strava application, registered under your own Strava "
        "subscription with your own callback domain",
    ),
    "never another's credentials": (
        "### Running your own Strava application",
        "Never use another operator's application credentials",
    ),
}


def statement_problems(text: str) -> list[str]:
    problems = []
    for name, (heading, sentence) in STATEMENTS.items():
        if sentence not in flat(subsection(text, heading)):
            problems.append(name)
    return problems


def provider_problems(text: str) -> list[str]:
    lowered = text.lower()
    return [
        word
        for word in PROVIDER_WORDS
        if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", lowered)
    ]


BRAND_PHRASES = ("Connect with Strava", "View on Strava", "Compatible with Strava")


def brand_problems(text: str) -> list[str]:
    """Quoted brand phrases in the Strava section other than the three allowed."""
    quoted = re.findall(r'"([^"\n]{0,40}Strava)"', strava_section(text))
    return [phrase for phrase in quoted if phrase not in BRAND_PHRASES]


# --- the real page ------------------------------------------------------------------


def test_the_strava_section_has_its_subsections_in_order() -> None:
    assert heading_problems(page_text()) == []


def test_the_policy_summary_is_the_policys_section_list() -> None:
    assert summary_problems(page_text()) == []


def test_the_policy_summary_was_actually_read() -> None:
    assert len(summary_headings(page_text())) == len(POLICY_HEADINGS) >= 9


def test_the_routes_table_is_the_codes_routes() -> None:
    assert route_problems(page_text()) == []


def test_the_page_names_no_hosting_or_email_provider() -> None:
    text = page_text()
    assert len(text) > 20_000, "the page was read wrongly"
    assert provider_problems(text) == []


def test_the_strava_section_uses_only_the_allowed_brand_phrases() -> None:
    assert brand_problems(page_text()) == []


def test_the_upload_bound_the_page_states_is_the_codes() -> None:
    assert MAX_UPLOAD_REQUEST_BYTES == 22 * 1024 * 1024
    assert list(ROUTE_BODY_LIMITS.values()) == [MAX_UPLOAD_REQUEST_BYTES]


# --- the bindings can fail ------------------------------------------------------------


@pytest.mark.parametrize("index", range(len(POLICY_HEADINGS)))
def test_removing_any_policy_section_from_the_summary_reds_the_binding(
    index: int,
) -> None:
    text = page_text()
    heading = POLICY_HEADINGS[index]
    lines = text.splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith(f"- **{heading}**")]
    assert len(rows) == 1, "the summary line scan found the wrong lines"
    del lines[rows[0]]
    assert summary_problems("\n".join(lines)) == [f"missing section: {heading}"]


def test_an_invented_summary_section_reds_the_binding() -> None:
    text = page_text()
    marker = f"- **{POLICY_HEADINGS[-1]}**"
    assert text.count(marker) == 1
    changed = text.replace(marker, "- **Invented section** -- not real.\n" + marker)
    assert summary_problems(changed) == ["unexpected section: Invented section"]


def test_reordering_the_summary_reds_the_binding() -> None:
    text = page_text()
    lines = text.splitlines()
    rows = [
        i
        for i, line in enumerate(lines)
        if line.startswith(f"- **{POLICY_HEADINGS[0]}**")
        or line.startswith(f"- **{POLICY_HEADINGS[1]}**")
    ]
    assert len(rows) == 2
    lines[rows[0]], lines[rows[1]] = lines[rows[1]], lines[rows[0]]
    assert summary_problems("\n".join(lines)) == [
        "the sections are not in the policy's order"
    ]


def test_deleting_a_route_row_reds_the_binding() -> None:
    lines = page_text().splitlines()
    rows = [
        i for i, line in enumerate(lines) if line.startswith(f"| `{CALLBACK_PATH}`")
    ]
    assert len(rows) == 1
    del lines[rows[0]]
    assert route_problems("\n".join(lines)) == [f"missing route: `{CALLBACK_PATH}`"]


def test_changing_a_route_method_reds_the_binding() -> None:
    text = page_text()
    changed = text.replace(
        f"| `{PRIVACY_PATH}` | GET |", f"| `{PRIVACY_PATH}` | POST |", 1
    )
    assert changed != text, "the fixture changed nothing"
    assert route_problems(changed) != []


def test_reordering_routes_reds_the_binding() -> None:
    lines = page_text().splitlines()
    first = next(i for i, line in enumerate(lines) if line == ROUTES_HEADER) + 2
    lines[first], lines[first + 1] = lines[first + 1], lines[first]
    assert route_problems("\n".join(lines)) == [
        "the routes are not in the code's order"
    ]


def test_a_provider_name_reds_the_provider_scan() -> None:
    assert provider_problems(page_text() + "\nHost it on Cloudflare.\n") == [
        "cloudflare"
    ]
    assert provider_problems(page_text() + "\nMail through SendGrid.\n") == ["sendgrid"]


def test_a_provider_word_inside_another_word_is_not_a_hit() -> None:
    assert provider_problems(page_text() + "\nThe laws of motion.\n") == []


def test_an_unlisted_brand_phrase_reds_the_brand_scan() -> None:
    text = page_text().replace(
        STRAVA_HEADING + "\n", STRAVA_HEADING + '\n\nUse "Post to Strava".\n', 1
    )
    assert brand_problems(text) == ["Post to Strava"]


def test_a_missing_subsection_reds_the_structure_check() -> None:
    text = page_text().replace("### Operator obligations\n", "### Obligations\n", 1)
    assert len(heading_problems(text)) == 1
