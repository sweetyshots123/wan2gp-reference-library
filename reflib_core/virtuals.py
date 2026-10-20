"""1.6.6 virtual copies (Lightroom-like): non-destructive references to ONE original file that store only parameters.

    image  {"rect": [x, y, w, h]}                    crop rectangle in the original's displayed pixels (EXIF applied)
    video  {"rect": [x, y, w, h], "start", "end"}    crop and / or in-out (seconds), either one optional
    audio  {"start", "end"}                          in-out (seconds)

<data>/virtuals/virtuals.json   {"version": 1, "copies": [entry], "trash": [entry + {"_deleted", "_token"}]}
<data>/virtuals/.cache/<id>/<sig>/<name>.<ext>     the rendered file, made on demand (ffmpeg / PIL), one per params

The original is never written to. Deleting a copy never touches the original (restorable for 15 min); a copy whose
original is gone is "broken" (shown, can be deleted, never rendered). In the media browser a copy is one more item with a
stable synthetic hash (vhash(id)), listed under the pseudo folder "⧉ Copias virtuales" (id VFOLDER)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from . import media, storage

VERSION = 1
VFOLDER = "__virtual"
KINDS = ("image", "video", "audio")
SUFFIX = {"es": "copia virtual", "en": "virtual copy"}
TRASH_TTL = 15 * 60
MIN_SPAN = 0.1              # seconds: shortest in-out range
MIN_SIDE = 8                # pixels: smallest crop side
_lock = threading.RLock()
_render_locks: Dict[str, threading.Lock] = {}
_jobs: Dict[str, Dict[str, Any]] = {}          # id -> {"state": rendering|ready|failed, "error", "path"}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class VirtualError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------------- paths / index
def root() -> str:
    return os.path.join(os.path.dirname(storage.COLLECTIONS_DIR), "virtuals")


def index_path() -> str:
    return os.path.join(root(), "virtuals.json")


def cache_root() -> str:
    return os.path.join(root(), ".cache")


def vhash(vid: str) -> str:
    return hashlib.sha256(b"reflib-virtual-v1:" + str(vid).encode()).hexdigest()


def load() -> Dict[str, Any]:
    try:
        with open(index_path(), "r", encoding="utf-8") as reader:
            data = json.load(reader)
    except FileNotFoundError:
        data = {}
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid virtuals.json: {e}")
        data = {}
    copies = [c for c in (data.get("copies") or []) if isinstance(c, dict) and _ID_RE.match(str(c.get("id") or "")) and c.get("kind") in KINDS]
    trash = [c for c in (data.get("trash") or []) if isinstance(c, dict) and _ID_RE.match(str(c.get("id") or ""))]
    return {"version": VERSION, "copies": copies, "trash": trash}


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(root(), exist_ok=True)
    tmp = index_path() + f".{uuid.uuid4().hex[:8]}.tmp"
    with open(tmp, "w", encoding="utf-8") as writer:
        json.dump({"version": VERSION, "copies": data["copies"], "trash": data["trash"]}, writer, ensure_ascii=False, indent=1)
    os.replace(tmp, index_path())


def entries() -> List[Dict[str, Any]]:
    return load()["copies"]


def get(vid: str) -> Optional[Dict[str, Any]]:
    return next((c for c in entries() if c["id"] == vid), None)


def by_hash(h: str) -> Optional[Dict[str, Any]]:
    h = str(h or "")
    return next((c for c in entries() if vhash(c["id"]) == h), None)


def copies_of(orig_hash: str) -> List[Dict[str, Any]]:
    return [c for c in entries() if (c.get("orig") or {}).get("hash") == orig_hash]


# ---------------------------------------------------------------------------------------------------- params
def clean_params(kind: str, params: Any, width: int = 0, height: int = 0, duration: float = 0.0) -> Dict[str, Any]:
    """Validated, clamped params. A rect that covers the whole frame and an in-out that covers the whole clip are dropped
    (they change nothing). Raises VirtualError for unusable values (too small, end before start)."""
    p = params if isinstance(params, dict) else {}
    out: Dict[str, Any] = {}
    if kind in ("image", "video") and p.get("rect") is not None:
        r = p["rect"]
        if isinstance(r, dict):
            r = [r.get("x"), r.get("y"), r.get("w"), r.get("h")]
        try:
            x, y, w, h = (float(v) for v in r)
        except Exception:
            raise VirtualError("bad rect")
        if width and height:
            x, y = max(0.0, min(x, width - 1)), max(0.0, min(y, height - 1))
            w, h = max(0.0, min(w, width - x)), max(0.0, min(h, height - y))
        x, y, w, h = int(round(x)), int(round(y)), int(round(w)), int(round(h))
        if kind == "video":   # yuv420p: even sides and offsets
            x, y, w, h = x - x % 2, y - y % 2, w - w % 2, h - h % 2
        if w < MIN_SIDE or h < MIN_SIDE:
            raise VirtualError("rect too small")
        if not (width and height and x == 0 and y == 0 and w >= width - (2 if kind == "video" else 0) and h >= height - (2 if kind == "video" else 0)):
            out["rect"] = [x, y, w, h]
    if kind in ("video", "audio") and (p.get("start") is not None or p.get("end") is not None):
        try:
            s = float(p.get("start") or 0.0)
            e = float(p["end"]) if p.get("end") is not None else (duration or 0.0)
        except Exception:
            raise VirtualError("bad in/out")
        s = max(0.0, s)
        if duration:
            e = min(e, duration)
        if e - s < MIN_SPAN:
            raise VirtualError("in/out too short")
        if not (s < 0.02 and duration and e > duration - 0.02):
            out["start"], out["end"] = round(s, 3), round(e, 3)
    return out


def _stem(name: str) -> str:
    stem = os.path.splitext(os.path.basename(str(name or "")))[0]
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", stem)
    stem = re.sub(r"\s*\((?:copia virtual|virtual copy)(?: \d+)?\)\s*$", "", stem).strip().strip(".")
    return stem[:100] or "media"


def default_name(orig_name: str, lang: str = "es", taken: Iterable[str] = ()) -> str:
    base = f"{_stem(orig_name)} ({SUFFIX.get(lang, SUFFIX['en'])}"
    taken = {str(t).casefold() for t in taken}
    name, k = base + ")", 2
    while name.casefold() in taken:
        name, k = f"{base} {k})", k + 1
    return name


# ---------------------------------------------------------------------------------------------------- original
def _catalog_original(h: str) -> Optional[str]:
    """The original's file through the browser catalog (a moved / re-indexed copy of the same content counts)."""
    try:
        from . import imagelib
        ent = imagelib.catalog()["by_hash"].get(h)
    except Exception:
        return None
    if not ent or ent.get("virtual"):
        return None
    return next((p for p in [ent.get("path")] + list(ent.get("files") or []) if p and os.path.isfile(p)), None)


