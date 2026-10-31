"""Persistent storage for the Reference Library video library (control / reference videos).

Layout (inside the plugin folder, next to collections/; never shipped in the zip, gitignored):
  videos/
    videos.json            # index, in the user's order (newest first unless reordered)
    <video_id>/
      video.mp4            # copied file (original extension kept)
      poster.jpg           # poster frame (may be missing if the file couldn't be decoded)
    .trash/                # soft-deleted videos (undo window), purged after 15 minutes

videos.json:
  {"version": 1, "videos": [
     {"id": "uuidhex", "name": "Dance 3:4", "file": "video.mp4", "poster": "poster.jpg" | null,
      "hash": "sha256", "size": 123, "width": 720, "height": 960, "fps": 24.0, "frames": 120, "duration": 5.0,
      "source": "manual" | "cropper" | "import" | "<plugin>", "meta": {...}, "created": 1696..., "updated": 1696...}]}

The image collections (collections/) are a separate store and are never touched from here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import media
    from .storage import StorageError, _safe_name, _inside
except ImportError:  # unit tests import the modules top-level
    import media  # type: ignore
    from storage import StorageError, _safe_name, _inside  # type: ignore

# data root: $REFLIB_DATA_DIR, else the folder that contains reflib_core/ (the WanGP plugin folder); see reflib_core.configure()
PLUGIN_DIR = os.environ.get("REFLIB_DATA_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEOS_DIR = os.path.join(PLUGIN_DIR, "videos")
INDEX_VERSION = 1
TRASH_NAME = ".trash"

_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")
_lock = threading.RLock()
_META_MAX = 4000  # bytes of JSON kept from caller-supplied meta


def _clean_name(name, fallback: str = "Video") -> str:
    """Display names keep characters like ':' ("Dance 3:4"); only control characters and extra spaces go."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(name or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return (text or str(fallback or "Video"))[:120]


def videos_dir() -> str:
    return VIDEOS_DIR


def _index_path() -> str:
    return os.path.join(VIDEOS_DIR, "videos.json")


def _trash_root() -> str:
    return os.path.join(VIDEOS_DIR, TRASH_NAME)


def _check_id(video_id: str) -> str:
    vid = str(video_id or "").strip().lower()
    if not _ID_RE.match(vid):
        raise StorageError("video not found")
    return vid


def _video_dir(video_id: str) -> str:
    return os.path.join(VIDEOS_DIR, _check_id(video_id))


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as reader:
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_json(path: str, data: Any) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".videos_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(data, writer, indent=2, ensure_ascii=False)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _clean_meta(meta) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    try:
        text = json.dumps(meta, ensure_ascii=False, default=str)
    except Exception:
        return {}
    if len(text.encode("utf-8")) > _META_MAX:
        return {"truncated": True}
    try:
        return json.loads(text)
    except Exception:
        return {}


def _num(value, kind=float, default=0):
    try:
        out = kind(value)
        return out if out == out and out >= 0 else default  # NaN / negative -> default
    except Exception:
        return default


def _clean_entry(entry) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    vid = str(entry.get("id") or "")
    if not _ID_RE.match(vid):
        return None
    fname = os.path.basename(str(entry.get("file") or ""))
    if not fname or fname in (".", ".."):
        return None
    poster = entry.get("poster")
    poster = os.path.basename(str(poster)) if poster else None
    now = time.time()
    return {
        "id": vid,
        "name": _clean_name(entry.get("name"), "Video"),
        "file": fname,
        "poster": poster or None,
        "hash": str(entry.get("hash") or "")[:64],
        "size": _num(entry.get("size"), int, 0),
        "width": _num(entry.get("width"), int, 0),
        "height": _num(entry.get("height"), int, 0),
        "fps": _num(entry.get("fps"), float, 0.0),
        "frames": _num(entry.get("frames"), int, 0),
        "duration": _num(entry.get("duration"), float, 0.0),
        "source": str(entry.get("source") or "manual")[:40],
        "meta": _clean_meta(entry.get("meta")),
        "created": _num(entry.get("created"), float, 0.0) or now,
        "updated": _num(entry.get("updated"), float, 0.0) or now,
    }


def load_index() -> Dict[str, Any]:
    try:
        with open(_index_path(), "r", encoding="utf-8") as reader:
            data = json.load(reader)
    except FileNotFoundError:
        return {"version": INDEX_VERSION, "videos": []}
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid videos.json: {e}")
        return {"version": INDEX_VERSION, "videos": []}
    items = data.get("videos") if isinstance(data, dict) else None
    out, seen = [], set()
    for entry in items if isinstance(items, list) else []:
        clean = _clean_entry(entry)
        if clean and clean["id"] not in seen:
            seen.add(clean["id"])
            out.append(clean)
    return {"version": INDEX_VERSION, "videos": out}


