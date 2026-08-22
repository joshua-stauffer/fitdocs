"""The generic prompt flow and the two interaction sessions (Req 3.1-3.6).

This module holds everything front-end about collecting missing athlete inputs
*without* knowing any methodology. :func:`collect_missing_fields` walks a
calculator's declared :class:`AthleteField`s, prompts only for the ones absent
from the profile (asked once, Req 3.3), and persists each accepted answer
immediately so a later crash loses nothing (Req 3.3). It presents each field's
meaning and valid range (Req 3.2); the *session* owns the re-ask-on-invalid
loop and hands back either a valid, in-range value or ``None`` -- the flow never
re-parses. A ``None`` answer means declined or non-interactive: the field stays
missing, nothing is persisted, nothing is substituted, and the flow moves on
(Req 3.4, 3.5). An optional per-field confirm *hint* lets a methodology echo
derived context after a valid answer -- e.g. a calculator that derives a
threshold from a recorded race time might echo that time back for the user
to sanity-check (Req 3.6); the user may re-enter, and a declined confirmation
leaves the field missing.

Two sessions ship here. :class:`RichInteractionSession` is the interactive,
terminal-backed implementation: it re-asks on unparseable or out-of-range
input, documents a ``s``/``skip`` decline keyword in every prompt, and -- so
tests never need a real TTY -- reads its raw input through an injectable
callable. It never probes the environment; the CLI decides interactivity and
constructs the right session. :class:`NonInteractiveSession` answers nothing:
every ask/confirm/choose returns ``None`` and ``inform`` is a no-op, so a
non-interactive pass never blocks and never fabricates consent (Req 3.5, 9.1).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from rich.console import Console

from fitdocs.load.profile import AthleteProfile
from fitdocs.load.types import AthleteField, InteractionSession

if TYPE_CHECKING:  # annotation-only -- this module reads no clock (Req 8's
    # prompt-flow invariant): `on` is supplied by the caller, never resolved
    # here.
    from datetime import date

__all__ = [
    "NonInteractiveSession",
    "RichInteractionSession",
    "collect_missing_fields",
]

_NO_HINTS: Final[Mapping[str, Callable[[float], str]]] = MappingProxyType({})
"""Immutable empty default for ``hints`` -- avoids a B006 mutable default."""

_SKIP_KEYWORDS: Final[frozenset[str]] = frozenset({"s", "skip"})
"""Typed at any interactive prompt, these decline the field (return ``None``)."""

_SKIP_NOTE: Final[str] = "(type 's' to skip)"
"""Documents the decline keyword in every interactive prompt's text (Req 3.4)."""

_INPUT_PROMPT: Final[str] = "> "
"""The short line the interactive session reads a raw answer against."""


