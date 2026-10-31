"""1.11.0 duplicates: exact and near-duplicate photos, one logic for the Media Library and the Galería (DUPES_API.md).

* exact   = the same content hash (the library's item key) present as several files on disk (watched folders), or
            several library entries whose pixels hash the same (pHash distance 0 and identical size).
* near    = perceptual hash (64-bit DCT pHash) within `threshold` bits (default 6, adjustable 0..16), confirmed with a
            64-bit dHash within threshold+4 so crops / different photos with a similar layout don't group.
The similarity index (SIMILARITY_API.md) only has pose and face vectors, which match *different* photos of the same
person/pose, so it is not used to decide duplicates.
Hashes are computed in a background thread, incrementally (only new hashes), cached in COLLECTIONS_DIR/dupes.json
({version, entries:{hash:{p,d,w,h,fmt}}}); groups are cached per (catalog rev, threshold).
Resolving never deletes by itself: dup_resolve returns the tags to move (dup_transfer, after the delete) and
the hashes to drop; the UIs then run the existing delete flow (forget_plan -> forget / delete_all, 1.9.7). The only
exception is extra files of one same-content item (exact, same hash): those go to the Recycle Bin through the same
forget.recycle() + folder rescan the delete flow uses, and only for files in user watched folders."""
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

from . import storage
from .actions import action, ActionError

DEFAULT_THRESHOLD = 6
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".jfif", ".heic", ".avif"}
_lock = threading.RLock()
_state: Dict[str, Any] = {"running": False, "done": 0, "total": 0, "errors": 0, "started": 0.0, "finished": 0.0, "rev": 0}
_db: Dict[str, Any] = {"loaded": False, "entries": {}, "dirty": 0}
_groups_cache: Dict[str, Any] = {"key": None, "data": None}


def _path() -> str:
    return os.path.join(storage.COLLECTIONS_DIR, "dupes.json")


def _load() -> Dict[str, Dict[str, Any]]:
    with _lock:
        if not _db["loaded"]:
            try:
                import json
                with open(_path(), "r", encoding="utf-8") as r:
                    d = json.load(r)
                _db["entries"] = {k: v for k, v in (d.get("entries") or {}).items() if isinstance(v, dict)}
            except Exception:
                _db["entries"] = {}
            _db["loaded"] = True
        return _db["entries"]


def _save() -> None:
    with _lock:
        os.makedirs(storage.COLLECTIONS_DIR, exist_ok=True)
        storage._atomic_write_json(_path(), {"version": 1, "entries": _db["entries"]})
        _db["dirty"] = 0


# ------------------------------------------------------------------------------------------------ hashing
_DCT = None


