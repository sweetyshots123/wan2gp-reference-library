"""Persistent storage for Reference Library collections.

Layout (inside the plugin folder, never shipped in the zip / gitignored):
  collections/
    collections.json          # index of all collections
    <collection_id>/
      a1b2c3d4e5f6....png     # copied image files (sha256 hex + original ext)
      ...

collections.json:
  {
    "version": 1,
    "collections": [
      {
        "id": "uuidhex",
        "name": "My characters",
        "images": [
          {"file": "a1b2....png", "hash": "a1b2....", "name": "hero.png"}
        ],
        "cover": "a1b2....png" | null,   # file name inside the folder, or null = first image
        "created": 1696...,
        "updated": 1696...
      },
      ...
    ]
  }
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

# data root: $REFLIB_DATA_DIR, else the folder that contains reflib_core/ (the WanGP plugin folder); see reflib_core.configure()
PLUGIN_DIR = os.environ.get("REFLIB_DATA_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTIONS_DIR = os.path.join(PLUGIN_DIR, "collections")
INDEX_PATH = os.path.join(COLLECTIONS_DIR, "collections.json")
INDEX_VERSION = 1

_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_lock = threading.RLock()


# 1.4.0: called with [(path, name, hash)] right before image files leave the collections (remove, update, delete), so the
# image browser can keep images that are no longer in any collection in its unassigned pool. Must never raise.
_orphan_hook = None


def _orphans(items, exclude_cid=None) -> None:
    if _orphan_hook is None or not items:
        return
    try:
        _orphan_hook(items, exclude_cid)
    except Exception as e:
        print(f"[Reference Library] keeping removed images in the pool failed: {e}")


class StorageError(Exception):
    """User-facing storage error (safe to show)."""


def _ensure_dirs() -> None:
    os.makedirs(COLLECTIONS_DIR, exist_ok=True)


def _safe_name(name: str, fallback: str = "Collection") -> str:
    text = _BAD_CHARS.sub(" ", str(name or "")).strip(" ._")
    text = re.sub(r"\s+", " ", text)
    return (text or fallback)[:120]


def _check_id(collection_id: str) -> str:
    cid = str(collection_id or "").strip().lower()
    if not _ID_RE.match(cid):
        raise StorageError("invalid collection id")
    return cid


def _collection_dir(collection_id: str) -> str:
    return os.path.join(COLLECTIONS_DIR, _check_id(collection_id))


def _inside(path: str, root: str) -> bool:
    try:
        path, root = os.path.realpath(path), os.path.realpath(root)
        return os.path.commonpath([path, root]) == root
    except Exception:
        return False


_MEDIA_SAMPLED = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus")
SAMPLED_HASH_MIN = 48 * 1024 * 1024   # 1.6.0: big video/audio files get a sampled content hash (12k-file folders stay fast)


def _sampled_hash(path: str, size: int) -> str:
    """sha256 over the size + 4 MB at the start, middle and end. Same 64-hex shape as a full hash; still content-based
    (a copy of the file gets the same hash), but a 4 GB video costs 12 MB of reading instead of 4 GB."""
    h = hashlib.sha256(b"reflib-sampled-v1:" + str(size).encode())
    blk = 4 * 1024 * 1024
    with open(path, "rb") as reader:
        for off in (0, max(0, size // 2 - blk // 2), max(0, size - blk)):
            reader.seek(off)
            h.update(reader.read(blk))
    return h.hexdigest()


def _file_hash(path: str) -> str:
    try:
        if os.path.splitext(path)[1].lower() in _MEDIA_SAMPLED:
            size = os.path.getsize(path)
            if size >= SAMPLED_HASH_MIN:
                return _sampled_hash(path, size)
    except OSError:
        pass
    h = hashlib.sha256()
    with open(path, "rb") as reader:
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_json(path: str, data: Any) -> None:
    _ensure_dirs()
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".collections_", suffix=".tmp", dir=directory)
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


def _empty_index() -> Dict[str, Any]:
    return {"version": INDEX_VERSION, "collections": []}


def load_index(path: Optional[str] = None) -> Dict[str, Any]:
    path = path or INDEX_PATH
    try:
        with open(path, "r", encoding="utf-8") as reader:
            data = json.load(reader)
    except FileNotFoundError:
        return _empty_index()
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid collections.json: {e}")
        return _empty_index()
    if not isinstance(data, dict):
        return _empty_index()
    cols = data.get("collections")
    if not isinstance(cols, list):
        cols = []
    cleaned = []
    for entry in cols:
        if not isinstance(entry, dict):
            continue
        cid = str(entry.get("id") or "")
        if not _ID_RE.match(cid):
            continue
        images = entry.get("images") if isinstance(entry.get("images"), list) else []
        cleaned_images = []
        for img in images:
            if not isinstance(img, dict):
                continue
            fname = os.path.basename(str(img.get("file") or ""))
            if not fname or fname in (".", "..") or "/" in fname or "\\" in fname:
                continue
            item = {
                "file": fname,
                "hash": str(img.get("hash") or "")[:64],
                "name": str(img.get("name") or fname)[:120],
            }
            # Optional (1.3.0, images added through the API, e.g. Cropper): origin and dedupe key.
            if img.get("source"):
                item["source"] = str(img["source"])[:40]
            if img.get("key"):
                item["key"] = str(img["key"])[:200]
            try:
                if img.get("added_at"):
                    item["added_at"] = float(img["added_at"])
            except (TypeError, ValueError):
                pass
            if isinstance(img.get("meta"), dict) and img["meta"]:
                item["meta"] = img["meta"]   # 1.4.0: full API meta (size-checked when it was added)
            cleaned_images.append(item)
        cover = entry.get("cover")
        cover = os.path.basename(str(cover)) if cover else None
        if cover and cover not in {i["file"] for i in cleaned_images}:
            cover = None
        cleaned.append({
            "id": cid,
            "name": _safe_name(entry.get("name"), "Collection"),
            "images": cleaned_images,
            "cover": cover,
            "created": float(entry.get("created") or 0) or time.time(),
            "updated": float(entry.get("updated") or 0) or time.time(),
        })
    return {"version": INDEX_VERSION, "collections": cleaned}


def save_index(index: Dict[str, Any], path: Optional[str] = None) -> None:
    path = path or INDEX_PATH
    payload = {
        "version": INDEX_VERSION,
        "collections": list(index.get("collections") or []),
    }
    _atomic_write_json(path, payload)


def list_collections() -> List[Dict[str, Any]]:
    with _lock:
        cols = load_index()["collections"]
        return sorted(cols, key=lambda c: (c["name"].lower(), c["created"]))


def get_collection(collection_id: str) -> Dict[str, Any]:
    with _lock:
        cid = _check_id(collection_id)
        for col in load_index()["collections"]:
            if col["id"] == cid:
                return dict(col)
        raise StorageError("collection not found")


def image_path(collection_id: str, filename: str) -> str:
    cid = _check_id(collection_id)
    fname = os.path.basename(str(filename or ""))
    if not fname or fname in (".", ".."):
        raise StorageError("invalid image file")
    path = os.path.join(_collection_dir(cid), fname)
    if not _inside(path, COLLECTIONS_DIR) or not os.path.isfile(path):
        raise StorageError("image file not found")
    return os.path.realpath(path)


def cover_path(collection: Dict[str, Any]) -> Optional[str]:
    images = collection.get("images") or []
    if not images:
        return None
    cover = collection.get("cover") or images[0]["file"]
    try:
        return image_path(collection["id"], cover)
    except StorageError:
        return None


def _ext_of(path: str, name: str = "") -> str:
    for candidate in (path, name):
        ext = os.path.splitext(candidate)[1].lower()
        if ext and len(ext) <= 8 and re.match(r"^\.[a-z0-9]+$", ext):
            return ext
    return ".png"


def _copy_image_into(collection_id: str, src: str, display_name: str, known_hashes: Optional[set] = None) -> Dict[str, str]:
    if not isinstance(src, str) or not os.path.isfile(src):
        raise StorageError("source image not found")
    digest = _file_hash(src)
    if known_hashes is not None and digest in known_hashes:
        return {"skipped": True, "hash": digest}  # type: ignore[return-value]
    ext = _ext_of(src, display_name)
    fname = digest + ext
    dest_dir = _collection_dir(collection_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, fname)
    if not os.path.isfile(dest):
        shutil.copy2(src, dest)
        # verify we landed inside collections/
        if not _inside(dest, COLLECTIONS_DIR):
            try:
                os.unlink(dest)
            except OSError:
                pass
            raise StorageError("path safety check failed")
    return {
        "file": fname,
        "hash": digest,
        "name": os.path.basename(display_name or fname)[:120] or fname,
        "added_at": time.time(),   # 1.4.2: "Recent" view (older entries fall back to the file mtime)
    }


def name_taken(name: str, exclude_id: Optional[str] = None) -> bool:
    key = _safe_name(name, "").casefold()
    return any(c["name"].casefold() == key and c["id"] != exclude_id for c in load_index()["collections"])


def unique_name(name: str) -> str:
    """`name`, or `name 2`, `name 3`... when a collection already uses it (case-insensitive)."""
    with _lock:
        base = _safe_name(name, "") or "Collection"
        if not name_taken(base):
            return base
        n = 2
        while name_taken(f"{base} {n}"):
            n += 1
        return f"{base} {n}"


_COPY_TAIL = re.compile(r"\s*\((?:copy|copia)(?:\s+\d+)?\)\s*$", re.IGNORECASE)


def copy_name(name: str, suffix: str = "copy") -> str:
    """Name for a duplicate: `X (copy)`, then `X (copy 2)`, `X (copy 3)`... A copy of a copy stays `X (copy N)`."""
    with _lock:
        base = _COPY_TAIL.sub("", str(name or "")).strip() or str(name or "").strip() or "Collection"
        candidate = f"{base} ({suffix})"
        n = 2
        while name_taken(candidate):
            candidate = f"{base} ({suffix} {n})"
            n += 1
        return candidate


def create_collection(name: str, image_sources: Optional[List[Tuple[str, str]]] = None,
                      fallback: str = "Collection") -> Dict[str, Any]:
    """Create a collection. image_sources = list of (path, display_name). `fallback` = (translated) name used when
    `name` is empty after cleaning."""
    with _lock:
        _ensure_dirs()
        cid = uuid.uuid4().hex
        now = time.time()
        images: List[Dict[str, str]] = []
        hashes: set = set()
        for src, display in image_sources or []:
            try:
                entry = _copy_image_into(cid, src, display, hashes)
            except StorageError:
                continue
            if entry.get("skipped"):
                continue
            images.append(entry)
            hashes.add(entry["hash"])
        col = {
            "id": cid,
            "name": _safe_name(name, fallback),
            "images": images,
            "cover": images[0]["file"] if images else None,
            "created": now,
            "updated": now,
        }
        index = load_index()
        index["collections"].append(col)
        save_index(index)
        return dict(col)


def rename_collection(collection_id: str, name: str, fallback: str = "Collection") -> Dict[str, Any]:
    with _lock:
        cid = _check_id(collection_id)
        index = load_index()
        for col in index["collections"]:
            if col["id"] == cid:
                col["name"] = _safe_name(name, fallback)
                col["updated"] = time.time()
                save_index(index)
                return dict(col)
        raise StorageError("collection not found")


def duplicate_collection(collection_id: str, new_name: Optional[str] = None, copy_suffix: str = "copy") -> Dict[str, Any]:
    """Copy a collection (new id). Without `new_name` it is named `X (<copy_suffix>)`, numbered if that name exists;
    the caller passes the translated suffix (e.g. "copia")."""
    with _lock:
        src = get_collection(collection_id)
        sources = []
        for img in src["images"]:
            try:
                sources.append((image_path(src["id"], img["file"]), img["name"]))
            except StorageError:
                continue
        name = new_name or copy_name(src["name"], copy_suffix)
        return create_collection(name, sources, fallback=src["name"])


def delete_collection(collection_id: str) -> None:
    with _lock:
        cid = _check_id(collection_id)
        index = load_index()
        before = len(index["collections"])
        index["collections"] = [c for c in index["collections"] if c["id"] != cid]
        if len(index["collections"]) == before:
            raise StorageError("collection not found")
        save_index(index)
        folder = _collection_dir(cid)
        if os.path.isdir(folder) and _inside(folder, COLLECTIONS_DIR):
            shutil.rmtree(folder, ignore_errors=True)


def add_images(collection_id: str, image_sources: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Append images (deduped by hash within the collection). Returns updated collection + added count."""
    with _lock:
        cid = _check_id(collection_id)
        index = load_index()
        col = None
        for entry in index["collections"]:
            if entry["id"] == cid:
                col = entry
                break
        if col is None:
            raise StorageError("collection not found")
        hashes = {img["hash"] for img in col["images"] if img.get("hash")}
        added = 0
        for src, display in image_sources:
            try:
                entry = _copy_image_into(cid, src, display, hashes)
            except StorageError:
                continue
            if entry.get("skipped"):
                continue
            col["images"].append(entry)
            hashes.add(entry["hash"])
            added += 1
        if not col.get("cover") and col["images"]:
            col["cover"] = col["images"][0]["file"]
        col["updated"] = time.time()
        save_index(index)
        out = dict(col)
        out["_added"] = added
        return out


