"""The Strava publisher: publish a post onto the activity that is a page's session.

A request has one deadline. Every Strava call is counted against the budget
first (unless the deadline has already passed, when the call is not made and not
counted) and made with the shorter of the per-call timeout and the time left.
The publish flow lists around the page's start, picks the one activity the
strict rule matches, updates its name and description once (repeated once,
identically, after a server or network failure), and records the publication
if the connection exists just before the write. A withdrawal after that check
can still leave a record.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_targets import STRAVA, PublishFacts
from fitdocs_relay.storage.interface import Publication, Storage
from fitdocs_relay.strava.api import (
    Candidate,
    Failure,
    Step,
    StravaApi,
    StravaFailure,
)
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import StravaConfig
from fitdocs_relay.strava.custody import Custody, Usable
from fitdocs_relay.strava.resolve import LIST_PAGE_SIZE, Pick, list_window, pick

__all__ = [
    "CALL_TIMEOUT_S",
    "PUBLISH_DEADLINE_S",
    "STEP_OUTCOMES",
    "Landed",
    "StravaPublisher",
    "activity_page",
]

PUBLISH_DEADLINE_S: Final = 20.0
CALL_TIMEOUT_S: Final = 8.0

_P = PublishCode
_F = Failure
_S = Step

# One row of design.md's step-outcome table per (step, failure); a budget
# refusal is read as LIMITED. An update that answered 2xx is posted whatever
# its body held, so the table has no (update, unreadable) row.
_ROWS: Final[Mapping[Failure, tuple[PublishCode | None, ...]]] = {
    # list, update, upload, upload-status, refresh
    _F.AUTH: (
        _P.AUTH_REJECTED,
        _P.AUTH_REJECTED,
        _P.AUTH_REJECTED,
        _P.UNCONFIRMED,
        _P.AUTH_REJECTED,
    ),
    _F.FORBIDDEN: (
        _P.PERMISSION_DENIED,
        _P.PERMISSION_DENIED,
        _P.PERMISSION_DENIED,
        _P.UNCONFIRMED,
        _P.AUTH_REJECTED,
    ),
    _F.MISSING: (
        _P.UNAVAILABLE,
        _P.NOT_UPDATABLE,
        _P.REJECTED,
        _P.UNCONFIRMED,
        _P.UNAVAILABLE,
    ),
    _F.LIMITED: (
        _P.RATE_LIMITED,
        _P.RATE_LIMITED,
        _P.RATE_LIMITED,
        _P.UNCONFIRMED,
        _P.RATE_LIMITED,
    ),
    _F.INVALID: (
        _P.UNAVAILABLE,
        _P.REJECTED,
        _P.REJECTED,
        _P.UNCONFIRMED,
        _P.AUTH_REJECTED,
    ),
    _F.SERVER: (
        _P.UNAVAILABLE,
        _P.UNAVAILABLE,
        _P.UNCONFIRMED,
        _P.UNCONFIRMED,
        _P.UNAVAILABLE,
    ),
    _F.NETWORK: (
        _P.UNAVAILABLE,
        _P.UNAVAILABLE,
        _P.UNCONFIRMED,
        _P.UNCONFIRMED,
        _P.UNAVAILABLE,
    ),
    _F.UNREADABLE: (
        _P.UNAVAILABLE,
        None,
        _P.UNCONFIRMED,
        _P.UNCONFIRMED,
        _P.UNAVAILABLE,
    ),
}
_COLUMNS: Final = (_S.LIST, _S.UPDATE, _S.UPLOAD, _S.UPLOAD_STATUS, _S.REFRESH)
STEP_OUTCOMES: Final[Mapping[tuple[Step, Failure], PublishCode]] = MappingProxyType(
    {
        (step, failure): code
        for failure, row in _ROWS.items()
        for step, code in zip(_COLUMNS, row, strict=True)
        if code is not None
    }
)


@dataclass(frozen=True)
class Landed:
    """A post that landed (POSTED or UPLOADED) and the activity page it landed on."""

    code: PublishCode
    activity_page: str = field(repr=False)


def activity_page(web_url: str, activity_id: str) -> str:
    """The address of an activity's page: ``<web_url>/activities/<id>``."""
    return f"{web_url}/activities/{activity_id}"


