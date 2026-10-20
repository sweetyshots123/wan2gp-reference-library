"""1.7.0 mask library: mask videos (WanGP's "Video Mask" input, Matanyone / mask creator output) kept per source video.

Each mask is linked to its video by the library key the media browser uses for that video: the content hash of a
real video (watched folder, collection, pool, Video Library), or the synthetic hash of a virtual copy (a trimmed /
cropped virtual copy has its own masks). The mask file itself is copied into ``masks/<id>/`` (the source may be a
Gradio temp file that disappears), never moved; deleting a mask never touches its video.

Index ``masks/masks.json``::

    {"version": 1, "masks": [{"id", "label", "file", "fhash", "video", "video_name", "video_path", "virtual",
                              "w", "h", "dur", "fps", "created", "source"}]}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from . import storage

VERSION = 1
MFOLDER = "__masks"          # pseudo folder "🎭 Máscaras" of the media browser
TRASH_TTL = 15 * 60
LABEL_MAX = 80
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_lock = threading.RLock()


def root() -> str:
    return os.path.join(os.path.dirname(storage.COLLECTIONS_DIR), "masks")


def index_path() -> str:
    return os.path.join(root(), "masks.json")


def _trash() -> str:
    return os.path.join(root(), ".trash")


def _clean_label(label, fallback: str = "") -> str:
    s = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]", " ", str(label or ""))).strip()[:LABEL_MAX]
    return s or fallback


def load() -> Dict[str, Any]:
    with _lock:
        try:
            with open(index_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        d.setdefault("version", VERSION)
        d["masks"] = [m for m in (d.get("masks") or []) if isinstance(m, dict) and _ID_RE.match(str(m.get("id") or ""))]
        d["trash"] = [t for t in (d.get("trash") or []) if isinstance(t, dict)]
        return d


def _save(d: Dict[str, Any]) -> None:
    os.makedirs(root(), exist_ok=True)
    tmp = index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, index_path())
    _bump()


_rev = [0]


def _bump() -> None:
    _rev[0] += 1
    try:
        from . import imagelib
        imagelib.invalidate()
    except Exception:
        pass


def rev() -> int:
    return _rev[0]


def entries() -> List[Dict[str, Any]]:
    _purge()
    return list(load()["masks"])


def get(mid: str) -> Optional[Dict[str, Any]]:
    return next((m for m in load()["masks"] if m["id"] == str(mid)), None)


def path_of(m: Dict[str, Any]) -> str:
    return os.path.join(root(), m["id"], m["file"])


def for_video(key: str) -> List[Dict[str, Any]]:
    """Masks of one video (library key), newest first."""
    return sorted((m for m in entries() if m.get("video") == key), key=lambda m: -float(m.get("created") or 0))


def counts() -> Dict[str, int]:
    c: Dict[str, int] = {}
    for m in entries():
        c[m["video"]] = c.get(m["video"], 0) + 1
    return c


def by_file_hash(fh: str) -> List[Dict[str, Any]]:
    return [m for m in entries() if m.get("fhash") == fh]


# ------------------------------------------------------------------------------------------------ facts / matching
def facts(path: str) -> Dict[str, Any]:
    """{w, h, dur, fps} of a video file (ffprobe, no decoding); zeros when unknown."""
    out = {"w": 0, "h": 0, "dur": 0.0, "fps": 0.0}
    try:
        from . import resize
        i = resize._ffprobe_info(path) or {}
        out.update(w=int(i.get("width") or 0), h=int(i.get("height") or 0), dur=round(float(i.get("duration") or 0), 3),
                   fps=round(float(i.get("fps") or 0), 3))
    except Exception:
        pass
    return out


def video_facts(key: str) -> Dict[str, Any]:
    """{w, h, dur, name, virtual} of the video a key points at (a virtual copy: its trim / crop applied)."""
    from . import virtuals as _vc
    c = _vc.by_hash(key)
    if c:
        d = _vc.describe(c)
        return {"w": int(d.get("width") or 0), "h": int(d.get("height") or 0), "dur": float(d.get("dur") or 0),
                "name": c.get("name") or "", "virtual": c["id"]}
    out = {"w": 0, "h": 0, "dur": 0.0, "name": "", "virtual": None}
    try:
        from . import imagelib
        ent = imagelib.catalog()["by_hash"].get(key)
    except Exception:
        ent = None
    if ent:
        out["name"] = ent.get("name") or ""
        p = next((q for q in [ent.get("path")] + list(ent.get("files") or []) if q and os.path.isfile(q)), None)
        if p:
            out.update({k: v for k, v in facts(p).items() if k in ("w", "h", "dur")})
    return out


def mismatch(m: Dict[str, Any], vf: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Problems between a mask and its video: [{"what": "duration"|"size", "mask": .., "video": ..}]."""
    vf = vf if vf is not None else video_facts(m.get("video") or "")
    out = []
    md, vd = float(m.get("dur") or 0), float(vf.get("dur") or 0)
    if md > 0 and vd > 0 and abs(md - vd) > max(0.25, 0.03 * vd):
        out.append({"what": "duration", "mask": round(md, 2), "video": round(vd, 2)})
    mw, mh, vw, vh = int(m.get("w") or 0), int(m.get("h") or 0), int(vf.get("w") or 0), int(vf.get("h") or 0)
    if mw and mh and vw and vh and (abs(mw - vw) > 2 or abs(mh - vh) > 2):
        out.append({"what": "size", "mask": f"{mw}x{mh}", "video": f"{vw}x{vh}"})
    return out


