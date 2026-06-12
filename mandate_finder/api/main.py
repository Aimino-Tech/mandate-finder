"""Compatibility shim — re-exports the consolidated FastAPI app.

The canonical application is defined in ``src/mandate_finder/api/main.py``.
This module exists only so that ``import mandate_finder.api.main`` still
resolves, e.g. for existing Docker images and test imports.  All new code
should import from ``src.mandate_finder.api.main`` instead.
"""

from __future__ import annotations

import warnings

from src.mandate_finder.api.main import app  # noqa: F401

warnings.warn(
    "Import 'mandate_finder.api.main' is deprecated — use 'src.mandate_finder.api.main' instead.",
    DeprecationWarning,
    stacklevel=2,
)
