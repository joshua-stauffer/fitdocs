"""The Strava target's pages, consent text and privacy policy (task 3.11)."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from html.parser import HTMLParser

import pytest

from fitdocs_relay.strava import pages, policy
from fitdocs_relay.strava.pages import Operator, Page

HOSTILE = "x\"><b id='h'>&amp;"
CONTACT = "help-sentinel@operator.example"
POLICY_URL = "https://operator.example/own-policy"
AUTH_URL = "https://oauth.example/authorize?client=1&state=abc"
USER_CODE = "KQ7-M2X"
OPERATOR = Operator("Operator Sentinel", CONTACT, None)
OWN = Operator("Operator Sentinel", CONTACT, POLICY_URL)

BuildPage = Callable[[Operator], Page]

SIMPLE: dict[str, BuildPage] = {
    "in_use": pages.in_use_page,
    "invalid_code": pages.invalid_code_page,
    "granted": pages.granted_page,
    "refused": pages.refused_page,
    "try_later": pages.try_later_page,
    "unavailable": pages.unavailable_page,
}


def _all_pages(operator: Operator) -> dict[str, Page]:
    built = {name: build(operator) for name, build in SIMPLE.items()}
    built["connect"] = pages.connect_page(
        user_code=USER_CODE, authorize_url=AUTH_URL, operator=operator
    )
    built["privacy"] = pages.privacy_page(operator)
    return built


ALL_NAMES = [*SIMPLE, "connect", "privacy"]


def test_the_page_list_is_the_design_list() -> None:
    assert sorted(_all_pages(OPERATOR)) == sorted(
        [
            "connect",
            "in_use",
            "invalid_code",
            "granted",
            "refused",
            "try_later",
            "unavailable",
            "privacy",
        ]
    )


# --- escaping ---------------------------------------------------------------


@pytest.mark.parametrize("field", ["name", "contact", "policy_url"])
def test_operator_values_are_escaped_on_every_page(field: str) -> None:
    values = {"name": "N", "contact": "C", "policy_url": "https://p.example/"}
    values[field] = HOSTILE
    operator = Operator(values["name"], values["contact"], values["policy_url"])
    built = _all_pages(operator)
    for name, page in built.items():
        assert "<b id='h'>" not in page.html, name
        assert 'x"><b' not in page.html, name
    # The value reaches the pages that show it, in escaped form.
    shown = {
        "name": ["privacy"],
        "contact": ALL_NAMES,
        "policy_url": ALL_NAMES,
    }[field]
    for name in shown:
        assert escape(HOSTILE, quote=True) in built[name].html, name


def test_user_code_and_authorize_url_are_escaped() -> None:
    hostile_code = "x\"><b id='c'>&amp;"
    hostile_url = "https://a.example/?q=\"><i id='u'>&x=1"
    page = pages.connect_page(
        user_code=hostile_code,
        authorize_url=hostile_url,
        operator=OPERATOR,
    )
    assert "<b id='c'>" not in page.html
    assert "<i id='u'>" not in page.html
    assert escape(hostile_code, quote=True) in page.html
    assert f'href="{escape(hostile_url, quote=True)}"' in page.html


# --- support contact and policy link ---------------------------------------


@pytest.mark.parametrize("operator", [OPERATOR, OWN])
@pytest.mark.parametrize("name", ALL_NAMES)
def test_each_page_carries_the_support_contact(name: str, operator: Operator) -> None:
    page = _all_pages(operator)[name]
    assert page.html.count(CONTACT) >= 1


@pytest.mark.parametrize("name", ALL_NAMES)
def test_built_in_policy_link_is_used_without_an_operator_address(name: str) -> None:
    page = _all_pages(OPERATOR)[name]
    assert re.findall(r'href="([^"]*)"', page.html).count("/privacy") == 1


@pytest.mark.parametrize("name", ALL_NAMES)
def test_operators_own_policy_address_replaces_the_built_in_one(name: str) -> None:
    page = _all_pages(OWN)[name]
    hrefs = re.findall(r'href="([^"]*)"', page.html)
    assert POLICY_URL in hrefs
    assert "/privacy" not in hrefs


# --- the connect page -------------------------------------------------------


def _connect() -> str:
    return pages.connect_page(
        user_code=USER_CODE, authorize_url=AUTH_URL, operator=OWN
    ).html


def test_the_connect_page_is_in_the_stated_order() -> None:
    html = _connect()
    consent = [escape(p) for p in policy.consent_text()]
    markers = [
        USER_CODE,
        "this same code",
        *consent,
        "Connect with Strava",
        POLICY_URL,
        CONTACT,
    ]
    for marker in markers:
        assert html.count(marker) == 1, marker
    positions = [html.index(m) for m in markers]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_the_connect_control_is_a_48px_link_with_no_artwork() -> None:
    html = _connect()
    controls = re.findall(r"<a [^>]*>Connect with Strava</a>", html)
    assert len(controls) == 1
    control = controls[0]
    assert f'href="{escape(AUTH_URL, quote=True)}"' in control
    assert re.search(r"height:48px", control)
    assert re.search(r"line-height:48px", control)
    for artwork in ("<img", "<svg", "url(", "<picture", "<canvas", "background"):
        assert artwork not in html.lower(), artwork
    assert "<script" not in html.lower()


# --- brand phrases ----------------------------------------------------------

_BRANDISH = re.compile(r"[A-Z]\w*\s+(?:with|on|by|for|via|to)\s+Strava")
_STRAVA_THEN_CAPITAL = re.compile(r"Strava[ \t]+[A-Z]")


def _visible(html: str) -> str:
    return re.sub(r"<[^>]*>", "\n", html)


@pytest.mark.parametrize("name", ALL_NAMES)
def test_the_only_brand_phrase_is_connect_with_strava_on_the_connect_page(
    name: str,
) -> None:
    html = _all_pages(OPERATOR)[name].html
    text = _visible(html)
    found = _BRANDISH.findall(text)
    assert found == (["Connect with Strava"] if name == "connect" else [])
    assert _STRAVA_THEN_CAPITAL.findall(text) == []
    for phrase in ("View on Strava", "Compatible with Strava"):
        assert phrase not in html, phrase


def test_the_brand_scan_can_see_a_planted_phrase() -> None:
    assert _BRANDISH.findall("<p>Powered by Strava</p>") == ["Powered by Strava"]
    assert _STRAVA_THEN_CAPITAL.findall("Strava Connect") == ["Strava C"]


# --- consent and policy texts -----------------------------------------------

ACTIVITY_CONSENT = (
    "The relay returns the Strava address of each activity a post lands on "
    "to your fitdocs, which writes it into the workout's page. It returns "
    "nothing else that Strava supplied."
)


def test_consent_text_is_one_fixed_text() -> None:
    consent = policy.consent_text()
    assert ACTIVITY_CONSENT in consent
    assert consent == policy.consent_text()
    assert len(consent) == 4


def test_consent_text_states_what_the_relay_will_and_will_not_do() -> None:
    text = " ".join(policy.consent_text())
    for needed in (
        "start time, sport, distance and duration",
        "name and description",
        "only if you have enabled uploads",
        "will never read your activities for another purpose",
        "store or show them",
        "share this access",
        "fitdocs disconnect",
    ):
        assert needed in text, needed


def test_the_connect_page_shows_the_consent_text() -> None:
    assert escape(ACTIVITY_CONSENT) in _connect()


EXPECTED_HEADINGS = (
    "The relay's operator",
    "What fitdocs sends",
    "What the relay receives from Strava and keeps",
    "What the relay sends to Strava",
    "What the relay returns to fitdocs",
    "Deletion",
    "Your choices",
    "Security",
    "Contact",
)
RETURNS = "What the relay returns to fitdocs"


def test_policy_sections_are_the_designed_headings_in_order() -> None:
    assert policy.POLICY_HEADINGS == EXPECTED_HEADINGS
    sections = policy.policy_sections()
    assert tuple(h for h, _ in sections) == EXPECTED_HEADINGS
    assert all(text.strip() for _, text in sections)


def test_the_returns_section_says_the_relay_returns_the_activity_address() -> None:
    returns = dict(policy.policy_sections())[RETURNS]
    assert "Strava address of the activity it landed on" in returns
    assert "It returns nothing else that Strava supplied." in returns


def test_the_privacy_page_lists_the_sections_in_order_and_names_the_operator() -> None:
    html = pages.privacy_page(OPERATOR).html
    headings = [h.replace("&#x27;", "'") for h in re.findall(r"<h2>(.*?)</h2>", html)]
    assert tuple(headings) == EXPECTED_HEADINGS
    assert html.count("Operator: Operator Sentinel") == 1
    assert html.count(f"Support contact: {CONTACT}") == 1
    for _, text in policy.policy_sections():
        assert escape(text) in html


# --- next steps and policy statements ---------------------------------------


def test_the_invalid_code_and_refused_pages_carry_their_next_step() -> None:
    invalid = _visible(pages.invalid_code_page(OPERATOR).html)
    refused = _visible(pages.refused_page(OPERATOR).html)
    assert "Start again from fitdocs to get a new code." in invalid
    assert "To try again, start again from fitdocs." in refused


SHARED_POLICY = {
    "The relay's operator": (
        "This relay is a service that publishes workouts from "
        "fitdocs to Strava on your behalf. It is operated by the "
        "person or organization named below."
    ),
    "What fitdocs sends": (
        "When you publish a workout, your fitdocs sends the relay "
        "the workout's start time, sport, distance and duration, "
        "the name and description to set, an identifier fitdocs "
        "made for the publication, and, only when you have enabled "
        "uploads, the workout's file. Each request carries the "
        "relay token that identifies you to the relay."
    ),
    "What the relay receives from Strava and keeps": (
        "When you connect, Strava gives the relay an access token "
        "and a refresh token for your account, with the time the "
        "access token expires. The relay keeps the tokens "
        "encrypted and that time beside them, with a keyed hash of "
        "your Strava account (not the account identifier itself) "
        "and the identifiers and match facts that fitdocs sent for "
        "your publications. It keeps nothing else from Strava: no "
        "activities, activity identifiers, athlete identifiers, "
        "profile details or copies of any answer. Anything else "
        "Strava returns to a request is used inside that request "
        "and then dropped."
    ),
    "What the relay sends to Strava": (
        "When you connect, the relay sends Strava the "
        "authorization code it received, to exchange it for "
        "tokens. To act on your account it sends Strava your "
        "access token, sends your refresh token to renew the "
        "access token when it is about to expire, and, when a "
        "disconnect request reaches it and its call budget allows, "
        "sends your refresh token to ask Strava to revoke the "
        "relay's access. It asks Strava to list your activities so "
        "that it can find the one that matches a published workout "
        "by start time, sport, distance and duration, sets that "
        "activity's name and description, and, only with uploads "
        "enabled, creates one by uploading the workout's file with "
        "the name and description and the publication's identifier "
        "as the upload's external identifier, then asks Strava for "
        "the upload's status a limited number of times within the "
        "request's deadline. It changes no other field and deletes "
        "nothing on Strava. It reads activities for no other "
        "purpose."
    ),
    "Deletion": (
        "The relay deletes your Strava tokens and the records of "
        "your publications at once in each of these cases: you "
        "disconnect; Strava reports that you revoked the relay's "
        "access, in your Strava settings or by removing the "
        "application, which it delivers as a deauthorization "
        "event; Strava refuses to renew the connection's tokens; "
        "or your relay account is deleted."
    ),
    "Your choices": (
        "The command fitdocs disconnect withdraws the connection: "
        "when the relay's call budget allows, it also asks Strava "
        "to revoke the relay's access. Revoking the relay's access "
        "in your Strava settings also ends the connection. You can "
        "use fitdocs without this relay."
    ),
    "Security": (
        "Strava tokens are encrypted before they are stored, and "
        "the relay writes no Strava token, authorization code or "
        "response into its logs. If a breach affects your data, "
        "the operator will notify Strava within 24 hours."
    ),
    "Contact": (
        "Questions about this policy or your data go to the "
        "operator's support contact shown on this page."
    ),
}
RETURNS_TEXT = (
    "For each workout that fitdocs publishes and the relay posts "
    "or uploads, the relay returns to your fitdocs the Strava "
    "address of the activity it landed on, and your fitdocs writes "
    "that address into the workout's page. It returns nothing else "
    "that Strava supplied. The relay does not record the address "
    "it returned."
)
CONSENT_FIRST = (
    "By continuing, you let this relay act on your Strava account "
    "for fitdocs. For each workout you publish with fitdocs, the "
    "relay will find the matching activity by start time, sport, "
    "distance and duration, set its name and description, and, "
    "only if you have enabled uploads, create one from the "
    "workout's file."
)
CONSENT_THIRD = (
    "The relay will never read your activities for another "
    "purpose, store or show them, share this access, or change "
    "anything else on your account."
)
CONSENT_FOURTH = (
    "The command fitdocs disconnect withdraws the connection at "
    "any time, and so does revoking access in your Strava settings."
)


def test_every_policy_section_is_pinned_word_for_word() -> None:
    expected = {**SHARED_POLICY, RETURNS: RETURNS_TEXT}
    assert policy.policy_sections() == tuple(
        (heading, expected[heading]) for heading in EXPECTED_HEADINGS
    )


def test_every_consent_paragraph_is_pinned_word_for_word() -> None:
    assert policy.consent_text() == (
        CONSENT_FIRST,
        ACTIVITY_CONSENT,
        CONSENT_THIRD,
        CONSENT_FOURTH,
    )


# --- statuses and headers ---------------------------------------------------


def test_page_statuses() -> None:
    built = _all_pages(OPERATOR)
    assert {name: page.status for name, page in built.items()} == {
        "connect": 200,
        "in_use": 409,
        "invalid_code": 404,
        "granted": 200,
        "refused": 200,
        "try_later": 429,
        "unavailable": 503,
        "privacy": 200,
    }


def test_page_headers() -> None:
    assert dict(pages.PAGE_HEADERS) == {
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; "
            "form-action 'none'; base-uri 'none'"
        ),
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


# --- every page's title and visible text ------------------------------------


class _Lines(HTMLParser):
    """The visible text lines of a page: stylesheet and <title> left out."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.title: list[str] = []
        self._in: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._in = tag

    def handle_endtag(self, tag: str) -> None:
        self._in = None

    def handle_data(self, data: str) -> None:
        if self._in == "title":
            self.title.append(data)
        elif self._in != "style" and data.strip():
            self.lines.append(data.strip())


