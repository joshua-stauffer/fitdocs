"""The three training-load channels: Power, Heart Rate and Pace.

This package is a **re-export point**: given one activity, one already-
resolved threshold benchmark and one resolved sufficiency configuration, each
channel returns either a load value on the shared "one hour at threshold =
100" scale or a typed statement of why no honest value exists. Nothing in
this layer reads a file, consults a clock, prompts, or decides which channel
wins -- that is ``threshold-load``'s job.

This module itself holds no logic and performs no import side effect. Its
public surface -- the result vocabulary, the three ``compute`` entry points,
the heart-rate intensity seam and the provenance records -- is populated in
task 4.1, once every leaf module it re-exports from exists.
"""

from __future__ import annotations
