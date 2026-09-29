"""Keep secret text out of every string fitdocs shows (Requirements 10.1-10.3).

:class:`Secret` wraps one credential, token, or signed-download value so that
its ordinary text forms -- ``str()``, ``repr()``, and an f-string or
``format()`` call -- never show the underlying value, only the shared
:data:`REDACTED` marker. The only way to read the value back is
:meth:`Secret.reveal`.

:class:`Redactor` is the per-command-invocation scrubber: every stored or
environment credential value, every token, every secret header, and every
signed URL the run touches is registered with one ``Redactor``, and every
string that reaches a report -- connector reasons, exception text, service
messages -- is passed through :meth:`Redactor.redact` before it is printed.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

REDACTED: Final[str] = "<redacted>"


class Secret:
    """Holds one secret string; text forms never reveal it."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"Secret value must be a str, got {type(value).__name__}")
        self._value = value

    def reveal(self) -> str:
        """The only way to read the underlying value back out."""
        return self._value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return REDACTED

    def __repr__(self) -> str:
        return REDACTED

    def __format__(self, format_spec: str) -> str:
        # The marker whatever the spec: never the value, never a truncated
        # marker (a precision spec), never a ValueError (a numeric spec).
        return REDACTED


class Redactor:
    """Registers secret values and scrubs them out of arbitrary text."""

    def __init__(self) -> None:
        self._values: set[str] = set()

    def add(self, value: str | Secret) -> None:
        """Register a value (and its percent-encoded form, if different).

        The empty string is ignored: registering it would make ``redact``
        match every position in every string.
        """
        raw = value.reveal() if isinstance(value, Secret) else value
        if raw == "":
            return
        self._values.add(raw)
        encoded = quote(raw, safe="")
        if encoded != raw:
            self._values.add(encoded)

    def redact(self, text: str) -> str:
        """Replace every registered value in ``text``, longest first.

        Longest-first ordering matters when one registered value is a
        substring of another: replacing the shorter one first would leave
        the longer value's remaining tail exposed in the output.
        """
        for value in sorted(self._values, key=len, reverse=True):
            text = text.replace(value, REDACTED)
        return text
