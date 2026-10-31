"""Imports every module that registers shared actions (see actions.py). Add one line per new feature module."""
from . import actions  # noqa: F401
from . import colactions  # noqa: F401
from . import tagactions  # noqa: F401
# from . import similarity  # noqa: F401   <- e.g. the pose/face similarity module registers itself here
