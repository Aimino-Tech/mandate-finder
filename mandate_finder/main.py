"""Compatibility shim — re-exports the consolidated FastAPI app.

The canonical application is in ``src/mandate_finder/api/main.py``.
This module redirects there so that ``from mandate_finder.main import app``
(used by some tooling) still works.
"""

from __future__ import annotations

import warnings

from src.mandate_finder.api.main import app  # noqa: F401

warnings.warn(
    "Import 'mandate_finder.main' is deprecated — use 'src.mandate_finder.api.main' instead.",
    DeprecationWarning,
    stacklevel=2,
)