def source_path(c: Dict[str, Any], use_catalog: bool = True) -> Optional[str]:
    o = c.get("orig") or {}
    p = o.get("path")
    if p and os.path.isfile(p):
        return p
    return _catalog_original(o.get("hash") or "") if use_catalog else None


def original_facts(path: str, kind: str) -> Dict[str, Any]:
    """{width, height, duration} as displayed (EXIF / rotation applied)."""
    out = {"width": 0, "height": 0, "duration": 0.0}
    if kind == "image":
        try:
            from PIL import Image, ImageOps
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                out["width"], out["height"] = im.size
        except Exception:
            pass
        return out
    if kind == "video":
        from . import resize
        i = resize._ffprobe_info(path)
        out.update(width=int(i.get("width") or 0), height=int(i.get("height") or 0), duration=float(i.get("duration") or 0))
        return out
    from . import mediainfo
    out["duration"] = float(mediainfo.probe_audio(path).get("duration") or 0)
    return out


# ---------------------------------------------------------------------------------------------------- lifecycle
def create(orig_hash: str, params: Any = None, name: Optional[str] = None, lang: str = "es") -> Dict[str, Any]:
    """New copy of a library item. A copy of a copy references the SAME original (with that copy's params unless
    params are given), never a chain."""
    from . import imagelib
    src_entry = imagelib.entry_for(orig_hash)
    if not src_entry:
        raise VirtualError("original not in the library")
    base_params = None
    if src_entry.get("virtual"):
        parent = by_hash(orig_hash)
        if not parent:
            raise VirtualError("original not in the library")
        if source_path(parent) is None:
            raise VirtualError("original missing")
        orig = dict(parent["orig"])
        kind, path, base_params = parent["kind"], source_path(parent), parent.get("params") or {}
    else:
        kind = src_entry.get("kind") or "image"
        kind = "video" if kind == "mask" else kind   # 1.7.0
        path = next((p for p in [src_entry.get("path")] + list(src_entry.get("files") or []) if p and os.path.isfile(p)), None)
        if not path:
            raise VirtualError("original missing")
        try:
            st = os.stat(path)
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size, mtime = 0, 0.0
        orig = {"hash": orig_hash, "path": os.path.abspath(path), "name": src_entry.get("name") or os.path.basename(path),
                "size": size, "mtime": round(mtime, 3)}
    facts = original_facts(path, kind)
    clean = clean_params(kind, base_params if params is None else params, facts["width"], facts["height"], facts["duration"])
    with _lock:
        data = load()
        nm = str(name or "").strip()[:120] or default_name(orig.get("name"), lang, (c["name"] for c in data["copies"]))
        now = time.time()
        entry = {"id": uuid.uuid4().hex, "kind": kind, "name": nm, "orig": orig, "params": clean, "facts": facts,
                 "created": round(now, 3), "updated": round(now, 3)}
        data["copies"].append(entry)
        _save(data)
    return dict(entry, hash=vhash(entry["id"]))


