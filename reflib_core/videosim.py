"""Video frame sampling for similarity / Personas (1.12.0-videofaces).

Samples frames at a fixed interval plus cheap scene cuts (HSV histogram diff),
capped per video. Used by SimService to index kind=video items. Pure helpers
here so unit tests need no models.
"""
from __future__ import annotations
import os, shutil, subprocess, tempfile, warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# defaults (mirrored in similarity.DEFAULTS)
INTERVAL_S = 2.0
MAX_FRAMES = 60
SCENE_THR = 0.35   # mean abs HSV-hist diff in [0,1]; ~scene change
MERGE_GAP_S = 4.0  # merge nearby match times into one segment


def video_cache_key(mtime: float, interval_s: float, scene: bool, max_frames: int) -> Dict[str, Any]:
    """Stable fingerprint stored on the index item so unchanged videos are skipped."""
    return {
        "mtime": float(mtime),
        "interval_s": float(interval_s),
        "scene": bool(scene),
        "max_frames": int(max_frames),
    }


def merge_segments(times: Sequence[float], gap: float = MERGE_GAP_S) -> List[Dict[str, float]]:
    """Merge sorted (or unsorted) timestamps into [{t0, t1}, ...] when consecutive gaps ≤ gap."""
    ts = sorted(float(t) for t in times if t is not None and np.isfinite(t))
    if not ts:
        return []
    out = [{"t0": ts[0], "t1": ts[0]}]
    for t in ts[1:]:
        if t - out[-1]["t1"] <= gap:
            out[-1]["t1"] = t
        else:
            out.append({"t0": t, "t1": t})
    for s in out:
        s["t0"] = round(s["t0"], 3)
        s["t1"] = round(s["t1"], 3)
    return out


def _hist(frame_bgr: np.ndarray) -> np.ndarray:
    import cv2
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    h = h.astype(np.float32).ravel()
    s = float(h.sum()) or 1.0
    return h / s


def _hist_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean()) * 8.0  # scale so typical cuts land near 0.3–0.6


def sample_times(duration: float, fps: float, interval_s: float, max_frames: int,
                 scene_times: Optional[Sequence[float]] = None) -> List[float]:
    """Uniform grid + optional scene-cut times, capped to max_frames (prefer even spacing)."""
    duration = max(0.0, float(duration or 0))
    interval_s = max(0.2, float(interval_s or INTERVAL_S))
    max_frames = max(1, int(max_frames or MAX_FRAMES))
    times: List[float] = []
    if duration <= 0:
        times = [0.0]
    else:
        t = 0.0
        while t < duration - 1e-3 and len(times) < max_frames * 4:
            times.append(round(t, 4))
            t += interval_s
        if not times or times[-1] < duration - 0.05:
            times.append(round(max(0.0, duration - 1.0 / max(fps, 1.0)), 4))
    for st in scene_times or ():
        if 0 <= st < duration:
            times.append(round(float(st), 4))
    times = sorted(set(times))
    if len(times) > max_frames:
        # keep endpoints + evenly spaced middle
        idx = np.linspace(0, len(times) - 1, max_frames).round().astype(int)
        times = [times[i] for i in sorted(set(idx.tolist()))]
    return times


def _open_capture(path: str):
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return None
    return cap


