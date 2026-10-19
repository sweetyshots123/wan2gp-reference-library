"""1.6.0 media facts for the browser (duration, size, codec) of videos and audio, probed with ffprobe in ONE
low-priority background thread, throttled, and cached by content hash in <data>/mediainfo.json. Never on the request
path: the UI shows "–" until a duration arrives. Also posters (video) and waveform thumbnails (audio)."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Dict, Iterable, Optional, Tuple

from . import media

PATH: Optional[str] = None          # set by imagelib.init / the host (data dir)
PROBE_GAP = 0.05                    # seconds between two ffprobe runs (throttle)
SAVE_EVERY = 2.0
QUEUE_MAX = 20000
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_lock = threading.Lock()
_info: Dict[str, Dict] = {}
_loaded = [False]
_q: Dict[str, Tuple[str, str]] = {}     # hash -> (path, kind), insertion order (newest requests moved to the end)
_state = {"running": False, "done": 0, "dirty": False, "last_save": 0.0, "rev": 0}


def _path() -> str:
    if PATH:
        return PATH
    from . import storage
    return os.path.join(storage.COLLECTIONS_DIR, "mediainfo.json")


def _load() -> None:
    if _loaded[0]:
        return
    _loaded[0] = True
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            # 1.6.7: a 0 duration measured before the packet-scan fallback (MediaRecorder WebM) is probed again, once
            _info.update({k: v for k, v in (d.get("items") or {}).items()
                          if isinstance(v, dict) and (v.get("duration") or v.get("missing") or (v.get("v") or 0) >= 2)})
    except Exception:
        pass


def _save(force=False) -> None:
    if not _state["dirty"] or (not force and time.time() - _state["last_save"] < SAVE_EVERY):
        return
    with _lock:
        data = json.dumps({"version": 1, "items": _info}, separators=(",", ":"))
        _state["dirty"] = False
        _state["last_save"] = time.time()
    try:
        target = _path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, target)
    except Exception as e:
        print(f"[Reference Library] mediainfo save failed: {e}")


def get(h: str) -> Optional[Dict]:
    with _lock:
        _load()
        return _info.get(h)


def rev() -> int:
    return _state["rev"]


def pending() -> int:
    with _lock:
        return len(_q)


def probe_audio(path: str) -> Dict:
    exe = media.find_binary("ffprobe")
    if not exe:
        return {}
    try:
        r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,sample_rate,channels",
                            "-of", "json", path], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30,
                           creationflags=_NO_WINDOW)
        d = json.loads(r.stdout or "{}")
    except Exception:
        return {}
    a = next((s for s in d.get("streams") or [] if s.get("codec_type") == "audio"), {})
    try:
        dur = float((d.get("format") or {}).get("duration") or 0)
    except Exception:
        dur = 0.0
    if dur <= 0:   # 1.6.7: live-written WebM / Ogg (MediaRecorder) has no container duration
        dur = media.scan_duration(path, "a:0" if a else "0")
    return {"duration": round(dur, 3), "codec": a.get("codec_name") or "", "rate": int(a.get("sample_rate") or 0), "ch": int(a.get("channels") or 0)}


def _probe(path: str, kind: str) -> Dict:
    if kind == "video":
        p = media.probe(path)
        out = {"duration": p.get("duration") or 0.0, "w": p.get("width") or 0, "h": p.get("height") or 0, "fps": p.get("fps") or 0}
    else:
        out = probe_audio(path)
    out["at"] = round(time.time())
    out["v"] = 2
    return out


def _worker() -> None:
    while True:
        with _lock:
            if not _q:
                _state["running"] = False
                break
            h = next(reversed(_q))
            path, kind = _q.pop(h)
        try:
            info = _probe(path, kind) if os.path.isfile(path) else {"duration": 0.0, "missing": True}
        except Exception:
            info = {"duration": 0.0}
        with _lock:
            _info[h] = info
            _state["dirty"] = True
            _state["done"] += 1
            _state["rev"] += 1
        _save()
        time.sleep(PROBE_GAP)
    _save(force=True)


def want(items: Iterable[Tuple[str, str, str]], front: bool = False) -> int:
    """Queue (hash, path, kind) for probing when not known yet. front=True: these are on screen, probe them first."""
    n = 0
    with _lock:
        _load()
        for h, path, kind in items:
            if kind not in ("video", "audio") or h in _info:
                continue
            if front:
                _q.pop(h, None)
            elif h in _q:
                continue
            _q[h] = (path, kind)
            n += 1
        while len(_q) > QUEUE_MAX:
            _q.pop(next(iter(_q)))
        if _q and not _state["running"]:
            _state["running"] = True
            threading.Thread(target=_worker, name="reflib-mediainfo", daemon=True).start()
    return n


def wait(timeout: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        with _lock:
            if not _q and not _state["running"]:
                return
        time.sleep(0.05)


# ---- thumbnails ----------------------------------------------------------------------------------------------
def video_thumb(src: str, dest: str, size: int = 440) -> bool:
    return media.make_poster(src, dest, max_side=size, at=0.1)


def audio_thumb(src: str, dest: str, size: int = 440) -> bool:
    """Waveform picture (ffmpeg showwavespic) on a dark card, written as JPEG."""
    exe = media.find_binary("ffmpeg")
    if not exe:
        return False
    w, h = size, int(size * 0.75)
    tmp = dest + ".wave.png"
    try:
        subprocess.run([exe, "-v", "error", "-y", "-i", src, "-filter_complex",
                        f"aformat=channel_layouts=mono,showwavespic=s={w}x{int(h * 0.62)}:colors=#60a5fa:scale=sqrt", "-frames:v", "1", tmp],
                       capture_output=True, timeout=60, creationflags=_NO_WINDOW)
        if not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
            return False
        from PIL import Image, ImageDraw
        bg = Image.new("RGB", (w, h), (24, 28, 38))
        with Image.open(tmp) as wave:
            wave = wave.convert("RGBA")
            bg.paste(wave, (0, (h - wave.height) // 2), wave)
        d = ImageDraw.Draw(bg)
        d.line([(0, h // 2), (w, h // 2)], fill=(51, 65, 85), width=1)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        part = dest + ".part.jpg"
        bg.save(part, "JPEG", quality=84)
        os.replace(part, dest)
        return True
    except Exception as e:
        print(f"[Reference Library] waveform failed for {src}: {e}")
        return False
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
