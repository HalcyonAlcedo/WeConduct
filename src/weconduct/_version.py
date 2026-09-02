"""Single source of truth for the WeConduct application version (Python side).

Imported by both the low-level ``contracts`` layer and the ``application`` layer,
so it must stay dependency-free (no imports from any weconduct subpackage). Keep
this value in sync with ``pyproject.toml`` ``[project].version`` on each release.
"""

APP_VERSION = "0.9.2"
