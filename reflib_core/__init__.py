"""reflib_core: the Reference Library engine, with no Gradio and no WanGP imports.

Library:   storage (collections), videostore, imagestore (crops), imagelib (pool, watched folders, catalog, search,
           Recent, thumbnails, selection), api (versioned public API), media (ffmpeg helpers).
Auto-tag:  taxonomy (taxonomy.json), tagstore (autotags.json), backends (fake / WD / Qwen2.5-VL / Jev / cloud),
           jobs (TagQueue).

Hosts (the WanGP plugin, a future standalone app, the CLI) call configure(data_dir) and talk to these modules.
"""
import os

__version__ = "1.6.9"
FORMAT_VERSION = 1


def configure(data_dir: str) -> None:
    """Point every store at one data folder (collections/, videos/, pool/, folders/, autotags.json)."""
    from . import storage, videostore, imagelib
    data_dir = os.path.abspath(data_dir)
    storage.PLUGIN_DIR = data_dir
    storage.COLLECTIONS_DIR = os.path.join(data_dir, "collections")
    storage.INDEX_PATH = os.path.join(storage.COLLECTIONS_DIR, "collections.json")
    videostore.PLUGIN_DIR = data_dir
    videostore.VIDEOS_DIR = os.path.join(data_dir, "videos")
    imagelib.invalidate()
