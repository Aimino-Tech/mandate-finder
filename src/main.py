"""
DEPRECATED — Duplicate FastAPI application.

This module defined a separate FastAPI app with A/B Testing routes that
overlapped with routes in src/mandate_finder/api/main.py.

All routes have been consolidated into ``src.mandate_finder.api.main``.
This file is kept only to avoid breaking existing imports; it forwards
to the canonical app.

To run the API use::

    uvicorn src.mandate_finder.api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import warnings as _warnings

from src.mandate_finder.api.main import app as _app

app = _app

_warnings.warn(
    "Importing 'src.main' is deprecated. Use 'src.mandate_finder.api.main' instead.",
    DeprecationWarning,
    stacklevel=2,
)
