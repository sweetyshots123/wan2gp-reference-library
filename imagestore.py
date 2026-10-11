"""Compatibility alias (1.5.0): the library core lives in reflib_core/ (no Gradio / WanGP imports). This module IS
reflib_core.imagestore, so `import imagestore` / `from . import imagestore` keep working for the plugin, other code and the tests."""
import importlib as _il
import sys as _sys
try:
    _m = _il.import_module(".reflib_core.imagestore", __package__) if __package__ else None
except ImportError:
    _m = None
if _m is None:
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))) if _os.path.dirname(_os.path.abspath(__file__)) not in _sys.path else None
    _m = _il.import_module("reflib_core.imagestore")
_sys.modules[__name__] = _m
globals().update({_k: _v for _k, _v in vars(_m).items() if not _k.startswith("__")})   # file-spec loaders get the real API too
