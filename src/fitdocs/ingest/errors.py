"""The FIT decode error taxonomy (Req 1.2, 1.3).

Two failure regimes are distinguished for an invalid *source file* so callers
can react differently: input that is not a FIT file at all versus a FIT file
whose integrity check fails. Both derive from a common base so a caller may
catch every decode failure with a single ``except``.

This module imports nothing external — in particular not the ``garmin-fit-sdk``
— so the taxonomy is usable and testable with zero FIT-format knowledge.
"""

from __future__ import annotations


class FitDecodeError(Exception):
    """Base class for every FIT decode failure (Req 1.1).

    Catch this to handle any decode error uniformly; catch the specific
    subclasses to distinguish non-FIT input from an integrity failure.
    """


class NotFitFileError(FitDecodeError):
    """The source is not a FIT file: its header fails ``is_fit`` (Req 1.2)."""


class FitIntegrityError(FitDecodeError):
    """The source is a FIT file but fails its integrity check, e.g. truncated
    or CRC-mismatched bytes (Req 1.3)."""