# ------------------------------------------------------------------------------------------------ video key of a file
_key_cache: Dict[tuple, str] = {}


def key_for_path(path: str) -> Optional[str]:
    """Library key of a video file: a virtual copy's render -> that copy; else the file's library content hash.
    (A Gradio staged copy has the same bytes as the library file, so it resolves to the same item.)"""
    if not path or not os.path.isfile(path):
        return None
    st = os.stat(path)
    k = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if k in _key_cache:
        return _key_cache[k]
    h = storage._file_hash(path)
    key = h
    try:
        from . import virtuals as _vc
        ap = os.path.abspath(path)
        for c in _vc.entries():
            if c.get("kind") != "video":
                continue
            t = _vc.cached(c)
            if not t:
                continue
            if os.path.abspath(t) == ap or (os.path.getsize(t) == st.st_size and storage._file_hash(t) == h):
                if (c.get("params") or {}):
                    key = _vc.vhash(c["id"])
                break
    except Exception:
        pass
    _key_cache[k] = key
    return key


# ------------------------------------------------------------------------------------------------ lifecycle
def _safe_name(name: str) -> str:
    s = re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(name or ""))).strip().strip(".")[:100]
    return s or "mask"


def add(src: str, video_key: str, label: Optional[str] = None, source: str = "manual", video_name: str = "",
        video_path: str = "") -> Dict[str, Any]:
    """Store a copy of ``src`` as a mask of ``video_key``. The same mask file on the same video is stored once:
    returns {"mask": entry, "created": bool}."""
    if not src or not os.path.isfile(src):
        raise FileNotFoundError(src)
    if not _HASH_RE.match(str(video_key or "")):
        raise ValueError("bad video key")
    fh = storage._file_hash(src)
    with _lock:
        d = load()
        for m in d["masks"]:
            if m.get("fhash") == fh and m.get("video") == video_key:
                return {"mask": m, "created": False}
        if fh == video_key:
            raise ValueError("a video can't be its own mask")
        mid = uuid.uuid4().hex
        ext = os.path.splitext(src)[1].lower() or ".mp4"
        n = sum(1 for m in d["masks"] if m.get("video") == video_key) + 1
        lab = _clean_label(label, f"{'Máscara'} {n}")
        fname = _safe_name(lab) + ext
        os.makedirs(os.path.join(root(), mid), exist_ok=True)
        shutil.copy2(src, os.path.join(root(), mid, fname))
        f = facts(os.path.join(root(), mid, fname))
        from . import virtuals as _vc
        c = _vc.by_hash(video_key)
        m = {"id": mid, "label": lab, "file": fname, "fhash": fh, "video": video_key, "video_name": str(video_name or "")[:200],
             "video_path": str(video_path or "")[:1000], "virtual": c["id"] if c else None, **f,
             "created": time.time(), "source": str(source or "manual")[:20]}
        d["masks"].append(m)
        _save(d)
        return {"mask": m, "created": True}


