"""1.7.1: remove library entries that the library does not own ("Quitar de la librería").

A watched-folder file (image, video, audio) or an entry whose file is gone can be removed from the library: its manual
and automatic tags, thumbnail, collection copies, masks and virtual copies go, and the folder remembers it in a
per-folder exclusion list so a rescan does not bring it back. The file on disk is NEVER deleted or moved, unless the
user ticks "also delete the file from disk": then it goes to the system Recycle Bin / Trash (never a permanent delete;
a failed recycle keeps the file and is reported). Undo (15 min, like the other undos) restores the library entry;
"Mostrar excluidos / Restaurar" on a folder brings excluded items back at any time.

Files the library owns (collection copies, pool, masks, virtual copies) keep their own delete paths.
1.7.3: a Video Library video ("Librería de vídeos") can be removed here too: its Video Library entry is soft-deleted
(undo brings it back); when the undo window ends its file goes to the Recycle Bin (videostore.purge_trash)."""
from __future__ import annotations
import glob, json, os, shutil, sys, time, uuid
from typing import Any, Dict, Iterable, List, Optional
from . import storage

EXCL_MAX = 200000


# ------------------------------------------------------------------------------------------------ exclusions
def excluded(data: Dict[str, Any], fid: str) -> Dict[str, Dict[str, Any]]:
    f = next((x for x in data["folders"] if x["id"] == fid), None)
    return dict((f or {}).get("exclude") or {})


def excluded_list(fid: str) -> List[Dict[str, Any]]:
    from . import imagelib
    data = imagelib.load_folders()
    ex = excluded(data, fid)
    root = next((f["path"] for f in data["folders"] if f["id"] == fid), "")
    present = {v["hash"]: p for p, v in data["files"].items() if v["folder"] == fid}
    out = []
    for h, e in ex.items():
        path = present.get(h) or (os.path.join(root, e.get("rel") or "", e["name"]) if e.get("name") else "")
        out.append({"hash": h, "name": e.get("name") or "", "rel": e.get("rel") or "", "at": e.get("at") or 0,
                    "path": path, "on_disk": bool(path) and os.path.isfile(path), "recycled": bool(e.get("recycled"))})
    return sorted(out, key=lambda x: -x["at"])


def _set_exclusions(add: Dict[str, Dict[str, Dict[str, Any]]] = None, remove: Dict[str, Iterable[str]] = None) -> int:
    """add {fid: {hash: meta}}, remove {fid: [hash] | None (all)} -> number of changes."""
    from . import imagelib
    n = 0
    with storage._lock:
        data = imagelib.load_folders()
        for f in data["folders"]:
            ex = dict(f.get("exclude") or {})
            for h, meta in ((add or {}).get(f["id"]) or {}).items():
                if h not in ex:
                    ex[h] = meta; n += 1
            if remove and f["id"] in remove:
                gone = list(ex) if remove[f["id"]] is None else [h for h in remove[f["id"]] if h in ex]
                for h in gone:
                    ex.pop(h, None); n += 1
            if len(ex) > EXCL_MAX:
                ex = dict(list(ex.items())[-EXCL_MAX:])
            if ex:
                f["exclude"] = ex
            else:
                f.pop("exclude", None)
        if n:
            imagelib._save_folders(data)
            imagelib.invalidate()
    return n


def restore(fid: str, hashes: Optional[Iterable[str]] = None) -> int:
    """'Restaurar': excluded items of a folder come back (None = all)."""
    return _set_exclusions(remove={fid: None if hashes is None else [str(h) for h in hashes]})