def update(vid: str, params: Any = None, name: Optional[str] = None) -> Dict[str, Any]:
    with _lock:
        data = load()
        c = next((x for x in data["copies"] if x["id"] == vid), None)
        if not c:
            raise VirtualError("virtual copy not found")
        if params is not None:
            path = source_path(c)
            if not path:
                raise VirtualError("original missing")
            facts = original_facts(path, c["kind"])
            c["params"], c["facts"] = clean_params(c["kind"], params, facts["width"], facts["height"], facts["duration"]), facts
        if name is not None and str(name).strip():
            c["name"] = str(name).strip()[:120]
        c["updated"] = round(time.time(), 3)
        _save(data)
    _drop_thumb(vid)
    with _lock:
        _jobs.pop(vid, None)
    return dict(c, hash=vhash(vid))


def refresh_facts(vid: str, facts: Dict[str, Any]) -> bool:
    """1.6.7: copies made before the duration fix stored duration 0 for files without a container duration (MediaRecorder
    WebM). Store freshly measured facts when they differ (params untouched). True when something changed."""
    if not isinstance(facts, dict) or not (facts.get("width") or facts.get("duration")):
        return False
    with _lock:
        data = load()
        c = next((x for x in data["copies"] if x["id"] == vid), None)
        if not c:
            return False
        old = c.get("facts") or {}
        new = {k: facts.get(k, old.get(k)) for k in ("width", "height", "duration")}
        if all(abs(float(old.get(k) or 0) - float(new.get(k) or 0)) < 0.002 for k in new):
            return False
        c["facts"] = new
        _save(data)
    return True


def soft_delete(ids: Iterable[str]) -> Dict[str, Any]:
    """Copies -> trash (restorable for TRASH_TTL). The original is never touched. Returns {deleted, token}."""
    want = {str(i) for i in ids or []}
    token = "v:" + uuid.uuid4().hex[:16]
    with _lock:
        data = load()
        keep, gone = [], []
        for c in data["copies"]:
            (gone if c["id"] in want else keep).append(c)
        now = time.time()
        for c in gone:
            data["trash"].append(dict(c, _deleted=round(now, 3), _token=token))
        data["copies"] = keep
        _purge(data, now)
        _save(data)
    for c in gone:
        _drop_thumb(c["id"])
    return {"deleted": len(gone), "token": token if gone else "", "ids": [c["id"] for c in gone]}


def restore(token: str) -> int:
    with _lock:
        data = load()
        back = [c for c in data["trash"] if c.get("_token") == token]
        if not back:
            return 0
        data["trash"] = [c for c in data["trash"] if c.get("_token") != token]
        have = {c["id"] for c in data["copies"]}
        for c in back:
            if c["id"] not in have:
                data["copies"].append({k: v for k, v in c.items() if not k.startswith("_")})
        _save(data)
    return len(back)


def _purge(data: Dict[str, Any], now: float) -> None:
    old = [c for c in data["trash"] if now - float(c.get("_deleted") or 0) > TRASH_TTL]
    data["trash"] = [c for c in data["trash"] if c not in old]
    for c in old:
        shutil.rmtree(os.path.join(cache_root(), c["id"]), ignore_errors=True)


def _drop_thumb(vid: str) -> None:
    try:
        from . import imagelib
        os.unlink(os.path.join(imagelib._thumbs_dir(), vhash(vid) + ".jpg"))
    except Exception:
        pass


