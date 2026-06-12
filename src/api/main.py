"""
DEPRECATED — Duplicate FastAPI application.

This module defined a separate FastAPI app for billing/stripe routes with
its own /health endpoint, overlapping with the consolidated app in
``src/mandate_finder/api/main.py``.

All routes have been consolidated into ``src.mandate_finder.api.main``.
"""

from __future__ import annotations

import warnings as _warnings

from src.mandate_finder.api.main import app as _app

app = _app

_warnings.warn(
    "Importing 'src.api.main' is deprecated. Use 'src.mandate_finder.api.main' instead.",
    DeprecationWarning,
    stacklevel=2,
)
