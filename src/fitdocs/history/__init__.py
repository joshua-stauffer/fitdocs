"""The ``fitdocs.history`` package: the fitness/fatigue/form model, the daily
load series it is computed from, and the one longitudinal page that reports
both (load-history spec).

This module holds the package's published surface only -- the names a
consumer outside this package may import -- and re-exports nothing of its
own computation. ``__all__`` starts empty here (task 2.1) and is **append
only** from here on: every later task in this plan that publishes a name
(2.2, 3.2, 4.2, 5.1, 5.2) appends only its own module's names to the list
below and rewrites nothing already there, and task 5.4 pins the final list
once against ``tests/test_public_api.py``'s ``_HISTORY_SURFACE``. A
wholesale rewrite of this list by a later task would silently drop an
earlier task's published names.
"""

from __future__ import annotations

from fitdocs.history.page import (
    HISTORY_FRONTMATTER_KEYS,
    HISTORY_TITLE,
    HISTORY_TYPE,
    HISTORY_VERSION,
    HISTORY_VERSION_KEY,
)
from fitdocs.history.settings import (
    DEFAULT_HISTORY_SETTINGS,
    HistorySettings,
    HistorySettingsError,
    load_history_settings,
    resolve_constants,
)

__all__: list[str] = [
    "HISTORY_FRONTMATTER_KEYS",
    "HISTORY_TITLE",
    "HISTORY_TYPE",
    "HISTORY_VERSION",
    "HISTORY_VERSION_KEY",
    "DEFAULT_HISTORY_SETTINGS",
    "HistorySettings",
    "HistorySettingsError",
    "load_history_settings",
    "resolve_constants",
]
