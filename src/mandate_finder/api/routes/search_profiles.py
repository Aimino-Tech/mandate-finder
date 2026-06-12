"""Search profile routes — re-exported from legacy mandate_finder/api/routes.py.

Uses importlib to load the module from the root package tree so that it
does not collide with the src/mandate_finder package resolution.
"""

from __future__ import annotations

import importlib.util as _util
import logging as _logging
import os as _os
import sys as _sys

_logger = _logging.getLogger(__name__)

_router = None
# __file__ = src/mandate_finder/api/routes/search_profiles.py
# Going up 4 levels reaches the project root
_here = _os.path.dirname(_os.path.abspath(__file__))
_root_pkg = _os.path.normpath(_os.path.join(_here, *([".."] * 4)))
_routes_path = _os.path.join(_root_pkg, "mandate_finder", "api", "routes.py")

if _os.path.isfile(_routes_path):
    _spec = _util.spec_from_file_location("mandate_finder.api.routes", _routes_path)
    if _spec and _spec.loader:
        _mod = _util.module_from_spec(_spec)
        _sys.path.insert(0, _root_pkg)
        try:
            _spec.loader.exec_module(_mod)
        finally:
            if _root_pkg in _sys.path:
                _sys.path.remove(_root_pkg)
        _router = getattr(_mod, "router", None)
else:
    _logger.warning("Legacy routes module not found at %s", _routes_path)

router = _router
