"""Video facts and poster frames for the Reference Library video library.

Uses WanGP's own ffprobe lookup when available (same binary WanGP uses), then OpenCV (always installed with WanGP),
then plain ffprobe/ffmpeg on PATH. Never raises: missing facts are 0 / None.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".wmv", ".ts", ".mts", ".m2ts", ".flv", ".3gp")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_video_path(path) -> bool:
    return isinstance(path, str) and os.path.splitext(path)[1].lower() in VIDEO_EXTS


BINARY_RESOLVER = None   # host hook (1.5.0): the WanGP adapter sets WanGP's resolver; standalone apps may leave it


def find_binary(name):
    try:
        path = BINARY_RESOLVER(name) if BINARY_RESOLVER else None
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def _ratio(text):
    try:
        a, b = str(text).split("/", 1)
        a, b = float(a), float(b)
        return a / b if b else 0.0
    except Exception:
        try:
            return float(text)
        except Exception:
            return 0.0


def scan_duration(path, stream="v:0", timeout=120) -> float:
    """Duration of a file whose container doesn't say it (1.6.7): browser MediaRecorder WebM / Matroska written live has
    no duration and no cues, so format/stream duration are missing and players report Infinity. Reads only the packet
    timestamps of one stream (no decoding: ~0.3 s for a 65 MB / 3.5 min webcam clip) and returns the end of the last
    packet. 0.0 when there's no ffprobe or nothing readable."""
    exe = find_binary("ffprobe")
    if not exe or not isinstance(path, str) or not os.path.isfile(path):
        return 0.0
    cmd = [exe, "-v", "error", "-select_streams", stream, "-show_entries", "packet=pts_time,dts_time,duration_time",
           "-of", "csv=p=0", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout,
                             creationflags=_NO_WINDOW)
    except Exception:
        return 0.0
    end = 0.0
    first = None
    for line in (res.stdout or "").splitlines():
        parts = line.strip().split(",")
        if not parts:
            continue
        t = None
        for v in parts[:2]:
            try:
                t = float(v)
                break
            except Exception:
                continue
        if t is None:
            continue
        try:
            d = float(parts[2]) if len(parts) > 2 else 0.0
        except Exception:
            d = 0.0
        if first is None or t < first:
            first = t
        end = max(end, t + max(0.0, d))
    if first and first > 0 and first < end:   # streams that don't start at 0 (rare in recordings): the span
        end -= first
    return round(end, 3) if end > 0 else 0.0


def _probe_ffprobe(path):
    exe = find_binary("ffprobe")
    if not exe:
        return None
    cmd = [exe, "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format", "-of", "json", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30,
                             creationflags=_NO_WINDOW)
        data = json.loads(res.stdout or "{}")
    except Exception:
        return None
    streams = data.get("streams") or []
    if not streams:
        return None
    s = streams[0]
    width, height = int(s.get("width") or 0), int(s.get("height") or 0)
    if width <= 0 or height <= 0:
        return None
    rotation = 0
    for side in s.get("side_data_list") or []:
        try:
            rotation = int(float(side.get("rotation") or 0))
        except Exception:
            pass
    try:
        rotation = rotation or int(float((s.get("tags") or {}).get("rotate") or 0))
    except Exception:
        pass
    if abs(rotation) % 180 == 90:
        width, height = height, width
    fps = _ratio(s.get("avg_frame_rate")) or _ratio(s.get("r_frame_rate"))
    duration = 0.0
    for src in (s.get("duration"), (data.get("format") or {}).get("duration")):
        try:
            duration = float(src)
            if duration > 0:
                break
        except Exception:
            continue
    if duration <= 0:   # 1.6.7: MediaRecorder WebM & co. carry no duration
        duration = scan_duration(path, "v:0")
    try:
        frames = int(s.get("nb_frames") or 0)
    except Exception:
        frames = 0
    if not frames and fps and duration:
        frames = int(round(fps * duration))
    return {"width": width, "height": height, "fps": round(fps, 3), "frames": frames, "duration": round(duration, 3)}


def _probe_cv2(path):
    try:
        import cv2
    except Exception:
        return None
    cap = None
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if width <= 0 or height <= 0:
            return None
        duration = frames / fps if fps > 0 and frames > 0 else 0.0
        if duration <= 0:
            duration = scan_duration(path, "v:0")
        return {"width": width, "height": height, "fps": round(fps, 3), "frames": max(frames, 0), "duration": round(duration, 3)}
    except Exception:
        return None
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass


def probe(path) -> dict:
    """{width, height, fps, frames, duration}; zeros when the file can't be read."""
    empty = {"width": 0, "height": 0, "fps": 0.0, "frames": 0, "duration": 0.0}
    if not isinstance(path, str) or not os.path.isfile(path):
        return empty
    return _probe_ffprobe(path) or _probe_cv2(path) or empty


def make_poster(path, dest, max_side=480, at=0.1) -> bool:
    """Write a JPEG poster frame (frame at `at` of the duration, first frame as fallback). True when written."""
    tmp = dest + ".part.jpg"
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        try:
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            ok, frame = False, None
            if frames > 1:
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(frames - 1, int(frames * at))))
                ok, frame = cap.read()
            if not ok or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
        finally:
            cap.release()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            scale = min(1.0, float(max_side) / max(h, w))
            if scale < 1.0:
                frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if ok:
                with open(tmp, "wb") as writer:
                    writer.write(buf.tobytes())
                os.replace(tmp, dest)
                return True
    except Exception:
        pass
    exe = find_binary("ffmpeg")
    if not exe:
        return False
    try:
        info = probe(path)
        ss = max(0.0, info["duration"] * at) if info["duration"] else 0.0
        cmd = [exe, "-v", "error", "-y", "-ss", f"{ss:.3f}", "-i", path, "-frames:v", "1",
               "-vf", f"scale='min({max_side},iw)':-2", "-q:v", "4", tmp]
        subprocess.run(cmd, capture_output=True, timeout=60, creationflags=_NO_WINDOW)
        if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, dest)
            return True
    except Exception:
        pass
    try:
        os.unlink(tmp)
    except OSError:
        pass
    return False


def fmt_duration(seconds) -> str:
    try:
        total = float(seconds or 0)
    except Exception:
        total = 0.0
    if total <= 0:
        return "–"
    if total < 10:
        return f"{total:.1f} s"
    s = int(round(total))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(nbytes) -> str:
    try:
        n = float(nbytes or 0)
    except Exception:
        n = 0.0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def fmt_fps(fps) -> str:
    try:
        f = float(fps or 0)
    except Exception:
        return ""
    if f <= 0:
        return ""
    return f"{f:.0f} fps" if abs(f - round(f)) < 0.01 else f"{f:.2f} fps"
