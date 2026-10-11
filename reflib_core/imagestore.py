"""Images handed over by other plugins (Cropper 1.2+): where they go and how duplicates are avoided.

Destination: the collection given by the caller (collection_id), else the automatic crops collection
("Crops" / "Recortes", created on first use; its id is remembered in collections/.crops.json so renaming it is fine).
The user's other collections are never changed implicitly.

Duplicates: an image is not added again to a collection that already holds the same content (sha256) or the same
meta["dedupe_key"]. Collections in the undo trash don't count. When the crops collection was deleted and a new one was
created meanwhile, undoing the delete merges the new one back into the restored collection (merge_after_restore).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import storage
except ImportError:  # unit tests
    import storage  # type: ignore

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def is_image_path(path) -> bool:
    return isinstance(path, str) and os.path.splitext(path)[1].lower() in IMAGE_EXTS


def _crops_file() -> str:
    return os.path.join(storage.COLLECTIONS_DIR, ".crops.json")


def _read_crops() -> Dict[str, Any]:
    try:
        with open(_crops_file(), "r", encoding="utf-8") as reader:
            data = json.load(reader)
        if isinstance(data, dict):
            ids = [str(x) for x in data.get("replaced") or [] if isinstance(x, str)]
            return {"id": str(data.get("id") or ""), "replaced": ids[-20:]}
    except Exception:
        pass
    return {"id": "", "replaced": []}


def _write_crops(data: Dict[str, Any]) -> None:
    os.makedirs(storage.COLLECTIONS_DIR, exist_ok=True)
    storage._atomic_write_json(_crops_file(), {"id": data.get("id") or "", "replaced": list(data.get("replaced") or [])[-20:]})


def _live(cid: str) -> Optional[Dict[str, Any]]:
    if not cid:
        return None
    try:
        return storage.get_collection(cid)
    except Exception:
        return None


def crops_collection_id() -> str:
    """Id of the automatic crops collection if it exists (live), else ""."""
    with storage._lock:
        cid = _read_crops()["id"]
        return cid if _live(cid) else ""


def _crops_target(name: str) -> Tuple[Dict[str, Any], bool]:
    """(collection, created). Creates the crops collection when missing or deleted (remembering the old id)."""
    data = _read_crops()
    col = _live(data["id"])
    if col:
        return col, False
    if data["id"]:
        data["replaced"] = [x for x in data["replaced"] if x != data["id"]] + [data["id"]]
    col = storage.create_collection(storage.unique_name(name or "Crops"), [], fallback=name or "Crops")
    data["id"] = col["id"]
    _write_crops(data)
    return col, True


def find_in(col: Dict[str, Any], digest: str, key: str = "") -> Optional[Dict[str, Any]]:
    for img in col.get("images") or []:
        if digest and img.get("hash") == digest:
            return img
        if key and img.get("key") == key:
            return img
    return None


def resolve_target(collection_id: Optional[str], crops_name: str, create: bool = True) -> Tuple[Optional[Dict[str, Any]], bool, bool]:
    """(collection or None, is_crops, created). An unknown / trashed collection_id falls back to the crops collection."""
    col = _live(str(collection_id or "")) if collection_id else None
    if col:
        return col, col["id"] == _read_crops()["id"], False
    if not create:
        cid = _read_crops()["id"]
        col = _live(cid)
        return col, True, False
    col, created = _crops_target(crops_name)
    return col, True, created


def add_image(src: str, name: Optional[str], source: str, meta: Optional[dict], collection_id: Optional[str],
              crops_name: str = "Crops", digest: Optional[str] = None) -> Dict[str, Any]:
    """Copy `src` into the target collection. Returns {collection, image, created, is_crops, new_collection}.
    created=False when it was already there (same hash or same meta.dedupe_key). Raises storage.StorageError."""
    if not isinstance(src, str) or not os.path.isfile(src):
        raise storage.StorageError("source image not found")
    meta = meta if isinstance(meta, dict) else {}
    key = str(meta.get("dedupe_key") or "")[:200]
    digest = digest or storage._file_hash(src)
    with storage._lock:
        col, is_crops, new_col = resolve_target(collection_id, crops_name)
        existing = find_in(col, digest, key)
        if existing:
            return {"collection": col, "image": dict(existing), "created": False, "is_crops": is_crops, "new_collection": new_col}
        display = (name or "").strip() or os.path.basename(src)
        entry = storage._copy_image_into(col["id"], src, display)
        entry["source"] = str(source or "manual")[:40]
        if key:
            entry["key"] = key
        if meta:
            entry["meta"] = dict(meta)   # full meta (crop, target, source_file, dedupe_key, …) — 1.4.0
        index = storage.load_index()
        for c in index["collections"]:
            if c["id"] == col["id"]:
                c["images"].append(entry)
                if not c.get("cover"):
                    c["cover"] = entry["file"]
                c["updated"] = time.time()
                col = c
                break
        storage.save_index(index)
        return {"collection": dict(col), "image": dict(entry), "created": True, "is_crops": is_crops, "new_collection": new_col}


def merge_after_restore(restored_id: str) -> Optional[Dict[str, Any]]:
    """Called after a collection is restored from the trash. If it was the crops collection and another crops collection
    was created while it was deleted, move that one's images back in (skipping duplicates), delete it and make the
    restored one the crops collection again. Returns {merged_name, added, skipped} or None."""
    with storage._lock:
        data = _read_crops()
        if restored_id not in data["replaced"]:
            return None
        current = _live(data["id"])
        data["replaced"] = [x for x in data["replaced"] if x != restored_id]
        if not current or current["id"] == restored_id:
            data["id"] = restored_id
            _write_crops(data)
            return None
        index = storage.load_index()
        target = next((c for c in index["collections"] if c["id"] == restored_id), None)
        newer = next((c for c in index["collections"] if c["id"] == current["id"]), None)
        if target is None or newer is None:
            return None
        added = skipped = 0
        for img in newer["images"]:
            if find_in(target, img.get("hash") or "", img.get("key") or ""):
                skipped += 1
                continue
            src = os.path.join(storage._collection_dir(newer["id"]), img["file"])
            try:
                copied = storage._copy_image_into(restored_id, src, img.get("name") or img["file"])
            except storage.StorageError:
                continue
            for k in ("source", "key", "meta"):
                if img.get(k):
                    copied[k] = img[k]
            target["images"].append(copied)
            added += 1
        if not target.get("cover") and target["images"]:
            target["cover"] = target["images"][0]["file"]
        target["updated"] = time.time()
        storage.save_index(index)
        storage.delete_collection(newer["id"])
        data["id"] = restored_id
        _write_crops(data)
        return {"merged_name": newer["name"], "merged_id": newer["id"], "added": added, "skipped": skipped,
                "name": target["name"]}
