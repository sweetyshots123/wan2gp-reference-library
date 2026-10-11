"""1.5.2 "Show in folder": open the OS file manager on an image the library knows about (never an arbitrary path).

    Windows  explorer.exe /select, "<path>"   (file highlighted)
    macOS    open -R "<path>"                 (revealed in Finder)
    Linux    xdg-open "<parent folder>"
Argument lists only, no shell. Only meaningful when the browser runs on the same PC as the server: the host checks
that the request comes from localhost before calling reveal().
"""
from __future__ import annotations
import os, subprocess, sys
from typing import Callable, List, Optional

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def is_local(host: Optional[str]) -> bool:
    return bool(host) and (host in LOCAL_HOSTS or host.startswith("127."))


def command(path: str, platform: str = sys.platform) -> List[str]:
    if platform.startswith("win"):
        # two arguments: explorer accepts "/select," followed by the (quoted by subprocess) path, spaces included
        return ["explorer.exe", "/select,", os.path.normpath(path)]
    if platform == "darwin":
        return ["open", "-R", path]
    return ["xdg-open", os.path.dirname(path) or "."]


def reveal(path: str, platform: str = sys.platform, run: Callable = None) -> List[str]:
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path)
    cmd = command(path, platform)
    run = run or (lambda c: subprocess.Popen(c, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             creationflags=0x08000000 if platform.startswith("win") else 0))
    run(cmd)
    return cmd


def known_path(h: str) -> Optional[str]:
    """The file the library itself holds for this hash: the stored copy for collection / pool images, the original
    for watched-folder images. None for unknown hashes."""
    from . import imagelib
    i = imagelib.catalog()["by_hash"].get(str(h or ""))
    if not i:
        return None
    for p in (i.get("path"),) + tuple(i.get("files") or ()):
        if p and os.path.isfile(p):
            return p
    return None
