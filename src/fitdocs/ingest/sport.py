"""Sport detection: raw FIT ``sport``/``sub_sport`` strings -> normalized triple.

:func:`detect_sport` is a PURE function over the two raw FIT strings a device
records for an activity. It returns a normalized ``(Sport, Modality, is_indoor)``
triple, isolating device-quirk churn in this one lookup-table module so the rest
of the pipeline never parses device-specific sport codes (Req 5).

The three outputs are independent (Req 5.6 -- the indoor flag is separate from
the sport label):

* **Sport label (Req 5.1-5.3)** -- ``cycling``/``running``/``swimming``/
  ``walking``/``hiking``/``rowing`` map to their normalized labels; ``training``/
  ``fitness_equipment``/``generic`` map to :attr:`Sport.WORKOUT`; ANYTHING else,
  including an unrecognized string, ``None``, or a non-string value, also falls
  back to :attr:`Sport.WORKOUT`. Detection NEVER raises (Req 5.3).
* **Modality (Req 5.4, 5.5)** -- exactly one of run/bike/swim/strength/other. A
  ``strength_training`` sub-sport forces :attr:`Modality.STRENGTH`, winning over
  the sport-derived modality (Req 5.5); otherwise running/cycling/swimming map to
  run/bike/swim and every other sport (walking, hiking, rowing, unknown, absent)
  maps to :attr:`Modality.OTHER`.
* **Indoor flag (Req 5.6)** -- ``True`` only for the verified machine-bound
  sub-sports in :data:`INDOOR_SUB_SPORTS`. Ambiguous sub-sports the device does
  not tie to a machine (``lap_swimming``, ``strength_training``,
  ``cardio_training``) are deliberately NOT flagged: asserting indoorness there
  would fabricate data the device never recorded.

Every lookup is a dict ``.get`` or set membership, so an unexpected or
non-string argument simply falls back (Workout / other / not-indoor) rather than
raising. Source precedence -- session ``sport``/``sub_sport`` versus a fallback
``sport_mesgs`` -- is the orchestrator's job (Req 5 wiring in ``parse_fit``); this
function is pure over the two resolved strings.

This module depends only on :mod:`fitdocs.model`; it never touches the SDK, the
decoder, the metrics layer, or sibling ingest modules.
"""

from __future__ import annotations

from fitdocs.model import Modality, Sport

# Normalized sport label per FIT ``sport`` string (Req 5.1, 5.2). Any string not
# present here -- and any non-string / ``None`` -- falls back to WORKOUT (Req 5.3).
SPORT_MAP: dict[str, Sport] = {
    "cycling": Sport.RIDE,
    "running": Sport.RUN,
    "swimming": Sport.SWIM,
    "walking": Sport.WALK,
    "hiking": Sport.HIKE,
    "rowing": Sport.ROWING,
    "training": Sport.WORKOUT,
    "fitness_equipment": Sport.WORKOUT,
    "generic": Sport.WORKOUT,
}

# Coarse modality per FIT ``sport`` string (Req 5.4). Sports absent here map to
# OTHER; a ``strength_training`` sub-sport overrides this entirely (Req 5.5).
MODALITY_MAP: dict[str, Modality] = {
    "running": Modality.RUN,
    "cycling": Modality.BIKE,
    "swimming": Modality.SWIM,
}

# The verified machine-bound sub-sports the device ties to indoor equipment
# (Req 5.6). AMBIGUOUS sub-sports (``lap_swimming``, ``strength_training``,
# ``cardio_training``) are intentionally excluded: the device does not assert
# indoorness for them, and fabricating it would violate the no-fabrication rule.
INDOOR_SUB_SPORTS: frozenset[str] = frozenset(
    {
        "treadmill",
        "spin",
        "indoor_cycling",
        "indoor_rowing",
        "indoor_walking",
        "indoor_running",
        "virtual_activity",
        "elliptical",
        "stair_climbing",
    }
)


def detect_sport(
    sport: str | None, sub_sport: str | None
) -> tuple[Sport, Modality, bool]:
    """Normalize a raw FIT ``sport``/``sub_sport`` pair (Req 5.1-5.6).

    Returns ``(label, modality, is_indoor)``:

    * ``label`` -- the normalized :class:`Sport`, with :attr:`Sport.WORKOUT` as
      the never-failing fallback for unrecognized, absent, or non-string sports
      (Req 5.1-5.3);
    * ``modality`` -- exactly one :class:`Modality`; a ``strength_training``
      sub-sport forces :attr:`Modality.STRENGTH`, otherwise the sport-derived
      modality is used (running/cycling/swimming -> run/bike/swim, else other)
      (Req 5.4, 5.5);
    * ``is_indoor`` -- ``True`` only for a verified machine-bound sub-sport in
      :data:`INDOOR_SUB_SPORTS` (Req 5.6).

    Every lookup is membership- or ``.get``-based, so this function NEVER raises,
    even for a non-string argument (Req 5.3).
    """
    label = (
        SPORT_MAP.get(sport, Sport.WORKOUT) if isinstance(sport, str) else Sport.WORKOUT
    )

    if sub_sport == "strength_training":
        modality = Modality.STRENGTH
    elif isinstance(sport, str):
        modality = MODALITY_MAP.get(sport, Modality.OTHER)
    else:
        modality = Modality.OTHER

    is_indoor = isinstance(sub_sport, str) and sub_sport in INDOOR_SUB_SPORTS

    return label, modality, is_indoor
