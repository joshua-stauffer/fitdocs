"""The scripted outbound fake: serves canned answers, records every request.

An `Outbound` stand-in for the whole relay suite, so no test reaches Strava.
A request nobody scripted raises `UnscriptedCall`, an `AssertionError`, so
it is never swallowed as a provider failure and never answered by default.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fitdocs_relay.outbound import OutboundError, OutboundRequest, OutboundResponse

Answer = OutboundResponse | OutboundError


class UnscriptedCall(AssertionError):
    """The code under test made a request the test did not script."""


@dataclass(frozen=True)
class Call:
    request: OutboundRequest
    timeout: float

    @property
    def form(self) -> dict[str, str]:
        assert self.request.body is not None
        return dict(parse_qsl(self.request.body.decode("ascii"), strict_parsing=True))


def reply(
    status: int,
    body: object = b"",
    headers: Mapping[str, str] | None = None,
) -> OutboundResponse:
    """A canned answer; a non-bytes body is encoded as JSON.

    Header names are lowercased, as the real outbound client delivers them.
    """
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    named = {name.lower(): value for name, value in (headers or {}).items()}
    return OutboundResponse(status, named, raw)


class ScriptedOutbound:
    def __init__(self) -> None:
        self.calls: list[Call] = []
        self._script: defaultdict[tuple[str, str], deque[Answer]] = defaultdict(deque)

    def expect(self, method: str, url: str, *answers: Answer) -> None:
        """Queue answers for `method url`; each serves one request, in order."""
        self._script[(method, url)].extend(answers)

    def __call__(self, request: OutboundRequest, timeout: float) -> OutboundResponse:
        self.calls.append(Call(request, timeout))
        queue = self._script.get((request.method, request.url))
        if not queue:
            raise UnscriptedCall(f"unscripted request: {request.method} {request.url}")
        answer = queue.popleft()
        if isinstance(answer, OutboundError):
            raise answer
        return answer

    def unserved(self) -> int:
        return sum(len(queue) for queue in self._script.values())
