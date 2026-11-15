"""1.12.19: browser-playable copies of videos the browser cannot decode (mp4v / MPEG-4 Part 2, MPEG-1/2, Xvid/DivX, WMV, HEVC, …).

A transcode or remux is written under the plugin's own cache directory — never next to the user's files — and originals
are never modified or moved. h264_nvenc is used when a short probe succeeds (e.g. an RTX GPU), otherwise libx264.
Jobs are single-flight per source file; the cache has a size cap (LRU of finished copies).

Used by both UIs through the ilib ``media_url`` action and ``GET /reflib/play/<hash>``. Does not touch the catalog.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from . import media, storage

# Video codecs a typical Chrome/Edge build can decode in a common container (mp4 / webm / ogg).
PLAYABLE_VIDEO = frozenset({
    "h264", "avc1", "vp8", "vp9", "av1", "av01", "theora", "mjpeg",
})
# Always re-encode these (mp4v is the case Ramón hit). xvid/divx are mpeg4 with a different tag.
TRANSCODE_VIDEO = frozenset({
    "mpeg4", "msmpeg4", "msmpeg4v2", "msmpeg4v3",
    "mpeg1video", "mpeg2video",
    "wmv1", "wmv2", "wmv3", "vc1", "wvc1",
    "hevc", "h265", "hev1", "hvc1",
    "flv1", "flashsv", "svq3", "huffyuv", "rawvideo", "prores", "dnxhd", "ffv1",
    "indeo3", "indeo5", "msvideo1", "cinepak", "tscc", "vp6f", "vp6",
})
PLAYABLE_AUDIO_MP4 = frozenset({"aac", "mp3", "alac"})
MP4_EXTS = frozenset({".mp4", ".m4v", ".mov"})
WEB_EXTS = frozenset({".webm", ".ogv", ".ogg"})

CACHE_VERSION = 1
DEFAULT_CACHE_MAX = 4 * 1024 * 1024 * 1024  # 4 GiB
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_lock = threading.RLock()
_jobs: Dict[str, Dict[str, Any]] = {}          # key -> job
_flight: Dict[str, threading.Event] = {}       # key -> event set when the job finishes
_encoder: Optional[list] = None                # ["h264_nvenc", ...] or ["libx264", ...]
_encoder_name: Optional[str] = None


def cache_dir() -> str:
    # Prefer the live env so tests (and a late configure) don't keep a PLUGIN_DIR frozen at import time.
    root = os.environ.get("REFLIB_DATA_DIR") or storage.PLUGIN_DIR
    return os.path.join(root, "cache", "play")


def cache_max() -> int:
    try:
        return max(16 * 1024 * 1024, int(os.environ.get("REFLIB_PLAY_CACHE_MAX") or DEFAULT_CACHE_MAX))
    except ValueError:
        return DEFAULT_CACHE_MAX


def _reset_for_tests() -> None:
    global _encoder, _encoder_name
    with _lock:
        for j in list(_jobs.values()):
            proc = j.get("proc")
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
        _jobs.clear()
        _flight.clear()
        _encoder = None
        _encoder_name = None
    d = cache_dir()
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


def probe(path: str) -> Dict[str, Any]:
    """ffprobe of the first video (and first audio) stream. Empty dict if unreadable."""
    empty: Dict[str, Any] = {"vcodec": "", "acodec": "", "vtag": "", "width": 0, "height": 0, "fps": 0.0,
                             "duration": 0.0, "pix_fmt": "", "ext": ""}
    if not isinstance(path, str) or not os.path.isfile(path):
        return empty
    exe = media.find_binary("ffprobe")
    if not exe:
        return empty
    cmd = [exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                             timeout=30, creationflags=_NO_WINDOW)
        data = json.loads(res.stdout or "{}")
    except Exception:
        return empty
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fps = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            n, d = str(v.get(key) or "0/1").split("/", 1)
            fps = (float(n) / float(d)) if float(d) else 0.0
            if fps:
                break
        except Exception:
            continue
    dur = 0.0
    for src in (v.get("duration"), (data.get("format") or {}).get("duration")):
        try:
            dur = float(src)
            if dur > 0:
                break
        except Exception:
            continue
    if dur <= 0:
        dur = media.scan_duration(path, "v:0")
    return {
        "vcodec": str(v.get("codec_name") or "").lower(),
        "acodec": str(a.get("codec_name") or "").lower(),
        "vtag": str(v.get("codec_tag_string") or "").lower(),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": round(fps, 3),
        "duration": round(dur, 3),
        "pix_fmt": str(v.get("pix_fmt") or ""),
        "ext": os.path.splitext(path)[1].lower(),
        "has_audio": bool(a),
    }


def classify(info: Dict[str, Any]) -> str:
    """'original' (browser can play the file as-is), 'remux' (bitstream copy into mp4) or 'transcode'."""
    vc = (info.get("vcodec") or "").lower()
    ac = (info.get("acodec") or "").lower()
    ext = (info.get("ext") or "").lower()
    if not vc:
        return "transcode"
    if vc in TRANSCODE_VIDEO or (vc not in PLAYABLE_VIDEO):
        return "transcode"
    # Already in a container Chrome plays well.
    if ext in WEB_EXTS and vc in {"vp8", "vp9", "av1", "av01", "theora"}:
        return "original"
    if ext in MP4_EXTS and vc in {"h264", "avc1", "mjpeg"} and (not ac or ac in PLAYABLE_AUDIO_MP4):
        return "original"
    # H.264 (or mjpeg) in mkv/avi/…: remux to mp4 when the audio can be copied; otherwise transcode audio only.
    if vc in {"h264", "avc1", "mjpeg"}:
        if not ac or ac in PLAYABLE_AUDIO_MP4:
            return "remux"
        return "transcode"
    return "original"


def needs_convert(info: Dict[str, Any]) -> bool:
    return classify(info) != "original"


def encoder() -> list:
    """Cached ffmpeg video-encoder args, starting with the codec name. Tests may set REFLIB_PLAY_ENCODER=libx264."""
    global _encoder, _encoder_name
    with _lock:
        if _encoder is not None:
            return list(_encoder)
        forced = (os.environ.get("REFLIB_PLAY_ENCODER") or "").strip().lower()
        if forced == "libx264" or forced == "x264":
            _encoder = ["libx264", "-preset", "veryfast", "-crf", "23"]
            _encoder_name = "libx264"
        elif forced in {"h264_nvenc", "nvenc"}:
            _encoder = _nvenc_args()
            _encoder_name = "h264_nvenc"
        elif _nvenc_works():
            _encoder = _nvenc_args()
            _encoder_name = "h264_nvenc"
            print("[Reference Library] playable: using h264_nvenc")
        else:
            _encoder = ["libx264", "-preset", "veryfast", "-crf", "23"]
            _encoder_name = "libx264"
        return list(_encoder)


def encoder_name() -> str:
    encoder()
    return _encoder_name or "libx264"


def _nvenc_args() -> list:
    return ["h264_nvenc", "-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "23", "-b:v", "0"]


def _nvenc_works() -> bool:
    exe = media.find_binary("ffmpeg")
    if not exe:
        return False
    import tempfile
    td = tempfile.mkdtemp(prefix="reflib-nvenc-")
    out = os.path.join(td, "t.mp4")
    try:
        for args in (_nvenc_args(), ["h264_nvenc", "-preset", "medium"]):
            r = subprocess.run(
                [exe, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=s=64x64:d=0.2",
                 "-frames:v", "2", "-c:v", *args, "-pix_fmt", "yuv420p", out],
                capture_output=True, timeout=20, creationflags=_NO_WINDOW)
            if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                return True
        return False
    except Exception:
        return False
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _sig(path: str, info: Dict[str, Any], mode: str) -> str:
    st = os.stat(path)
    raw = "|".join([
        str(CACHE_VERSION), mode, encoder_name(),
        str(int(st.st_size)), str(int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime)),
        info.get("vcodec") or "", info.get("acodec") or "",
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _paths(digest: str, sig: str) -> Dict[str, str]:
    root = cache_dir()
    base = os.path.join(root, f"{digest[:24]}_{sig}")
    return {"dir": root, "part": base + ".part.mp4", "final": base + ".mp4", "meta": base + ".json"}


def _key(digest: str, path: str) -> str:
    return f"{digest}:{os.path.abspath(path)}"


def _write_meta(meta_path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, meta_path)


def evict(needed: int = 0) -> None:
    """Drop the oldest finished cache files until the cap has ``needed`` extra bytes of headroom."""
    root = cache_dir()
    if not os.path.isdir(root):
        return
    entries = []
    total = 0
    for name in os.listdir(root):
        if not name.endswith(".mp4") or name.endswith(".part.mp4"):
            continue
        p = os.path.join(root, name)
        try:
            st = os.stat(p)
        except OSError:
            continue
        # skip files a running job still owns
        busy = False
        with _lock:
            for j in _jobs.values():
                if j.get("final") == p or j.get("part") == p:
                    busy = True
                    break
        if busy:
            continue
        entries.append((st.st_mtime, st.st_size, p))
        total += st.st_size
    cap = cache_max()
    if total + needed <= cap:
        return
    entries.sort()  # oldest first
    for _, size, p in entries:
        if total + needed <= cap:
            break
        for ext in ("", ".json"):
            q = p if not ext else p[:-4] + ext  # .mp4 -> .json
            try:
                os.remove(q)
            except OSError:
                pass
        total -= size


def _job_snapshot(j: Optional[Dict[str, Any]], info: Dict[str, Any], mode: str) -> Dict[str, Any]:
    if not j:
        return {"play": "failed", "ok": False, "url": None, "codec": info.get("vcodec") or "",
                "progress": 0.0, "error": "no job", "mode": mode}
    st = j.get("state") or "preparing"
    play = "ready" if st == "ready" else ("failed" if st == "failed" else "preparing")
    out = {
        "ok": play != "failed",
        "play": play,
        "url": None,
        "codec": info.get("vcodec") or j.get("codec") or "",
        "progress": float(j.get("progress") or 0.0),
        "mode": mode or j.get("mode") or "",
        "path": j.get("final") if play == "ready" else (j.get("part") if play == "preparing" else None),
        "part": j.get("part") if play == "preparing" else None,
        "error": j.get("error") if play == "failed" else None,
        "rendering": play == "preparing",
        "encoder": encoder_name(),
    }
    return out


def status(digest: str, path: str) -> Dict[str, Any]:
    """Current play status for ``path`` (does not start a job)."""
    digest = str(digest or "")
    info = probe(path)
    mode = classify(info) if info.get("vcodec") else "transcode"
    if mode == "original":
        return {"ok": True, "play": "original", "url": None, "codec": info.get("vcodec") or "",
                "progress": 1.0, "mode": mode, "path": os.path.abspath(path) if path and os.path.isfile(path) else None,
                "rendering": False, "info": info}
    if not path or not os.path.isfile(path):
        return {"ok": False, "play": "failed", "url": None, "codec": "", "progress": 0.0,
                "error": "file not found", "rendering": False, "mode": mode}
    sig = _sig(path, info, mode)
    paths = _paths(digest, sig)
    if os.path.isfile(paths["final"]) and os.path.getsize(paths["final"]) > 0:
        return {"ok": True, "play": "ready", "url": None, "codec": info.get("vcodec") or "",
                "progress": 1.0, "mode": mode, "path": paths["final"], "rendering": False, "info": info,
                "encoder": encoder_name()}
    with _lock:
        j = _jobs.get(_key(digest, path))
        if j:
            snap = _job_snapshot(j, info, mode)
            snap["info"] = info
            return snap
    return {"ok": True, "play": "preparing", "url": None, "codec": info.get("vcodec") or "",
            "progress": 0.0, "mode": mode, "path": None, "part": None, "rendering": True, "info": info,
            "idle": True}


def ensure(digest: str, path: str, start: bool = True) -> Dict[str, Any]:
    """Return play status, starting a transcode/remux in the background when needed (single-flight)."""
    digest = str(digest or "")
    st = status(digest, path)
    if st.get("play") in {"original", "ready", "failed"} and not st.get("idle"):
        return st
    if st.get("play") == "failed" and st.get("error") == "file not found":
        return st
    if not start:
        return st
    key = _key(digest, path)
    with _lock:
        j = _jobs.get(key)
        if j and j.get("state") in {"preparing", "ready"}:
            snap = _job_snapshot(j, st.get("info") or {}, st.get("mode") or "")
            snap["info"] = st.get("info")
            return snap
        ev = threading.Event()
        _flight[key] = ev
        info = st.get("info") or probe(path)
        mode = st.get("mode") or classify(info)
        sig = _sig(path, info, mode)
        paths = _paths(digest, sig)
        job = {"state": "preparing", "progress": 0.0, "mode": mode, "codec": info.get("vcodec") or "",
               "part": paths["part"], "final": paths["final"], "meta": paths["meta"], "src": os.path.abspath(path),
               "proc": None, "error": None, "started": time.time()}
        _jobs[key] = job

    def run():
        try:
            _transcode(job, path, info, mode, paths)
        except Exception as e:
            job["state"] = "failed"
            job["error"] = str(e)[:300]
        finally:
            ev.set()

    threading.Thread(target=run, name=f"reflib-play-{digest[:8]}", daemon=True).start()
    snap = _job_snapshot(job, info, mode)
    snap["info"] = info
    return snap


def wait(digest: str, path: str, timeout: float = 120.0) -> Dict[str, Any]:
    """Block until the job for this file finishes (or is already original/ready/failed)."""
    st = ensure(digest, path, start=True)
    if st.get("play") in {"original", "ready", "failed"}:
        return st
    key = _key(digest, path)
    ev = _flight.get(key)
    if ev is not None:
        ev.wait(timeout)
    return status(digest, path)


def play_file(digest: str, path: str) -> Optional[str]:
    """Local path the browser should stream: finished cache, growing part (if it already has a box), or the original."""
    st = status(digest, path)
    if st.get("play") == "original":
        return st.get("path")
    if st.get("play") == "ready" and st.get("path") and os.path.isfile(st["path"]):
        return st["path"]
    part = st.get("part")
    if part and os.path.isfile(part) and os.path.getsize(part) >= 64:
        return part
    return None


def part_ready(digest: str, path: str, min_bytes: int = 64) -> bool:
    st = status(digest, path)
    p = st.get("part") or (st.get("path") if st.get("play") == "ready" else None)
    try:
        return bool(p) and os.path.isfile(p) and os.path.getsize(p) >= min_bytes
    except OSError:
        return False


def _transcode(job: Dict[str, Any], src: str, info: Dict[str, Any], mode: str, paths: Dict[str, str]) -> None:
    exe = media.find_binary("ffmpeg")
    if not exe:
        job["state"] = "failed"
        job["error"] = "ffmpeg not found"
        return
    os.makedirs(paths["dir"], exist_ok=True)
    evict(needed=max(int(os.path.getsize(src) * 1.2), 8 * 1024 * 1024))
    part, final = paths["part"], paths["final"]
    for p in (part, final):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-fflags", "+genpts", "-i", src, "-map", "0:v:0"]
    if info.get("has_audio"):
        cmd += ["-map", "0:a:0?"]
    if mode == "remux" and (not info.get("acodec") or info.get("acodec") in PLAYABLE_AUDIO_MP4):
        cmd += ["-c:v", "copy"]
        if info.get("has_audio"):
            cmd += ["-c:a", "copy"]
        cmd += ["-movflags", "+faststart", final]
        target = final
        growing = False
    else:
        enc = encoder()
        cmd += ["-c:v", *enc, "-pix_fmt", "yuv420p"]
        if info.get("has_audio"):
            if info.get("acodec") in PLAYABLE_AUDIO_MP4 and mode != "transcode":
                cmd += ["-c:a", "copy"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "160k", "-ac", "2"]
        else:
            cmd += ["-an"]
        # Fragmented MP4 so the browser can start before the whole file is written.
        cmd += ["-movflags", "+frag_keyframe+empty_moov+default_base_moof", part]
        target = part
        growing = True
    # Progress on stdout (key=value).
    cmd += ["-progress", "pipe:1"]
    dur = float(info.get("duration") or 0.0)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
    job["proc"] = proc
    out_line = b""
    try:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            out_line += chunk
            while b"\n" in out_line:
                line, out_line = out_line.split(b"\n", 1)
                text = line.decode("utf-8", "ignore").strip()
                if text.startswith("out_time_ms="):
                    try:
                        ms = int(text.split("=", 1)[1])
                        if dur > 0:
                            job["progress"] = max(job.get("progress") or 0.0, min(0.99, (ms / 1e6) / dur))
                    except ValueError:
                        pass
                elif text.startswith("out_time="):
                    # HH:MM:SS.micro
                    try:
                        hms = text.split("=", 1)[1].strip()
                        hh, mm, ss = hms.split(":")
                        t = int(hh) * 3600 + int(mm) * 60 + float(ss)
                        if dur > 0:
                            job["progress"] = max(job.get("progress") or 0.0, min(0.99, t / dur))
                    except Exception:
                        pass
        rc = proc.wait(timeout=max(60, int(dur * 8) + 30))
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        job["state"] = "failed"
        job["error"] = str(e)[:300]
        return
    finally:
        job["proc"] = None
    if rc != 0 or not os.path.isfile(target) or os.path.getsize(target) == 0:
        err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace").strip().splitlines()
        job["state"] = "failed"
        job["error"] = (err[-1] if err else "ffmpeg failed")[:300]
        return
    if growing:
        # Remux the fragmented copy to a seekable, faststart MP4.
        tmp_final = final + ".tmp.mp4"
        r = subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", part,
             "-c", "copy", "-movflags", "+faststart", tmp_final],
            capture_output=True, timeout=max(60, int(dur * 2) + 30), creationflags=_NO_WINDOW)
        if r.returncode == 0 and os.path.isfile(tmp_final) and os.path.getsize(tmp_final) > 0:
            os.replace(tmp_final, final)
            try:
                os.remove(part)   # may fail on Windows if the part is still being streamed; evict cleans it later
            except OSError:
                pass
        else:
            # Keep the fragmented file: it still plays and seeks once complete.
            try:
                os.replace(part, final)
            except OSError:
                job["state"] = "failed"
                job["error"] = "could not finalise cache"
                return
    job["progress"] = 1.0
    job["state"] = "ready"
    job["part"] = None
    _write_meta(paths["meta"], {
        "v": CACHE_VERSION, "src": os.path.abspath(src), "mode": mode,
        "codec": info.get("vcodec") or "", "encoder": encoder_name(), "at": time.time(),
        "duration": info.get("duration") or 0,
    })


def serve_name(digest: str, path: str) -> str:
    """Suggested filename for Content-Disposition (cache copy, not the user's original name)."""
    return f"{str(digest or 'media')[:16]}.mp4"
