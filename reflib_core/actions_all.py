"""Imports every module that registers shared actions (see actions.py). Add one line per new feature module."""
from . import actions  # noqa: F401
from . import colactions  # noqa: F401
from . import tagactions  # noqa: F401
from . import ioactions  # noqa: F401   (1.9.5 collection zips + Video Library manager)
from . import similarity  # noqa: F401   (1.9.0 pose / face similarity: sim_*)
