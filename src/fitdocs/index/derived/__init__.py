"""Derived index producers for mean-max, load series, benchmarks, and blocks.

These producers may use index.producer, index.schema, other index.derived
modules, metrics.mean_max, the history and plans package roots, benchmarks,
load.profile, layout, settings, model, and the standard library. They never
use the index store, refresh/build internals, DuckDB, the clock, or the network.
"""