class StravaPublisher:
    def __init__(
        self,
        storage: Storage,
        custody: Custody,
        api: StravaApi,
        budget: StravaBudget,
        config: StravaConfig,
        *,
        clock: Callable[[], int],
        monotonic: Callable[[], float],
    ) -> None:
        self._storage = storage
        self._custody = custody
        self._api = api
        self._budget = budget
        self._web_url = config.web_url
        self._clock = clock
        self._monotonic = monotonic

    def publish(self, principal_id: str, facts: PublishFacts) -> PublishCode | Landed:
        deadline = self._monotonic() + PUBLISH_DEADLINE_S
        refused = self._common_start(principal_id, facts)
        if refused is not None:
            return refused
        access = self._custody.access_token(principal_id, deadline=deadline)
        if not isinstance(access, Usable):
            return access
        found = self._find(principal_id, access.access, facts, deadline)
        if not isinstance(found, Candidate):
            return found
        failure = self._update(principal_id, access.access, found, facts, deadline)
        if failure is not None:
            return failure
        self._record(principal_id, facts)
        return Landed(_P.POSTED, activity_page(self._web_url, found.activity_id))

    # --- the common start ------------------------------------------------

    def _common_start(
        self, principal_id: str, facts: PublishFacts
    ) -> PublishCode | None:
        if facts.elapsed_s is None and facts.distance_m is None:
            return _P.ACTIVITY_FACTS_MISSING
        known = self._storage.get_publication(STRAVA, facts.publication_id)
        if known is not None and known.principal_id != principal_id:
            return _P.REJECTED
        return None

    # --- the steps -----------------------------------------------------------

    def _timeout(self, deadline: float) -> float | None:
        left = min(CALL_TIMEOUT_S, deadline - self._monotonic())
        return left if left > 0 else None

    def _find(
        self, principal_id: str, access: str, facts: PublishFacts, deadline: float
    ) -> Candidate | PublishCode:
        timeout = self._timeout(deadline)
        if timeout is None:
            return _P.UNAVAILABLE
        if not self._budget.spend(principal_id).allowed:
            return STEP_OUTCOMES[(_S.LIST, _F.LIMITED)]
        after, before = list_window(facts.start)
        listing = self._api.list_activities(
            access, after=after, before=before, per_page=LIST_PAGE_SIZE, timeout=timeout
        )
        if isinstance(listing, StravaFailure):
            return self._failed(listing)
        picked = pick(facts, listing)
        if picked is Pick.NONE:
            return _P.NOT_FOUND
        if picked is Pick.MANY:
            return _P.AMBIGUOUS
        return picked

    def _update(
        self,
        principal_id: str,
        access: str,
        found: Candidate,
        facts: PublishFacts,
        deadline: float,
    ) -> PublishCode | None:
        """None once the activity is updated, else the code that ends the request."""
        for attempt in (1, 2):
            timeout = self._timeout(deadline)
            if timeout is None:
                return _P.UNAVAILABLE
            if not self._budget.spend(principal_id).allowed:
                return STEP_OUTCOMES[(_S.UPDATE, _F.LIMITED)]
            answer = self._api.update_activity(
                access,
                found.activity_id,
                name=facts.title,
                description=facts.description,
                timeout=timeout,
            )
            if answer is None:
                return None
            repeatable = answer.failure in (_F.SERVER, _F.NETWORK)
            if attempt == 2 or not repeatable:
                return self._failed(answer)
        raise AssertionError("unreachable")  # pragma: no cover

    def _failed(self, failure: StravaFailure) -> PublishCode:
        if failure.failure is _F.LIMITED:
            self._budget.mark_spent(daily=failure.daily_spent)
        return STEP_OUTCOMES[(failure.step, failure.failure)]

    def _record(self, principal_id: str, facts: PublishFacts) -> None:
        """Write the link record if the connection still exists just before the
        write. A connection withdrawn before that check leaves no record; one
        withdrawn between the check and the write can still leave one (closing
        that gap needs a storage-level write, not done here)."""
        if self._storage.get_connection(principal_id, STRAVA) is None:
            return
        self._storage.put_publication(
            Publication(
                STRAVA,
                facts.publication_id,
                principal_id,
                facts.sport,
                facts.start.timestamp(),
                facts.elapsed_s,
                facts.distance_m,
            ),
            now=self._clock(),
        )
