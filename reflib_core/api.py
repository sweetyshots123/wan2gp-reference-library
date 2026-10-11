"""Public API of Reference Library for other WanGP plugins (Prompt Library, Cropper...).

Registered at plugin load as ``sys.modules["wan2gp_reference_library_api"]``. Other plugins should look it up lazily at
call time (load order is not guaranteed) and feature-detect by ``API_VERSION``::

    api = sys.modules.get("wan2gp_reference_library_api")
    if api and getattr(api, "API_VERSION", 0) >= 2:
        api.add_video(path, name="Dance 3:4", source="cropper")

API_VERSION 1 (unchanged): list_collections, get_collection, image_paths. Read-only; collections in the undo trash count
as not found. Prompt Library owns the prompt links.

API_VERSION 2 (Reference Library 1.2.0) adds the video library: list_videos, get_video, video_path, add_video,
crop_policy. No function raises: failures return None / [] and are printed to the console.

API_VERSION 4 (Reference Library 1.4.0) adds read-only list_images / list_tags / image_tags; add_image now stores the
full meta and also returns name + meta.
API_VERSION 3 (Reference Library 1.3.0) adds add_image (crops of start/end, reference and control images) and
image_crop_policy. Everything from v1 and v2 is unchanged.

API_VERSION 4 (Reference Library 1.4.0) adds read-only access to the image browser: list_images, list_tags, image_tags.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

try:
    from . import storage, videostore, media, imagestore, imagelib
except ImportError:  # imported as a top-level module (unit tests)
    import storage  # type: ignore
    import videostore  # type: ignore
    import media  # type: ignore
    import imagestore  # type: ignore
    import imagelib  # type: ignore

API_VERSION = 4
MODULE_NAME = "wan2gp_reference_library_api"
CROP_POLICIES = ("auto", "ask", "off")


# ------------------------------------------------------------------ collections (v1)
def _summary(col: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": col["id"],
        "name": col["name"],
        "count": len(col.get("images") or []),
        "cover_path": storage.cover_path(col),
        "updated": col.get("updated"),
    }


def list_collections() -> List[Dict[str, Any]]:
    """[{id, name, count, cover_path|None, updated}] sorted by name."""
    try:
        return [_summary(c) for c in storage.list_collections()]
    except Exception as e:  # never break the caller
        print(f"[Reference Library] api.list_collections failed: {e}")
        return []


def get_collection(cid: str) -> Optional[Dict[str, Any]]:
    """{id, name, count, cover_path, updated, created, images: [abs paths]} or None (unknown, invalid or trashed)."""
    try:
        col = storage.get_collection(str(cid or ""))
    except Exception:
        return None
    out = _summary(col)
    out["created"] = col.get("created")
    out["images"] = image_paths(col["id"])
    return out


def image_paths(cid: str) -> List[str]:
    """Absolute image paths in collection order; [] when the collection does not exist."""
    try:
        return storage.absolute_image_paths(str(cid or ""))
    except Exception:
        return []


# ------------------------------------------------------------------ videos (v2)
_policy_provider: Callable[[], str] = lambda: "auto"   # plugin.py installs the real one (settings.json)
_fallback_name: Callable[[], str] = lambda: "Video"
_lock = threading.RLock()
_offers: Dict[str, Dict[str, Any]] = {}   # token -> pending "ask" offer {path, name, source, meta, time}
_notes: Dict[str, Dict[str, Any]] = {}    # basename -> what happened to a file handed to add_video (for the UI toast)
OFFER_TTL = 30 * 60
NOTE_TTL = 10 * 60


def _video_summary(v: Dict[str, Any]) -> Dict[str, Any]:
    try:
        path = videostore.video_file(v)
    except Exception:
        path = None
    return {
        "id": v["id"], "name": v["name"], "path": path, "poster_path": videostore.poster_file(v),
        "width": v.get("width"), "height": v.get("height"), "fps": v.get("fps"), "frames": v.get("frames"),
        "duration": v.get("duration"), "size": v.get("size"), "source": v.get("source"), "meta": dict(v.get("meta") or {}),
        "created": v.get("created"), "updated": v.get("updated"),
    }


def list_videos() -> List[Dict[str, Any]]:
    """[{id, name, path, poster_path|None, width, height, fps, frames, duration, size, source, meta, created, updated}]
    in library order (newest first unless the user reordered)."""
    try:
        return [_video_summary(v) for v in videostore.list_videos()]
    except Exception as e:
        print(f"[Reference Library] api.list_videos failed: {e}")
        return []


def get_video(vid: str) -> Optional[Dict[str, Any]]:
    """Same dict as list_videos() items, or None (unknown, invalid or in the undo trash)."""
    try:
        return _video_summary(videostore.get_video(str(vid or "")))
    except Exception:
        return None


def video_path(vid: str) -> Optional[str]:
    """Absolute path of the stored video file, or None. Treat it as read-only."""
    try:
        return videostore.video_file(str(vid or ""))
    except Exception:
        return None


def crop_policy() -> str:
    """What happens to crops: "auto" (saved), "ask" (the user gets a Save button), "off" (not saved)."""
    try:
        value = str(_policy_provider() or "auto")
    except Exception:
        value = "auto"
    return value if value in CROP_POLICIES else "auto"


def _clean_src(path) -> Optional[str]:
    if isinstance(path, dict):
        inner = path.get("video")
        path = path.get("path") or (inner.get("path") if isinstance(inner, dict) else None)
    if not isinstance(path, str) or not path.strip():
        return None
    text = path.strip()
    if "|" in text and not os.path.isfile(text):  # WanGP virtual media "path|start_frame=..." -> the real file
        text = text.split("|", 1)[0].strip()
    return os.path.abspath(text)


def _note(path: str, **info) -> None:
    now = time.time()
    with _lock:
        for key in [k for k, v in _notes.items() if now - v["time"] > NOTE_TTL]:
            _notes.pop(key, None)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        _notes[os.path.basename(path)] = {**info, "size": size, "time": now}


def take_note(path) -> Optional[Dict[str, Any]]:
    """(internal, used by the UI) Pop what add_video / add_image did with a file that has the same name and size as
    `path`. `path` may also be a Gradio gallery value (list): the first matching file wins."""
    if isinstance(path, (list, tuple)):
        for item in path:
            note = take_note(item[0] if isinstance(item, (list, tuple)) and item else item)
            if note:
                return note
        return None
    if isinstance(path, dict) and isinstance(path.get("image"), dict):
        path = path["image"]
    src = _clean_src(path)
    if not src:
        return None
    with _lock:
        note = _notes.get(os.path.basename(src))
        if not note or time.time() - note["time"] > NOTE_TTL:
            return None
        try:
            size = os.path.getsize(src)
        except OSError:
            size = -1
        if note["size"] >= 0 and size >= 0 and size != note["size"]:
            return None
        return _notes.pop(os.path.basename(src))


def take_recent_image_note(max_age: float = 20.0) -> Optional[Dict[str, Any]]:
    """(internal) Pop the newest image note younger than `max_age` s (for inputs whose value has no file name)."""
    now = time.time()
    with _lock:
        best = None
        for key, note in _notes.items():
            if note.get("what") == "image" and now - note["time"] <= max_age and (best is None or note["time"] > _notes[best]["time"]):
                best = key
        return _notes.pop(best) if best else None


def has_notes() -> bool:
    return bool(_notes)


def add_video(path, name: Optional[str] = None, source: str = "cropper", meta: Optional[dict] = None) -> Optional[str]:
    """Save a video file into the library (the file is copied into the plugin folder, so it survives WanGP's temp
    cleanup). Returns the video id, or None when it was not saved.

    - source="cropper" follows the user's setting (crop_policy()): "auto" saves, "off" returns None, "ask" returns None
      and offers a "Save to library" button in the page (shown when the cropped file is put in a video input).
      Any other source (e.g. "manual", your plugin name) always saves.
    - Duplicates are never stored twice: same file content (sha256), or the same meta["dedupe_key"], returns the
      existing id (also in "ask" mode).
    - name: display name (made unique: "X 2"...). Default: the file name.
    - meta: small JSON-able dict kept with the video (e.g. {"crop": [x, y, w, h], "source_file": "...", "dedupe_key": "..."}).
    """
    try:
        src = _clean_src(path)
        if not src or not os.path.isfile(src):
            print(f"[Reference Library] add_video: file not found: {path!r}")
            return None
        if not media.is_video_path(src):
            print(f"[Reference Library] add_video: not a video file: {src}")
            return None
        source = str(source or "manual")[:40]
        meta = videostore._clean_meta(meta)
        policy = crop_policy() if source == "cropper" else "auto"
        if policy == "off":
            return None
        digest = videostore.file_hash(src)
        existing = videostore.find_by_hash(digest) or videostore.find_by_key(meta.get("dedupe_key"))
        if existing:
            _note(src, kind="duplicate", id=existing["id"], name=existing["name"], source=source)
            return existing["id"]
        if policy == "ask":
            offer(src, name=name, source=source, meta=meta)
            return None
        entry, created = videostore.add_video(src, name=name, source=source, meta=meta, fallback=_fallback_name(),
                                              digest=digest)
        _note(src, kind="saved" if created else "duplicate", id=entry["id"], name=entry["name"], source=source)
        return entry["id"]
    except Exception as e:
        print(f"[Reference Library] add_video failed: {e}")
        return None


def offer(src: str, name: Optional[str] = None, source: str = "cropper", meta: Optional[dict] = None) -> str:
    """(internal) Register an "ask" offer for `src`; the page shows it with a Save button. Returns the offer token."""
    now = time.time()
    token = uuid.uuid4().hex
    with _lock:
        for key in [k for k, v in _offers.items() if now - v["time"] > OFFER_TTL]:
            _offers.pop(key, None)
        _offers[token] = {"path": src, "name": name, "source": source, "meta": meta or {}, "time": now, "what": "video"}
    _note(src, kind="offer", token=token, name=(name or videostore.name_from_path(src)), source=source)
    return token


def accept_offer(token: str):
    """(internal) Save a pending offer. Returns (entry, created) or raises storage.StorageError."""
    with _lock:
        item = _offers.get(str(token or ""))
        if item and item.get("what") == "image":
            raise storage.StorageError("offer expired")   # image offers are accepted with accept_image_offer()
        if not item or time.time() - item["time"] > OFFER_TTL:
            _offers.pop(str(token or ""), None)
            raise storage.StorageError("offer expired")
        if not os.path.isfile(item["path"]):
            _offers.pop(str(token), None)
            raise storage.StorageError("source video not found")
        entry, created = videostore.add_video(item["path"], name=item["name"], source=item["source"], meta=item["meta"],
                                              fallback=_fallback_name())
        _offers.pop(str(token), None)
        return entry, created


# ------------------------------------------------------------------ images (v3)
_image_policy_provider: Callable[[], str] = lambda: "auto"   # plugin.py installs the real one (settings.json)
_crops_name: Callable[[], str] = lambda: "Crops"              # translated name of the automatic crops collection


def image_crop_policy() -> str:
    """What happens to image crops: "auto" (saved), "ask" (Save button in the page), "off" (not saved)."""
    try:
        value = str(_image_policy_provider() or "auto")
    except Exception:
        value = "auto"
    return value if value in CROP_POLICIES else "auto"


def _clean_image_src(path) -> Optional[str]:
    if isinstance(path, dict):
        inner = path.get("image")
        path = path.get("path") or (inner.get("path") if isinstance(inner, dict) else None)
    elif isinstance(path, (list, tuple)) and path and not isinstance(path, str):
        path = path[0]   # Gradio gallery item (file, caption)
    return _clean_src(path)


def _image_result(res: Dict[str, Any]) -> Dict[str, Any]:
    col, img = res["collection"], res["image"]
    return {"collection_id": col["id"], "collection_name": col["name"], "file": img["file"], "name": img.get("name") or img["file"],
            "meta": dict(img.get("meta") or {}),
            "path": os.path.join(storage._collection_dir(col["id"]), img["file"]), "created": bool(res["created"])}


def add_image(path, name: Optional[str] = None, source: str = "cropper", meta: Optional[dict] = None,
              collection_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Save an image into a collection (the file is copied into the plugin folder). Never raises.

    Returns {collection_id, collection_name, file, path, created} or None when it was not saved.
    - Destination: `collection_id` when it is a live collection; otherwise the automatic crops collection
      ("Crops" / "Recortes", created on first use). The user's other collections are never changed implicitly.
    - source="cropper" follows the user's image-crop setting (image_crop_policy()): "auto" saves, "off" returns None,
      "ask" returns None and offers a "Save" button in the page (shown when the cropped image lands in an image input).
      Any other source always saves.
    - Duplicates are never stored twice in the same collection: same content (sha256) or same meta["dedupe_key"]
      returns the existing image with created=False (also in "ask" mode). Collections in the undo trash don't count.
    - name: display name of the image (default: the file name). meta: small JSON-able dict; stored with the image (1.4.0+);
      "dedupe_key" is also used for dedupe.
    """
    try:
        src = _clean_image_src(path)
        if not src or not os.path.isfile(src):
            print(f"[Reference Library] add_image: file not found: {path!r}")
            return None
        if not imagestore.is_image_path(src):
            print(f"[Reference Library] add_image: not an image file: {src}")
            return None
        source = str(source or "manual")[:40]
        meta = videostore._clean_meta(meta)
        policy = image_crop_policy() if source == "cropper" else "auto"
        if policy == "off":
            return None
        digest = storage._file_hash(src)
        key = str(meta.get("dedupe_key") or "")
        col, is_crops, _ = imagestore.resolve_target(collection_id, _crops_name(), create=False)
        if col:
            existing = imagestore.find_in(col, digest, key)
            if existing:
                res = {"collection": col, "image": existing, "created": False}
                _note(src, kind="duplicate", what="image", collection_id=col["id"], collection=col["name"],
                      name=existing.get("name"), source=source)
                return _image_result(res)
        if policy == "ask":
            image_offer(src, name=name, source=source, meta=meta, collection_id=collection_id)
            return None
        res = imagestore.add_image(src, name, source, meta, collection_id, crops_name=_crops_name(), digest=digest)
        _note(src, kind="saved" if res["created"] else "duplicate", what="image", collection_id=res["collection"]["id"],
              collection=res["collection"]["name"], name=res["image"].get("name"), source=source)
        return _image_result(res)
    except Exception as e:
        print(f"[Reference Library] add_image failed: {e}")
        return None