def collect_missing_fields(
    fields: Sequence[AthleteField],
    profile: AthleteProfile,
    session: InteractionSession,
    persist: Callable[[AthleteProfile], None],
    hints: Mapping[str, Callable[[float], str]] = _NO_HINTS,
    *,
    on: date,
) -> tuple[AthleteProfile, tuple[AthleteField, ...]]:
    """Prompt for each missing declared field; return (updated profile, still-missing).

    ``on`` is the date the pass is running -- the date an accepted benchmark
    answer is recorded as measured (Req 6.2). It is supplied by the caller;
    this module never reads a clock itself.

    For every ``field`` in declaration order:

    * The "already have it" check branches on whether ``field`` declares a
      benchmark (``field.benchmark is not None``). A benchmark field's
      presence is ``profile.has_benchmark(ref.kind, discipline=ref.discipline)``
      -- undated, so a benchmark already on file is never re-asked, even while
      processing an activity no entry on file applies to (Req 8.3, 8.4). A
      flat field keeps the existing ``profile.get_number(field.key)`` check.
      Either way, present means skipped -- asked once (Req 3.3, 8.1, 8.2).
    * Otherwise the field is prompted through ``session`` (``int`` -> ``ask_int``,
      ``float`` -> ``ask_float``) with a question that presents the field's
      meaning and valid range (Req 3.2). The session owns re-asking on invalid
      input and returns either a valid in-range value or ``None``.
    * A ``None`` answer means declined or non-interactive: the field is appended
      to the still-missing list, nothing is persisted, nothing is substituted,
      and the flow continues (Req 3.4, 3.5, 8.5, 8.6).
    * On a valid value, if a ``hints`` entry exists for ``field.key`` the derived
      context is echoed via ``session.inform`` and confirmed (Req 3.6): a ``No``
      re-asks the field from the top, a ``None`` is treated as a decline, and a
      ``Yes`` accepts.
    * On acceptance, a benchmark field is stored via
      ``profile.with_benchmark(ref.kind, discipline=ref.discipline, value=value,
      measured_on=on)``; a flat field keeps ``profile.with_value``. Either way
      ``persist`` is invoked immediately (Req 3.3, 8.7) so a later crash loses
      nothing; the updated profile is threaded forward so later fields see
      earlier answers.

    Returns the updated profile and the tuple of fields still missing afterward.
    """
    still_missing: list[AthleteField] = []
    for field in fields:
        ref = field.benchmark
        already_have_it = (
            profile.has_benchmark(ref.kind, discipline=ref.discipline)
            if ref is not None
            else profile.get_number(field.key) is not None
        )
        if already_have_it:
            continue  # already have it -- ask once (Req 3.3, 8.2, 8.3)
        value = _prompt_until_accepted(field, session, hints.get(field.key))
        if value is None:
            still_missing.append(field)  # declined / non-interactive (Req 3.4, 3.5)
            continue
        if ref is not None:
            profile = profile.with_benchmark(
                ref.kind, discipline=ref.discipline, value=value, measured_on=on
            )
        else:
            profile = profile.with_value(field, value)
        persist(profile)  # immediate persistence per accepted answer (Req 3.3, 8.7)
    return profile, tuple(still_missing)


def _prompt_until_accepted(
    field: AthleteField,
    session: InteractionSession,
    hint: Callable[[float], str] | None,
) -> int | float | None:
    """Prompt for ``field`` (with optional confirm-hint) until accepted or declined.

    Returns the accepted value, or ``None`` when the field is declined -- either
    the ask itself was declined/non-interactive, or (when a ``hint`` is present)
    the user declined the derived-context confirmation. A ``No`` at the
    confirmation re-asks the field from the top (Req 3.6).
    """
    question = _compose_question(field)
    while True:
        value = _ask(field, question, session)
        if value is None:
            return None  # declined / non-interactive -- do not compute
        if hint is None:
            return value
        session.inform(hint(float(value)))
        confirmed = session.confirm(
            f"Does the entered {field.label} match your current fitness?",
            default=True,
        )
        if confirmed is None:
            return None  # no confirmation given -- treat as decline
        if confirmed:
            return value
        # confirmed is False -> re-ask the field from the top (Req 3.6)


def _ask(
    field: AthleteField, question: str, session: InteractionSession
) -> int | float | None:
    """Route ``field`` to the session's typed ask; return its value or ``None``.

    Bounds are taken from the field (coerced to ``int`` for an ``int`` field) and
    no default is offered -- the session owns re-ask-on-invalid, so this returns
    exactly what the session returns.
    """
    if field.kind == "int":
        return session.ask_int(
            question,
            minimum=None if field.minimum is None else int(field.minimum),
            maximum=None if field.maximum is None else int(field.maximum),
        )
    return session.ask_float(
        question,
        minimum=field.minimum,
        maximum=field.maximum,
    )


def _compose_question(field: AthleteField) -> str:
    """Build a prompt presenting the field's label, meaning, and range (Req 3.2)."""
    text = field.label
    if field.help_text:
        text = f"{text} — {field.help_text}"
    span = _range_text(field)
    if span:
        text = f"{text} ({span})"
    return text


def _range_text(field: AthleteField) -> str:
    """Render the field's inclusive range, formatting int bounds without a decimal."""
    low = None if field.minimum is None else _format_bound(field, field.minimum)
    high = None if field.maximum is None else _format_bound(field, field.maximum)
    if low is not None and high is not None:
        return f"{low}–{high}"
    if low is not None:
        return f"≥ {low}"
    if high is not None:
        return f"≤ {high}"
    return ""


def _format_bound(field: AthleteField, bound: float) -> str:
    """Format a bound: bare integer for an ``int`` field, otherwise the value."""
    if field.kind == "int":
        return str(int(bound))
    return str(bound)