def save_index(index: Dict[str, Any]) -> None:
    _atomic_write_json(_index_path(), {"version": INDEX_VERSION, "videos": list(index.get("videos") or [])})


def list_videos() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(v) for v in load_index()["videos"]]


def get_video(video_id: str) -> Dict[str, Any]:
    with _lock:
        vid = _check_id(video_id)
        for v in load_index()["videos"]:
            if v["id"] == vid:
                return dict(v)
        raise StorageError("video not found")


def _file_in(video: Dict[str, Any], fname: Optional[str]) -> Optional[str]:
    if not fname:
        return None
    path = os.path.join(_video_dir(video["id"]), os.path.basename(fname))
    if _inside(path, VIDEOS_DIR) and os.path.isfile(path):
        return os.path.realpath(path)
    return None


def video_file(video_or_id) -> str:
    video = video_or_id if isinstance(video_or_id, dict) else get_video(video_or_id)
    path = _file_in(video, video.get("file"))
    if not path:
        raise StorageError("video file not found")
    return path


def poster_file(video_or_id) -> Optional[str]:
    try:
        video = video_or_id if isinstance(video_or_id, dict) else get_video(video_or_id)
    except StorageError:
        return None
    return _file_in(video, video.get("poster"))


def _equivalent_live(index: Dict[str, Any], entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Live entry holding the same video as `entry`: same content hash, or same meta.dedupe_key. Caller holds _lock."""
    digest = entry.get("hash")
    key = str((entry.get("meta") or {}).get("dedupe_key") or "")
    for v in index["videos"]:
        if v["id"] == entry["id"]:
            continue
        if digest and v.get("hash") == digest:
            return v
        if key and str((v.get("meta") or {}).get("dedupe_key") or "") == key:
            return v
    return None


def find_by_hash(digest: str) -> Optional[Dict[str, Any]]:
    if not digest:
        return None
    with _lock:
        for v in load_index()["videos"]:
            if v.get("hash") == digest:
                return dict(v)
    return None


def find_by_key(key: str) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    with _lock:
        for v in load_index()["videos"]:
            if str((v.get("meta") or {}).get("dedupe_key") or "") == str(key):
                return dict(v)
    return None


def name_taken(name: str, exclude_id: Optional[str] = None) -> bool:
    key = _clean_name(name, "").casefold()
    return any(v["name"].casefold() == key and v["id"] != exclude_id for v in load_index()["videos"])


def unique_name(name: str, fallback: str = "Video", exclude_id: Optional[str] = None) -> str:
    """`name`, or `name 2`, `name 3`... when another video already uses it (case-insensitive)."""
    with _lock:
        base = _clean_name(name, "") if (name or "").strip() else _clean_name(fallback, "Video")
        if not name_taken(base, exclude_id):
            return base
        n = 2
        while name_taken(f"{base} {n}", exclude_id):
            n += 1
        return f"{base} {n}"


def name_from_path(path: str) -> str:
    stem = os.path.splitext(os.path.basename(str(path or "")))[0]
    stem = re.sub(r"[_\-.]+", " ", stem).strip()
    return stem


def _ext(path: str) -> str:
    ext = os.path.splitext(str(path or ""))[1].lower()
    return ext if ext in media.VIDEO_EXTS else ".mp4"


def add_video(src: str, name: Optional[str] = None, source: str = "manual", meta: Optional[dict] = None,
              fallback: str = "Video", digest: Optional[str] = None) -> Tuple[Dict[str, Any], bool]:
    """Copy `src` into the library. Returns (entry, created). A file whose content (sha256) is already in the library,
    or whose meta.dedupe_key matches an existing video, is not added again: (existing entry, False)."""
    if not isinstance(src, str) or not os.path.isfile(src):
        raise StorageError("source video not found")
    if not media.is_video_path(src):
        raise StorageError("not a video file")
    meta = _clean_meta(meta)
    digest = digest or file_hash(src)
    with _lock:
        existing = find_by_hash(digest) or find_by_key(meta.get("dedupe_key"))
        if existing:
            return existing, False
        vid = uuid.uuid4().hex
        folder = os.path.join(VIDEOS_DIR, vid)
        os.makedirs(folder, exist_ok=True)
        fname = "video" + _ext(src)
        dest = os.path.join(folder, fname)
        try:
            shutil.copyfile(src, dest)
            if not _inside(dest, VIDEOS_DIR):
                raise StorageError("path safety check failed")
            info = media.probe(dest)
            poster = "poster.jpg" if media.make_poster(dest, os.path.join(folder, "poster.jpg")) else None
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        now = time.time()
        clean_name = unique_name(name if (name or "").strip() else name_from_path(src), fallback)
        entry = _clean_entry({
            "id": vid, "name": clean_name, "file": fname, "poster": poster, "hash": digest,
            "size": os.path.getsize(dest), **info, "source": source or "manual", "meta": meta,
            "created": now, "updated": now,
        })
        index = load_index()
        index["videos"].insert(0, entry)  # newest first
        save_index(index)
        return dict(entry), True


def rename_video(video_id: str, name: str, fallback: str = "Video") -> Dict[str, Any]:
    with _lock:
        vid = _check_id(video_id)
        index = load_index()
        for v in index["videos"]:
            if v["id"] == vid:
                v["name"] = unique_name(name, fallback, exclude_id=vid) if (name or "").strip() else v["name"]
                v["updated"] = time.time()
                save_index(index)
                return dict(v)
        raise StorageError("video not found")


def move_video(video_id: str, delta: int) -> Tuple[Dict[str, Any], int]:
    """Move one place up (-1) / down (+1). Returns (entry, new_index)."""
    with _lock:
        vid = _check_id(video_id)
        index = load_index()
        items = index["videos"]
        for i, v in enumerate(items):
            if v["id"] == vid:
                j = i + int(delta)
                if 0 <= j < len(items) and j != i:
                    items[i], items[j] = items[j], items[i]
                    save_index(index)
                    return dict(v), j
                return dict(v), i
        raise StorageError("video not found")


def reorder_videos(ids: List[str]) -> List[Dict[str, Any]]:
    """Set the full order (a permutation of the current ids)."""
    with _lock:
        index = load_index()
        current = [v["id"] for v in index["videos"]]
        wanted = [str(i or "").lower() for i in ids or []]
        if sorted(wanted) != sorted(current):
            raise StorageError("invalid video order")
        by_id = {v["id"]: v for v in index["videos"]}
        index["videos"] = [by_id[i] for i in wanted]
        save_index(index)
        return [dict(v) for v in index["videos"]]


def soft_delete(video_id: str) -> Dict[str, Any]:
    """Remove from the index and move the folder to videos/.trash/<id>/ (undo window)."""
    with _lock:
        vid = _check_id(video_id)
        index = load_index()
        entry, kept, position = None, [], 0
        for i, v in enumerate(index["videos"]):
            if v["id"] == vid:
                entry, position = v, i
            else:
                kept.append(v)
        if entry is None:
            raise StorageError("video not found")
        index["videos"] = kept
        save_index(index)
        trash = _trash_root()
        os.makedirs(trash, exist_ok=True)
        src, dest = _video_dir(vid), os.path.join(trash, vid)
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        if os.path.isdir(src) and _inside(src, VIDEOS_DIR):
            shutil.move(src, dest)
            try:
                os.utime(dest)   # 1.7.3: the undo window starts now (a move keeps the folder's old mtime)
            except OSError:
                pass
        _atomic_write_json(os.path.join(trash, vid + ".json"), {**entry, "_position": position})
        return dict(entry)


def restore_soft_deleted(video_id: str) -> Dict[str, Any]:
    with _lock:
        vid = _check_id(video_id)
        trash = _trash_root()
        meta_path, folder = os.path.join(trash, vid + ".json"), os.path.join(trash, vid)
        if not os.path.isfile(meta_path):
            raise StorageError("undo expired")
        with open(meta_path, "r", encoding="utf-8") as reader:
            raw = json.load(reader)
        entry = _clean_entry(raw)
        if not entry or entry["id"] != vid:
            raise StorageError("undo expired")
        index = load_index()
        if any(v["id"] == vid for v in index["videos"]):
            raise StorageError("video already exists")
        live = _equivalent_live(index, entry)
        if live is not None:
            # The same video was saved again while this one sat in the trash (e.g. the same crop made again).
            # Keep the live entry (its id may already be referenced, e.g. returned to Cropper) and drop the trash copy.
            shutil.rmtree(folder, ignore_errors=True)
            try:
                os.unlink(meta_path)
            except OSError:
                pass
            merged = dict(live)
            merged["_merged_from"] = {"id": vid, "name": entry["name"]}
            return merged
        # Another video may have taken the name meanwhile: keep names unique ("X 2"), as when saving.
        entry["name"] = unique_name(entry["name"], exclude_id=vid)
        dest = _video_dir(vid)
        if os.path.isdir(folder):
            if os.path.isdir(dest):
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(folder, dest)
        position = raw.get("_position") if isinstance(raw.get("_position"), int) else 0
        index["videos"].insert(max(0, min(position, len(index["videos"]))), entry)
        save_index(index)
        try:
            os.unlink(meta_path)
        except OSError:
            pass
        return dict(entry)


def purge_trash(max_age_s: float = 15 * 60) -> None:
    trash = _trash_root()
    if not os.path.isdir(trash):
        return
    now = time.time()
    for name in list(os.listdir(trash)):
        path = os.path.join(trash, name)
        try:
            if now - os.path.getmtime(path) < max_age_s:
                continue
            if os.path.isdir(path):
                # 1.7.3: the video file itself goes to the Recycle Bin / Trash (never a permanent delete); if that fails
                # the folder stays in .trash (retried on the next purge) instead of being destroyed
                vids = [os.path.join(path, f) for f in os.listdir(path) if media.is_video_path(f)]
                if vids:
                    try:
                        from . import forget as _fg
                    except ImportError:
                        import forget as _fg  # type: ignore
                    if _fg.recycle(vids):
                        continue
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.unlink(path)
        except OSError:
            pass


def export_file(video_id: str, dest_dir: str, fallback: str = "Video") -> str:
    """Copy the video out as `<name>.<ext>` (for downloading)."""
    video = get_video(video_id)
    src = video_file(video)
    os.makedirs(dest_dir, exist_ok=True)
    safe = _safe_name(video["name"], fallback).replace(" ", "_")
    dest = os.path.join(dest_dir, safe + os.path.splitext(src)[1])
    shutil.copyfile(src, dest)
    return dest


def export_all_zip(dest_zip: str) -> Tuple[str, int]:
    videos = list_videos()
    dest_zip = os.path.abspath(dest_zip)
    os.makedirs(os.path.dirname(dest_zip) or ".", exist_ok=True)
    count = 0
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_STORED) as zf:
        listed = []
        for v in videos:
            try:
                path = video_file(v)
            except StorageError:
                continue
            arc = f"videos/{v['id']}{os.path.splitext(path)[1]}"
            zf.write(path, arcname=arc)
            listed.append({"file": arc, "name": v["name"], "source": v.get("source"), "meta": v.get("meta") or {},
                           "hash": v.get("hash")})
            count += 1
        zf.writestr("videos.json", json.dumps({"exported_by": "wan2gp-reference-library", "kind": "videos",
                                               "videos": listed}, indent=2, ensure_ascii=False) + "\n")
    return dest_zip, count


def import_zip(zip_path: str, fallback: str = "Video") -> Tuple[List[Dict[str, Any]], int]:
    """Import a zip made by export_all_zip (or any zip with video files). Returns (added entries, skipped duplicates)."""
    if not isinstance(zip_path, str) or not os.path.isfile(zip_path):
        raise StorageError("zip not found")
    added, skipped = [], 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        listing = {}
        if "videos.json" in names:
            try:
                meta = json.loads(zf.read("videos.json").decode("utf-8"))
                for item in meta.get("videos") or []:
                    if isinstance(item, dict) and item.get("file"):
                        listing[str(item["file"])] = item
            except Exception:
                listing = {}
        order = list(listing.keys()) + [n for n in names if n not in listing]
        with tempfile.TemporaryDirectory(prefix="reflib_vimport_") as tmp:
            for member in reversed(order):  # add_video inserts at the top: reverse keeps the zip order
                base = os.path.basename(member)
                if member not in names or not base or ".." in member.replace("\\", "/").split("/") or not media.is_video_path(base):
                    continue
                dest = os.path.join(tmp, base)
                with zf.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                info = listing.get(member) or {}
                entry, created = add_video(dest, name=info.get("name") or name_from_path(base),
                                           source=str(info.get("source") or "import"), meta=info.get("meta"), fallback=fallback)
                if created:
                    added.append(entry)
                else:
                    skipped += 1
                try:
                    os.unlink(dest)
                except OSError:
                    pass
    added.reverse()
    return added, skipped


def public_summary(video: Dict[str, Any]) -> Dict[str, Any]:
    """Compact dict safe for the page (no absolute paths)."""
    return {k: video.get(k) for k in ("id", "name", "width", "height", "fps", "frames", "duration", "size", "source",
                                      "created", "updated")}
