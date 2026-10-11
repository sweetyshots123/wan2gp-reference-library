"""Image browser (1.4.0): every image of every collection, deduplicated by content hash, with tags.

Tags belong to the image content (sha256), so they apply in every collection that uses it. They live in
collections/tags.json ({"version": 1, "tags": {"<sha256>": ["tag", ...]}}); nothing else is migrated or rewritten.
Thumbnails are cached in collections/.thumbs/<sha256>.jpg (safe to delete).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

try:
    from . import storage
except ImportError:  # unit tests
    import storage  # type: ignore

TAG_MAX = 40
TAGS_PER_IMAGE = 30
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _tags_path() -> str:
    return os.path.join(storage.COLLECTIONS_DIR, "tags.json")


def _thumbs_dir() -> str:
    return os.path.join(storage.COLLECTIONS_DIR, ".thumbs")


def clean_tag(tag) -> str:
    text = re.sub(r"\s+", " ", str(tag or "")).strip().strip(",;").strip()
    text = text.replace(",", " ").replace(";", " ")
    text = "".join(ch for ch in text if ch.isprintable())
    return re.sub(r"\s+", " ", text)[:TAG_MAX].strip()


def _fold(tag: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", tag.casefold()) if not unicodedata.combining(c))


def load_tags() -> Dict[str, List[str]]:
    try:
        with open(_tags_path(), "r", encoding="utf-8") as reader:
            data = json.load(reader)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid tags.json: {e}")
        return {}
    raw = data.get("tags") if isinstance(data, dict) else None
    out: Dict[str, List[str]] = {}
    if isinstance(raw, dict):
        for h, tags in raw.items():
            if not _HASH_RE.match(str(h)) or not isinstance(tags, list):
                continue
            seen, clean = set(), []
            for tag in tags:
                c = clean_tag(tag)
                if c and _fold(c) not in seen:
                    seen.add(_fold(c)); clean.append(c)
            if clean:
                out[str(h)] = clean[:TAGS_PER_IMAGE]
    return out


def save_tags(tags: Dict[str, List[str]]) -> None:
    os.makedirs(storage.COLLECTIONS_DIR, exist_ok=True)
    storage._atomic_write_json(_tags_path(), {"version": 1, "tags": {h: t for h, t in sorted(tags.items()) if t}})


def list_images() -> List[Dict[str, Any]]:
    """Every image in live collections, one entry per content hash (first appearance order):
    {hash, name, names, file, path, collections: [{id, name}], tags}."""
    with storage._lock:
        tags = load_tags()
        by_hash: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        def stamp(entry, when, path):
            if not when:
                try:
                    when = os.path.getmtime(path)
                except OSError:
                    when = 0.0
            if when > entry.get("added", 0.0):
                entry["added"] = float(when)
        for col in storage.list_collections():
            for img in col.get("images") or []:
                h = img.get("hash") or ""
                path = os.path.join(storage._collection_dir(col["id"]), img["file"])
                if not h:
                    continue
                entry = by_hash.get(h)
                if entry is None:
                    entry = by_hash[h] = {"hash": h, "name": img.get("name") or img["file"], "names": [], "file": img["file"],
                                          "path": path, "collections": [], "tags": list(tags.get(h, []))}
                    order.append(h)
                elif not os.path.isfile(entry["path"]) and os.path.isfile(path):
                    entry["path"] = path
                if (img.get("name") or img["file"]) not in entry["names"]:
                    entry["names"].append(img.get("name") or img["file"])
                if not any(c["id"] == col["id"] for c in entry["collections"]):
                    entry["collections"].append({"id": col["id"], "name": col["name"]})
                stamp(entry, img.get("added_at"), path)
        for it in load_pool():
            h = it["hash"]
            entry = by_hash.get(h)
            if entry is None:
                entry = by_hash[h] = {"hash": h, "name": it["name"], "names": [it["name"]], "file": it["file"],
                                      "path": pool_path(it), "collections": [], "tags": list(tags.get(h, []))}
                order.append(h)
            stamp(entry, it.get("added"), pool_path(it))
            entry["in_pool"] = True
        fdata = load_folders()
        fpaths = {f["id"]: f["path"] for f in fdata["folders"]}
        for p, v in fdata["files"].items():
            h = v["hash"]
            entry = by_hash.get(h)
            if entry is None:
                name = os.path.basename(p)
                entry = by_hash[h] = {"hash": h, "name": name, "names": [name], "file": name, "path": p,
                                      "collections": [], "tags": list(tags.get(h, []))}
                order.append(h)
            elif not os.path.isfile(entry["path"]) and os.path.isfile(p):
                entry["path"] = p
            entry.setdefault("folders", [])
            if not any(x["id"] == v["folder"] for x in entry["folders"]):
                entry["folders"].append({"id": v["folder"], "path": fpaths.get(v["folder"], "")})
            entry.setdefault("files", []).append(p)
            stamp(entry, max(v["mtime"], v.get("first") or 0.0), p)
            entry.setdefault("locs", []).append([v["folder"], _rel_dir(fpaths.get(v["folder"], ""), p)])
        for h in order:
            by_hash[h].setdefault("in_pool", False)
            by_hash[h].setdefault("folders", [])
            by_hash[h].setdefault("files", [])
            by_hash[h].setdefault("locs", [])
            by_hash[h].setdefault("added", 0.0)
        return [by_hash[h] for h in order]


def tag_counts(images: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """[{tag, count}] over images in live collections, most used first, then alphabetical."""
    images = list_images() if images is None else images
    counts: Dict[str, Dict[str, Any]] = {}
    for img in images:
        for tag in img["tags"]:
            item = counts.setdefault(_fold(tag), {"tag": tag, "count": 0})
            item["count"] += 1
    return sorted(counts.values(), key=lambda x: (-x["count"], _fold(x["tag"])))


def image_tags(digest: str) -> List[str]:
    return list(load_tags().get(str(digest or ""), []))


def set_tags(hashes: Iterable[str], add: Iterable[str] = (), remove: Iterable[str] = ()) -> Dict[str, Any]:
    """Add / remove tags on several images (by hash). Matching is case- and accent-insensitive; an existing spelling of a
    tag is reused. Returns {changed, add, remove}. Raises storage.StorageError on bad input."""
    hashes = [h for h in dict.fromkeys(str(h) for h in hashes or []) if _HASH_RE.match(h)]
    if not hashes:
        raise storage.StorageError("no images selected")
    add_tags = [t for t in (clean_tag(x) for x in add or []) if t]
    rem = {_fold(clean_tag(x)) for x in remove or [] if clean_tag(x)}
    if not add_tags and not rem:
        raise storage.StorageError("no tags given")
    with storage._lock:
        tags = load_tags()
        known = {}
        for lst in tags.values():
            for t in lst:
                known.setdefault(_fold(t), t)
        add_tags = list(dict.fromkeys(known.get(_fold(t), t) for t in add_tags))
        changed = 0
        for h in hashes:
            cur = list(tags.get(h, []))
            new = [t for t in cur if _fold(t) not in rem]
            folded = {_fold(t) for t in new}
            for t in add_tags:
                if _fold(t) not in folded and len(new) < TAGS_PER_IMAGE:
                    new.append(t); folded.add(_fold(t))
            if new != cur:
                changed += 1
                if new:
                    tags[h] = new
                else:
                    tags.pop(h, None)
        if changed:
            save_tags(tags)
        return {"changed": changed, "add": add_tags, "remove": sorted(rem)}


def add_to_collection(hashes: Iterable[str], collection_id: str) -> Dict[str, Any]:
    """Copy images (by hash, from any collection) into `collection_id`. Same content is never added twice.
    Returns {collection, added, skipped}."""
    hashes = [h for h in dict.fromkeys(str(h) for h in hashes or []) if _HASH_RE.match(h)]
    if not hashes:
        raise storage.StorageError("no images selected")
    with storage._lock:
        target = storage.get_collection(collection_id)
        have = {i.get("hash") for i in target["images"]}
        by_hash = {img["hash"]: img for img in list_images()}
        sources, skipped = [], 0
        for h in hashes:
            img = by_hash.get(h)
            if h in have or img is None or not os.path.isfile(img["path"]):
                skipped += 1
                continue
            sources.append((img["path"], img["name"]))
        col = storage.add_images(collection_id, sources) if sources else target
        added = col.get("_added", 0) if sources else 0
        skipped += len(sources) - added
        return {"collection": col, "added": added, "skipped": skipped}


def new_collection_with(hashes: Iterable[str], name: str, fallback: str = "Collection") -> Dict[str, Any]:
    hashes = [h for h in dict.fromkeys(str(h) for h in hashes or []) if _HASH_RE.match(h)]
    if not hashes:
        raise storage.StorageError("no images selected")
    by_hash = {img["hash"]: img for img in list_images()}
    sources = [(by_hash[h]["path"], by_hash[h]["name"]) for h in hashes if h in by_hash and os.path.isfile(by_hash[h]["path"])]
    col = storage.create_collection(storage.unique_name(name or fallback), sources, fallback=fallback)
    return {"collection": col, "added": len(col["images"]), "skipped": len(hashes) - len(col["images"])}


def _img_data_uri(path: str, size: int, cache: Optional[str] = None) -> Optional[str]:
    try:
        if cache and os.path.isfile(cache) and os.path.getsize(cache) > 0 and os.path.getmtime(cache) >= os.path.getmtime(path):
            with open(cache, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        from PIL import Image
        if os.path.getsize(path) > MAX_SOURCE_BYTES:
            return None
        with Image.open(path) as im:
            if im.width * im.height > MAX_SOURCE_PIXELS:
                return None
            im.seek(0)
            if im.format == "JPEG":
                im.draft("RGB", (size * 2, size * 2))   # 1.4.4: decode a 4K JPEG at 1/8 scale
            im = im.convert("RGBA") if im.mode in ("P", "LA") else im
            if im.mode == "RGBA":
                bg = Image.new("RGB", im.size, (40, 40, 46)); bg.paste(im, mask=im.split()[3]); im = bg
            else:
                im = im.convert("RGB")
            im.thumbnail((size, size), reducing_gap=2.0)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            data = buf.getvalue()
        if cache:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, cache)
        return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    except Exception as e:
        print(f"[Reference Library] thumbnail failed for {path}: {e}")
        return None


MAX_SOURCE_BYTES = 200 * 1024 * 1024    # 1.4.4 guards: bigger sources get the placeholder instead of a thumbnail
MAX_SOURCE_PIXELS = 120_000_000


def thumb(img: Dict[str, Any], size: int = 220) -> Optional[str]:
    return _img_data_uri(img["path"], size, os.path.join(_thumbs_dir(), img["hash"] + ".jpg"))


def paths_for_hashes(hashes: Iterable[str]) -> Dict[str, List[str]]:
    """Candidate source files per hash (collection/pool copies first), from the cached catalog (1.4.4)."""
    want = {h for h in hashes if _HASH_RE.match(str(h or ""))}
    out: Dict[str, List[str]] = {h: [] for h in want}
    if not want:
        return out
    by = catalog()["by_hash"]
    for h in want:
        i = by.get(h)
        if i:
            out[h] = list(dict.fromkeys([i["path"]] + list(i.get("files") or [])))
    return out


def _cached_thumb(h: str) -> Optional[str]:
    cache = os.path.join(_thumbs_dir(), h + ".jpg")
    try:
        if os.path.getsize(cache) > 0:
            with open(cache, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        pass
    return None


def _make_thumb(h: str, cands: List[str], size: int = 220) -> Optional[str]:
    for src in cands:
        if os.path.isfile(src):
            uri = _img_data_uri(src, size, os.path.join(_thumbs_dir(), h + ".jpg"))
            if uri:
                return uri
    return None


# Background thumbnail worker (1.4.4): one low-priority thread, newest requests first (they are what's on screen),
# bounded queue. Only hashes a browser actually asked for are ever queued: never the whole library up front.
THUMB_QUEUE_MAX = 600
_thumb_q: Dict[str, List[str]] = {}
_thumb_lock = threading.Lock()
_thumb_state = {"running": False, "done": 0, "failed": set()}


def _thumb_worker() -> None:
    while True:
        with _thumb_lock:
            if not _thumb_q:
                _thumb_state["running"] = False
                return
            h = next(reversed(_thumb_q))
            cands = _thumb_q.pop(h)
        try:
            if _make_thumb(h, cands) is None:
                with _thumb_lock:
                    _thumb_state["failed"].add(h)
        except Exception as e:
            print(f"[Reference Library] background thumbnail failed: {e}")
        _thumb_state["done"] += 1
        time.sleep(0.002)   # yield: never compete with the UI / generation threads


def _queue_thumbs(items: Dict[str, List[str]]) -> None:
    with _thumb_lock:
        for h, c in items.items():
            _thumb_q.pop(h, None)
            _thumb_q[h] = c
        while len(_thumb_q) > THUMB_QUEUE_MAX:
            _thumb_q.pop(next(iter(_thumb_q)))
        if _thumb_q and not _thumb_state["running"]:
            _thumb_state["running"] = True
            threading.Thread(target=_thumb_worker, name="reflib-thumbs", daemon=True).start()


def thumbs_pending() -> int:
    with _thumb_lock:
        return len(_thumb_q)


def thumbs_for(hashes: Iterable[str], size: int = 220, budget: Optional[float] = None,
               pending: Optional[List[str]] = None) -> Dict[str, Optional[str]]:
    """{hash: data URI or None}. A cached .thumbs/<hash>.jpg is served as-is (the hash IS the content, so it can't be
    stale); otherwise the first readable source is thumbnailed and cached. None = no readable source (placeholder).
    1.4.4: with `budget` (seconds) and a `pending` list, generation stops when the budget is spent; the rest is handed
    to the background worker and listed in `pending` (value None), so a request never waits on a pile of 4K originals."""
    hashes = [h for h in dict.fromkeys(str(h) for h in hashes or []) if _HASH_RE.match(h)]
    out: Dict[str, Optional[str]] = {}
    missing = []
    for h in hashes:
        uri = _cached_thumb(h)
        if uri:
            out[h] = uri
        else:
            missing.append(h)
    if missing:
        t0 = time.time()
        cands = paths_for_hashes(missing)
        later = {}
        for h in missing:
            out[h] = None
            if budget is not None and pending is not None and time.time() - t0 > budget:
                with _thumb_lock:
                    failed = h in _thumb_state["failed"]
                if not failed and cands.get(h):
                    later[h] = cands[h]
                    pending.append(h)
                continue
            out[h] = _make_thumb(h, cands.get(h) or [], size)
        if later:
            _queue_thumbs(later)
    return out


def preview(digest: str, size: int = 1024) -> Optional[Dict[str, Any]]:
    img = catalog()["by_hash"].get(str(digest or ""))
    for img in [img] if img else []:
        if True:
            cat = catalog()
            cname = {c["id"]: c["name"] for c in cat["collections"]}
            fpath = {f["id"]: f["path"] for f in cat["folders"]}
            out = {"hash": img["hash"], "name": img["name"], "names": list(img["names"]), "path": img["path"], "files": list(img["files"]),
                   "collections": [{"id": c, "name": cname.get(c, c)} for c in sorted(img["colids"], key=lambda c: cname.get(c, c))],
                   "in_pool": img["in_pool"], "folders": [{"id": f, "path": fpath.get(f, "")} for f in img["folders"]],
                   "tags": list(img["tags"]), "added": img["added"]}
            out["locations"] = (locate(img["hash"]) or {}).get("folders", [])
            out.pop("path", None)
            src = next((c for c in [img["path"]] + list(img.get("files") or []) if os.path.isfile(c)), img["path"])
            img = dict(img, path=src)
            out["src"] = _img_data_uri(src, size)
            try:
                from PIL import Image
                with Image.open(img["path"]) as im:
                    out["width"], out["height"] = im.size
            except Exception:
                pass
            try:
                out["size"] = os.path.getsize(img["path"])
            except OSError:
                pass
            return out
    return None


# ---------------------------------------------------------------------------- unassigned pool (1.4.0)
# plugins/wan2gp-reference-library/pool/pool.json  {"version": 1, "images": [{hash, file, name, added, source}]}
#                                    pool/<sha256>.<ext>
#                                    pool/.trash/<sha256>.<ext> + <sha256>.json   (deleted, restorable 5 min, purged at 15)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def pool_dir() -> str:
    return os.path.join(os.path.dirname(storage.COLLECTIONS_DIR), "pool")


def _pool_index_path() -> str:
    return os.path.join(pool_dir(), "pool.json")


def load_pool() -> List[Dict[str, Any]]:
    try:
        with open(_pool_index_path(), "r", encoding="utf-8") as reader:
            data = json.load(reader)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid pool.json: {e}")
        return []
    out, seen = [], set()
    for it in (data.get("images") if isinstance(data, dict) else None) or []:
        if not isinstance(it, dict):
            continue
        h, f = str(it.get("hash") or ""), os.path.basename(str(it.get("file") or ""))
        if not _HASH_RE.match(h) or not f or h in seen:
            continue
        seen.add(h)
        out.append({"hash": h, "file": f, "name": str(it.get("name") or f)[:120],
                    "added": float(it.get("added") or 0), "source": str(it.get("source") or "")[:40]})
    return out


def _save_pool(items: List[Dict[str, Any]]) -> None:
    os.makedirs(pool_dir(), exist_ok=True)
    storage._atomic_write_json(_pool_index_path(), {"version": 1, "images": items})


def pool_path(item: Dict[str, Any]) -> str:
    return os.path.join(pool_dir(), item["file"])


def _known_hashes() -> set:
    hs = {i["hash"] for i in load_pool()}
    for col in storage.list_collections():
        hs.update(i.get("hash") for i in col["images"] if i.get("hash"))
    return hs


def pool_add(src: str, name: Optional[str] = None, source: str = "import", skip_known: bool = True) -> Dict[str, Any]:
    """Copy an image file into the pool. Returns {hash, created, where} (where: "pool" / "collection" when it was
    already known). Raises storage.StorageError."""
    if not isinstance(src, str) or not os.path.isfile(src):
        raise storage.StorageError("source image not found")
    ext = os.path.splitext(name or src)[1].lower() or os.path.splitext(src)[1].lower()
    if ext not in IMAGE_EXTS:
        ext = os.path.splitext(src)[1].lower()
    if ext not in IMAGE_EXTS:
        raise storage.StorageError("not an image file")
    digest = storage._file_hash(src)
    with storage._lock:
        items = load_pool()
        if any(i["hash"] == digest for i in items):
            return {"hash": digest, "created": False, "where": "pool"}
        if skip_known and any(digest == i.get("hash") for c in storage.list_collections() for i in c["images"]):
            return {"hash": digest, "created": False, "where": "collection"}
        os.makedirs(pool_dir(), exist_ok=True)
        fname = digest + ext
        dest = os.path.join(pool_dir(), fname)
        if not os.path.isfile(dest):
            import shutil
            shutil.copy2(src, dest)
        items.append({"hash": digest, "file": fname, "name": os.path.basename(name or src)[:120] or fname,
                      "added": time.time(), "source": str(source or "")[:40]})
        _save_pool(items)
        return {"hash": digest, "created": True, "where": "pool"}


def keep_orphans(items, exclude_cid=None) -> None:
    """storage._orphan_hook: images leaving their last collection go to the pool (until deleted there)."""
    with storage._lock:
        live = set()
        for col in storage.list_collections():
            if col["id"] == exclude_cid:
                continue
            live.update(i.get("hash") for i in col["images"])
        for path, name, digest in items:
            if digest and digest in live:
                continue
            if os.path.isfile(path):
                try:
                    pool_add(path, name=name, source="removed", skip_known=False)
                except storage.StorageError:
                    pass


def _pool_trash() -> str:
    return os.path.join(pool_dir(), ".trash")


def purge_pool_trash(max_age_s: float = 15 * 60) -> None:
    root = _pool_trash()
    if not os.path.isdir(root):
        return
    now = time.time()
    for name in os.listdir(root):
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) >= max_age_s:
                os.unlink(path)
        except OSError:
            pass


def pool_delete(hashes: Iterable[str]) -> Dict[str, Any]:
    """Move unassigned pool images to pool/.trash (Undo for 5 min). Images still in a collection are not deleted.
    Returns {deleted: [hash], kept: n}."""
    hashes = [h for h in dict.fromkeys(str(h) for h in hashes or []) if _HASH_RE.match(h)]
    if not hashes:
        raise storage.StorageError("no images selected")
    purge_pool_trash()
    with storage._lock:
        in_cols = set()
        for col in storage.list_collections():
            in_cols.update(i.get("hash") for i in col["images"])
        items = load_pool()
        keep, deleted = [], []
        os.makedirs(_pool_trash(), exist_ok=True)
        for it in items:
            if it["hash"] in hashes and it["hash"] not in in_cols:
                src = pool_path(it)
                if os.path.isfile(src):
                    os.replace(src, os.path.join(_pool_trash(), it["file"]))
                storage._atomic_write_json(os.path.join(_pool_trash(), it["hash"] + ".json"), it)
                deleted.append(it["hash"])
            else:
                keep.append(it)
        _save_pool(keep)
        return {"deleted": deleted, "kept": len(hashes) - len(deleted)}


def pool_restore(hashes: Iterable[str]) -> Dict[str, Any]:
    """Undo pool_delete. Dedupe-aware: an image that is back in the library meanwhile (re-imported) is not restored
    twice. Returns {restored, merged}. Raises storage.StorageError("undo expired") when nothing was left."""
    restored = merged = 0
    with storage._lock:
        items = load_pool()
        have = {i["hash"] for i in items}
        for h in [h for h in dict.fromkeys(str(h) for h in hashes or []) if _HASH_RE.match(h)]:
            meta = os.path.join(_pool_trash(), h + ".json")
            if not os.path.isfile(meta):
                continue
            with open(meta, "r", encoding="utf-8") as reader:
                it = json.load(reader)
            src = os.path.join(_pool_trash(), os.path.basename(str(it.get("file") or "")))
            if h in have:
                merged += 1
                for p in (src, meta):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
                continue
            if os.path.isfile(src):
                os.replace(src, os.path.join(pool_dir(), os.path.basename(src)))
            os.unlink(meta)
            items.append(it); have.add(h); restored += 1
        if not restored and not merged:
            raise storage.StorageError("undo expired")
        _save_pool(items)
        return {"restored": restored, "merged": merged}


# ---------------------------------------------------------------------------- watched folders (1.4.0, 1.4.1)
# plugins/wan2gp-reference-library/folders/index.json
#   {"version": 1, "folders": [{id, path, recursive, added}], "files": {"<abs path>": {folder, size, mtime, hash}}}
# Files are referenced in place: never copied, moved, modified or deleted (only os.stat / open "rb").
# Adding one to a collection copies it there. 1.4.1: scans can run in a background thread with progress, committing
# partial results every few hundred files so the browser fills in while a big folder is indexed.
import ntpath
import threading

FOLDER_MAX_FILES = 50000
_SCAN_COMMIT_EVERY = 200


def _folders_dir() -> str:
    return os.path.join(os.path.dirname(storage.COLLECTIONS_DIR), "folders")


def _folders_index() -> str:
    return os.path.join(_folders_dir(), "index.json")


def load_folders() -> Dict[str, Any]:
    try:
        with open(_folders_index(), "r", encoding="utf-8") as reader:
            data = json.load(reader)
    except FileNotFoundError:
        return {"folders": [], "files": {}}
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid folders index: {e}")
        return {"folders": [], "files": {}}
    folders = []
    for f in (data.get("folders") if isinstance(data, dict) else None) or []:
        if isinstance(f, dict) and re.match(r"^[0-9a-f]{8,64}$", str(f.get("id") or "")) and isinstance(f.get("path"), str):
            folders.append({"id": f["id"], "path": f["path"], "recursive": bool(f.get("recursive")),
                            "added": float(f.get("added") or 0) or time.time()})
    ids = {f["id"] for f in folders}
    files = {}
    for p, v in ((data.get("files") if isinstance(data, dict) else None) or {}).items():
        if isinstance(v, dict) and v.get("folder") in ids and _HASH_RE.match(str(v.get("hash") or "")):
            files[p] = {"folder": v["folder"], "size": int(v.get("size") or 0), "mtime": float(v.get("mtime") or 0), "hash": v["hash"],
                        "first": float(v.get("first") or 0)}
    return {"folders": folders, "files": files}


def _save_folders(data: Dict[str, Any]) -> None:
    os.makedirs(_folders_dir(), exist_ok=True)
    storage._atomic_write_json(_folders_index(), {"version": 1, "folders": data["folders"], "files": data["files"]})


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))


def clean_folder_input(text: str, pathmod=os.path) -> str:
    """Tidy a folder path typed or pasted by the user: surrounding quotes/spaces, a file:// prefix, a bare drive
    ("D:" -> "D:\\"), and trailing separators. Spaces inside the path, backslashes and drive letters are kept as they
    are. `pathmod` lets the tests check Windows rules (ntpath) on Linux."""
    t = str(text or "").strip()
    while len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    if t.lower().startswith("file:///"):
        t = t[8:] if re.match(r"^[A-Za-z]:", t[8:]) else t[7:]
        t = t.replace("%20", " ")
    if pathmod is ntpath:
        if re.match(r"^[A-Za-z]:$", t):
            t += "\\"
        if len(t) > 3 or not re.match(r"^[A-Za-z]:[\\/]$", t):
            t = t.rstrip("\\/") or t
    elif len(t) > 1:
        t = t.rstrip("/") or "/"
    return t


def _rel_dir(root: str, path: str) -> str:
    """Folder of `path` relative to `root`, always with "/" (also on Windows), "" for the root itself."""
    try:
        rel = os.path.relpath(os.path.dirname(path), root)
    except ValueError:
        return ""
    if rel in (".", ""):
        return ""
    return rel.replace(os.sep, "/").replace("\\", "/")


def add_folder(path: str, recursive: bool = True, background: bool = False) -> Dict[str, Any]:
    """Validate and watch a folder, then index it (in a background thread when background=True).
    Raises storage.StorageError("folder not found" / "not a folder" / "folder already added" / "folder not allowed")."""
    text = clean_folder_input(path)
    if not text or not os.path.exists(text):
        raise storage.StorageError("folder not found")
    if not os.path.isdir(text):
        raise storage.StorageError("not a folder")
    real = _norm(text)
    plugin_dir = _norm(os.path.dirname(storage.COLLECTIONS_DIR))
    if real == plugin_dir or real.startswith(plugin_dir.rstrip(os.sep) + os.sep) or plugin_dir.startswith(real.rstrip(os.sep) + os.sep):
        raise storage.StorageError("folder not allowed")
    import uuid
    with storage._lock:
        data = load_folders()
        if any(_norm(f["path"]) == real for f in data["folders"]):
            raise storage.StorageError("folder already added")
        entry = {"id": uuid.uuid4().hex, "path": os.path.realpath(os.path.abspath(text)), "recursive": bool(recursive), "added": time.time()}
        data["folders"].append(entry)
        _save_folders(data)
    if background:
        start_scan([entry["id"]])
    else:
        rescan([entry["id"]])
    return entry


def set_folder_recursive(fid: str, recursive: bool, background: bool = False) -> Dict[str, Any]:
    with storage._lock:
        data = load_folders()
        for f in data["folders"]:
            if f["id"] == fid:
                f["recursive"] = bool(recursive)
                _save_folders(data)
                break
        else:
            raise storage.StorageError("folder not found")
    if background:
        start_scan([fid])
    else:
        rescan([fid])
    return f


def remove_folder(fid: str) -> Dict[str, Any]:
    """Stop watching a folder: only the index entry goes, the files on disk are untouched."""
    with storage._lock:
        data = load_folders()
        f = next((x for x in data["folders"] if x["id"] == fid), None)
        if f is None:
            raise storage.StorageError("folder not found")
        data["folders"] = [x for x in data["folders"] if x["id"] != fid]
        data["files"] = {p: v for p, v in data["files"].items() if v["folder"] != fid}
        _save_folders(data)
        return f


def _walk(folder: Dict[str, Any]):
    root = folder["path"]
    if folder["recursive"]:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in ("$RECYCLE.BIN", "System Volume Information"))
            for n in sorted(filenames):
                yield os.path.join(dirpath, n)
    else:
        try:
            for n in sorted(os.listdir(root)):
                yield os.path.join(root, n)
        except OSError:
            return


def _candidates(folder: Dict[str, Any], with_stat: bool = False):
    """Image files of a watched folder, sorted per directory. with_stat=True returns (path, size, mtime) from
    os.scandir entries (1.4.4: free on Windows, where DirEntry carries the stat — no extra call per file)."""
    out = []
    skip_dirs = ("$RECYCLE.BIN", "System Volume Information")
    stack = [folder["path"]]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        subdirs = []
        for e in entries:
            n = e.name
            if n.startswith("."):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if folder["recursive"] and n not in skip_dirs:
                        subdirs.append(e.path)
                    continue
            except OSError:
                continue
            if os.path.splitext(n)[1].lower() not in IMAGE_EXTS:
                continue
            if with_stat:
                try:
                    st = e.stat()
                except OSError:
                    continue
                out.append((e.path, st.st_size, st.st_mtime))
            else:
                out.append(e.path)
            if len(out) >= FOLDER_MAX_FILES:
                return out
        stack.extend(reversed(subdirs))
    return out


_scan_state: Dict[str, Any] = {"running": False, "folder_id": "", "path": "", "done": 0, "total": 0, "added": 0,
                               "removed": 0, "files": 0, "missing": [], "finished": 0.0, "seq": 0}
_scan_lock = threading.Lock()
_scan_queue: List[str] = []
_paused = threading.Event()
SCAN_COMMIT_SECONDS = 1.0     # 1.4.4: partial commits at most once a second (each rewrites the whole index)
AUTO_SCAN_INTERVAL = 10 * 60  # 1.4.4: opening the browser re-checks folders at most every 10 minutes


def _set_scan(**kw) -> None:
    with _scan_lock:
        _scan_state.update(kw)


def set_paused(paused: bool) -> None:
    (_paused.set if paused else _paused.clear)()
    _set_scan(paused=bool(paused) and _scan_state.get("running", False))


def is_paused() -> bool:
    return _paused.is_set()


def maybe_scan(min_interval: Optional[float] = None) -> Dict[str, Any]:
    """Background re-check of every watched folder, throttled (opening the browser calls this; Re-scan forces)."""
    iv = AUTO_SCAN_INTERVAL if min_interval is None else min_interval
    with _scan_lock:
        recent = time.time() - max(_scan_state.get("started", 0.0), _scan_state.get("finished", 0.0)) < iv
        running = _scan_state["running"]
    if running or recent or not load_folders()["folders"]:
        return scan_status()
    return start_scan()


def scan_status() -> Dict[str, Any]:
    with _scan_lock:
        st = dict(_scan_state, missing=list(_scan_state["missing"]), queued=len(_scan_queue))
    st["paused"] = bool(st["running"] and _paused.is_set())
    st["pause_set"] = _paused.is_set()
    st["thumbs_pending"] = thumbs_pending()
    return st


def _scan_folder(f: Dict[str, Any], progress=None) -> Dict[str, int]:
    """Index one watched folder. Hashing happens outside the storage lock; results are merged in small commits."""
    fid = f["id"]
    if not os.path.isdir(f["path"]):
        return {"missing": 1, "added": 0, "removed": 0}
    old = {p: v for p, v in load_folders()["files"].items() if v["folder"] == fid}
    paths = _candidates(f, with_stat=True)
    if progress:
        progress(0, len(paths))
    seen: Dict[str, Dict[str, Any]] = {}
    pending: Dict[str, Dict[str, Any]] = {}
    added = 0
    changed = [False]
    last_commit = [time.time()]

    def commit(final=False):
        last_commit[0] = time.time()
        if final and not changed[0] and len(seen) == len(old):
            return True             # 1.4.4: nothing changed -> don't rewrite a multi-MB index
        with storage._lock:
            data = load_folders()
            if not any(x["id"] == fid for x in data["folders"]):
                return False            # removed while scanning
            if final:
                data["files"] = {p: v for p, v in data["files"].items() if v["folder"] != fid}
                data["files"].update(seen)
            else:
                data["files"].update(pending)
            _save_folders(data)
        pending.clear()
        return True

    for i, (p, size, mtime) in enumerate(paths, 1):
        while _paused.is_set():     # 1.4.4: "Pause indexing"
            _set_scan(paused=True)
            time.sleep(0.3)
        _set_scan(paused=False)
        prev = old.get(p)
        if prev and prev["size"] == size and abs(prev["mtime"] - mtime) < 1e-3:
            seen[p] = prev
            if progress and i % 50 == 0:
                progress(i, len(paths))
            continue
        try:
            digest = storage._file_hash(p)
        except OSError:
            continue
        changed[0] = True
        added += 0 if prev else 1
        seen[p] = pending[p] = {"folder": fid, "size": size, "mtime": mtime, "hash": digest,
                                "first": (prev or {}).get("first") or time.time()}
        if progress:
            progress(i, len(paths))
        time.sleep(0)               # low priority: let request threads run between files
        if len(pending) >= _SCAN_COMMIT_EVERY and time.time() - last_commit[0] >= SCAN_COMMIT_SECONDS and not commit():
            return {"missing": 0, "added": added, "removed": 0}
    if progress:
        progress(len(paths), len(paths))
    commit(final=True)
    return {"missing": 0, "added": added, "removed": len([p for p in old if p not in seen])}


def rescan(folder_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Re-index watched folders (all, or the given ids) synchronously; only reads the disk. Unchanged files (same size
    + mtime) keep their hash; new and changed files are hashed; vanished files drop out.
    Returns {folders, files, added, removed, missing: [folder ids]}."""
    data = load_folders()
    want = set(folder_ids) if folder_ids is not None else None
    added = removed = 0
    missing = []
    for f in data["folders"]:
        if want is not None and f["id"] not in want:
            continue
        r = _scan_folder(f)
        added += r["added"]
        removed += r["removed"]
        if r["missing"]:
            missing.append(f["id"])
    data = load_folders()
    return {"folders": len(data["folders"]), "files": len(data["files"]), "added": added, "removed": removed, "missing": missing}