def _dct_mat():
    global _DCT
    if _DCT is None:
        import numpy as np
        n = 32
        k = np.arange(n)[:, None]; x = np.arange(n)[None, :]
        m = np.cos(np.pi * (2 * x + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
        m[0] /= np.sqrt(2.0)
        _DCT = m
    return _DCT


FLAT_STD = 6.0   # below this grey std an image is too flat for perceptual hashing


def hashes_of(path: str) -> Dict[str, Any]:
    """{p, d (hex 64-bit), w, h, fmt} of an image file."""
    import numpy as np
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        w, h = im.size
        fmt = (im.format or os.path.splitext(path)[1].lstrip(".")).upper()
        try:
            im.draft("L", (128, 128))
        except Exception:
            pass
        try:
            im.seek(0)
        except Exception:
            pass
        g = ImageOps.exif_transpose(im) if hasattr(ImageOps, "exif_transpose") else im
        g = g.convert("L")
        a = np.asarray(g.resize((32, 32), Image.LANCZOS), dtype=np.float64)
        b = np.asarray(g.resize((9, 8), Image.LANCZOS), dtype=np.float64)
    m = _dct_mat()
    c = (m @ a @ m.T)[:8, :8].flatten()
    med = np.median(c[1:])
    p = int("".join("1" if v > med else "0" for v in c), 2)
    d = int("".join("1" if v else "0" for v in (b[:, 1:] > b[:, :-1]).flatten()), 2)
    # "s": contrast (grey std at 32x32). Flat / near-solid images hash to ~0 and would all "match" each other,
    # so groups() leaves them out of near-duplicate matching (identical files are still found by content hash).
    return {"p": f"{p:016x}", "d": f"{d:016x}", "w": int(w), "h": int(h), "fmt": fmt, "s": round(float(a.std()), 2)}


VID_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def video_meta(path: str) -> Dict[str, Any]:
    """1.11.1 videos: exact duplicates only (never perceptual). Cheap ffprobe metadata for the row; empty if unavailable."""
    import json as _j, shutil as _sh, subprocess as _sp
    out: Dict[str, Any] = {"v": 1, "w": 0, "h": 0, "fmt": os.path.splitext(path)[1].lstrip(".").upper(), "dur": None, "codec": "", "fps": None}
    exe = _sh.which("ffprobe")
    if not exe:
        return out
    try:
        r = _sp.run([exe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name,avg_frame_rate:format=duration",
                     "-of", "json", path], capture_output=True, timeout=15, **({"creationflags": 0x08000000} if os.name == "nt" else {}))
        d = _j.loads(r.stdout or b"{}"); st = (d.get("streams") or [{}])[0]
        out.update(w=int(st.get("width") or 0), h=int(st.get("height") or 0), codec=str(st.get("codec_name") or ""))
        n, _, m = str(st.get("avg_frame_rate") or "").partition("/")
        if n and m and float(m):
            out["fps"] = round(float(n) / float(m), 2)
        if (d.get("format") or {}).get("duration"):
            out["dur"] = round(float(d["format"]["duration"]), 2)
    except Exception:
        pass
    return out


def _full_sha(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _candidates() -> List[Dict[str, Any]]:
    from . import imagelib
    out = []
    for i in imagelib.catalog()["items"]:
        # virtual copies / clips are never duplicates; videos only for exact (same content) groups
        if i.get("virtual") or i.get("kind") not in (None, "image", "video") or i.get("missing"):
            continue
        p = i.get("path") or ""
        if os.path.splitext(p)[1].lower() in (IMG_EXT | VID_EXT):
            out.append(i)
    return out


def _worker(full: bool) -> None:
    try:
        ents = _load()
        if full:
            with _lock:
                ents.clear()
        todo = [i for i in _candidates() if i["hash"] not in ents or ("s" not in ents[i["hash"]] and not ents[i["hash"]].get("v"))]   # 1.11.0 cache gained "s"
        with _lock:
            _state.update(total=len(todo), done=0, errors=0)
        for n, i in enumerate(todo):
            r = None
            for p in dict.fromkeys([i.get("path")] + list(i.get("files") or [])):
                try:
                    if p and os.path.isfile(p):
                        r = video_meta(p) if os.path.splitext(p)[1].lower() in VID_EXT else hashes_of(p); break
                except Exception:
                    continue
            with _lock:
                if r:
                    ents[i["hash"]] = r; _db["dirty"] += 1
                else:
                    _state["errors"] += 1
                _state["done"] = n + 1
                if _db["dirty"] >= 200:
                    _save()
        with _lock:
            if _db["dirty"]:
                _save()
    except Exception as e:
        print(f"[Reference Library] duplicate scan failed: {e!r}")
    finally:
        with _lock:
            _state.update(running=False, finished=time.time(), rev=_state["rev"] + 1)
            _groups_cache["key"] = None


def scan(full: bool = False) -> Dict[str, Any]:
    with _lock:
        if not _state["running"]:
            _state.update(running=True, started=time.time(), done=0, total=0)
            threading.Thread(target=_worker, args=(bool(full),), name="reflib-dupes", daemon=True).start()
    return status()


def status() -> Dict[str, Any]:
    ents = _load()
    with _lock:
        s = dict(_state)
    s["hashed"] = len(ents)
    return s


def wait(timeout: float = 60.0) -> Dict[str, Any]:
    t = time.time() + timeout
    while _state["running"] and time.time() < t:
        time.sleep(0.05)
    return status()


# ------------------------------------------------------------------------------------------------ grouping
_POP = None


def _near_pairs(keys: List[str], ph, dh, thr: int):
    """Pairs (i, j) with pHash distance <= thr and dHash distance <= thr + 4 (numpy, chunked)."""
    import numpy as np
    global _POP
    if _POP is None:
        _POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    n = len(keys)
    pb = ph.view(np.uint8).reshape(n, 8); db = dh.view(np.uint8).reshape(n, 8)
    out = []
    step = 512
    for s in range(0, n, step):
        e = min(n, s + step)
        x = _POP[np.bitwise_xor(pb[s:e, None, :], pb[None, :, :])].sum(-1, dtype=np.int16)
        ii, jj = np.nonzero(x <= thr)
        m = (ii + s) < jj
        ii, jj = ii[m] + s, jj[m]
        if len(ii):
            dd = _POP[np.bitwise_xor(db[ii], db[jj])].sum(-1, dtype=np.int16)
            ok = dd <= thr + 4
            out.extend(zip(ii[ok].tolist(), jj[ok].tolist(), x[ii[ok] - s, jj[ok]].tolist()))
    return out


def _row(i: Dict[str, Any], e: Dict[str, Any], path: Optional[str] = None, folders=None) -> Dict[str, Any]:
    p = path or i.get("path") or ""
    try:
        st = os.stat(p); size, mt = st.st_size, st.st_mtime
    except OSError:
        size, mt = 0, float(i.get("mtime") or 0)
    w, h = int(e.get("w") or 0), int(e.get("h") or 0)
    fol = None
    for fid in i.get("folders") or ():
        f = (folders or {}).get(fid)
        if f and p.startswith(f["path"]):
            fol = f["path"]
    return {"hash": i["hash"], "name": os.path.basename(p) or i.get("name"), "path": p, "dir": os.path.dirname(p), "folder": fol,
            "w": w, "h": h, "mp": round(w * h / 1e6, 2), "bytes": size, "fmt": e.get("fmt") or os.path.splitext(p)[1].lstrip(".").upper(),
            "date": mt, "origin": i.get("origin") or "real", "tags": len(i.get("tags") or ()),
            "in_library": bool(i.get("colids") or i.get("in_pool")), "on_disk": bool(i.get("folders")),
            "video": bool(e.get("v")), "dur": e.get("dur"), "codec": e.get("codec") or "", "fps": e.get("fps")}


def _rank(r):
    return (r["w"] * r["h"], r["bytes"], -r["date"])


def groups(threshold: Optional[int] = None) -> Dict[str, Any]:
    """{ok, threshold, groups:[{id, kind:'exact'|'near', dist, rows:[ROW], keep:index, biggest, smallest, waste}], hashed, total}"""
    import numpy as np
    from . import imagelib
    thr = DEFAULT_THRESHOLD if threshold is None else max(0, min(16, int(threshold)))
    cat = imagelib.catalog()
    ents = _load()
    key = (id(cat), cat.get("rev"), len(ents), _state["rev"], thr)
    with _lock:
        if _groups_cache["key"] == key:
            return _groups_cache["data"]
    by = cat["by_hash"]
    folders = {f["id"]: f for f in imagelib.list_folders()}
    managed = {fid for fid, f in folders.items() if f.get("managed")}
    fdata = imagelib.load_folders()
    files_of: Dict[str, List[str]] = {}
    for p, v in fdata["files"].items():
        if v["folder"] not in managed:
            files_of.setdefault(v["hash"], []).append(p)
    out = []
    # exact: one content hash, several files on disk
    for h, ps in files_of.items():
        i = by.get(h)
        if i is None or len(ps) < 2 or h not in ents:
            continue
        if ents[h].get("v"):
            # the library hash of big videos is sampled: confirm byte-for-byte with a full sha256 (cached per path/size/mtime)
            fs = ents[h].setdefault("fs", {}); by_sha: Dict[str, List[str]] = {}
            for p in ps:
                try:
                    st = os.stat(p); sig = [st.st_size, int(st.st_mtime)]
                    if (fs.get(p) or [None])[:2] != sig:
                        fs[p] = sig + [_full_sha(p)]; _db["dirty"] += 1
                    by_sha.setdefault(fs[p][2], []).append(p)
                except OSError:
                    continue
            for sps in by_sha.values():
                if len(sps) > 1:
                    out.append({"kind": "exact", "dist": 0, "video": True, "rows": [_row(i, ents[h], p, folders) for p in sorted(sps)]})
            continue
        rows = [_row(i, ents[h], p, folders) for p in sorted(ps)]
        out.append({"kind": "exact", "dist": 0, "rows": rows})
    # near: pHash
    keys = [i["hash"] for i in _candidates() if i["hash"] in ents and "p" in ents[i["hash"]] and float(ents[i["hash"]].get("s", 99)) >= FLAT_STD]
    if len(keys) > 1:
        ph = np.array([int(ents[k]["p"], 16) for k in keys], dtype=np.uint64)
        dh = np.array([int(ents[k]["d"], 16) for k in keys], dtype=np.uint64)
        # Star clustering (no chaining): every member is within the threshold of the group's seed, and seeds are
        # taken largest-first, so the seed is the suggested keeper. Union-find would chain A~B~C into huge groups.
        adj: Dict[int, Dict[int, int]] = {}
        for a, b, d in _near_pairs(keys, ph, dh, thr):
            adj.setdefault(a, {})[b] = d; adj.setdefault(b, {})[a] = d
        if adj:
            rowc = {m: _row(by[keys[m]], ents[keys[m]], None, folders) for m in adj}
            used = set()
            for c in sorted(adj, key=lambda m: _rank(rowc[m]), reverse=True):
                if c in used:
                    continue
                ms = [c] + sorted((m for m in adj[c] if m not in used), key=lambda m: adj[c][m])
                if len(ms) < 2:
                    continue
                used.update(ms)
                rows = [rowc[m] for m in ms]
                dmax = max(adj[c][m] for m in ms[1:])
                # 'exact' only for the same content hash (handled above); equal pHash + size is still 'near'
                out.append({"kind": "near", "dist": int(dmax), "rows": rows})
    for g in out:
        rs = g["rows"]
        order = sorted(range(len(rs)), key=lambda k: _rank(rs[k]), reverse=True)
        g["keep"] = order[0]
        g["biggest"] = order[0]; g["smallest"] = order[-1]
        g["waste"] = sum(r["bytes"] for k, r in enumerate(rs) if k != order[0])
        g["same_item"] = len({r["hash"] for r in rs}) == 1
        g["id"] = "|".join(sorted(f'{r["hash"][:12]}:{r["path"]}' for r in rs))[:200]
    out.sort(key=lambda g: (-g["waste"], g["id"]))
    data = {"ok": True, "threshold": thr, "groups": out, "hashed": len(ents), "total": len(_candidates()),
            "waste": sum(g["waste"] for g in out)}
    with _lock:
        _groups_cache.update(key=key, data=data)
        if _db["dirty"]:
            _save()
    return data


# ------------------------------------------------------------------------------------------------ resolve
def resolve(keep: str, drop: Iterable[str], transfer: bool = True, copies: Iterable[str] = ()) -> Dict[str, Any]:
    """Plan for keeping one copy. Never touches tags: returns {drop:[hashes for the delete flow], tags:[to move]};
    the UI calls dup_transfer only after its delete succeeded, so cancelling the dialog changes nothing.
    Extra same-content `copies` (file paths) of `keep` (watched-folder files only, one always stays) are recycled
    here: the caller confirms before calling."""
    from . import imagelib, forget as _fg
    by = imagelib.catalog()["by_hash"]
    if keep not in by:
        raise ActionError("dup_not_found", hash=str(keep))
    drop = [h for h in dict.fromkeys(str(x) for x in drop or ()) if h in by and h != keep]
    tags = sorted({t for h in drop for t in by[h].get("tags") or ()} - set(by[keep].get("tags") or ())) if transfer else []
    recycled, errs = 0, {}
    copies = [p for p in dict.fromkeys(str(x) for x in copies or ()) if p]
    if copies:
        fdata = imagelib.load_folders()
        managed = {f["id"] for f in fdata["folders"] if f.get("managed")}
        mine = [p for p, v in fdata["files"].items() if v["hash"] == keep and v["folder"] not in managed]
        ok = [p for p in copies if p in mine]
        if len(ok) >= len(mine):
            raise ActionError("dup_keep_one")
        errs = _fg.recycle(ok)
        recycled = len(ok) - len(errs)
        fids = {fdata["files"][p]["folder"] for p in ok}
        imagelib.rescan(sorted(fids))
    with _lock:
        _groups_cache["key"] = None
    return {"ok": True, "keep": keep, "drop": drop, "tags": tags, "recycled": recycled, "recycle_errors": sorted(errs)}


def transfer(keep: str, tags: Iterable[str]) -> Dict[str, Any]:
    """Add `tags` (favorites / personas are tags) to `keep`; called after the delete of the other copies succeeded."""
    from . import imagelib
    by = imagelib.catalog()["by_hash"]
    if keep not in by:
        raise ActionError("dup_not_found", hash=str(keep))
    tags = sorted({str(t) for t in tags or () if t} - set(by[keep].get("tags") or ()))
    if tags:
        imagelib.set_tags([keep], add=tags)
    return {"ok": True, "keep": keep, "tags_moved": len(tags)}


# ------------------------------------------------------------------------------------------------ actions
@action("dup_scan", doc="Start the background duplicate hashing {full?} (incremental)")
def a_scan(req, ctx):
    return {"ok": True, "dupes": scan(bool(req.get("full")))}


@action("dup_status", fast=True, doc="Duplicate hashing progress")
def a_status(req, ctx):
    return {"ok": True, "dupes": status()}


@action("dup_groups", doc="Duplicate groups {threshold?, offset, limit, kind?}")
def a_groups(req, ctx):
    d = groups(req.get("threshold"))
    gs = d["groups"]
    if req.get("kind") in ("exact", "near"):
        gs = [g for g in gs if g["kind"] == req["kind"]]
    off, lim = max(0, int(req.get("offset") or 0)), max(1, min(500, int(req.get("limit") or 50)))
    return dict(d, groups=gs[off:off + lim], count=len(gs), status=status())


@action("dup_resolve", doc="Keep one copy {keep, drop[], transfer=true, copies[]} -> {drop, tags} for the delete flow")
def a_resolve(req, ctx):
    # `copies`, not `paths`: plugin.py strips client `paths` from every action (1.9.5)
    return resolve(str(req.get("keep") or ""), req.get("drop") or [], req.get("transfer", True) is not False, req.get("copies") or [])


@action("dup_transfer", doc="After a successful delete: move {keep, tags[]} to the kept copy")
def a_transfer(req, ctx):
    return transfer(str(req.get("keep") or ""), req.get("tags") or [])