def remove_image(collection_id: str, index: int) -> Dict[str, Any]:
    with _lock:
        cid = _check_id(collection_id)
        data = load_index()
        col = None
        for entry in data["collections"]:
            if entry["id"] == cid:
                col = entry
                break
        if col is None:
            raise StorageError("collection not found")
        if not isinstance(index, int) or not (0 <= index < len(col["images"])):
            raise StorageError("invalid image index")
        removed = col["images"].pop(index)
        if col.get("cover") == removed["file"]:
            col["cover"] = col["images"][0]["file"] if col["images"] else None
        # delete file if no longer referenced
        still = {img["file"] for img in col["images"]}
        if removed["file"] not in still:
            path = os.path.join(_collection_dir(cid), removed["file"])
            save_index(data)
            _orphans([(path, removed.get("name") or removed["file"], removed.get("hash") or "")])
            if _inside(path, COLLECTIONS_DIR) and os.path.isfile(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        col["updated"] = time.time()
        save_index(data)
        return dict(col)


def reorder_images(collection_id: str, order: List[int]) -> Dict[str, Any]:
    """Reorder by a permutation of current indices (list of old indices in new order)."""
    with _lock:
        cid = _check_id(collection_id)
        data = load_index()
        col = None
        for entry in data["collections"]:
            if entry["id"] == cid:
                col = entry
                break
        if col is None:
            raise StorageError("collection not found")
        n = len(col["images"])
        if not isinstance(order, list) or len(order) != n or sorted(order) != list(range(n)):
            raise StorageError("invalid image order")
        col["images"] = [col["images"][i] for i in order]
        col["updated"] = time.time()
        save_index(data)
        return dict(col)


def move_image(collection_id: str, index: int, delta: int) -> Dict[str, Any]:
    with _lock:
        cid = _check_id(collection_id)
        data = load_index()
        col = None
        for entry in data["collections"]:
            if entry["id"] == cid:
                col = entry
                break
        if col is None:
            raise StorageError("collection not found")
        n = len(col["images"])
        if not isinstance(index, int) or not (0 <= index < n):
            raise StorageError("invalid image index")
        j = index + int(delta)
        if j < 0 or j >= n:
            return dict(col)
        col["images"][index], col["images"][j] = col["images"][j], col["images"][index]
        col["updated"] = time.time()
        save_index(data)
        return dict(col)


def set_cover(collection_id: str, index: int) -> Dict[str, Any]:
    with _lock:
        cid = _check_id(collection_id)
        data = load_index()
        col = None
        for entry in data["collections"]:
            if entry["id"] == cid:
                col = entry
                break
        if col is None:
            raise StorageError("collection not found")
        if not isinstance(index, int) or not (0 <= index < len(col["images"])):
            raise StorageError("invalid image index")
        col["cover"] = col["images"][index]["file"]
        col["updated"] = time.time()
        save_index(data)
        return dict(col)


def replace_images(collection_id: str, image_sources: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Replace all images of a collection with the given sources (used by 'Update from current refs')."""
    with _lock:
        cid = _check_id(collection_id)
        data = load_index()
        col = None
        for entry in data["collections"]:
            if entry["id"] == cid:
                col = entry
                break
        if col is None:
            raise StorageError("collection not found")
        # clear folder contents carefully
        folder = _collection_dir(cid)
        _orphans([(os.path.join(folder, i["file"]), i.get("name") or i["file"], i.get("hash") or "") for i in col["images"]], cid)
        if os.path.isdir(folder) and _inside(folder, COLLECTIONS_DIR):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
        col["images"] = []
        hashes: set = set()
        for src, display in image_sources:
            try:
                entry = _copy_image_into(cid, src, display, hashes)
            except StorageError:
                continue
            if entry.get("skipped"):
                continue
            col["images"].append(entry)
            hashes.add(entry["hash"])
        col["cover"] = col["images"][0]["file"] if col["images"] else None
        col["updated"] = time.time()
        save_index(data)
        return dict(col)


def absolute_image_paths(collection_id: str) -> List[str]:
    col = get_collection(collection_id)
    out = []
    for img in col["images"]:
        try:
            out.append(image_path(col["id"], img["file"]))
        except StorageError:
            continue
    return out


def export_collection_zip(collection_id: str, dest_zip: str) -> str:
    col = get_collection(collection_id)
    dest_zip = os.path.abspath(dest_zip)
    os.makedirs(os.path.dirname(dest_zip) or ".", exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "name": col["name"],
            "images": [{"file": i["file"], "name": i["name"], "hash": i["hash"]} for i in col["images"]],
            "cover": col.get("cover"),
            "exported_by": "wan2gp-reference-library",
        }
        zf.writestr("collection.json", json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        for img in col["images"]:
            try:
                path = image_path(col["id"], img["file"])
            except StorageError:
                continue
            zf.write(path, arcname="images/" + img["file"])
    return dest_zip


def import_collection_zip(zip_path: str, name: Optional[str] = None, default_name: str = "Imported collection") -> Dict[str, Any]:
    if not isinstance(zip_path, str) or not os.path.isfile(zip_path):
        raise StorageError("zip not found")
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        meta = {}
        if "collection.json" in names:
            try:
                meta = json.loads(zf.read("collection.json").decode("utf-8"))
            except Exception:
                meta = {}
        # stage images to a temp dir then create_collection
        with tempfile.TemporaryDirectory(prefix="reflib_import_") as tmp:
            sources: List[Tuple[str, str]] = []
            image_names = [n for n in names if n.startswith("images/") and not n.endswith("/")]
            # preserve order from meta if available
            order = []
            if isinstance(meta.get("images"), list):
                order = [os.path.basename(i.get("file") or "") for i in meta["images"] if isinstance(i, dict)]
            def sort_key(n: str):
                base = os.path.basename(n)
                return (order.index(base) if base in order else 10**6, base)
            for member in sorted(image_names, key=sort_key):
                base = os.path.basename(member)
                if not base or ".." in member:
                    continue
                dest = os.path.join(tmp, base)
                with zf.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                display = base
                for info in (meta.get("images") or []):
                    if isinstance(info, dict) and os.path.basename(str(info.get("file") or "")) == base:
                        display = str(info.get("name") or base)
                        break
                sources.append((dest, display))
            col_name = name or (str(meta.get("name")) if meta.get("name") else "") or default_name
            return create_collection(col_name, sources, fallback=default_name)



def soft_delete(collection_id: str) -> Dict[str, Any]:
    """Remove from the index and move the folder to collections/.trash/<id>/ for a short undo window."""
    with _lock:
        cid = _check_id(collection_id)
        index = load_index()
        col = None
        kept = []
        for entry in index["collections"]:
            if entry["id"] == cid:
                col = entry
            else:
                kept.append(entry)
        if col is None:
            raise StorageError("collection not found")
        index["collections"] = kept
        save_index(index)
        src = _collection_dir(cid)
        _orphans([(os.path.join(src, i["file"]), i.get("name") or i["file"], i.get("hash") or "") for i in col["images"]])
        trash_root = os.path.join(COLLECTIONS_DIR, ".trash")
        os.makedirs(trash_root, exist_ok=True)
        dest = os.path.join(trash_root, cid)
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        if os.path.isdir(src) and _inside(src, COLLECTIONS_DIR):
            shutil.move(src, dest)
        # write meta next to trash folder
        meta_path = os.path.join(trash_root, cid + ".json")
        _atomic_write_json(meta_path, col)
        return dict(col)


def restore_soft_deleted(collection_id: str) -> Dict[str, Any]:
    with _lock:
        cid = _check_id(collection_id)
        trash_root = os.path.join(COLLECTIONS_DIR, ".trash")
        meta_path = os.path.join(trash_root, cid + ".json")
        folder = os.path.join(trash_root, cid)
        if not os.path.isfile(meta_path):
            raise StorageError("undo expired")
        with open(meta_path, "r", encoding="utf-8") as reader:
            col = json.load(reader)
        if not isinstance(col, dict) or col.get("id") != cid:
            raise StorageError("undo expired")
        index = load_index()
        if any(c["id"] == cid for c in index["collections"]):
            raise StorageError("collection already exists")
        dest = _collection_dir(cid)
        if os.path.isdir(folder):
            if os.path.isdir(dest):
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(folder, dest)
        index["collections"].append(col)
        save_index(index)
        try:
            os.unlink(meta_path)
        except OSError:
            pass
        return dict(col)


def purge_trash(max_age_s: float = 15 * 60) -> None:
    trash_root = os.path.join(COLLECTIONS_DIR, ".trash")
    if not os.path.isdir(trash_root):
        return
    now = time.time()
    for name in list(os.listdir(trash_root)):
        path = os.path.join(trash_root, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age < max_age_s:
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.unlink(path)
        except OSError:
            pass

def public_summary(col: Dict[str, Any]) -> Dict[str, Any]:
    """Compact dict safe for the UI / JS (no absolute paths)."""
    return {
        "id": col["id"],
        "name": col["name"],
        "count": len(col.get("images") or []),
        "cover": col.get("cover"),
        "created": col.get("created"),
        "updated": col.get("updated"),
    }