def image_offer(src: str, name: Optional[str] = None, source: str = "cropper", meta: Optional[dict] = None,
                collection_id: Optional[str] = None) -> str:
    """(internal) Register an "ask" offer for an image. Returns the offer token."""
    now = time.time()
    token = uuid.uuid4().hex
    with _lock:
        for key in [k for k, v in _offers.items() if now - v["time"] > OFFER_TTL]:
            _offers.pop(key, None)
        _offers[token] = {"path": src, "name": name, "source": source, "meta": meta or {}, "time": now,
                          "what": "image", "collection_id": collection_id}
    col, _, _ = imagestore.resolve_target(collection_id, _crops_name(), create=False)
    _note(src, kind="offer", what="image", token=token, name=(name or os.path.basename(src)), source=source,
          collection=(col or {}).get("name") or _crops_name())
    return token


def accept_image_offer(token: str) -> Dict[str, Any]:
    """(internal) Save a pending image offer. Returns the add_image result dict or raises storage.StorageError."""
    with _lock:
        item = _offers.get(str(token or ""))
        if not item or item.get("what") != "image" or time.time() - item["time"] > OFFER_TTL:
            _offers.pop(str(token or ""), None)
            raise storage.StorageError("offer expired")
        if not os.path.isfile(item["path"]):
            _offers.pop(str(token), None)
            raise storage.StorageError("source image not found")
        res = imagestore.add_image(item["path"], item["name"], item["source"], item["meta"], item.get("collection_id"),
                                   crops_name=_crops_name())
        _offers.pop(str(token), None)
        return _image_result(res)


