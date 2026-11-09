"""Playback resume positions (1.12.7).

Shared by Media Library, Galería and the standalone Media Library page.
Positions and the minimum-duration threshold live in ``playback.json`` under the
plugin data dir — never in settings.json. Installing the plugin does not create
or rewrite settings.json; if ``min_s`` is absent, the code default (300 s) is used.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

from . import actions, storage

DEFAULT_MIN_S = 300.0
HEAD_S = 5.0
TAIL_S = 5.0
TAIL_FRAC = 0.95
_LOCK = threading.RLock()
_cache: Optional[Dict[str, Any]] = None


def _path() -> str:
    return os.path.join(storage.PLUGIN_DIR, "playback.json")


def _empty() -> Dict[str, Any]:
    return {"version": 1, "positions": {}}


def _load() -> Dict[str, Any]:
    global _cache
    with _LOCK:
        if _cache is not None:
            return _cache
        try:
            with open(_path(), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                data = _empty()
        except FileNotFoundError:
            data = _empty()
        except Exception:
            data = _empty()
        data.setdefault("version", 1)
        data.setdefault("positions", {})
        if not isinstance(data["positions"], dict):
            data["positions"] = {}
        _cache = data
        return _cache


def _save(data: Dict[str, Any]) -> None:
    global _cache
    with _LOCK:
        _cache = data
        storage._atomic_write_json(_path(), data)


def min_s_from(raw: Any = None) -> float:
    """Clamp a threshold (seconds) to [0, 86400]; invalid -> DEFAULT_MIN_S."""
    try:
        v = float(raw) if raw is not None else DEFAULT_MIN_S
    except (TypeError, ValueError):
        v = DEFAULT_MIN_S
    if not (v == v) or v < 0:  # NaN
        v = DEFAULT_MIN_S
    return max(0.0, min(86400.0, v))


def get_min_s() -> float:
    """User threshold in seconds. Default 300 when the key was never saved."""
    with _LOCK:
        data = _load()
        if "min_s" not in data:
            return DEFAULT_MIN_S
        return min_s_from(data.get("min_s"))


def set_min_s(value: Any) -> float:
    """Persist the threshold in playback.json (creates the file on first change)."""
    v = min_s_from(value)
    with _LOCK:
        data = _load()
        data["min_s"] = v
        _save(data)
    return v


def should_track(duration: float, t: float, min_s: Optional[float] = None) -> bool:
    """Whether a position is worth saving / offering (mirrored in playback_rules.js)."""
    try:
        dur = float(duration or 0)
        pos = float(t or 0)
        thr = float(min_s) if min_s is not None else get_min_s()
    except (TypeError, ValueError):
        return False
    if dur <= thr or dur <= 0 or pos < 0:
        return False
    if pos < HEAD_S:
        return False
    if pos > dur - TAIL_S or pos >= dur * TAIL_FRAC:
        return False
    return True


def get(hash_: str) -> Optional[Dict[str, Any]]:
    h = str(hash_ or "")
    if not h:
        return None
    with _LOCK:
        ent = _load()["positions"].get(h)
        return dict(ent) if isinstance(ent, dict) else None


def set_pos(hash_: str, t: float, duration: float, min_s: Optional[float] = None) -> Dict[str, Any]:
    h = str(hash_ or "")
    if not h:
        return {"ok": False, "error": "no_hash"}
    thr = get_min_s() if min_s is None else min_s_from(min_s)
    if not should_track(duration, t, thr):
        clear(h)
        return {"ok": True, "cleared": True, "tracked": False}
    with _LOCK:
        data = _load()
        data["positions"][h] = {"t": round(float(t), 3), "dur": round(float(duration), 3), "at": time.time()}
        if len(data["positions"]) > 5000:
            items = sorted(data["positions"].items(), key=lambda kv: float((kv[1] or {}).get("at") or 0))
            for k, _ in items[: len(items) - 5000]:
                data["positions"].pop(k, None)
        _save(data)
    return {"ok": True, "tracked": True, "t": round(float(t), 3)}


def clear(hash_: str) -> Dict[str, Any]:
    h = str(hash_ or "")
    with _LOCK:
        data = _load()
        if h in data["positions"]:
            data["positions"].pop(h, None)
            _save(data)
            return {"ok": True, "cleared": True}
    return {"ok": True, "cleared": False}


def _reset_for_tests() -> None:
    global _cache
    with _LOCK:
        _cache = None
        p = _path()
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


@actions.action("playback_get", fast=True, doc="Saved resume position for one media hash (or null).")
def playback_get(req: Dict[str, Any], ctx: actions.Ctx) -> Dict[str, Any]:
    h = str(req.get("hash") or "")
    thr = get_min_s()
    ent = get(h)
    if ent and not should_track(ent.get("dur") or 0, ent.get("t") or 0, thr):
        return {"ok": True, "pos": None, "min_s": thr}
    return {"ok": True, "pos": ent, "min_s": thr}


@actions.action("playback_set", fast=False, doc="Save or clear a resume position (clears when not trackable).")
def playback_set(req: Dict[str, Any], ctx: actions.Ctx) -> Dict[str, Any]:
    h = str(req.get("hash") or "")
    if req.get("clear"):
        return {**clear(h), "ok": True}
    try:
        t = float(req.get("t"))
        dur = float(req.get("duration") or req.get("dur") or 0)
    except (TypeError, ValueError):
        return ctx.err("bad_request")
    return set_pos(h, t, dur)


@actions.action("playback_settings", fast=True, doc="Read / update resume threshold {min_s} (seconds; default 300).")
def playback_settings(req: Dict[str, Any], ctx: actions.Ctx) -> Dict[str, Any]:
    if "min_s" in (req or {}) or "resume_min_s" in (req or {}) or "min_m" in (req or {}):
        raw = req.get("min_s", req.get("resume_min_s"))
        if raw is None and "min_m" in req:
            try:
                raw = float(req.get("min_m")) * 60.0
            except (TypeError, ValueError):
                raw = DEFAULT_MIN_S
        thr = set_min_s(raw)
    else:
        thr = get_min_s()
    return {
        "ok": True,
        "min_s": thr,
        "resume_min_s": thr,
        "min_m": round(thr / 60.0, 2),
        "default_min_s": DEFAULT_MIN_S,
        "head_s": HEAD_S,
        "tail_s": TAIL_S,
        "tail_frac": TAIL_FRAC,
    }
