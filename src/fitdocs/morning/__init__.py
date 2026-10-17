"""Morning-of wellness blocks on existing workout pages.

The pure ``block`` module consumes the wellness and recovery facades and the
render layer's formatting and attribution helpers. The independent ``docedit``
module uses contract constants and the generic region grammar. Only ``engine``
combines them with the document reader and layout; only the CLI imports that
engine. Render modules do not import this package. See the workout-wellness
design's Allowed Dependencies for the complete per-module import contract.
"""
