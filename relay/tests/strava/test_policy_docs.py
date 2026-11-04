"""The Strava section of `docs/relay.md` checked against the code (strava-publish
Requirements 16.1, 17.2).

The page's `## The Strava target` section must keep its subsections in order and
its policy summary must list the policy's sections in the policy's order. The
page must name no hosting or email provider, use only the allowed brand phrases,
and state the upload bound the code enforces. Each check is a function over page
text, so the mutations at the foot of the file can feed it an altered page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs_relay.routes import ROUTE_BODY_LIMITS
from fitdocs_relay.shared.relay_targets import MAX_UPLOAD_REQUEST_BYTES
from fitdocs_relay.strava.policy import POLICY_HEADINGS

PAGE = Path(__file__).resolve().parents[3] / "docs" / "relay.md"
STRAVA_HEADING = "## The Strava target"

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
