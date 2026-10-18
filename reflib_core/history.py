"""1.5.5 generation history: one entry per WanGP generation with its inputs (refs, start/end images, control video,
masks), the prompt + full settings and the output path. Host-agnostic: the WanGP plugin captures through the
`before_metadata_save` data hook (no core change); anything can call capture().

Storage (data dir / history): entries.json + blobs/<sha256>.<ext> + thumbs/<sha256>.jpg. Media are deduped by hash.
In-memory images (PIL) are always stored; files are copied only when they could vanish (Gradio / temp uploads);
files that live in a stable place are referenced by path + hash. A size cap (MB) prunes the oldest entries;
deletes go to a trash with undo."""
from __future__ import annotations
import copy, hashlib, io, json, os, shutil, tempfile, threading, time, uuid
from typing import Any, Dict, Iterable, List, Optional
from . import storage

FIELDS = ("image_refs", "image_start", "image_end", "video_guide", "video_mask", "image_mask", "image_guide", "video_source",
          "audio_guide", "audio_guide2", "audio_guide3")   # 1.6.0: audio inputs too
VIDEO_FIELDS = {"video_guide", "video_mask", "video_source"}
AUDIO_FIELDS = {"audio_guide", "audio_guide2", "audio_guide3"}
_AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus")
KEY_SETTINGS = ("prompt", "negative_prompt", "seed", "resolution", "video_length", "num_inference_steps", "guidance_scale",
                "flow_shift", "model_type", "type", "video_prompt_type", "image_prompt_type", "sliding_window_size",
                "activated_loras", "loras_multipliers", "creation_date", "generation_time")
DEFAULT_CAP_MB = 2048
TRASH_MAX = 50
_lock = threading.RLock()
_cache: Dict[str, Any] = {"mtime": None, "data": None}
VOLATILE = []   # extra volatile roots (tests); temp dir + Gradio upload dirs are always volatile


def root() -> str:
    return os.path.join(storage.PLUGIN_DIR, "history")


def _p(*a) -> str:
    return os.path.join(root(), *a)


