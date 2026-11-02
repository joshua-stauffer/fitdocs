"""The Strava call budget: every call is counted before it is made.

The application's overall and non-upload ("read") limits, per quarter hour and
per day, are counted in the configured database, each call also against the
calling principal's share of them (Requirements 9.2, 9.7). Resolving links
leaves a share of the non-upload windows unspent (9.5), an upload is reserved
together with the calls its flow may follow it with (9.3), and a window Strava
says is spent is marked so (9.4).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from enum import StrEnum
from fractions import Fraction
from typing import Final

from fitdocs_relay.storage.interface import BudgetCharge, BudgetDecision, BudgetStore
from fitdocs_relay.strava.config import Limits

SHORT_WINDOW_S: Final = 900
DAY_WINDOW_S: Final = 86400

PRINCIPAL_SHARE: Final = 0.5
LINK_HEADROOM: Final = 0.2


class CallKind(StrEnum):
    READ = "read"
    UPLOAD = "upload"


def application_key(scope: str, window_s: int) -> str:
    """`strava:all:900`, `strava:read:86400`, ..."""
    return f"strava:{scope}:{window_s}"


def principal_key(principal_id: str, scope: str, window_s: int) -> str:
    """`strava:p:<principal>:all:900`, ..."""
    return f"strava:p:{principal_id}:{scope}:{window_s}"


def _floor_of(limit: int, *factors: float) -> int:
    """floor(limit x factors...), exact: each factor is read as its decimal text."""
    value = Fraction(limit)
    for factor in factors:
        value *= Fraction(str(factor))
    return math.floor(value)


class StravaBudget:
    def __init__(
        self, storage: BudgetStore, limits: Limits, *, clock: Callable[[], int]
    ) -> None:
        self._storage = storage
        self._limits = limits
        self._clock = clock

    def _limit(self, scope: str, window_s: int) -> int:
        short = window_s == SHORT_WINDOW_S
        if scope == "all":
            return self._limits.overall_15m if short else self._limits.overall_day
        return self._limits.read_15m if short else self._limits.read_day

    def _charges(
        self,
        principal_id: str,
        *,
        uploads: int,
        reads: int,
        for_link: bool,
    ) -> tuple[BudgetCharge, ...]:
        """The charges of `uploads` upload calls and `reads` non-upload calls.

        Every call counts against the overall windows; only a non-upload call
        counts against the non-upload ones. A zero amount is left out."""
        charges: list[BudgetCharge] = []
        for scope, amount in (("all", uploads + reads), ("read", reads)):
            if amount < 1:
                continue
            for window_s in (SHORT_WINDOW_S, DAY_WINDOW_S):
                limit = self._limit(scope, window_s)
                headroom = for_link and scope == "read"
                application = _floor_of(limit, 1 - LINK_HEADROOM) if headroom else limit
                if headroom:
                    own = _floor_of(limit, PRINCIPAL_SHARE, 1 - LINK_HEADROOM)
                else:
                    own = max(1, _floor_of(limit, PRINCIPAL_SHARE))
                charges.append(
                    BudgetCharge(
                        application_key(scope, window_s), window_s, application, amount
                    )
                )
                charges.append(
                    BudgetCharge(
                        principal_key(principal_id, scope, window_s),
                        window_s,
                        own,
                        amount,
                        principal_id,
                    )
                )
        return tuple(charges)

    def _spend(self, charges: tuple[BudgetCharge, ...]) -> BudgetDecision:
        if any(c.amount > c.ceiling for c in charges):
            # No window will ever hold this much, so no wait is named.
            return BudgetDecision(False, None)
        return self._storage.spend_budget(charges, now=self._clock())

    def spend(
        self,
        principal_id: str,
        kind: CallKind = CallKind.READ,
        *,
        count: int = 1,
        for_link: bool = False,
    ) -> BudgetDecision:
        """Count `count` calls of `kind`, or none when any window would pass."""
        if count < 1:
            raise ValueError("a spend counts one call or more")
        upload = kind is CallKind.UPLOAD
        return self._spend(
            self._charges(
                principal_id,
                uploads=count if upload else 0,
                reads=0 if upload else count,
                for_link=for_link,
            )
        )

    def reserve_upload(self, principal_id: str, *, reads: int) -> BudgetDecision:
        """Count one upload and `reads` non-upload calls, all or none."""
        if reads < 0:
            raise ValueError("a reservation holds zero reads or more")
        return self._spend(
            self._charges(principal_id, uploads=1, reads=reads, for_link=False)
        )

    def mark_spent(self, *, daily: bool) -> None:
        """Raise the application's quarter-hour overall and non-upload windows
        to their limits, and the daily ones too when `daily`."""
        now = self._clock()
        windows = (SHORT_WINDOW_S, DAY_WINDOW_S) if daily else (SHORT_WINDOW_S,)
        for window_s in windows:
            for scope in ("all", "read"):
                self._storage.exhaust_budget(
                    key=application_key(scope, window_s),
                    window_s=window_s,
                    count=self._limit(scope, window_s),
                    now=now,
                )
