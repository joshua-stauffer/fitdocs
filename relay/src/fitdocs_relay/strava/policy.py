"""The relay's privacy policy sections and consent text (fixed fitdocs wording).

Imports the standard library only at run time; `LinkSetting` is imported for
typing alone.
The two link settings differ in exactly one policy section and one consent
paragraph (Requirements 10.7, 16.1, 16.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from fitdocs_relay.strava.config import LinkSetting

POLICY_HEADINGS: Final[tuple[str, ...]] = (
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

_RETURNS_ACTIVITY: Final = (
    "For each workout that fitdocs publishes and the relay posts or uploads, "
    "the relay returns to your fitdocs the Strava address of the activity it "
    "landed on, and your fitdocs writes that address into the workout's page. "
    "It returns nothing else that Strava supplied. The relay does not record "
    "the address it returned."
)
_RETURNS_RELAY: Final = (
    "The relay returns nothing that Strava supplied to your fitdocs. The "
    "link on a workout's page points at the relay, which finds the activity "
    "when the link is opened and sends the browser there; it does not record "
    "what it found."
)
_CONSENT_RETURNS_ACTIVITY: Final = (
    "The relay returns the Strava address of each activity a post lands on "
    "to your fitdocs, which writes it into the workout's page. It returns "
    "nothing else that Strava supplied."
)
_CONSENT_RETURNS_RELAY: Final = (
    "The relay returns nothing that Strava supplied to your fitdocs."
)

_SHARED: Final[dict[str, str]] = {
    "The relay's operator": (
        "This relay is a service that publishes workouts from fitdocs to "
        "Strava on your behalf. It is operated by the person or organization "
        "named below."
    ),
    "What fitdocs sends": (
        "When you publish a workout, your fitdocs sends the relay the "
        "workout's start time, sport, distance and duration, the name and "
        "description to set, an identifier fitdocs made for the publication, "
        "and, only when you have enabled uploads, the workout's file. Each "
        "request carries the relay token that identifies you to the relay."
    ),
    "What the relay receives from Strava and keeps": (
        "When you connect, Strava gives the relay an access token and a "
        "refresh token for your account, with the time the access token "
        "expires. The relay keeps the tokens encrypted and that time beside "
        "them, with a keyed hash of your Strava account (not the account "
        "identifier itself) and the identifiers and match facts that fitdocs "
        "sent for your publications. It keeps nothing else from Strava: no "
        "activities, activity identifiers, athlete identifiers, profile "
        "details or copies of any answer. Anything else Strava returns to a "
        "request is used inside that request and then dropped."
    ),
    "What the relay sends to Strava": (
        "When you connect, the relay sends Strava the authorization code it "
        "received, to exchange it for tokens. To act on your account it sends "
        "Strava your access token, sends your refresh token to renew the "
        "access token when it is about to expire, and, when a disconnect "
        "request reaches it and its call budget allows, sends your refresh "
        "token to ask Strava to revoke the relay's access. It asks Strava to "
        "list your activities so that it can find the one that matches a "
        "published workout by start time, sport, distance and duration, sets "
        "that activity's name and description, and, only with uploads "
        "enabled, creates one by uploading the workout's file with the name "
        "and description and the publication's identifier as the upload's "
        "external identifier, then asks Strava for the upload's status a "
        "limited number of times within the request's deadline. It changes no "
        "other field and deletes nothing on Strava. It reads activities for no "
        "other purpose."
    ),
    "Deletion": (
        "The relay deletes your Strava tokens and the records of your "
        "publications at once in each of these cases: you disconnect; Strava "
        "reports that you revoked the relay's access, in your Strava settings "
        "or by removing the application, which it delivers as a "
        "deauthorization event; Strava refuses to renew the connection's "
        "tokens; or your relay account is deleted."
    ),
    "Your choices": (
        "The command fitdocs disconnect withdraws the connection: when the "
        "relay's call budget allows, it also asks Strava to revoke the relay's access. "
        "Revoking the relay's access in your Strava settings also ends the "
        "connection. You can use fitdocs without this relay."
    ),
    "Security": (
        "Strava tokens are encrypted before they are stored, and the relay writes no "
        "Strava token, authorization code or response into its logs. If a "
        "breach affects your data, the operator will notify Strava within 24 hours."
    ),
    "Contact": (
        "Questions about this policy or your data go to the operator's "
        "support contact shown on this page."
    ),
}


def _returns(links: LinkSetting, *, consent: bool) -> str:
    setting = links.value
    if setting == "activity":
        return _CONSENT_RETURNS_ACTIVITY if consent else _RETURNS_ACTIVITY
    if setting == "relay":
        return _CONSENT_RETURNS_RELAY if consent else _RETURNS_RELAY
    raise ValueError(f"unknown link setting: {setting!r}")


def policy_sections(links: LinkSetting) -> tuple[tuple[str, str], ...]:
    """(heading, text) for every policy section, in `POLICY_HEADINGS` order."""
    returns = _returns(links, consent=False)
    return tuple(
        (
            heading,
            returns
            if heading == "What the relay returns to fitdocs"
            else _SHARED[heading],
        )
        for heading in POLICY_HEADINGS
    )


def consent_text(links: LinkSetting) -> tuple[str, ...]:
    """The paragraphs shown on the connect page before the Connect control."""
    return (
        "By continuing, you let this relay act on your Strava account for "
        "fitdocs. For each workout you publish with fitdocs, the relay will "
        "find the matching activity by start time, sport, distance and "
        "duration, set its name and description, and, only if you have "
        "enabled uploads, create one from the workout's file.",
        _returns(links, consent=True),
        "The relay will never read your activities for another purpose, "
        "store or show them, share this access, or change anything else on "
        "your account.",
        "The command fitdocs disconnect withdraws the connection at any time, and so "
        "does revoking access in your Strava settings.",
    )