# ---------------------------------------------------------------------------------------------------- facts for the UI
def duration(c: Dict[str, Any]) -> float:
    p = c.get("params") or {}
    if p.get("end") is not None:
        return round(float(p["end"]) - float(p.get("start") or 0), 3)
    return float((c.get("facts") or {}).get("duration") or 0)


def describe(c: Dict[str, Any]) -> Dict[str, Any]:
    """What the browser shows about a copy (details panel, card)."""
    src = source_path(c)
    o = c.get("orig") or {}
    p = c.get("params") or {}
    out = {"id": c["id"], "hash": vhash(c["id"]), "kind": c["kind"], "name": c["name"], "params": p, "facts": c.get("facts") or {},
           "broken": src is None, "orig": {"hash": o.get("hash"), "name": o.get("name"), "path": o.get("path")},
           "orig_in_library": False, "dur": duration(c)}
    try:
        from . import imagelib
        ent = imagelib.catalog()["by_hash"].get(o.get("hash") or "")
        out["orig_in_library"] = bool(ent and not ent.get("virtual"))
    except Exception:
        pass
    if p.get("rect"):
        out["width"], out["height"] = p["rect"][2], p["rect"][3]
    elif (c.get("facts") or {}).get("width"):
        out["width"], out["height"] = c["facts"]["width"], c["facts"]["height"]
    return out


# ---------------------------------------------------------------------------------------------------- rendering
def _sig(c: Dict[str, Any], src: str) -> str:
    try:
        st = os.stat(src)
        stamp = f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        stamp = "?"
    return hashlib.sha1(json.dumps([c.get("params") or {}, os.path.abspath(src), stamp], sort_keys=True).encode()).hexdigest()[:12]


def _ext(c: Dict[str, Any], src: str) -> str:
    if c["kind"] == "video":
        return ".mp4"
    if c["kind"] == "audio":
        return ".wav"
    e = os.path.splitext(src)[1].lower()
    return e if e in (".png", ".jpg", ".jpeg", ".webp") else ".png"


def render_target(c: Dict[str, Any], src: Optional[str] = None) -> Optional[str]:
    """Where the current render lives (may not exist yet). A copy without params IS its original (no render)."""
    src = src or source_path(c)
    if not src:
        return None
    if not (c.get("params") or {}):
        return src
    safe = re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(c.get("name") or ""))).strip().strip(".")[:120] or "media"
    return os.path.join(cache_root(), c["id"], _sig(c, src), safe + _ext(c, src))


def cached(c: Dict[str, Any]) -> Optional[str]:
    t = render_target(c)
    return t if t and os.path.isfile(t) and os.path.getsize(t) > 0 else None


def render(vid: str) -> str:
    """Render now (blocking) and return the file. Raises VirtualError (broken original, ffmpeg failure)."""
    c = get(vid)
    if not c:
        raise VirtualError("virtual copy not found")
    src = source_path(c)
    if not src:
        raise VirtualError("original missing")
    out = render_target(c, src)
    if out == src or (os.path.isfile(out) and os.path.getsize(out) > 0):
        return out
    with _lock:
        lk = _render_locks.setdefault(vid, threading.Lock())
    with lk:
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            return out
        d = os.path.dirname(out)
        os.makedirs(d, exist_ok=True)
        part = os.path.join(d, ".part-" + uuid.uuid4().hex[:8] + os.path.splitext(out)[1])
        try:
            if c["kind"] == "image":
                _render_image(src, part, c["params"])
            else:
                _render_av(src, part, c["kind"], c["params"], original_facts(src, c["kind"]) if c["kind"] == "video" else None)
            os.replace(part, out)
        finally:
            if os.path.exists(part):
                os.unlink(part)
        for other in os.listdir(os.path.join(cache_root(), vid)):   # keep only the current params' render
            if other != os.path.basename(d):
                shutil.rmtree(os.path.join(cache_root(), vid, other), ignore_errors=True)
    return out


def _render_image(src: str, out: str, p: Dict[str, Any]) -> None:
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if p.get("rect"):
            x, y, w, h = p["rect"]
            im = im.crop((x, y, x + w, y + h))
        ext = os.path.splitext(out)[1].lower()
        if ext in (".jpg", ".jpeg"):
            im.convert("RGB").save(out, "JPEG", quality=95, subsampling=0)
        elif ext == ".webp":
            im.save(out, "WEBP", quality=95)
        else:
            im.save(out, "PNG")