def _ffmpeg_extract(path: str, times: List[float], out_dir: str) -> List[Tuple[float, str]]:
    """Fallback: extract individual frames with ffmpeg (PATH or WanGP's)."""
    ff = shutil.which("ffmpeg")
    if not ff:
        for cand in (
            os.path.join(os.getcwd(), "ffmpeg.exe"),
            os.path.join(os.getcwd(), "ffmpeg"),
            os.path.join(os.path.dirname(os.getcwd()), "ffmpeg", "ffmpeg.exe"),
        ):
            if os.path.isfile(cand):
                ff = cand
                break
    if not ff:
        return []
    out: List[Tuple[float, str]] = []
    for i, t in enumerate(times):
        dest = os.path.join(out_dir, "f%04d.jpg" % i)
        try:
            r = subprocess.run(
                [ff, "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % t, "-i", path,
                 "-frames:v", "1", "-q:v", "3", "-y", dest],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0:
                out.append((t, dest))
        except Exception:
            continue
    return out


def sample_frames(path: str, interval_s: float = INTERVAL_S, scene_detect: bool = True,
                  max_frames: int = MAX_FRAMES, scene_thr: float = SCENE_THR,
                  out_dir: Optional[str] = None) -> Dict[str, Any]:
    """Decode `path` and write JPEG frames to out_dir (temp if None).

    Returns {ok, times, paths, w, h, duration, fps, mtime, method, warning?}
    method = "cv2" | "ffmpeg" | "".
    """
    import cv2
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "file not found", "times": [], "paths": []}
    mtime = os.path.getmtime(path)
    own_dir = out_dir is None
    if own_dir:
        out_dir = tempfile.mkdtemp(prefix="rlvid_")
    cap = _open_capture(path)
    warning = ""
    method = "cv2"
    if cap is None:
        warning = "cv2 cannot open; trying ffmpeg"
        # probe duration via ffprobe/ffmpeg roughly: we still need times — use ffmpeg with interval
        # Without duration, sample first max_frames seconds at interval
        duration, fps = float(max_frames) * float(interval_s), 25.0
        times = sample_times(duration, fps, interval_s, max_frames, None)
        pairs = _ffmpeg_extract(path, times, out_dir)
        if not pairs:
            if own_dir:
                shutil.rmtree(out_dir, ignore_errors=True)
            return {"ok": False, "error": "cannot decode video (cv2/ffmpeg)", "times": [], "paths": [], "warning": warning}
        w = h = 0
        try:
            im = cv2.imread(pairs[0][1])
            if im is not None:
                h, w = im.shape[:2]
        except Exception:
            pass
        return {"ok": True, "times": [t for t, _ in pairs], "paths": [p for _, p in pairs],
                "w": w, "h": h, "duration": duration, "fps": fps, "mtime": mtime,
                "method": "ffmpeg", "warning": warning, "tmpdir": out_dir if own_dir else None}

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = (nframes / fps) if nframes > 0 else 0.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    scene_times: List[float] = []
    prev_hist = None
    if scene_detect and nframes > 0:
        # cheap pass: read every ~0.5s for hist diffs (capped)
        step = max(1, int(round(fps * 0.5)))
        fi = 0
        while fi < nframes:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok, frame = cap.read()
            if not ok or frame is None:
                fi += step
                continue
            hist = _hist(frame)
            if prev_hist is not None and _hist_diff(prev_hist, hist) >= scene_thr:
                scene_times.append(fi / fps)
            prev_hist = hist
            fi += step
            if len(scene_times) >= max_frames:
                break

    times = sample_times(duration or (max_frames * interval_s), fps, interval_s, max_frames, scene_times if scene_detect else None)
    paths: List[str] = []
    got_times: List[float] = []
    for i, t in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            # try frame index
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
            ok, frame = cap.read()
        if not ok or frame is None:
            continue
        dest = os.path.join(out_dir, "f%04d.jpg" % i)
        try:
            cv2.imwrite(dest, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if os.path.isfile(dest):
                paths.append(dest)
                got_times.append(t)
                if w <= 0 or h <= 0:
                    h, w = frame.shape[:2]
        except Exception:
            continue
    cap.release()

    if not paths:
        warning = (warning + "; " if warning else "") + "cv2 seek failed; trying ffmpeg"
        pairs = _ffmpeg_extract(path, times, out_dir)
        if pairs:
            method = "ffmpeg"
            got_times = [t for t, _ in pairs]
            paths = [p for _, p in pairs]
        else:
            if own_dir:
                shutil.rmtree(out_dir, ignore_errors=True)
            return {"ok": False, "error": "no frames decoded", "times": [], "paths": [], "warning": warning}

    return {"ok": True, "times": got_times, "paths": paths, "w": w, "h": h,
            "duration": duration, "fps": fps, "mtime": mtime, "method": method,
            "warning": warning, "tmpdir": out_dir if own_dir else None}


def read_frame_at(path: str, t: float) -> Optional[np.ndarray]:
    """BGR uint8 frame at t seconds, or None. cv2 first, ffmpeg fallback to temp JPEG."""
    import cv2
    cap = _open_capture(path)
    if cap is not None:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t)) * 1000.0)
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            return frame
    td = tempfile.mkdtemp(prefix="rlvid1_")
    try:
        pairs = _ffmpeg_extract(path, [float(t)], td)
        if pairs:
            im = cv2.imread(pairs[0][1])
            return im
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return None


def cleanup_sample(result: Dict[str, Any]):
    td = result.get("tmpdir")
    if td:
        shutil.rmtree(td, ignore_errors=True)
