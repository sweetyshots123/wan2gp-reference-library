"""Video resize (1.6.2): short-side presets (480p / 720p / 1080p), aspect kept, sides multiples of 16 (WanGP-friendly),
no upscaling unless confirmed. ffmpeg with NVENC when it really works on this machine, else libx264 CRF 18; audio kept.
The source file is never touched: the result is written to a private temp folder, the caller stores it (Video Library)
and the temp file is deleted. Jobs run one at a time in a background thread with progress."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from . import media

PRESETS = {"480p": 480, "720p": 720, "1080p": 1080}
ALIGN = 16
_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_run_lock = threading.Lock()
_enc_cache: Dict[str, Any] = {}


def _tmp_dir() -> str:
    from . import storage
    d = os.path.join(os.path.dirname(storage.COLLECTIONS_DIR), ".resize_tmp")
    os.makedirs(d, exist_ok=True)
    return d


def _ffprobe_info(path: str) -> Dict[str, Any]:
    """{width, height (as displayed, rotation applied), duration, has_audio}."""
    exe = media.find_binary("ffprobe")
    info = {"width": 0, "height": 0, "duration": 0.0, "has_audio": False}
    if exe:
        try:
            r = subprocess.run([exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                               capture_output=True, timeout=30, **_noshow())
            d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
            vs = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
            info["has_audio"] = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
            if vs:
                w, h = int(vs.get("width") or 0), int(vs.get("height") or 0)
                rot = 0
                try:
                    rot = int(float((vs.get("tags") or {}).get("rotate") or 0))
                except Exception:
                    pass
                for sd in vs.get("side_data_list") or []:
                    if "rotation" in sd:
                        try:
                            rot = int(float(sd["rotation"]))
                        except Exception:
                            pass
                if abs(rot) % 180 == 90:
                    w, h = h, w
                info["width"], info["height"] = w, h
                info["duration"] = float(vs.get("duration") or (d.get("format") or {}).get("duration") or 0)
        except Exception:
            pass
    if not info["width"]:
        p = media.probe(path)
        info.update(width=p.get("width", 0), height=p.get("height", 0), duration=p.get("duration", 0.0))
    return info


def _noshow() -> Dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


def _align(v: float) -> int:
    return max(ALIGN, int(round(v / ALIGN)) * ALIGN)


def target_size(w: int, h: int, preset: str) -> Tuple[int, int]:
    """Short side = the preset exactly (480 / 720 are multiples of 16, 1080 is even), long side scaled and rounded to a
    multiple of 16 (so the aspect ratio moves by at most a few pixels)."""
    short = PRESETS[preset]
    if w <= 0 or h <= 0:
        return 0, 0
    s = short / float(min(w, h))
    if w <= h:
        return short, _align(h * s)
    return _align(w * s), short


def plan(path: str, preset: str) -> Dict[str, Any]:
    if preset not in PRESETS:
        raise ValueError("bad preset")
    info = _ffprobe_info(path)
    w, h = info["width"], info["height"]
    tw, th = target_size(w, h, preset)
    return {"src": [w, h], "dst": [tw, th], "upscale": bool(w and h and (tw > w or th > h) and min(w, h) < PRESETS[preset]),
            "same": [w, h] == [tw, th], "duration": info["duration"], "has_audio": info["has_audio"]}


def encoder() -> Dict[str, Any]:
    """NVENC when listed AND a 1-frame test encode works (driver / GPU present); else libx264. Cached."""
    if "enc" in _enc_cache:
        return _enc_cache["enc"]
    exe = media.find_binary("ffmpeg")
    enc = {"name": "libx264", "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]}
    if exe and os.environ.get("REFLIB_NO_NVENC") != "1":
        try:
            r = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, timeout=20, **_noshow())
            if b"h264_nvenc" in r.stdout:
                t = subprocess.run([exe, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1", "-frames:v", "1",
                                    "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=30, **_noshow())
                if t.returncode == 0:
                    enc = {"name": "h264_nvenc", "args": ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr",
                                                          "-cq", "19", "-b:v", "0", "-spatial-aq", "1"]}
        except Exception:
            pass
    _enc_cache["enc"] = enc
    return enc


def start(src: str, preset: str, name: str, on_done=None) -> str:
    """Start a background job. on_done(out_path, job) -> dict result (e.g. store into the Video Library); its return
    value is kept in job["result"]. The temp file is deleted afterwards."""
    jid = uuid.uuid4().hex[:16]
    job = {"id": jid, "state": "queued", "progress": 0.0, "error": None, "result": None, "preset": preset, "name": name,
           "cancel": threading.Event(), "t0": time.time()}
    with _lock:
        _jobs[jid] = job
        for k in [k for k, j in _jobs.items() if j["state"] in ("done", "error", "cancelled") and time.time() - j["t0"] > 3600]:
            _jobs.pop(k, None)
    threading.Thread(target=_run, args=(job, src, preset, on_done), daemon=True, name=f"reflib-resize-{jid}").start()
    return jid


def _run(job, src, preset, on_done):
    with _run_lock:   # one encode at a time
        if job["cancel"].is_set():
            job["state"] = "cancelled"; return
        job["state"] = "running"
        out = os.path.join(_tmp_dir(), f"{job['id']}.mp4")
        try:
            p = plan(src, preset)
            tw, th = p["dst"]
            if not tw:
                raise RuntimeError("could not read the video size")
            job.update(src_size=p["src"], dst_size=[tw, th])
            exe = media.find_binary("ffmpeg")
            if not exe:
                raise RuntimeError("ffmpeg not found")
            enc = encoder()
            job["encoder"] = enc["name"]
            ok = _encode(exe, src, out, tw, th, enc, p, job, audio_copy=True)
            if not ok and not job["cancel"].is_set() and p["has_audio"]:
                ok = _encode(exe, src, out, tw, th, enc, p, job, audio_copy=False)   # audio not mp4-compatible: AAC
            if not ok and not job["cancel"].is_set() and enc["name"] != "libx264":
                job["encoder"] = "libx264"
                ok = _encode(exe, src, out, tw, th, {"name": "libx264", "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]},
                             p, job, audio_copy=False)
            if job["cancel"].is_set():
                job["state"] = "cancelled"; return
            if not ok:
                raise RuntimeError(job.get("ff_err") or "ffmpeg failed")
            job["progress"] = 1.0
            job["result"] = on_done(out, job) if on_done else {"path": out}
            job["state"] = "done"
        except Exception as e:
            job["state"], job["error"] = "error", str(e)[:300]
        finally:
            if on_done:
                try:
                    os.unlink(out)
                except OSError:
                    pass


def _encode(exe, src, out, tw, th, enc, p, job, audio_copy=True) -> bool:
    vf = f"scale={tw}:{th}:flags=lanczos,setsar=1,format=yuv420p"
    a = (["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"]) if p["has_audio"] else ["-an"]
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", src, "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
           *enc["args"], *a, "-map_metadata", "0", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", out]
    dur = max(0.01, float(p.get("duration") or 0))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_noshow())
    except Exception as e:
        job["ff_err"] = str(e); return False
    err = []
    t = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True); t.start()
    for line in iter(proc.stdout.readline, b""):
        if job["cancel"].is_set():
            proc.kill(); break
        m = re.match(rb"out_time_(?:us|ms)=(\d+)", line)
        if m:
            job["progress"] = max(job["progress"], min(0.99, int(m.group(1)) / 1e6 / dur))
    proc.wait(); t.join(2)
    if proc.returncode != 0:
        job["ff_err"] = (err[0].decode("utf-8", "replace").strip().splitlines() or ["ffmpeg failed"])[-1][:300] if err and err[0] else "ffmpeg failed"
        try:
            os.unlink(out)
        except OSError:
            pass
        return False
    return os.path.isfile(out) and os.path.getsize(out) > 0


def status(jid: str) -> Optional[Dict[str, Any]]:
    j = _jobs.get(str(jid or ""))
    if not j:
        return None
    return {k: j.get(k) for k in ("id", "state", "progress", "error", "result", "preset", "encoder", "src_size", "dst_size", "name")}


def cancel(jid: str) -> bool:
    j = _jobs.get(str(jid or ""))
    if not j:
        return False
    j["cancel"].set()
    return True


def result_name(name: str, preset: str) -> str:
    base = re.sub(r"\s*\((?:480p|720p|1080p)\)\s*$", "", os.path.splitext(str(name or "video"))[0]).strip() or "video"
    return f"{base} ({preset})"