def rename(mid: str, label: str) -> Dict[str, Any]:
    with _lock:
        d = load()
        m = next((x for x in d["masks"] if x["id"] == str(mid)), None)
        if not m:
            raise KeyError(mid)
        m["label"] = _clean_label(label, m.get("label") or "mask")
        _save(d)
        return m


def reassign(mid: str, video_key: str) -> Dict[str, Any]:
    if not _HASH_RE.match(str(video_key or "")):
        raise ValueError("bad video key")
    with _lock:
        d = load()
        m = next((x for x in d["masks"] if x["id"] == str(mid)), None)
        if not m:
            raise KeyError(mid)
        from . import virtuals as _vc
        c = _vc.by_hash(video_key)
        m["video"], m["virtual"] = video_key, (c["id"] if c else None)
        _save(d)
        return m


def soft_delete(ids: Iterable[str]) -> Dict[str, Any]:
    """Masks go to masks/.trash for 15 minutes (undo). The video is never touched."""
    ids = {str(i) for i in ids}
    with _lock:
        d = load()
        gone = [m for m in d["masks"] if m["id"] in ids]
        if not gone:
            return {"n": 0, "token": None}
        token = uuid.uuid4().hex
        os.makedirs(os.path.join(_trash(), token), exist_ok=True)
        for m in gone:
            src = os.path.join(root(), m["id"])
            if os.path.isdir(src):
                shutil.move(src, os.path.join(_trash(), token, m["id"]))
        d["masks"] = [m for m in d["masks"] if m["id"] not in ids]
        d["trash"].append({"token": token, "at": time.time(), "masks": gone})
        _save(d)
        return {"n": len(gone), "token": token}


def restore(token: str) -> int:
    with _lock:
        d = load()
        t = next((x for x in d["trash"] if x.get("token") == token), None)
        if not t:
            return 0
        n = 0
        for m in t["masks"]:
            src = os.path.join(_trash(), token, m["id"])
            if os.path.isdir(src) and not os.path.exists(os.path.join(root(), m["id"])):
                shutil.move(src, os.path.join(root(), m["id"]))
                d["masks"].append(m); n += 1
        d["trash"] = [x for x in d["trash"] if x.get("token") != token]
        shutil.rmtree(os.path.join(_trash(), token), ignore_errors=True)
        _save(d)
        return n


def _purge(now: Optional[float] = None) -> None:
    now = now or time.time()
    with _lock:
        d = load()
        old = [t for t in d["trash"] if now - float(t.get("at") or 0) > TRASH_TTL]
        if not old:
            return
        for t in old:
            shutil.rmtree(os.path.join(_trash(), str(t.get("token"))), ignore_errors=True)
        d["trash"] = [t for t in d["trash"] if t not in old]
        _save(d)


def public(m: Dict[str, Any], with_check: bool = True) -> Dict[str, Any]:
    """What the browser / API shows about a mask."""
    out = {"id": m["id"], "label": m.get("label") or "", "path": path_of(m), "video": m.get("video"), "virtual": m.get("virtual"),
           "video_name": m.get("video_name") or "", "w": m.get("w") or 0, "h": m.get("h") or 0, "dur": m.get("dur") or 0,
           "created": m.get("created") or 0, "source": m.get("source") or "", "hash": m.get("fhash")}
    if with_check:
        vf = video_facts(m.get("video") or "")
        out["video_facts"] = {k: vf.get(k) for k in ("w", "h", "dur")}
        if vf.get("name"):
            out["video_name"] = vf["name"]
        out["mismatch"] = mismatch(m, vf)
    return out