def offer_kind(token: str) -> Optional[str]:
    item = _offers.get(str(token or ""))
    return item.get("what", "video") if item else None


# ------------------------------------------------------------------ image browser (v4, read-only)
def list_images(tag: Optional[str] = None, collection_id: Optional[str] = None, unassigned: bool = False) -> List[Dict[str, Any]]:
    """Every image of every live collection plus the unassigned pool, once per content (sha256):
    [{hash, name, names, path, collections: [{id, name}], tags, unassigned}]. Optional filters: a tag
    (case/accent-insensitive), a collection id, or unassigned=True (pool images in no collection). `path` is a stored
    file: treat it as read-only. Never raises ([] on error)."""
    try:
        out = []
        want = imagelib._fold(imagelib.clean_tag(tag)) if tag else ""
        for img in imagelib.list_images():
            if want and want not in {imagelib._fold(t) for t in img["tags"]}:
                continue
            if collection_id and not any(c["id"] == collection_id for c in img["collections"]):
                continue
            if unassigned and (img["collections"] or not img.get("in_pool")):
                continue
            out.append({"hash": img["hash"], "name": img["name"], "names": list(img["names"]), "path": img["path"],
                        "collections": [dict(c) for c in img["collections"]], "tags": list(img["tags"]),
                        "unassigned": bool(img.get("in_pool")) and not img["collections"],
                        "folders": [dict(f) for f in img.get("folders") or []],
                        "added": float(img.get("added") or 0)})
        return out
    except Exception as e:
        print(f"[Reference Library] api.list_images failed: {e}")
        return []


def list_tags() -> List[Dict[str, Any]]:
    """[{tag, count}] for the images in live collections, most used first. Never raises."""
    try:
        return imagelib.tag_counts()
    except Exception as e:
        print(f"[Reference Library] api.list_tags failed: {e}")
        return []


def image_tags(digest: str) -> List[str]:
    """Tags of one image by its sha256 (also for images no longer in any collection). Never raises."""
    try:
        return imagelib.image_tags(digest)
    except Exception:
        return []


def register() -> None:
    sys.modules[MODULE_NAME] = sys.modules[__name__]
