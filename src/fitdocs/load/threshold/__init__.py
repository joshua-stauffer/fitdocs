"""The threshold calculator's own subpackage.

Empty of re-exports today: this task (2.1, ``DisciplineSupport``) adds the
first leaf, ``discipline.py``, and nothing yet consumes it from outside the
package. Later tasks build ``anchors.py``, ``calculator.py`` and this
package's public surface (see design.md's ``BuiltInRegistration`` /
``PublicSurfacePin``, which registers the calculator from
``fitdocs/load/__init__.py`` rather than from here, so importing a leaf
module for a test does not mutate global registry state).
"""

from __future__ import annotations