def _render_av(src: str, out: str, kind: str, p: Dict[str, Any], c_facts: Optional[Dict[str, Any]] = None) -> None:
    exe = media.find_binary("ffmpeg")
    if not exe:
        raise VirtualError("ffmpeg not found")
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if p.get("start") is not None:
        cmd += ["-ss", f"{float(p['start']):.3f}"]
    # 1.6.7: browser recordings (MediaRecorder WebM) have no duration / cues and sometimes missing pts: regenerate them
    cmd += ["-fflags", "+genpts", "-i", src]
    if p.get("end") is not None:
        cmd += ["-t", f"{float(p['end']) - float(p.get('start') or 0):.3f}"]
    if kind == "video":
        from . import resize
        enc = resize.encoder()
        args = list(enc["args"])
        if enc["name"] == "libx264":
            args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        vf = []
        if p.get("rect"):
            x, y, w, h = p["rect"]
            vf.append(f"crop={w}:{h}:{x}:{y}")
        vf += ["setsar=1", "format=yuv420p"]
        if (c_facts or {}).get("width"):
            cmd += ["-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(vf), *args]
        else:   # 1.6.7: an audio-only .webm / .mkv (browser voice recording) is listed as a video: keep just its sound
            cmd += ["-vn", "-map", "0:a:0"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    else:
        cmd += ["-vn", "-map", "0:a:0", "-c:a", "pcm_s16le", out]
    r = subprocess.run(cmd, capture_output=True, timeout=3600, creationflags=_NO_WINDOW)
    if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        msg = (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["ffmpeg failed"])[-1][:300]
        raise VirtualError(msg)


def render_async(vid: str) -> Dict[str, Any]:
    """Non-blocking: the file when it's ready, else start (once) a background render. {state, path?, error?}"""
    c = get(vid)
    if not c:
        return {"state": "failed", "error": "not found"}
    if source_path(c) is None:
        return {"state": "broken"}
    p = cached(c) or (render_target(c) if not (c.get("params") or {}) else None)
    if p:
        return {"state": "ready", "path": p}
    with _lock:
        job = _jobs.get(vid)
        if job and job["state"] in ("rendering", "failed"):
            return dict(job)
        _jobs[vid] = {"state": "rendering"}

    def run():
        try:
            if c["kind"] != "image" and not float((c.get("facts") or {}).get("duration") or 0):   # 1.6.7: heal 1.6.6 zeros
                src = source_path(c)
                if src:
                    refresh_facts(vid, original_facts(src, c["kind"]))
        except Exception:
            pass
        try:
            path = render(vid)
            st = {"state": "ready", "path": path}
        except Exception as e:
            st = {"state": "failed", "error": str(e)[:300]}
        with _lock:
            _jobs[vid] = st
    threading.Thread(target=run, name="reflib-virtual-render", daemon=True).start()
    return {"state": "rendering"}


def make_thumb(vid: str, dest: str, size: int = 440) -> bool:
    """Card thumbnail: crop of the image / first frame of the in-out with the crop (no full render) / waveform of the
    rendered audio."""
    c = get(vid)
    if not c:
        return False
    src = source_path(c)
    if not src:
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    p = c.get("params") or {}
    try:
        if c["kind"] == "image":
            from PIL import Image, ImageOps
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                if p.get("rect"):
                    x, y, w, h = p["rect"]
                    im = im.crop((x, y, x + w, y + h))
                im.thumbnail((size, size))
                part = dest + ".part.jpg"
                im.convert("RGB").save(part, "JPEG", quality=84)
                os.replace(part, dest)
            return True
        if c["kind"] == "audio":
            from . import mediainfo
            return mediainfo.audio_thumb(render(vid), dest, size)
        exe = media.find_binary("ffmpeg")
        if not exe:
            return False
        at = float(p.get("start") or 0) + min(0.5, duration(c) * 0.1)
        vf = [f"crop={p['rect'][2]}:{p['rect'][3]}:{p['rect'][0]}:{p['rect'][1]}"] if p.get("rect") else []
        vf.append(f"scale='min({size},iw)':'min({size},ih)':force_original_aspect_ratio=decrease")
        part = dest + ".part.jpg"
        r = subprocess.run([exe, "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", "-vf", ",".join(vf), "-q:v", "4", part],
                           capture_output=True, timeout=60, creationflags=_NO_WINDOW)
        if r.returncode == 0 and os.path.isfile(part) and os.path.getsize(part) > 0:
            os.replace(part, dest)
            return True
        return False
    except Exception as e:
        print(f"[Reference Library] virtual thumbnail failed: {e}")
        return False
