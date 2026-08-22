"""Static SVG chart generation for fitdocs (hero chart, HR-zone strip).

Chart modules take plain series and style parameters only -- no ``Activity`` and
no fit-ingest imports; ``fitdocs.render.sections`` prepares series from the
model. This package imports the standard library only.

The public chart API re-exports are added by a later task; this module is
currently a package marker only.
"""
