"""The threshold calculator's own subpackage.

Deliberately empty of re-exports (task 4.1, ``BuiltInRegistration`` /
``PublicSurfacePin``): ``fitdocs/load/__init__.py`` imports
``THRESHOLD_CALCULATOR`` straight from ``fitdocs.load.threshold.calculator``
and registers it there, and that module is also where the published surface
gains its calculator export -- this package's own ``__init__`` grows no
re-export of its own.

Note what "importing a leaf mutates no global state" can and cannot mean in
practice: because this package is nested under ``fitdocs.load``, Python
always initializes the parent package first, so *any* import reaching a leaf
here -- ``discipline.py``, ``anchors.py``, ``selection.py``,
``calculator.py`` -- necessarily runs ``fitdocs/load/__init__.py`` too and
therefore does register the built-in exactly once, the same way importing
``fitdocs.load`` directly does. What is true, and is what the calculator
module's own docstring and the registration tests pin, is narrower and still
load-bearing: no leaf module here, including ``calculator.py`` itself,
contains a registration call of its own, so no import path through this
package ever registers the built-in *twice*.
"""

from __future__ import annotations