def _parsed(html: str) -> _Lines:
    parser = _Lines()
    parser.feed(html)
    parser.close()
    return parser


FOOTER = ["Privacy policy", f"Support: {CONTACT}"]

SIMPLE_TEXT: dict[str, tuple[str, list[str]]] = {
    "in_use": (
        "This code is in use",
        [
            "Another browser has already opened this code.",
            "If that was not you, close this page and start again from fitdocs.",
        ],
    ),
    "invalid_code": (
        "This code does not work",
        [
            "The code is not valid, has expired, or has already been used.",
            "Start again from fitdocs to get a new code.",
        ],
    ),
    "granted": (
        "Connected",
        ["Return to your terminal; fitdocs will finish connecting there."],
    ),
    "refused": (
        "Not connected",
        [
            "The connection was not completed, and no Strava access was stored.",
            "To try again, start again from fitdocs.",
        ],
    ),
    "try_later": (
        "Try again later",
        ["Too many requests just now.", "Wait a little and open the link again."],
    ),
    "unavailable": (
        "Not available",
        ["This part of the relay is not available right now."],
    ),
}


@pytest.mark.parametrize("name", list(SIMPLE_TEXT))
def test_each_simple_page_shows_exactly_its_title_and_paragraphs(name: str) -> None:
    title, paragraphs = SIMPLE_TEXT[name]
    parsed = _parsed(SIMPLE[name](OPERATOR).html)
    assert "".join(parsed.title) == title
    assert parsed.lines == [title, *paragraphs, *FOOTER]


def test_the_connect_page_shows_exactly_its_text() -> None:
    html = pages.connect_page(
        user_code=USER_CODE, authorize_url=AUTH_URL, operator=OPERATOR
    ).html
    parsed = _parsed(html)
    assert "".join(parsed.title) == "Connect fitdocs"
    assert parsed.lines == [
        "Connect fitdocs",
        USER_CODE,
        "Continue only if the terminal where you started fitdocs shows this same code.",
        CONSENT_FIRST,
        ACTIVITY_CONSENT,
        CONSENT_THIRD,
        CONSENT_FOURTH,
        "Connect with Strava",
        *FOOTER,
    ]


def test_the_privacy_page_shows_exactly_its_text() -> None:
    parsed = _parsed(pages.privacy_page(OPERATOR).html)
    assert "".join(parsed.title) == "Privacy policy"
    expected = {**SHARED_POLICY, RETURNS: RETURNS_TEXT}
    lines = ["Privacy policy"]
    for heading in EXPECTED_HEADINGS:
        lines += [heading, expected[heading]]
        if heading == "The relay's operator":
            lines.append("Operator: Operator Sentinel")
        if heading == "Contact":
            lines.append(f"Support contact: {CONTACT}")
    assert parsed.lines == [*lines, *FOOTER]
