"""1.6.4 "Guardar en librería / Save to library": keep the current value of a WanGP audio or video input.

Gradio 5's own trim (the scissors on audio and video inputs) never edits the original: it renders the selection in
the browser (audio: Web Audio -> WAV, video: ffmpeg.wasm) and uploads it as a NEW temp file ("audio.wav" /
"video.mp4") that becomes the component's value. So saving the component's current value saves the trimmed version.
Gradio's temp files can be cleaned at any time, so the file is copied right away.

- Audio -> the managed "saved_audio" folder in the plugin data dir ("Audios guardados" / "Saved audio" in the browser),
  watched and indexed like any folder, so it shows up in the media browser at once. Readable file names.
- Video -> the Video Library through api.add_video (copied into videos/<id>/).
The source file is only read. Undo removes only the copy this save created.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import uuid
from typing import Any, Dict, Optional

try:
    from . import storage, imagelib, videostore, media, mediainfo
except ImportError:  # top-level import (unit tests)
    import storage, imagelib, videostore, media, mediainfo  # type: ignore

AUDIO_KEY = "saved_audio"
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus")
SUFFIX = {"es": "recorte", "en": "trim"}
GRADIO_TRIM_NAMES = ("audio.wav", "video.mp4")   # what Gradio 5 names a trimmed upload


class SaveError(Exception):
    pass


def audio_dir() -> str:
    return os.path.join(os.path.dirname(storage.COLLECTIONS_DIR), AUDIO_KEY)


def clean_name(name, fallback: str = "audio") -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(name or ""))
    t = re.sub(r"\s+", " ", t).strip().strip(".").strip()
    return t[:100].strip() or fallback


def stem_of(path_or_name) -> str:
    b = os.path.basename(str(path_or_name or "").replace("\\", "/").rstrip("/"))
    return os.path.splitext(b)[0]


def result_name(stem: str, trimmed: bool, lang: str = "es") -> str:
    """'clip' -> 'clip (recorte)' when trimmed. Never stacks: 'clip (recorte)' trimmed again stays 'clip (recorte)'."""
    base = clean_name(stem, "audio")
    if not trimmed:
        return base
    for suf in SUFFIX.values():
        if base.lower().endswith(f" ({suf})"):
            return base
    return f"{base} ({SUFFIX.get(lang, SUFFIX['en'])})"


def duration(path: str) -> float:
    try:
        return float((mediainfo.probe_audio(path) or {}).get("duration") or 0.0)
    except Exception:
        return 0.0


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _src(path) -> str:
    if isinstance(path, dict):   # FileData-like dicts: {"path": ...} or gr.Video's {"video": {"path": ...}}
        inner = path.get("video")
        path = inner.get("path") if isinstance(inner, dict) else path.get("path")
    if isinstance(path, (list, tuple)) and path:
        path = path[0]
    if not isinstance(path, str) or not path or not os.path.isfile(path):
        raise SaveError("no file in this input")
    return path


def kind_for(path: str) -> str:
    e = os.path.splitext(path)[1].lower()
    return "audio" if e in AUDIO_EXTS else "video" if media.is_video_path(path) else ""


def _unique(folder: str, name: str, ext: str) -> str:
    cand, n = os.path.join(folder, name + ext), 2
    while os.path.exists(cand):
        cand, n = os.path.join(folder, f"{name} {n}{ext}"), n + 1
    return cand


def save_audio(src, name: Optional[str] = None, trimmed: bool = False, lang: str = "es") -> Dict[str, Any]:
    src = _src(src)
    if kind_for(src) != "audio":
        raise SaveError("not an audio file")
    folder = audio_dir()
    os.makedirs(folder, exist_ok=True)
    # copy first (Gradio may clean its temp file any moment), then decide
    tmp = os.path.join(folder, f".incoming-{uuid.uuid4().hex}{os.path.splitext(src)[1].lower()}")
    shutil.copyfile(src, tmp)
    try:
        digest = _sha(tmp)
        f = imagelib.ensure_managed_folder(folder, AUDIO_KEY)
        same = next((p for p, v in imagelib.load_folders()["files"].items() if v["folder"] == f["id"] and v["hash"] == digest and os.path.isfile(p)), None)
        if same:
            os.remove(tmp)
            return {"ok": True, "kind": "audio", "created": False, "path": same, "name": stem_of(same), "hash": digest,
                    "duration": duration(same), "folder_id": f["id"]}
        final = result_name(stem_of(name) if name else stem_of(src), trimmed, lang)
        dest = _unique(folder, final, os.path.splitext(src)[1].lower())
        os.replace(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    imagelib.rescan([f["id"]])
    return {"ok": True, "kind": "audio", "created": True, "path": dest, "name": stem_of(dest), "hash": digest,
            "duration": duration(dest), "folder_id": f["id"]}


def undo_audio(path: str) -> Dict[str, Any]:
    """Delete a copy made by save_audio (only files inside the managed folder)."""
    folder = os.path.realpath(audio_dir())
    real = os.path.realpath(str(path or ""))
    if not real.startswith(folder.rstrip(os.sep) + os.sep) or not os.path.isfile(real):
        raise SaveError("not a saved audio file")
    os.remove(real)
    f = imagelib.ensure_managed_folder(folder, AUDIO_KEY)
    imagelib.rescan([f["id"]])
    return {"ok": True}


def save_video(src, name: Optional[str] = None, trimmed: bool = False, lang: str = "es", field: str = "") -> Dict[str, Any]:
    """Through the public api.add_video (source "wangp-input": always saves, deduped by content)."""
    try:
        from . import api
    except ImportError:
        import api  # type: ignore
    src = _src(src)
    if kind_for(src) != "video":
        raise SaveError("not a video file")
    digest = videostore.file_hash(src)
    existing = videostore.find_by_hash(digest)
    if existing:
        return {"ok": True, "kind": "video", "created": False, "id": existing["id"], "name": existing["name"],
                "duration": float(existing.get("duration") or 0)}
    final = result_name(stem_of(name) if name else stem_of(src), trimmed, lang)
    vid = api.add_video(src, name=final, source="wangp-input",
                        meta={"input": str(field)[:40], "trimmed": bool(trimmed), "source_name": stem_of(name or src)[:120],
                              "saved": round(time.time(), 1)})
    api.take_note(src)   # no "saved to library" notice from the crop watcher: we show our own toast
    if not vid:
        raise SaveError("could not save the video")
    v = videostore.get_video(vid)
    return {"ok": True, "kind": "video", "created": True, "id": vid, "name": v["name"], "duration": float(v.get("duration") or 0)}


def undo_video(vid: str) -> Dict[str, Any]:
    videostore.soft_delete(vid)
    return {"ok": True}


def save(field: str, value, name: Optional[str] = None, trimmed: bool = False, lang: str = "es") -> Dict[str, Any]:
    """Entry point for the plugin: audio or video by the file itself. Raises SaveError."""
    src = _src(value)
    k = kind_for(src)
    if k == "audio":
        return save_audio(src, name, trimmed, lang)
    if k == "video":
        return save_video(src, name, trimmed, lang, field)
    raise SaveError("not an audio or video file")
