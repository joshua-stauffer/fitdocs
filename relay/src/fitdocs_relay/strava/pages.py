"""The fitdocs-written HTML pages of the Strava target.

Imports the standard library and `strava.policy` only. Every operator-configured or
generated string that a page interpolates passes through `_e` (the values are
configuration or values fitdocs generated or validated; Requirements 12.4,
16.3). Fixed wording is escaped like every other text; only the markup, the
stylesheet and the control's numeric height are written as they are.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from typing import Final

from fitdocs_relay.strava.policy import consent_text, policy_sections

BUILT_IN_POLICY_PATH: Final = "/privacy"
CONNECT_CONTROL_HEIGHT_PX: Final = 48
CONNECT_PHRASE: Final = "Connect with Strava"

PAGE_HEADERS: Final[Mapping[str, str]] = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; "
        "form-action 'none'; base-uri 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}

_STYLE: Final = (
    "body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;"
    "padding:0 1rem;line-height:1.5}"
    ".code{font-size:2rem;font-weight:bold;letter-spacing:.2em}"
    "footer{margin-top:2rem;font-size:.9rem}"
)


@dataclass(frozen=True)
class Page:
    status: int
    html: str


@dataclass(frozen=True)
class Operator:
    name: str
    support_contact: str
    policy_url: str | None
    terms_url: str | None


def _e(value: str) -> str:
    return escape(value, quote=True)


def policy_address(operator: Operator) -> str:
    """The operator's own policy address, else the built-in one."""
    return operator.policy_url if operator.policy_url else BUILT_IN_POLICY_PATH


def _footer(operator: Operator) -> str:
    terms = (
        f'<p><a href="{_e(operator.terms_url)}">Terms of use</a></p>'
        if operator.terms_url
        else ""
    )
    return (
        "<footer>"
        f'<p><a href="{_e(policy_address(operator))}">Privacy policy</a></p>'
        f"{terms}"
        f"<p>Support: {_e(operator.support_contact)}</p>"
        "</footer>"
    )


def _document(title: str, body: str, operator: Operator, status: int) -> Page:
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main><h1>{_e(title)}</h1>{body}</main>{_footer(operator)}</body></html>"
    )
    return Page(status, html)


def _message(
    status: int, title: str, paragraphs: tuple[str, ...], operator: Operator
) -> Page:
    body = "".join(f"<p>{_e(p)}</p>" for p in paragraphs)
    return _document(title, body, operator, status)


def connect_page(*, user_code: str, authorize_url: str, operator: Operator) -> Page:
    consent = "".join(f"<p>{_e(p)}</p>" for p in consent_text())
    terms = (
        "<p>By connecting, you accept the "
        f'<a href="{_e(operator.terms_url)}">terms of use</a>.</p>'
        if operator.terms_url
        else ""
    )
    body = (
        f'<p class="code">{_e(user_code)}</p>'
        "<p>Continue only if the terminal where you started fitdocs shows "
        "this same code.</p>"
        f'<section id="consent">{consent}</section>'
        f"{terms}"
        f'<p><a class="connect" href="{_e(authorize_url)}" '
        'style="display:inline-block;box-sizing:border-box;'
        f"height:{CONNECT_CONTROL_HEIGHT_PX}px;line-height:{CONNECT_CONTROL_HEIGHT_PX}px;"
        "padding:0 24px;border:1px solid #333;border-radius:4px;"
        f'text-decoration:none">{_e(CONNECT_PHRASE)}</a></p>'
    )
    return _document("Connect fitdocs", body, operator, 200)


def in_use_page(operator: Operator) -> Page:
    return _message(
        409,
        "This code is in use",
        (
            "Another browser has already opened this code.",
            "If that was not you, close this page and start again from fitdocs.",
        ),
        operator,
    )


def invalid_code_page(operator: Operator) -> Page:
    return _message(
        404,
        "This code does not work",
        (
            "The code is not valid, has expired, or has already been used.",
            "Start again from fitdocs to get a new code.",
        ),
        operator,
    )


def granted_page(operator: Operator) -> Page:
    return _message(
        200,
        "Connected",
        ("Return to your terminal; fitdocs will finish connecting there.",),
        operator,
    )


def refused_page(operator: Operator) -> Page:
    return _message(
        200,
        "Not connected",
        (
            "The connection was not completed, and no Strava access was stored.",
            "To try again, start again from fitdocs.",
        ),
        operator,
    )


def try_later_page(operator: Operator) -> Page:
    return _message(
        429,
        "Try again later",
        ("Too many requests just now.", "Wait a little and open the link again."),
        operator,
    )


def unavailable_page(operator: Operator) -> Page:
    return _message(
        503,
        "Not available",
        ("This part of the relay is not available right now.",),
        operator,
    )


def privacy_page(operator: Operator) -> Page:
    parts: list[str] = []
    for heading, text in policy_sections():
        extra = ""
        if heading == "The relay's operator":
            extra = f"<p>Operator: {_e(operator.name)}</p>"
        elif heading == "Contact":
            extra = f"<p>Support contact: {_e(operator.support_contact)}</p>"
        parts.append(
            f"<section><h2>{_e(heading)}</h2><p>{_e(text)}</p>{extra}</section>"
        )
    return _document("Privacy policy", "".join(parts), operator, 200)