class RichInteractionSession:
    """Terminal-backed :class:`InteractionSession` with an injectable input source.

    Re-asks on unparseable or out-of-range input, re-showing the question and a
    helpful message each time, until a valid value or an explicit decline. A
    documented ``s``/``skip`` keyword declines any prompt (returns ``None``); an
    empty answer takes the offered default where one exists. Informational output
    (the question, its range, re-ask hints) goes through ``console`` so a test
    that captures the console's output can assert what was shown; the raw answer
    is read through ``input_fn`` so tests drive prompts without a real TTY. The
    session never probes the environment -- the CLI decides interactivity.
    """

    def __init__(
        self,
        console: Console | None = None,
        *,
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._console: Console = console or Console()
        self._input: Callable[[str], str] = input_fn or (
            lambda prompt: self._console.input(prompt)
        )

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        options = "[Y/n]" if default else "[y/N]"
        self._console.print(f"{question} {options} {_SKIP_NOTE}")
        while True:
            answer = self._input(_INPUT_PROMPT).strip().lower()
            if answer in _SKIP_KEYWORDS:
                return None
            if answer == "":
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            self._console.print(f"Please answer yes or no. {_SKIP_NOTE}")

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        self._console.print(f"{question} {_SKIP_NOTE}")
        while True:
            answer = self._input(_INPUT_PROMPT).strip()
            if answer.lower() in _SKIP_KEYWORDS:
                return None
            if answer == "" and default is not None:
                return default
            try:
                value = int(answer)
            except ValueError:
                self._reask(f"{answer!r} is not a whole number.", question)
                continue
            if not _within(value, minimum, maximum):
                self._reask(_range_message(minimum, maximum), question)
                continue
            return value

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        self._console.print(f"{question} {_SKIP_NOTE}")
        while True:
            answer = self._input(_INPUT_PROMPT).strip()
            if answer.lower() in _SKIP_KEYWORDS:
                return None
            if answer == "" and default is not None:
                return default
            try:
                value = float(answer)
            except ValueError:
                self._reask(f"{answer!r} is not a number.", question)
                continue
            if not _within(value, minimum, maximum):
                self._reask(_range_message(minimum, maximum), question)
                continue
            return value

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        self._console.print(f"{question} {_SKIP_NOTE}")
        for index, option in enumerate(options, start=1):
            self._console.print(f"  {index}. {option}")
        while True:
            answer = self._input(_INPUT_PROMPT).strip()
            if answer.lower() in _SKIP_KEYWORDS:
                return None
            if answer == "" and default_index is not None:
                return default_index
            try:
                choice = int(answer)
            except ValueError:
                choice = 0
            if 1 <= choice <= len(options):
                return choice - 1
            self._console.print(
                f"Enter a number from 1 to {len(options)}. {_SKIP_NOTE}"
            )

    def inform(self, message: str) -> None:
        self._console.print(message)

    def _reask(self, reason: str, question: str) -> None:
        """Show why the last answer was rejected and re-present it (Req 3.2)."""
        self._console.print(f"{reason} {question} {_SKIP_NOTE}")


class NonInteractiveSession:
    """An :class:`InteractionSession` that answers nothing and never blocks (Req 3.5).

    Every ask/confirm/choose returns ``None`` -- "no answer / do not compute" --
    and ``inform`` is a silent no-op. It never reads stdin, so a non-interactive
    pass completes cleanly without prompting and without fabricating consent.
    """

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        return None

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        return None

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        return None

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        return None

    def inform(self, message: str) -> None:
        return None


def _within(value: float, minimum: float | None, maximum: float | None) -> bool:
    """Return whether ``value`` is inside the inclusive ``[minimum, maximum]``."""
    if minimum is not None and value < minimum:
        return False
    return not (maximum is not None and value > maximum)


def _range_message(minimum: float | None, maximum: float | None) -> str:
    """A human hint naming the accepted range for a re-ask."""
    if minimum is not None and maximum is not None:
        return f"Enter a value from {minimum} to {maximum}."
    if minimum is not None:
        return f"Enter a value >= {minimum}."
    if maximum is not None:
        return f"Enter a value <= {maximum}."
    return "Enter a valid value."


if TYPE_CHECKING:
    # Structural conformance to the InteractionSession protocol, checked by mypy.
    _rich_conforms: InteractionSession = RichInteractionSession()
    _non_interactive_conforms: InteractionSession = NonInteractiveSession()