# ------------------------------------------------------------------------------------------------ recycle bin
def _recycle_windows(paths: List[str]) -> Dict[str, str]:
    """Shell API SHFileOperationW(FO_DELETE, FOF_ALLOWUNDO): to the Recycle Bin, never a permanent delete."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    FOF_WANTNUKEWARNING = 0x4000   # safety net: Windows asks before ever destroying a file instead of recycling it
    errs = {}
    for p in paths:   # one at a time: a failure names its file, the others still go
        why = _no_recycle_bin(p)
        if why:
            errs[p] = why
            continue
        buf = ctypes.create_unicode_buffer(os.path.abspath(p) + "\0")   # + the buffer's own NUL = double-NUL list
        op = SHFILEOPSTRUCTW(None, FO_DELETE, ctypes.cast(buf, wintypes.LPCWSTR), None,
                             FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING, False, None, None)
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc != 0 or op.fAnyOperationsAborted or os.path.exists(p):
            errs[p] = f"shell error {rc:#x}" if rc else "not moved to the Recycle Bin"
    return errs


def _no_recycle_bin(p: str) -> str:
    """Windows deletes files permanently on drives without a Recycle Bin (network shares, most USB sticks): refuse those."""
    import ctypes, ntpath   # Windows path rules (== os.path on Windows)
    ap = ntpath.abspath(p) if ntpath.isabs(p) else p
    if ap.startswith("\\\\"):
        return "network path: no Recycle Bin, file kept"
    root = ntpath.splitdrive(ap)[0] + "\\"
    DRIVE_FIXED = 3
    if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) != DRIVE_FIXED:
        return "this drive has no Recycle Bin (removable or network): file kept"
    return ""


def _recycle_xdg(paths: List[str]) -> Dict[str, str]:
    """freedesktop.org Trash (files/ + info/*.trashinfo): what file managers restore from. Same filesystem only."""
    from urllib.parse import quote
    base = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "Trash")
    errs = {}
    for p in paths:
        try:
            os.makedirs(os.path.join(base, "files"), exist_ok=True); os.makedirs(os.path.join(base, "info"), exist_ok=True)
            name = os.path.basename(p); stem, ext = os.path.splitext(name); k = 1
            while os.path.exists(os.path.join(base, "files", name)) or os.path.exists(os.path.join(base, "info", name + ".trashinfo")):
                k += 1; name = f"{stem}.{k}{ext}"
            with open(os.path.join(base, "info", name + ".trashinfo"), "w", encoding="utf-8") as w:
                w.write(f"[Trash Info]\nPath={quote(os.path.abspath(p))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
            if os.stat(p).st_dev != os.stat(base).st_dev:
                os.remove(os.path.join(base, "info", name + ".trashinfo"))
                raise OSError("the file is on another drive than the Trash")
            try:
                os.rename(p, os.path.join(base, "files", name))
            except OSError:
                os.remove(os.path.join(base, "info", name + ".trashinfo"))
                raise
        except Exception as e:
            errs[p] = str(e)
    return errs


RECYCLER = None   # tests can plug a fake


def recycle(paths: List[str]) -> Dict[str, str]:
    """-> {path: error} for the files that were NOT recycled (they stay where they are)."""
    paths = [p for p in dict.fromkeys(paths) if p]
    missing = {p: "not found" for p in paths if not os.path.isfile(p)}
    todo = [p for p in paths if p not in missing]
    if not todo:
        return missing
    try:
        if RECYCLER:
            errs = RECYCLER(todo)
        else:
            if sys.platform == "win32":
                errs = _recycle_windows(todo)
            else:
              try:
                from send2trash import send2trash   # optional
                errs = {}
                for p in todo:
                    try:
                        send2trash(p)
                    except Exception as e:
                        errs[p] = str(e)
              except ImportError:
                errs = _recycle_xdg(todo)
    except Exception as e:
        errs = {p: str(e) for p in todo}
    errs = {p: e for p, e in errs.items() if os.path.exists(p)}   # only what really stayed
    return dict(missing, **errs)


# ------------------------------------------------------------------------------------------------ plan / forget / undo
def _item_files(i) -> List[str]:
    return [p for p in dict.fromkeys([i.get("path")] + list(i.get("files") or [])) if p]


def is_missing(i) -> bool:
    if i.get("virtual") or i.get("kind") == "mask":
        return False
    return not any(os.path.isfile(p) for p in _item_files(i))


def _disk_files(i, fdata) -> List[str]:
    """Files of an item that "also delete from disk" may send to the Recycle Bin: existing files in watched folders
    the user added (never the library's own copies, never a folder the plugin manages such as saved audio)."""
    managed = {f["id"] for f in fdata["folders"] if f.get("managed")}
    out = []
    for p in i.get("files") or ():
        v = fdata["files"].get(p)
        if v and v["folder"] not in managed and os.path.isfile(p):
            out.append(p)
    return out


def _owned_only(i) -> bool:
    """A managed copy the library owns (collection / pool) and nothing else: the existing delete path."""
    return not forgettable(i) and not i.get("virtual") and i.get("kind") != "mask" and bool(i["colids"] or i["in_pool"])


def forgettable(i) -> bool:
    """Not owned by the library: in a watched folder, or its file is gone (virtual copies have their own delete)."""
    if i.get("virtual"):
        return False
    return bool(i.get("folders")) or bool(i.get("missing")) or bool(_vlib_ids(i))


def _vlib_ids(i) -> List[str]:
    if i.get("virtual") or i.get("kind") == "mask":
        return []
    return [v for v in dict.fromkeys(list(i.get("vlibs") or []) + [i.get("vlib")]) if v]


def plan(hashes: Iterable[str]) -> Dict[str, Any]:
    """What "Quitar de la librería" would remove (for the confirmation)."""
    from . import imagelib, masks as _mk, virtuals as _vc
    cat = imagelib.catalog()
    by = cat["by_hash"]
    folders = {f["id"]: f for f in imagelib.list_folders()}
    items = [by[h] for h in dict.fromkeys(str(x) for x in hashes or []) if h in by]
    fi = [i for i in items if forgettable(i)]
    hs = {i["hash"] for i in fi}
    copies = [c for c in _vc.entries() if (c.get("orig") or {}).get("hash") in hs]
    nmask = sum(len(_mk.for_video(h)) + len(_mk.by_file_hash(h)) for h in hs)
    fdata = imagelib.load_folders()
    disk = [p for i in fi for p in _disk_files(i, fdata)]   # the "also delete from disk" candidates
    owned_only = [i for i in items if _owned_only(i)]
    offline = {fid for i in fi if i.get("missing") for fid in i.get("folders") or () if folders.get(fid, {}).get("missing")}
    return {"n": len(fi), "skipped": len(items) - len(fi) - len(owned_only), "owned_only": len(owned_only), "tagged": sum(1 for i in fi if i["tags"] or i.get("auto")),
            "cols": len({c for i in fi for c in i["colids"]}), "copies_in_cols": sum(1 for i in fi if i["colids"] or i["in_pool"]),
            "masks": nmask, "virtuals": len(copies), "missing": sum(1 for i in fi if i.get("missing")),
            "vlib": sum(1 for i in fi if _vlib_ids(i)), "vlib_only": sum(1 for i in fi if _vlib_ids(i) and not i.get("folders")), "on_disk": len(disk), "disk_files": disk[:500],
            "offline_folders": [folders[f]["path"] for f in offline if f in folders],
            "folders": sorted({folders[f]["path"] for i in fi for f in i.get("folders") or () if f in folders})[:20]}


def forget(hashes: Iterable[str], delete_files: bool = False) -> Dict[str, Any]:
    from . import imagelib, masks as _mk, virtuals as _vc
    cat = imagelib.catalog()
    by = cat["by_hash"]
    fdata = imagelib.load_folders()
    fpaths = {f["id"]: f["path"] for f in fdata["folders"]}
    sel = [by[h] for h in dict.fromkeys(str(x) for x in hashes or []) if h in by]
    items = [i for i in sel if forgettable(i)]
    owned_extra = [i["hash"] for i in sel if _owned_only(i)]   # managed copies in the same selection: deleted as before
    if not items:
        return {"ok": False, "n": 0}
    hs = [i["hash"] for i in items]
    rec: Dict[str, Any] = {"kind": "forget", "at": time.time(), "hashes": hs, "excl": {}, "tags": {}, "auto": {}}
    with storage._lock:
        # 1) the folders remember them (a rescan keeps them hidden)
        now = time.time()
        for i in items:
            for fid, rel in i.get("locs") or ():
                if fid in fpaths:
                    p = next((q for q in i.get("files") or () if imagelib._rel_dir(fpaths[fid], q) == rel), None) or i["path"]
                    rec["excl"].setdefault(fid, {})[i["hash"]] = {"name": os.path.basename(p), "rel": rel, "at": now}
        # optional: the files themselves -> Recycle Bin / Trash (never a permanent delete); a failure keeps the file
        rec["recycled"], rec["recycle_errors"] = [], {}
        if delete_files:
            disk = [p for i in items for p in _disk_files(i, fdata)]
            errs = recycle(disk)
            rec["recycled"] = [p for p in disk if p not in errs]
            rec["recycle_errors"] = errs
            gone = {os.path.normcase(os.path.normpath(g)) for g in rec["recycled"]}
            for fid, ex in rec["excl"].items():
                for h, meta in ex.items():
                    if os.path.normcase(os.path.normpath(os.path.join(fpaths[fid], meta["rel"], meta["name"]))) in gone:
                        meta["recycled"] = True
        _set_exclusions(add=rec["excl"])
        # 2) collection / pool copies of them (owned copies: deleted with the usual undo stash)
        owned = [i["hash"] for i in items if i["colids"] or i["in_pool"]] + owned_extra
        if owned:
            rec["del_token"] = imagelib.delete_everywhere(owned)["token"]
        # 3) manual tags, auto tags
        tags = imagelib.load_tags()
        for h in hs:
            if h in tags:
                rec["tags"][h] = tags.pop(h)
        if rec["tags"]:
            imagelib.save_tags(tags)
        st = getattr(imagelib, "AUTOTAG_STORE", None)
        if st is not None and hasattr(st, "pop"):
            rec["auto"] = st.pop(hs)
        # 4) masks (of the video, or the item as a mask) and virtual copies of it
        mids = [m["id"] for h in hs for m in _mk.for_video(h) + _mk.by_file_hash(h)]
        if mids:
            rec["mask_token"] = _mk.soft_delete(mids)["token"]
        vids = [c["id"] for c in _vc.entries() if (c.get("orig") or {}).get("hash") in set(hs)]
        if vids:
            rec["virt_token"] = _vc.soft_delete(vids)["token"]
        # 4b) 1.7.3: Video Library copies (soft delete: undo restores; the file goes to the Recycle Bin when purged)
        from . import videostore as _vs
        rec["vlib_ids"] = []
        for i in items:
            for vid in _vlib_ids(i):
                try:
                    _vs.soft_delete(vid)
                    rec["vlib_ids"].append(vid)
                except Exception as e:
                    print(f"[Reference Library] video library delete failed: {e}")
        # 5) cached thumbnails (regenerated on demand)
        for h in hs:
            for p in glob.glob(os.path.join(imagelib._thumbs_dir(), h + "*")):
                try:
                    os.remove(p)
                except OSError:
                    pass
        token = uuid.uuid4().hex
        stash = os.path.join(imagelib._undo_root(), "f" + token)
        os.makedirs(stash, exist_ok=True)
        storage._atomic_write_json(os.path.join(stash, "forget.json"), rec)
    imagelib.invalidate()
    return {"ok": True, "n": len(hs), "token": token, "recycled": len(rec["recycled"]), "recycle_errors": rec["recycle_errors"],
            "masks": len(mids), "virtuals": len(vids), "owned": len(owned), "vlib": len(rec["vlib_ids"])}


def undo(token: str) -> Dict[str, Any]:
    """Undo "Quitar de la librería": entries, tags, exclusions, copies, masks come back. Recycled files stay in the
    Recycle Bin (restore them from there; they then reappear on the next rescan)."""
    import re
    from . import imagelib, masks as _mk, virtuals as _vc
    if not re.match(r"^[0-9a-f]{32}$", str(token or "")):
        raise storage.StorageError("undo expired")
    stash = os.path.join(imagelib._undo_root(), "f" + token)
    try:
        with open(os.path.join(stash, "forget.json"), "r", encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        raise storage.StorageError("undo expired")
    with storage._lock:
        _set_exclusions(remove={fid: list(ex) for fid, ex in rec.get("excl", {}).items()})
        if rec.get("tags"):
            tags = imagelib.load_tags()
            for h, t in rec["tags"].items():
                tags[h] = list(dict.fromkeys(list(tags.get(h, [])) + list(t)))
            imagelib.save_tags(tags)
        st = getattr(imagelib, "AUTOTAG_STORE", None)
        if rec.get("auto") and st is not None and hasattr(st, "restore"):
            st.restore(rec["auto"])
        if rec.get("del_token"):
            try:
                imagelib.undo_remove(rec["del_token"])
            except storage.StorageError:
                pass
        if rec.get("mask_token"):
            _mk.restore(rec["mask_token"])
        if rec.get("virt_token"):
            _vc.restore(rec["virt_token"])
        if rec.get("vlib_ids"):
            from . import videostore as _vs
            for vid in reversed(rec["vlib_ids"]):   # reversed: each goes back to its old position
                try:
                    _vs.restore_soft_deleted(vid)
                except Exception as e:
                    print(f"[Reference Library] video library undo failed: {e}")
        shutil.rmtree(stash, ignore_errors=True)
    imagelib.invalidate()
    return {"ok": True, "n": len(rec.get("hashes") or []), "recycled": len(rec.get("recycled") or [])}


def missing_hashes() -> List[str]:
    from . import imagelib
    return [i["hash"] for i in imagelib.catalog()["items"] if i.get("missing") and forgettable(i)]
