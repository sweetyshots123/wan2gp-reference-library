"""1.5.5 "Usadas como referencia": every image that ever landed in WanGP's Reference Images gallery, deduped by hash,
with first/last use and a use count. refusage.json in the data dir; tiny, rewritten atomically."""
from __future__ import annotations
import json, os, threading, time
from typing import Dict, Iterable, Optional
from . import storage

_lock = threading.RLock()
_cache = {"mt": None, "data": None}


def path() -> str:
    return os.path.join(storage.PLUGIN_DIR, "refusage.json")


def load() -> Dict[str, Dict]:
    try:
        mt = os.stat(path()).st_mtime_ns
    except OSError:
        return {}
    with _lock:
        if _cache["mt"] != mt:
            try:
                _cache["data"] = json.load(open(path(), encoding="utf-8")).get("images", {})
            except Exception:
                _cache["data"] = {}
            _cache["mt"] = mt
        return _cache["data"]


def rev():
    try:
        return os.stat(path()).st_mtime_ns
    except OSError:
        return 0


def _save(d: Dict[str, Dict]) -> None:
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    json.dump({"version": 1, "images": d}, open(tmp, "w", encoding="utf-8"), separators=(",", ":"))
    os.replace(tmp, path())
    _cache["mt"] = None


def record(hashes: Iterable[str], now: Optional[float] = None) -> int:
    now = now or time.time()
    hs = [h for h in dict.fromkeys(hashes or []) if isinstance(h, str) and h]
    if not hs:
        return 0
    with _lock:
        d = dict(load())
        for h in hs:
            e = dict(d.get(h) or {"first": now, "count": 0})
            e["last"] = now
            e["count"] = int(e.get("count", 0)) + 1
            d[h] = e
        _save(d)
    return len(hs)


_undo: Dict[str, Dict] = {}   # batch -> removed entries (session memory, last 10)


def select(hashes=None, since: Optional[float] = None, until: Optional[float] = None):
    d = load()
    want = set(hashes or [])
    return [h for h, e in d.items() if h in want or (since is not None and e.get("last", 0) >= since and (until is None or e.get("last", 0) <= until))]


def clear(hashes: Optional[Iterable[str]] = None) -> int:
    """Remove some (or, with None, all) entries from the history. Images themselves are untouched."""
    return clear_batch(None if hashes is None else list(hashes))["n"]


def clear_batch(hashes) -> Dict:
    import uuid
    with _lock:
        d = dict(load())
        hs = list(d) if hashes is None else [h for h in hashes if h in d]
        if not hs:
            return {"n": 0, "batch": None}
        removed = {h: d.pop(h) for h in hs}
        _save(d)
        b = uuid.uuid4().hex[:12]
        _undo[b] = removed
        while len(_undo) > 10:
            _undo.pop(next(iter(_undo)))
        return {"n": len(hs), "batch": b}


def undo(batch: str) -> int:
    with _lock:
        removed = _undo.pop(batch, None)
        if not removed:
            return 0
        d = dict(load())
        for h, e in removed.items():
            d.setdefault(h, e)
        _save(d)
        return len(removed)
