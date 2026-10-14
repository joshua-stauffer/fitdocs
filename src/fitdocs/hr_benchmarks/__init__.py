"""Derive dated athlete heart-rate benchmarks from recorded evidence."""

from .engine import HrStageSettings, derive_hr_benchmarks, load_hr_stage_settings
from .types import HrStageReport

__all__ = [
    "HrStageReport",
    "HrStageSettings",
    "derive_hr_benchmarks",
    "load_hr_stage_settings",
]