def _load() -> Dict[str, Any]:
    path = _p("entries.json")
    try:
        mt = os.stat(path).st_mtime_ns
    except OSError:
        return {"version": 1, "entries": [], "trash": []}
    with _lock:
        if _cache["mtime"] == mt:
            return _cache["data"]
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            data = {"version": 1, "entries": [], "trash": []}
        data.setdefault("entries", []); data.setdefault("trash", [])
        _cache.update(mtime=mt, data=data)
        return data


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(root(), exist_ok=True)
    tmp = _p("entries.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, _p("entries.json"))
    _cache.update(mtime=None, data=None)


# ---------------------------------------------------------------------------- media normalisation
def is_volatile(path: str) -> bool:
    ap = os.path.abspath(path).replace("\\", "/").lower()
    roots = [tempfile.gettempdir(), os.environ.get("GRADIO_TEMP_DIR") or ""] + VOLATILE
    if any(r and ap.startswith(os.path.abspath(r).replace("\\", "/").lower()) for r in roots):
        return True
    return "/gradio/" in ap or "/gradio_tmp" in ap


def _flatten(v) -> List[Any]:
    if v is None or v == "" or v == []:
        return []
    if isinstance(v, (list, tuple)):
        out = []
        for x in v:
            out.extend(_flatten(x[0] if isinstance(x, tuple) and len(x) == 2 and isinstance(x[1], (str, type(None))) and not isinstance(x[0], str) else x))
        return out
    if isinstance(v, dict):
        for k in ("path", "name", "video", "image", "background", "composite"):
            if v.get(k) is not None:
                return _flatten(v[k])
        return []
    return [v]


def _thumb_img(im, h: str) -> None:
    t = _p("thumbs", h + ".jpg")
    if os.path.exists(t):
        return
    os.makedirs(os.path.dirname(t), exist_ok=True)
    try:
        im2 = im.copy(); im2.thumbnail((256, 256)); im2.convert("RGB").save(t, "JPEG", quality=82)
    except Exception:
        pass


def _store_item(x, field: str) -> Optional[Dict[str, Any]]:
    """-> {"h": sha256, "kind": image|video, "blob": rel or None, "src": original path or None, "size": copied bytes}"""
    try:
        from PIL import Image
    except Exception:
        Image = None
    if Image is not None and isinstance(x, Image.Image):
        buf = io.BytesIO(); x.save(buf, "PNG"); data = buf.getvalue()
        h = hashlib.sha256(data).hexdigest()
        rel = os.path.join("blobs", h + ".png")
        if not os.path.exists(_p(rel)):
            os.makedirs(_p("blobs"), exist_ok=True)
            with open(_p(rel) + ".tmp", "wb") as f:
                f.write(data)
            os.replace(_p(rel) + ".tmp", _p(rel))
        _thumb_img(x, h)
        return {"h": h, "kind": "image", "blob": rel, "src": None, "size": len(data)}
    if isinstance(x, str) and os.path.isfile(x):
        h = storage._file_hash(x)
        e0 = os.path.splitext(x)[1].lower()
        kind = "audio" if field in AUDIO_FIELDS or e0 in _AUDIO_EXT else "video" if field in VIDEO_FIELDS or e0 in (".mp4", ".mkv", ".webm", ".mov", ".avi") else "image"
        ext = e0 or {"video": ".mp4", "audio": ".wav"}.get(kind, ".png")
        rel, size = None, 0
        if is_volatile(x):
            rel = os.path.join("blobs", h + ext)
            if not os.path.exists(_p(rel)):
                os.makedirs(_p("blobs"), exist_ok=True)
                shutil.copy2(x, _p(rel) + ".tmp"); os.replace(_p(rel) + ".tmp", _p(rel))
            size = os.path.getsize(_p(rel))
        t = _p("thumbs", h + ".jpg")
        if not os.path.exists(t):
            os.makedirs(os.path.dirname(t), exist_ok=True)
            if kind == "video":
                try:
                    from . import media
                    media.make_poster(_p(rel) if rel else x, t, max_side=256)
                except Exception:
                    pass
            elif kind == "audio":
                try:
                    from . import mediainfo
                    mediainfo.audio_thumb(_p(rel) if rel else x, t, size=256)
                except Exception:
                    pass
            elif Image is not None:
                try:
                    with Image.open(x) as im:
                        _thumb_img(im, h)
                except Exception:
                    pass
        return {"h": h, "kind": kind, "blob": rel, "src": None if rel else os.path.abspath(x), "size": size}
    return None


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except Exception:
        if isinstance(v, dict):
            return {str(k): _jsonable(x) for k, x in v.items() if _ok_json(x)}
        if isinstance(v, (list, tuple)):
            return [_jsonable(x) for x in v if _ok_json(x)]
        return None


def _ok_json(x):
    try:
        json.dumps(x); return True
    except Exception:
        return isinstance(x, (dict, list, tuple))


# ---------------------------------------------------------------------------- capture
EXTRA_SETTINGS = ("image_prompt_type", "keep_frames_video_source", "sliding_window_overlap")


def _extra(inputs: Dict[str, Any], configs: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """1.6.3: what WanGP's metadata cleaning may drop. The effective video_source (in "L" mode WanGP has already
    resolved it to the continued video in generate_media) as an absolute path, plus the three settings, taken from
    generate_media's own values first, then from the metadata."""
    extra = extra or {}
    out: Dict[str, Any] = {}
    vs = (inputs or {}).get("video_source")
    vs = vs[0] if isinstance(vs, (list, tuple)) and vs else vs
    out["video_source"] = os.path.abspath(vs) if isinstance(vs, str) and vs else None
    for k in EXTRA_SETTINGS:
        v = extra.get(k) if extra.get(k) is not None else configs.get(k)
        out[k] = v if _ok_json(v) and not isinstance(v, (dict, list, tuple)) else (None if v is None else str(v))
    return out


def capture(inputs: Dict[str, Any], configs: Optional[Dict[str, Any]], output, model_type: str = "", cap_mb: Optional[float] = None,
            extra: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
    """Record one generation. `inputs` = WanGP's raw inputs (PIL images / paths), `configs` = its metadata dict,
    `extra` (1.6.3) = generate_media's own image_prompt_type / keep_frames_video_source / sliding_window_overlap."""
    configs = dict(configs or {})
    outs = [o for o in (output if isinstance(output, (list, tuple)) else [output]) if isinstance(o, str)]
    if not outs:
        return None
    media: Dict[str, List[Dict]] = {}
    for f in FIELDS:
        items = []
        seen = set()
        for x in _flatten((inputs or {}).get(f)):
            try:
                r = _store_item(x, f)
            except Exception:
                r = None
            if r and r["h"] not in seen:
                seen.add(r["h"]); items.append(r)
        if items:
            media[f] = items
    settings = {k: _jsonable(v) for k, v in configs.items() if _ok_json(v)}
    entry = {"id": uuid.uuid4().hex, "ts": time.time(), "output": [os.path.abspath(o) for o in outs], "model_type": model_type or configs.get("model_type") or "",
             "prompt": str(configs.get("prompt") or (inputs or {}).get("prompt") or ""), "key": {k: settings.get(k) for k in KEY_SETTINGS if settings.get(k) is not None},
             "settings": settings, "media": media, "extra": _extra(inputs, configs, extra)}
    o0 = entry["output"][0]
    try:
        from . import media as _m
        pth = _p("thumbs", "out_" + entry["id"] + ".jpg"); os.makedirs(os.path.dirname(pth), exist_ok=True)
        if os.path.splitext(o0)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
            from PIL import Image
            with Image.open(o0) as im:
                im.thumbnail((320, 320)); im.convert("RGB").save(pth, "JPEG", quality=82)
        else:
            _m.make_poster(o0, pth, max_side=320)
        if os.path.exists(pth):
            entry["poster"] = os.path.basename(pth)
    except Exception:
        pass
    with _lock:
        data = _load()
        win = int(configs.get("window_no") or 1)
        updated = False
        if win > 1 and data["entries"] and data["entries"][0].get("prompt") == entry["prompt"] and time.time() - data["entries"][0]["ts"] < 3600:
            data["entries"][0].update(output=entry["output"], poster=entry.get("poster", data["entries"][0].get("poster")), ts=entry["ts"])   # sliding window: same generation
            entry = data["entries"][0]
            updated = True
        else:
            data["entries"].insert(0, entry)
        _save(data)
        enforce_cap(cap_mb)
    _notify(entry, updated)   # outside the lock: listeners may call back into the history
    return entry


# ---------------------------------------------------------------------------- listeners (API v5, 1.6.3)
_listeners: Dict[str, Any] = {}
_listeners_lock = threading.Lock()


def add_listener(cb) -> Optional[str]:
    if not callable(cb):
        return None
    tok = uuid.uuid4().hex
    with _listeners_lock:
        _listeners[tok] = cb
    return tok


def remove_listener(token) -> bool:
    with _listeners_lock:
        return _listeners.pop(str(token or ""), None) is not None


def _notify(entry: Dict, updated: bool) -> None:
    """Each callback gets its own copy of the resolved entry (+ "updated"); an exception in one never reaches capture()
    or the other callbacks."""
    with _listeners_lock:
        cbs = list(_listeners.items())
    if not cbs:
        return
    try:
        base = resolved(entry)
    except Exception as e:
        print(f"[Reference Library] history listeners: could not build the payload: {e}")
        return
    for tok, cb in cbs:
        try:
            cb(dict(copy.deepcopy(base), updated=bool(updated)))
        except Exception as e:
            print(f"[Reference Library] history listener {getattr(cb, '__qualname__', cb)!s} failed: {e!r}")


def resolved(e: Optional[Dict]) -> Optional[Dict]:
    """Public, path-resolved copy of an entry (API v5): {id, ts, output[], model_type, prompt, settings,
    media{field: [{h, kind, path, thumb_path}]}, poster_path, video_source, video_source_original}. path / thumb_path are absolute or None (file gone)."""
    if not e:
        return None
    media = {}
    for f, items in (e.get("media") or {}).items():
        media[f] = [{"h": x.get("h"), "kind": x.get("kind"), "path": item_path(x), "thumb_path": thumb_path(x.get("h") or "")} for x in items]
    poster = e.get("poster")
    ex = e.get("extra") or {}   # missing on entries recorded before 1.6.3
    settings = copy.deepcopy(e.get("settings") or {})
    for k in EXTRA_SETTINGS:   # always present: metadata value, else generate_media's value, else None
        if settings.get(k) is None:
            settings[k] = ex.get(k)
    orig = ex.get("video_source")
    copy_path = next((x["path"] for x in media.get("video_source") or [] if x.get("path")), None)
    vs = orig if orig and os.path.isfile(orig) else copy_path   # original file first (an output in "L" mode), else our stored copy
    return {"id": e["id"], "ts": e["ts"], "output": [os.path.abspath(o) for o in e.get("output") or []],
            "model_type": e.get("model_type", ""), "prompt": e.get("prompt", ""), "settings": settings,
            "media": media, "poster_path": thumb_path(os.path.splitext(poster)[0]) if poster else None,
            "video_source": vs, "video_source_original": orig}


def latest() -> Optional[Dict]:
    ents = _load()["entries"]
    return ents[0] if ents else None


# ---------------------------------------------------------------------------- queries
def _public(e: Dict) -> Dict:
    m = {f: [{"h": x["h"], "kind": x["kind"], "thumb": x["h"]} for x in v] for f, v in (e.get("media") or {}).items()}
    return {"id": e["id"], "ts": e["ts"], "output": e["output"], "prompt": e.get("prompt", ""), "model_type": e.get("model_type", ""),
            "key": e.get("key", {}), "media": m, "poster": e.get("poster"), "output_exists": any(os.path.isfile(o) for o in e["output"])}


def entries(q: str = "", offset: int = 0, limit: int = 50) -> Dict:
    data = _load()
    items = data["entries"]
    if q:
        ql = q.lower()
        items = [e for e in items if ql in (e.get("prompt") or "").lower() or ql in (e.get("model_type") or "").lower() or any(ql in os.path.basename(o).lower() for o in e["output"])]
    return {"total": len(items), "items": [_public(e) for e in items[offset:offset + limit]], "trash": len(data["trash"]), "size_mb": round(size_bytes() / 2**20, 1)}


def get(eid: str) -> Optional[Dict]:
    return next((e for e in _load()["entries"] if e["id"] == eid), None)


def item_path(x: Dict) -> Optional[str]:
    if x.get("blob") and os.path.isfile(_p(x["blob"])):
        return _p(x["blob"])
    if x.get("src") and os.path.isfile(x["src"]):
        return x["src"]
    return None


def paths(eid: str, field: str) -> List[str]:
    e = get(eid) or {}
    return [p for p in (item_path(x) for x in (e.get("media") or {}).get(field, [])) if p]


def thumb_path(h: str) -> Optional[str]:
    import re
    if not h or not re.fullmatch(r"(out_)?[0-9a-f]{32,64}(\.jpg)?", h):
        return None
    for name in (h + ".jpg", h):
        p = _p("thumbs", name)
        if os.path.isfile(p):
            return p
    return None


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def find_by_output(path: str) -> Optional[Dict]:
    n = _norm(path)
    for e in _load()["entries"]:
        if any(_norm(o) == n for o in e["output"]):
            return e
    b = os.path.basename(path).lower()
    return next((e for e in _load()["entries"] if any(os.path.basename(o).lower() == b for o in e["output"])), None)


def read_embedded(path: str) -> Optional[Dict]:
    """WanGP's own metadata reader (settings embedded in the mp4 / png); None outside WanGP or without metadata."""
    try:
        if os.path.splitext(path)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
            from shared.utils.audio_video import read_image_metadata
            return read_image_metadata(path)
        from shared.utils.video_metadata import read_metadata_from_video
        return read_metadata_from_video(path)
    except Exception:
        return None


def for_restore(settings: Optional[Dict]) -> Optional[Dict]:
    """1.6.5: settings as handed to WanGP's loader when reusing them: a copy with the seed reset to random (-1).
    The stored history entry is never changed; reusing settings must never copy the seed."""
    if not settings:
        return settings
    d = dict(settings)
    d.pop("seed", None)
    d["seed"] = -1
    return d


def settings_file(eid: str = "", video: str = "") -> Optional[str]:
    """A JSON settings file for WanGP's native "Load Settings From Media File / Json" (history entry or video metadata).
    The seed is always -1 (random) in it (1.6.5)."""
    s = None
    if eid:
        s = (get(eid) or {}).get("settings")
    elif video:
        e = find_by_output(video)
        s = e.get("settings") if e else read_embedded(video)
    if not s:
        return None
    s = for_restore(s)   # 1.6.5: never the seed of the original generation
    d = os.path.join(tempfile.gettempdir(), "reflib_settings"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"settings_{eid or hashlib.sha1(video.encode()).hexdigest()[:10]}.json")
    json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return p


# ---------------------------------------------------------------------------- delete / undo / cap
TRASH_BATCHES = 10   # undo keeps the last N delete operations (any size)


def select(ids=None, since: Optional[float] = None, until: Optional[float] = None) -> List[str]:
    """Entry ids by explicit list and/or time range (ts, seconds). ids=None + no range -> nothing; use since=0 for all."""
    out = []
    want = set(ids or [])
    for e in _load()["entries"]:
        if e["id"] in want:
            out.append(e["id"])
        elif since is not None and e["ts"] >= since and (until is None or e["ts"] <= until):
            out.append(e["id"])
    return out


def delete_many(ids: Iterable[str]) -> Dict[str, Any]:
    """Move entries to the trash as one undoable batch. Only history records go; blobs the history copied are removed
    by gc() once nothing (entries or trash) references them. Outputs and originals are never touched."""
    ids = set(ids or [])
    with _lock:
        data = _load()
        gone = [e for e in data["entries"] if e["id"] in ids]
        if not gone:
            return {"n": 0, "batch": None}
        batch = uuid.uuid4().hex[:12]
        now = time.time()
        data["entries"] = [e for e in data["entries"] if e["id"] not in ids]
        data["trash"] = [dict(e, deleted=now, batch=batch) for e in gone] + data["trash"]
        keep = []
        for e in data["trash"]:
            b = e.get("batch") or e["id"]
            if b not in keep:
                keep.append(b)
        keep = set(keep[:TRASH_BATCHES])
        data["trash"] = [e for e in data["trash"] if (e.get("batch") or e["id"]) in keep]
        _save(data)
    gc()
    return {"n": len(gone), "batch": batch}


def delete(eid: str) -> bool:
    return delete_many([eid])["n"] > 0


def undo_batch(batch: str) -> int:
    with _lock:
        data = _load()
        back = [e for e in data["trash"] if e.get("batch") == batch]
        if not back:
            return 0
        data["trash"] = [e for e in data["trash"] if e.get("batch") != batch]
        data["entries"] += [{k: v for k, v in e.items() if k not in ("deleted", "batch")} for e in back]
        data["entries"].sort(key=lambda x: -x["ts"])
        _save(data)
        return len(back)


def undo(eid: str = "") -> Optional[str]:
    with _lock:
        data = _load()
        if not data["trash"]:
            return None
        e = next((x for x in data["trash"] if x["id"] == eid), None) if eid else data["trash"][0]
        if not e:
            return None
        if e.get("batch"):
            undo_batch(e["batch"])
            return e["id"]
        data["trash"] = [x for x in data["trash"] if x["id"] != e["id"]]
        data["entries"].append({k: v for k, v in e.items() if k != "deleted"}); data["entries"].sort(key=lambda x: -x["ts"])
        _save(data)
        return e["id"]


def _referenced() -> set:
    data = _load()
    out = set()
    for e in data["entries"] + data["trash"]:
        for v in (e.get("media") or {}).values():
            for x in v:
                if x.get("blob"):
                    out.add(os.path.basename(x["blob"]))
                out.add(x["h"] + ".jpg")
        if e.get("poster"):
            out.add(e["poster"])
    return out


def gc() -> int:
    """Remove blobs / thumbs no entry (or trashed entry) references."""
    ref, n = _referenced(), 0
    for sub in ("blobs", "thumbs"):
        d = _p(sub)
        for name in (os.listdir(d) if os.path.isdir(d) else []):
            if name not in ref and not name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(d, name)); n += 1
                except OSError:
                    pass
    return n


def size_bytes() -> int:
    tot = 0
    for sub in ("blobs", "thumbs"):
        d = _p(sub)
        for name in (os.listdir(d) if os.path.isdir(d) else []):
            try:
                tot += os.path.getsize(os.path.join(d, name))
            except OSError:
                pass
    return tot


def enforce_cap(cap_mb: Optional[float] = None) -> int:
    """Drop trash first, then the oldest entries, until the stored copies fit the cap. Returns entries dropped."""
    cap = (DEFAULT_CAP_MB if cap_mb is None else float(cap_mb)) * 2**20
    if cap <= 0:
        return 0
    dropped = 0
    with _lock:
        while size_bytes() > cap:
            data = _load()
            if data["trash"]:
                data["trash"] = data["trash"][:-1]
            elif len(data["entries"]) > 1:
                data["entries"] = data["entries"][:-1]; dropped += 1
            else:
                break
            _save(data); gc()
    return dropped