def _scan_worker() -> None:
    totals = {"added": 0, "removed": 0, "missing": []}
    while True:
        with _scan_lock:
            if not _scan_queue:
                data = load_folders()
                _scan_state.update(running=False, finished=time.time(), added=totals["added"], removed=totals["removed"],
                                   missing=totals["missing"], files=len(data["files"]), seq=_scan_state["seq"] + 1)
                return
            fid = _scan_queue.pop(0)
        f = next((x for x in load_folders()["folders"] if x["id"] == fid), None)
        if f is None:
            continue
        with _scan_lock:
            _scan_state.update(folder_id=fid, path=f["path"], done=0, total=0)

        def progress(done, total):
            with _scan_lock:
                _scan_state["done"], _scan_state["total"] = done, total
        try:
            r = _scan_folder(f, progress)
        except Exception as e:
            print(f"[Reference Library] scanning {f['path']} failed: {e}")
            continue
        totals["added"] += r["added"]
        totals["removed"] += r["removed"]
        if r["missing"]:
            totals["missing"].append(fid)


def start_scan(folder_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Queue folders (default: all) for a background scan; returns scan_status(). Never blocks on hashing."""
    ids = list(folder_ids) if folder_ids is not None else [f["id"] for f in load_folders()["folders"]]
    with _scan_lock:
        for fid in ids:
            if fid not in _scan_queue and not (_scan_state["running"] and _scan_state["folder_id"] == fid and fid not in ids[:0]):
                _scan_queue.append(fid)
        if ids and not _scan_state["running"]:
            _scan_state.update(running=True, done=0, total=0, added=0, removed=0, missing=[], started=time.time())
            threading.Thread(target=_scan_worker, name="reflib-folder-scan", daemon=True).start()
    return scan_status()


def wait_scan(timeout: float = 60.0) -> Dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = scan_status()
        if not st["running"]:
            return st
        time.sleep(0.05)
    return scan_status()


def list_folders() -> List[Dict[str, Any]]:
    data = load_folders()
    counts: Dict[str, int] = {}
    for v in data["files"].values():
        counts[v["folder"]] = counts.get(v["folder"], 0) + 1
    return [{**f, "count": counts.get(f["id"], 0), "missing": not os.path.isdir(f["path"]),
             "name": os.path.basename(f["path"].rstrip("\\/")) or f["path"]} for f in data["folders"]]


# ---------------------------------------------------------------------------- folder picker (1.4.2)
# Read-only directory browsing for the "Browse…" button of "Add folder". Only os.scandir / os.path checks; every call
# runs in a worker thread with a timeout so a sleeping USB disk or a dead network drive can't hang the UI.
BROWSE_TIMEOUT = 4.0
BROWSE_MAX_DIRS = 2000
BROWSE_MAX_COUNT = 5000


def _with_timeout(fn, timeout=None):
    timeout = BROWSE_TIMEOUT if timeout is None else timeout
    box: Dict[str, Any] = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:   # reported to the caller
            box["error"] = e
    t = threading.Thread(target=run, name="reflib-browse", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise storage.StorageError("folder too slow")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def browse_roots(outputs_dir: Optional[str] = None) -> Dict[str, Any]:
    """Drives (Windows) or "/" plus shortcuts: home, Pictures, WanGP outputs. Missing ones are left out."""
    drives = []
    if os.name == "nt":
        import string

        def probe():
            found = []
            try:
                import ctypes
                mask = ctypes.windll.kernel32.GetLogicalDrives()
                letters = [c for i, c in enumerate(string.ascii_uppercase) if mask >> i & 1]
            except Exception:
                letters = list(string.ascii_uppercase)
            for c in letters:
                found.append(f"{c}:\\")
            return found
        try:
            drives = [{"name": d, "path": d, "kind": "drive"} for d in _with_timeout(probe)]
        except Exception:
            drives = []
    else:
        drives = [{"name": "/", "path": "/", "kind": "drive"}]
    home = os.path.expanduser("~")
    shortcuts = []

    def add(kind, path):
        try:
            if path and _with_timeout(lambda: os.path.isdir(path), 1.5) and not any(s["path"] == path for s in shortcuts):
                shortcuts.append({"kind": kind, "name": os.path.basename(path.rstrip("\\/")) or path, "path": path})
        except Exception:
            pass
    add("home", home)
    for sub in ("Pictures", "Imágenes", "Imagenes", "Fotos", "Photos"):
        p = os.path.join(home, sub)
        if os.path.isdir(p):
            add("pictures", p)
            break
    for cand in (outputs_dir, os.path.join(os.getcwd(), "outputs")):
        if cand:
            add("outputs", os.path.abspath(cand))
            break
    return {"path": "", "drives": drives, "shortcuts": shortcuts}


def browse_dir(path: str) -> Dict[str, Any]:
    """List the subfolders of `path` and count its images (not recursive). Read-only.
    Raises storage.StorageError("folder not found" / "not a folder" / "permission denied" / "folder too slow")."""
    text = clean_folder_input(path)
    if not text:
        raise storage.StorageError("folder not found")

    def scan():
        if not os.path.exists(text):
            raise storage.StorageError("folder not found")
        if not os.path.isdir(text):
            raise storage.StorageError("not a folder")
        dirs, images, more = [], 0, False
        with os.scandir(text) as it:
            for e in it:
                n = e.name
                try:
                    if e.is_dir(follow_symlinks=False):
                        if n.startswith(".") or n.startswith("$") or n in ("System Volume Information",):
                            continue
                        if len(dirs) < BROWSE_MAX_DIRS:
                            dirs.append({"name": n, "path": os.path.join(text, n)})
                        else:
                            more = True
                    elif images < BROWSE_MAX_COUNT and not n.startswith(".") and os.path.splitext(n)[1].lower() in IMAGE_EXTS:
                        images += 1
                except OSError:
                    continue
        dirs.sort(key=lambda d: d["name"].casefold())
        return dirs, images, more
    try:
        dirs, images, more = _with_timeout(scan)
    except PermissionError:
        raise storage.StorageError("permission denied")
    except storage.StorageError:
        raise
    except OSError as e:
        if getattr(e, "errno", None) in (13, 1) or getattr(e, "winerror", None) == 5:
            raise storage.StorageError("permission denied")
        raise storage.StorageError("folder not found")
    full = os.path.abspath(text)
    parent = os.path.dirname(full.rstrip("\\/")) if full.rstrip("\\/") else ""
    if os.name == "nt" and re.match(r"^[A-Za-z]:\\?$", full):
        parent = ""
    if parent == full:
        parent = ""
    crumbs, cur = [], full
    while True:
        head, tail = os.path.split(cur.rstrip("\\/") or cur)
        if not tail:
            crumbs.append({"name": cur, "path": cur})
            break
        crumbs.append({"name": tail, "path": cur})
        if head == cur:
            break
        cur = head
    crumbs.reverse()
    return {"path": full, "parent": parent, "crumbs": crumbs, "dirs": dirs, "images": images,
            "images_more": images >= BROWSE_MAX_COUNT, "dirs_more": more}


# ---------------------------------------------------------------------------- remove / delete any selection (1.4.3)
# "Remove from <collection>" and "Delete from library" work on any selection. Removed collection entries are stashed in
# collections/.undo/<token>/ (files + entries with their positions) so Undo puts them back exactly; stashes are purged
# after 15 minutes. Pool images go to pool/.trash as before. Watched-folder files are never touched.
UNDO_TTL = 15 * 60


def _undo_root() -> str:
    return os.path.join(storage.COLLECTIONS_DIR, ".undo")


def purge_undo(max_age_s: float = UNDO_TTL) -> None:
    root = _undo_root()
    if not os.path.isdir(root):
        return
    now = time.time()
    for name in os.listdir(root):
        p = os.path.join(root, name)
        try:
            if now - os.path.getmtime(p) > max_age_s:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def _stash_and_remove(index: Dict[str, Any], want: set, cids: Optional[set], stash: str, keep_orphans_in_pool: bool) -> Dict[str, Any]:
    """Remove entries whose hash is in `want` from the collections in `cids` (None = all). Returns the undo record."""
    record: List[Dict[str, Any]] = []
    orphan_items = []
    touched = set()
    for col in index["collections"]:
        if cids is not None and col["id"] not in cids:
            continue
        removed = [(k, img) for k, img in enumerate(col["images"]) if img.get("hash") in want]
        if not removed:
            continue
        touched.add(col["id"])
        folder = storage._collection_dir(col["id"])
        os.makedirs(os.path.join(stash, col["id"]), exist_ok=True)
        for k, img in removed:
            src = os.path.join(folder, img["file"])
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(stash, col["id"], img["file"]))
            record.append({"cid": col["id"], "index": k, "entry": img, "was_cover": col.get("cover") == img["file"]})
        col["images"] = [img for img in col["images"] if img.get("hash") not in want]
        if col.get("cover") not in {i["file"] for i in col["images"]}:
            col["cover"] = col["images"][0]["file"] if col["images"] else None
        col["updated"] = time.time()
        still = {i["file"] for i in col["images"]}
        for _, img in removed:
            if img["file"] not in still:
                orphan_items.append((os.path.join(folder, img["file"]), img.get("name") or img["file"], img.get("hash") or ""))
    storage.save_index(index)
    if keep_orphans_in_pool and orphan_items:
        storage._orphans(orphan_items)
    for path, _, _ in orphan_items:
        if os.path.isfile(path):
            try:
                os.unlink(path)
            except OSError:
                pass
    return {"items": record, "collections": sorted(touched)}


def remove_from_collection(hashes: Iterable[str], collection_id: str) -> Dict[str, Any]:
    """Take images out of one collection (Undo for 15 min). Images that leave their last collection stay in the pool,
    as with any other removal. Returns {token, removed, collection}."""
    hashes = {h for h in (str(x) for x in hashes or []) if _HASH_RE.match(h)}
    if not hashes:
        raise storage.StorageError("no images selected")
    purge_undo()
    import uuid
    with storage._lock:
        col = storage.get_collection(collection_id)
        token = uuid.uuid4().hex
        stash = os.path.join(_undo_root(), token)
        pool_before = {it["hash"] for it in load_pool()}
        rec = _stash_and_remove(storage.load_index(), hashes, {col["id"]}, stash, keep_orphans_in_pool=True)
        rec.update({"kind": "remove", "pool": [], "pooled_new": sorted({it["hash"] for it in load_pool()} - pool_before)})
        os.makedirs(stash, exist_ok=True)
        storage._atomic_write_json(os.path.join(stash, "undo.json"), rec)
        return {"token": token, "removed": len({r["entry"]["hash"] for r in rec["items"]}), "collection": col}


def delete_everywhere(hashes: Iterable[str]) -> Dict[str, Any]:
    """Delete images from every collection and from the pool (Undo for 15 min). Watched-folder files are never touched:
    images that are only in folders are skipped. Returns {token, deleted, collections, folder_only, on_disk}."""
    hashes = {h for h in (str(x) for x in hashes or []) if _HASH_RE.match(h)}
    if not hashes:
        raise storage.StorageError("no images selected")
    purge_undo()
    import uuid
    with storage._lock:
        folder_hashes = {v["hash"] for v in load_folders()["files"].values()}
        in_cols = set()
        for col in storage.list_collections():
            in_cols.update(i.get("hash") for i in col["images"])
        in_pool = {it["hash"] for it in load_pool()}
        target = hashes & (in_cols | in_pool)
        token = uuid.uuid4().hex
        stash = os.path.join(_undo_root(), token)
        rec = _stash_and_remove(storage.load_index(), target, None, stash, keep_orphans_in_pool=False) if target & in_cols \
            else {"items": [], "collections": []}
        pooled = []
        if target & in_pool:
            pooled = pool_delete(sorted(target & in_pool))["deleted"]
        rec.update({"kind": "delete", "pool": pooled})
        os.makedirs(stash, exist_ok=True)
        storage._atomic_write_json(os.path.join(stash, "undo.json"), rec)
        return {"token": token, "deleted": len(target), "collections": len(rec["collections"]),
                "folder_only": len(hashes - target), "on_disk": len(hashes & folder_hashes)}


def undo_remove(token: str) -> Dict[str, Any]:
    """Put back what remove_from_collection / delete_everywhere took out. Entries go back to their positions; anything
    already back (same hash in that collection) is not duplicated. Raises "undo expired"."""
    if not re.match(r"^[0-9a-f]{32}$", str(token or "")):
        raise storage.StorageError("undo expired")
    stash = os.path.join(_undo_root(), token)
    try:
        with open(os.path.join(stash, "undo.json"), "r", encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        raise storage.StorageError("undo expired")
    restored = 0
    with storage._lock:
        index = storage.load_index()
        cols = {c["id"]: c for c in index["collections"]}
        for item in sorted(rec.get("items") or [], key=lambda r: r["index"]):
            col = cols.get(item["cid"])
            entry = item["entry"]
            if col is None or any(i.get("hash") == entry.get("hash") for i in col["images"]):
                continue
            src = os.path.join(stash, item["cid"], entry["file"])
            dest = os.path.join(storage._collection_dir(item["cid"]), entry["file"])
            if os.path.isfile(src) and not os.path.isfile(dest):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
            if not os.path.isfile(dest):
                continue
            col["images"].insert(min(item["index"], len(col["images"])), entry)
            if item.get("was_cover") or not col.get("cover"):
                col["cover"] = entry["file"]
            col["updated"] = time.time()
            restored += 1
        storage.save_index(index)
        # a remove may have parked the last copy in the pool: it's back in its collection now, drop the pool copy
        if rec.get("kind") == "remove":
            back = set(rec.get("pooled_new") or [])
            items = load_pool()
            keep = [it for it in items if it["hash"] not in back]
            if len(keep) != len(items):
                for it in items:
                    if it["hash"] in back and os.path.isfile(pool_path(it)):
                        try:
                            os.unlink(pool_path(it))
                        except OSError:
                            pass
                _save_pool(keep)
    pooled = rec.get("pool") or []
    if pooled:
        try:
            restored += pool_restore(pooled)["restored"]
        except storage.StorageError:
            pass
    shutil.rmtree(stash, ignore_errors=True)
    return {"restored": restored, "collections": rec.get("collections") or []}


# ---------------------------------------------------------------------------- catalog, server-side pages (1.4.4)
# The browser never gets the whole library: it asks for counts + the folder tree + one page at a time. The catalog is
# built once from the on-disk indexes and reused until one of them changes (keyed by their mtime/size), so paging,
# filtering and selection over 10k+ images cost a list comprehension, not a disk walk or a JSON dump.
PAGE_MAX = 240
RANGE_MAX = 50000
RECENT_DAYS, RECENT_MAX, RECENT_MIN = 30, 500, 24
_cat: Dict[str, Any] = {"key": None, "data": None, "fkey": None, "flist": None}
_cat_lock = threading.Lock()


# 1.5.0 auto-tags: the host sets AUTOTAGS = callable -> (key, {hash: frozenset(effective tag ids incl. ancestors)})
AUTOTAGS = None
# 1.5.4: the host sets JOBSTATUS = callable -> (rev, {hash: queued|processing|done|failed|local})
JOBSTATUS = None
JST_KEYS = ("queued", "processing", "done", "failed", "local", "never")


def _jobmap():
    try:
        return JOBSTATUS() if JOBSTATUS else (0, {})
    except Exception:
        return (0, {})


def _auto_map():
    try:
        return AUTOTAGS() if AUTOTAGS else (None, {})
    except Exception:
        return (None, {})


def _index_key() -> tuple:
    out = [("auto", _auto_map()[0])]
    for p in (storage.INDEX_PATH, _pool_index_path(), _folders_index(), _tags_path()):
        try:
            st = os.stat(p)
            out.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((p, None))
    return tuple(out)


def catalog() -> Dict[str, Any]:
    """{items, by_hash, tree, tags, collections, n_unassigned, folders} built from list_images(), cached."""
    key = _index_key()
    with _cat_lock:
        if _cat["key"] == key and _cat["data"] is not None:
            return _cat["data"]
    import sys as _sys
    intern = _sys.intern
    items = []
    _am = _auto_map()
    amap = _am[1]
    bmap = _am[2] if len(_am) > 2 else {}
    for i in list_images():   # compact entries: ids/rels interned, tuples, no decoded data, ≤5 file paths
        names = tuple(i["names"]) or (i["name"],)
        fold = _fold(" ".join(dict.fromkeys((i["name"],) + names)))
        items.append({"hash": i["hash"], "name": i["name"], "names": names, "path": i["path"], "files": tuple(i["files"][:5]),
                      "colids": frozenset(intern(c["id"]) for c in i["collections"]), "in_pool": i["in_pool"],
                      "folders": tuple(dict.fromkeys(intern(f["id"]) for f in i["folders"])),
                      "locs": tuple((intern(a), intern(b)) for a, b in i["locs"]), "tags": tuple(i["tags"]),
                      "tagf": frozenset(_fold(t) for t in i["tags"]), "fold": fold, "added": i["added"],
                      "auto": amap.get(i["hash"], frozenset()), "body": bmap.get(i["hash"])})
    folders = list_folders()
    fids = {f["id"] for f in folders}
    direct: Dict[str, Dict[str, set]] = {f["id"]: {"": set()} for f in folders}
    subtree: Dict[str, Dict[str, set]] = {f["id"]: {"": set()} for f in folders}
    for i in items:
        for fid, rel in i["locs"]:
            if fid not in fids:
                continue
            direct[fid].setdefault(rel, set()).add(i["hash"])
            parts = rel.split("/") if rel else []
            for k in range(len(parts), -1, -1):
                subtree[fid].setdefault("/".join(parts[:k]), set()).add(i["hash"])
    tree = {fid: {rel: [len(direct[fid].get(rel, ())), len(s)] for rel, s in subtree[fid].items()} for fid in subtree}
    # 1.5.5: folder-name search. One folded "path" string per tree node (hundreds, not 11k), matched once per query.
    fpath = {f["id"]: f["path"].replace("\\", "/").rstrip("/") for f in folders}
    nodefold = {(fid, rel): _fold(fpath[fid] + ("/" + rel if rel else "")) for fid in subtree for rel in subtree[fid]}
    cols = [{"id": c["id"], "name": c["name"], "count": len(c["images"])} for c in storage.list_collections()]
    tagc: Dict[str, Dict[str, Any]] = {}
    for i in items:
        for tg in i["tags"]:
            tagc.setdefault(_fold(tg), {"tag": tg, "count": 0})["count"] += 1
    _cat["rev"] = _cat.get("rev", 0) + 1
    data = {"rev": _cat["rev"], "items": items, "by_hash": {i["hash"]: i for i in items}, "tree": tree, "nodefold": nodefold,
            "tags": sorted(tagc.values(), key=lambda x: (-x["count"], _fold(x["tag"]))),
            "collections": cols, "folders": folders, "n_unassigned": sum(1 for i in items if i["in_pool"] and not i["colids"])}
    with _cat_lock:
        _cat.update(key=key, data=data, fkey=None, flist=None, lru=[])
    return data


def _clean_filter(f) -> Dict[str, Any]:
    f = f if isinstance(f, dict) else {}
    node = f.get("node") if isinstance(f.get("node"), dict) else None
    return {"cols": sorted(str(c) for c in (f.get("cols") or []))[:200], "none": bool(f.get("none")),
            "tags": sorted({_fold(clean_tag(t)) for t in (f.get("tags") or []) if clean_tag(t)})[:50],
            "q": _fold(str(f.get("q") or "").strip())[:200],
            "atags": sorted({str(t) for t in (f.get("atags") or [])})[:50],
            "xtags": sorted({str(t) for t in (f.get("xtags") or [])})[:50],
            "jst": str(f.get("jst") or "") if str(f.get("jst") or "") in JST_KEYS else "",
            "ranges": [(str(r[0]), float(r[1]), float(r[2])) for r in (f.get("ranges") or []) if isinstance(r, (list, tuple)) and len(r) == 3][:20],
            "node": {"fid": str(node.get("fid") or ""), "rel": str(node.get("rel") or "")} if node and not f.get("recent") and not f.get("used") else None,
            "sub": f.get("sub", True) is not False, "recent": bool(f.get("recent")) and not f.get("used"), "used": bool(f.get("used")),
            "recent_pages": max(1, min(100, int(f.get("recent_pages") or 1)))}


def filtered(f, now: Optional[float] = None) -> Dict[str, Any]:
    """Apply a browser filter. Returns {items (ordered), recent_more}. Same rules the 1.4.3 client used."""
    cat = catalog()
    f = _clean_filter(f)
    jrev, jmap = _jobmap() if f.get("jst") else (0, None)
    from . import refusage as _ru
    fkey = (id(cat), json.dumps(f, sort_keys=True), int((now or time.time()) // 60) if f["recent"] else 0, jrev, _ru.rev() if f["used"] else 0)
    with _cat_lock:
        if _cat["fkey"] == fkey:
            return _cat["flist"]
        lru = _cat.get("lru") or []
        for k, v in lru:   # 1.5.1: a few recent filters (query + facets + autocomplete alternate on every keystroke)
            if k == fkey:
                return v
    cols, none, tags, q, node, sub = set(f["cols"]), f["none"], f["tags"], f["q"], f["node"], f["sub"]
    pre = node["rel"] + "/" if node and node["rel"] else ""
    atags = set(f["atags"])
    xtags = set(f.get("xtags") or [])
    agroups = {}   # 1.5.1: auto-tag chips of the same taxonomy group combine with OR, different groups with AND
    if atags:
        try:
            from . import taxonomy as _tg
            for t in atags:
                agroups.setdefault(_tg.group_of(t) or t, set()).add(t)
        except Exception:
            agroups = {t: {t} for t in atags}
    qx = set()
    bconds, bterms = [], []
    for rg in f.get("ranges") or []:
        bconds.append(rg)
    if q:
        try:
            from . import bodyshape, taxonomy as _tx
            bconds2, terms, rest = bodyshape.parse_query(q)
            if bconds2 or terms:
                bconds += bconds2
                bterms = [_tx.expand_loose(t) or {"__none__"} for t in terms]
                q = rest
        except Exception:
            pass
    if q:
        try:
            from . import taxonomy
            qx = taxonomy.expand(q)   # synonyms (EN/ES) + the whole subtree: "arena" -> hourglass, "curvy" -> pear…
        except Exception:
            qx = set()

    qnodes = set()
    if q:   # 1.5.5: images whose folder path (watched folder or any subfolder) contains the term
        qnodes = {k for k, fs in (cat.get("nodefold") or {}).items() if q in fs}

    def ok(i):
        if cols or none:
            if not (cols & i["colids"]) and not (none and i["in_pool"] and not i["colids"]):
                return False
        if node:
            hit = False
            for fid, rel in i["locs"]:
                if fid == node["fid"] and (rel == node["rel"] or (sub and (node["rel"] == "" or rel.startswith(pre)))):
                    hit = True
                    break
            if not hit:
                return False
        for t in tags:
            if t not in i["tagf"]:
                return False
        if agroups and not all(g & i["auto"] for g in agroups.values()):
            return False
        if xtags and xtags & i["auto"]:
            return False
        if bconds:
            from .bodyshape import matches
            if not i["body"] or not matches(i["body"], bconds):
                return False
        for tset in bterms:
            if not (tset & i["auto"]):
                return False
        return not q or q in i["fold"] or bool(qnodes and any(l in qnodes for l in i["locs"])) or any(q in t for t in i["tagf"]) or bool(qx and qx & i["auto"])
    out = [i for i in cat["items"] if ok(i)]
    more = False
    if f["recent"]:
        srt = sorted(out, key=lambda i: -(i["added"] or 0))
        pages = f["recent_pages"]
        since = (now or time.time()) - RECENT_DAYS * 86400 * pages
        capped = [i for i in srt if (i["added"] or 0) >= since][:RECENT_MAX * pages]
        if len(capped) < min(len(srt), RECENT_MIN):
            capped = srt[:min(len(srt), RECENT_MIN)]
        more = len(capped) < len(srt)
        out = capped
    if jmap is not None:   # 1.5.4 "Estado del etiquetado" filter
        if f["jst"] == "never":
            tagged = _auto_map()[1]
            out = [i for i in out if i["hash"] not in jmap and i["hash"] not in tagged]
        else:
            out = [i for i in out if jmap.get(i["hash"]) == f["jst"]]
    if f["used"]:   # 1.5.5 "Usadas como referencia": newest use first
        um = _ru.load()
        out = sorted((i for i in out if i["hash"] in um), key=lambda i: -um[i["hash"]].get("last", 0))
    res = {"items": out, "recent_more": more, "recent": f["recent"], "used": f["used"]}
    with _cat_lock:
        _cat.update(fkey=fkey, flist=res, lru=([(fkey, res)] + [x for x in (_cat.get("lru") or []) if x[0] != fkey and x[0][0] == fkey[0]])[:6])
    return res


def _light(i: Dict[str, Any]) -> Dict[str, Any]:
    return {"hash": i["hash"], "name": i["name"], "names": list(i["names"][:4]), "cols": sorted(i["colids"]), "pool": bool(i["in_pool"]),
            "folders": list(i["folders"]), "tags": list(i["tags"]), "added": round(i["added"] or 0, 1)}


def _groups(items: List[Dict[str, Any]], tz_min: int, now: float, ts=None) -> List[Dict[str, Any]]:
    """Recent view day groups over the whole (capped) list: today / yesterday / this week / one per older day, in the
    browser's time zone (tz_min = JS getTimezoneOffset())."""
    off = -int(tz_min or 0) * 60
    today = int((now + off) // 86400)
    out: List[Dict[str, Any]] = []
    for k, i in enumerate(items):
        t = (ts(i) if ts else i["added"]) or 0
        d = int((t + off) // 86400)
        key = "t" if d >= today else "y" if d == today - 1 else "w" if d >= today - 6 else str(d)
        if out and out[-1]["key"] == key:
            out[-1]["count"] += 1
        else:
            out.append({"key": key, "start": k, "count": 1, "ts": t})
    return out


def query(f, offset: int = 0, limit: int = 120, tz_min: int = 0) -> Dict[str, Any]:
    """One page of the filtered list: {total, offset, items: [light], recent_more, groups (recent only)}."""
    now = time.time()
    res = filtered(f, now)
    items = res["items"]
    offset = max(0, int(offset or 0))
    limit = max(0, min(PAGE_MAX, int(limit if limit is not None else 120)))
    jrev, jmap = _jobmap()
    page = [_light(i) for i in items[offset:offset + limit]]
    for x in page:
        st = jmap.get(x["hash"])
        if st:
            x["js"] = st
    out = {"total": len(items), "offset": offset, "items": page, "recent_more": res["recent_more"], "jrev": jrev}
    if res["recent"]:
        out["groups"] = _groups(items, tz_min, now)
    if res.get("used"):
        from . import refusage as _ru
        um = _ru.load()
        out["groups"] = _groups(items, tz_min, now, ts=lambda i: um.get(i["hash"], {}).get("last", 0))
        for x in page:
            u = um.get(x["hash"]) or {}
            x["uses"] = int(u.get("count", 0)); x["used_at"] = round(u.get("last", 0), 1)
    return out


def index_of(f, digest: str) -> int:
    """1.5.3: position of an image in a filtered result (-1 if absent), so the UI can scroll to it."""
    for k, i in enumerate(filtered(f)["items"]):
        if i["hash"] == digest:
            return k
    return -1


def locate(digest: str) -> Optional[Dict[str, Any]]:
    """1.5.3 "Localizar carpeta": watched-folder locations {fid, rel, root, root_name} (rel = sub-folder, "/"-separated)
    and collections of one image."""
    cat = catalog()
    img = cat["by_hash"].get(str(digest or ""))
    if not img:
        return None
    froot = {f["id"]: f["path"] for f in cat["folders"]}
    files = [p for p in [img["path"]] + list(img.get("files") or []) if p]
    locs = []
    for fid in img["folders"]:
        root = froot.get(fid, "")
        for p in files:
            try:
                rel = os.path.relpath(os.path.dirname(p), root)
            except ValueError:
                continue
            if root and not rel.startswith(".."):
                rel = "" if rel == "." else rel.replace(os.sep, "/").replace("\\", "/")
                locs.append({"fid": fid, "rel": rel, "root": root, "root_name": os.path.basename(root.rstrip("/\\")) or root})
                break
    cname = {c["id"]: c["name"] for c in cat["collections"]}
    return {"folders": locs, "collections": [{"id": c, "name": cname.get(c, c)} for c in img["colids"]], "in_pool": img["in_pool"]}


def range_hashes(f, start: int, end: int) -> List[str]:
    items = filtered(f)["items"]
    a, b = sorted((max(0, int(start)), max(0, int(end))))
    return [i["hash"] for i in items[a:min(b + 1, a + RANGE_MAX)]]


def resolve_selection(sel) -> List[str]:
    """{"hashes": [...]} or {"all": true, "f": filter, "except": [...]} -> hashes (the "all N matching" model)."""
    if not isinstance(sel, dict):
        return []
    if sel.get("all"):
        skip = set(sel.get("except") or [])
        return [i["hash"] for i in filtered(sel.get("f"))["items"] if i["hash"] not in skip]
    return [h for h in dict.fromkeys(str(h) for h in sel.get("hashes") or []) if _HASH_RE.match(h)]


def selection_info(hashes: Iterable[str], one_col: Optional[str] = None) -> Dict[str, Any]:
    """What the selection footer needs, without the client holding every selected item."""
    by = catalog()["by_hash"]
    n = deletable = folder_only = on_disk = in_one = 0
    cols, tags = set(), {}
    for h in hashes:
        i = by.get(h)
        if not i:
            continue
        n += 1
        if i["colids"] or i["in_pool"]:
            deletable += 1
            cols |= i["colids"]
        else:
            folder_only += 1
        if i["folders"]:
            on_disk += 1
        if one_col and one_col in i["colids"]:
            in_one += 1
        if len(tags) < 60:
            for t in i["tags"]:
                tags.setdefault(_fold(t), t)
    return {"n": n, "deletable": deletable, "cols": len(cols), "folder_only": folder_only, "on_disk": on_disk,
            "in_one": in_one, "tags": list(tags.values())}


def facets(f, limit: int = 400) -> Dict[str, int]:
    """Auto-tag counts over the current filter (ancestors included), for the facet panel."""
    c: Dict[str, int] = {}
    for i in filtered(f)["items"]:
        for t in i["auto"]:
            c[t] = c.get(t, 0) + 1
    # 1.5.1: a group's own selections combine with OR, so its siblings are counted without that group's filter
    ff = f if isinstance(f, dict) else {}
    sel = [str(t) for t in (ff.get("atags") or [])]
    if sel:
        try:
            from . import taxonomy as _tg
            groups = {}
            for t in sel:
                groups.setdefault(_tg.group_of(t) or t, []).append(t)
            for g, ts in groups.items():
                sub = dict(ff, atags=[t for t in sel if t not in ts])
                members = set(_tg.descendants(g)) if _tg.node(g) else set(ts)
                cg: Dict[str, int] = {}
                for i in filtered(sub)["items"]:
                    for t in i["auto"] & members:
                        cg[t] = cg.get(t, 0) + 1
                for t in members:
                    c.pop(t, None)
                c.update(cg)
        except Exception:
            pass
    return dict(sorted(c.items(), key=lambda kv: -kv[1])[:limit])


def body_stats(f) -> Dict[str, Dict[str, float]]:
    """min / max / count per numeric body field over the current filter (range sliders in the facet panel)."""
    st: Dict[str, Dict[str, float]] = {}
    for i in filtered(f)["items"]:
        for k, v in (i["body"] or {}).items():
            if isinstance(v, (int, float)):
                d = st.setdefault(k, {"min": v, "max": v, "n": 0})
                d["min"], d["max"], d["n"] = min(d["min"], v), max(d["max"], v), d["n"] + 1
    return st


def meta() -> Dict[str, Any]:
    cat = catalog()
    return {"rev": cat["rev"], "total": len(cat["items"]), "collections": cat["collections"], "tags": cat["tags"], "folders": cat["folders"],
            "tree": cat["tree"], "n_unassigned": cat["n_unassigned"]}


def invalidate() -> None:
    with _cat_lock:
        _cat.update(key=None, data=None, fkey=None, flist=None, lru=[])


def entry_for(digest: str) -> Optional[Dict[str, Any]]:
    return catalog()["by_hash"].get(str(digest or ""))


def suggest(text: str, f=None, lang: str = "es", limit: int = 10) -> List[Dict[str, Any]]:
    """1.5.1 search-box autocomplete: taxonomy tags (labels + synonyms, ES/EN, accent-insensitive, prefix or in-word)
    and manual tags, each with its image count over the current filter (minus the text query). Counted ones first."""
    from . import taxonomy as tx
    q = tx.fold(text or "").strip()
    if len(q) < 2:
        return []
    base = dict(f or {}, q="")
    counts = facets(base, limit=100000)
    out = []
    for nid, n in tx.load()["nodes"].items():
        if n.get("kind") != "tag" or nid in ("appears_minor", "needs_review"):   # review flags are not suggested
            continue
        words = [n.get("es", ""), n.get("en", "")] + list((n.get("syn") or {}).get("es", [])) + list((n.get("syn") or {}).get("en", []))
        best = None
        for wi, w in enumerate(words):
            fw = tx.fold(w)
            if fw.startswith(q):
                r = 0
            elif any(p.startswith(q) for p in fw.split()):
                r = 1
            elif q in fw:
                r = 2
            else:
                continue
            r += 0.5 if wi > 1 else 0   # 1.5.2: a label match ranks above a synonym match
            if best is None or r < best[0]:
                best = (r, w)
        if best is None:
            continue
        path, p = [], n.get("parent")
        while p:
            pn = tx.load()["nodes"].get(p)
            if not pn:
                break
            path.insert(0, tx.label(p, lang))   # 1.5.2: full path, any depth (Pose › Brazos › …)
            p = pn.get("parent")
        lab = tx.label(nid, lang)
        out.append({"kind": "at", "id": nid, "label": lab, "match": best[1] if tx.fold(best[1]) != tx.fold(lab) else "",
                    "path": " › ".join(path + [lab]), "n": counts.get(nid, 0), "r": best[0]})
    mc: Dict[str, int] = {}
    for i in filtered(base)["items"]:
        for t in i["tags"]:
            if q in tx.fold(t):
                mc[t] = mc.get(t, 0) + 1
    for t, c in mc.items():
        out.append({"kind": "tag", "id": t, "label": t, "match": "", "path": "#" + t, "n": c, "r": 0 if tx.fold(t).startswith(q) else 1})
    # 1.5.5: folders whose name matches (subfolders included); picking one = clicking it in the tree
    cat = catalog()
    names = {f["id"]: f["name"] for f in cat["folders"]}
    fol = []
    for (fid, rel), _fs in cat.get("nodefold", {}).items():
        last = rel.rsplit("/", 1)[-1] if rel else names.get(fid, "")
        fl = tx.fold(last)
        if q not in fl:
            continue
        cnt = (cat["tree"].get(fid, {}).get(rel) or [0, 0])[1]
        fol.append({"kind": "folder", "id": fid + "|" + rel, "fid": fid, "rel": rel, "label": last,
                    "match": "", "path": "/".join([names.get(fid, "")] + ([rel] if rel else [])), "n": cnt,
                    "r": 0 if fl.startswith(q) else 1})
    fol.sort(key=lambda s: (s["r"], -s["n"], s["path"]))
    out.sort(key=lambda s: (s["n"] == 0, s["r"], -s["n"], s["label"]))
    return (fol[:4] + out)[:limit]
