"""1.9.5: collection zip export / import and the Video Library manager as shared actions.

Moved out of the Gradio callbacks (on_export, on_import, on_vrename, on_vmove, on_vdelete, on_vundo, on_vimport,
on_vdownload, on_vexport) so the Media Library and the Galería run the same code. Files for download are written to
``req["dir"]`` (the Gradio host passes a folder Gradio may serve) or to EXPORT_ROOT/<random>/ (served by the Galería
route ``GET /reflib/export/<rel>``). Imports take server-side ``paths`` (an upload the host has already saved)."""
import os
import tempfile
import time
import uuid

from . import imagelib, storage, videostore
from .actions import ActionError, action

UNDO_S = 5 * 60
EXPORT_ROOT = os.path.join(tempfile.gettempdir(), "reflib-export")


def _t(ctx, key, **kw) -> str:
    return str(ctx.ok(key, **kw).get("message") or key)


def _fail(ctx, e):
    return {"ok": False, "error": ctx.exc(e)}


def _dest_dir(req) -> str:
    d = req.get("dir") or os.path.join(EXPORT_ROOT, uuid.uuid4().hex[:10])
    os.makedirs(d, exist_ok=True)
    return d


def _file_out(path: str) -> dict:
    root = os.path.realpath(EXPORT_ROOT)
    p = os.path.realpath(path)
    rel = os.path.relpath(p, root).replace(os.sep, "/") if p.startswith(root + os.sep) else ""
    return {"path": path, "name": os.path.basename(path), "rel": rel}


def _done(ctx, out, req):
    imagelib.invalidate()
    if req.get("meta", True) and ctx._payload:
        out.update(ctx.payload())
    return out


def _paths(req):
    return [p for p in (req.get("paths") or []) if isinstance(p, str) and os.path.isfile(p)]


# ---------------------------------------------------------------- collections
@action("col_export", doc="Export a collection as a zip {collection_id, dir?} -> {path, name, rel}")
def col_export(req, ctx):
    cid = str(req.get("collection_id") or "")
    if not cid:
        raise ActionError("no_collection")
    try:
        col = storage.get_collection(cid)
        safe = storage._safe_name(col["name"], _t(ctx, "default_name")).replace(" ", "_")
        dest = os.path.join(_dest_dir(req), f"{safe}-{cid[:8]}.zip")
        storage.export_collection_zip(cid, dest)
    except storage.StorageError:
        raise ActionError("not_found")
    return {**ctx.ok("exported", path=os.path.basename(dest)), **_file_out(dest)}


@action("col_import", doc="Import collection zips {paths} -> {collections}")
def col_import(req, ctx):
    paths = _paths(req)
    if not paths:
        raise ActionError("bad_request")
    cols, errs = [], []
    for p in paths:
        try:
            cols.append(storage.import_collection_zip(p, default_name=_t(ctx, "imported_name")))
        except Exception as e:
            errs.append(ctx.exc(e))
    if not cols:
        return {"ok": False, "error": errs[0] if errs else "?"}
    c = cols[-1]
    out = {**ctx.ok("imported", name=c["name"], n=len(c["images"]), _cid=c["id"]),
           "collections": [{"id": x["id"], "name": x["name"], "n": len(x["images"])} for x in cols], "errors": errs}
    return _done(ctx, out, req)


# ---------------------------------------------------------------- video library
def _vid(req) -> str:
    vid = str(req.get("vid") or req.get("video_id") or "")
    if not vid:
        raise ActionError("no_video")
    return vid


@action("v_list", fast=True, doc="Video Library entries (no paths) with the library hash for thumbnails")
def v_list(req, ctx):
    out = []
    for v in videostore.list_videos():
        s = videostore.public_summary(v)
        try:
            s["hash"] = imagelib.vlib_hash(v)
        except Exception:
            s["hash"] = ""
        out.append(s)
    return {"ok": True, "videos": out}


@action("v_rename", doc="Rename a Video Library video {vid, name}")
def v_rename(req, ctx):
    vid, name = _vid(req), str(req.get("name") or "").strip()
    if not name:
        raise ActionError("need_vname")
    try:
        v = videostore.rename_video(vid, name, fallback=_t(ctx, "video_default_name"))
    except storage.StorageError as e:
        return _fail(ctx, e)
    return _done(ctx, {**ctx.ok("vrenamed", name=v["name"], _cid=v["id"]), "video": videostore.public_summary(v)}, req)


@action("v_move", doc="Move a video left/right in the Video Library {vid, delta}")
def v_move(req, ctx):
    vid = _vid(req)
    try:
        videostore.move_video(vid, int(req.get("delta") or 0))
    except storage.StorageError as e:
        return _fail(ctx, e)
    return _done(ctx, {"ok": True, "message": "", "changed": {"reason": "video-reordered", "id": vid, "kind": "video"}}, req)


@action("v_delete", doc="Soft-delete a Video Library video {vid} -> undo_token (5 min)")
def v_delete(req, ctx):
    vid = _vid(req)
    videostore.purge_trash()
    try:
        v = videostore.soft_delete(vid)
    except storage.StorageError as e:
        return _fail(ctx, e)
    token = uuid.uuid4().hex
    ctx.state[token] = {"id": v["id"], "name": v["name"], "time": time.time(), "kind": "video"}
    out = {**ctx.ok("vdeleted_undo", name=v["name"], _cid=v["id"]), "undo_token": token, "undo_label": _t(ctx, "undo"),
           "deleted": v["id"]}
    return _done(ctx, out, req)


@action("v_undo_delete", doc="Restore a soft-deleted video {undo_token}")
def v_undo_delete(req, ctx):
    token = req.get("undo_token")
    info = ctx.state.get(token) if token else None
    if not info or info.get("kind") != "video" or time.time() - info["time"] > UNDO_S:
        ctx.state.pop(token, None)
        raise ActionError("undo_expired")
    ctx.state.pop(token, None)
    try:
        v = videostore.restore_soft_deleted(info["id"])
    except storage.StorageError:
        raise ActionError("undo_expired")
    merged = v.pop("_merged_from", None)
    if merged:
        msg = _t(ctx, "vrestore_dup", name=merged["name"], existing=v["name"])
        out = {"ok": True, "kind": "info", "message": msg, "toast": msg}
    else:
        out = ctx.ok("vrestored", name=v["name"], _cid=v["id"])
    out["vid"] = v["id"]
    return _done(ctx, out, req)


@action("v_import", doc="Import videos or video zips {paths}")
def v_import(req, ctx):
    added, skipped, errors = [], 0, []
    fb = _t(ctx, "video_default_name")
    for path in _paths(req):
        try:
            if path.lower().endswith(".zip"):
                got, skip = videostore.import_zip(path, fallback=fb)
                added.extend(got); skipped += skip
            else:
                entry, created = videostore.add_video(path, source="import", fallback=fb)
                added.append(entry) if created else None
                skipped += 0 if created else 1
        except Exception as e:
            errors.append(ctx.exc(e))
    if not added and not skipped:
        return {"ok": False, "error": errors[0] if errors else _t(ctx, "bad_request")}
    out = ctx.ok("vimported_skip" if skipped else "vimported", n=len(added), skipped=skipped, _cid=added[0]["id"] if added else None)
    out["vid"] = added[0]["id"] if added else ""
    return _done(ctx, out, req)


@action("v_export", doc="Copy one video out {vid, dir?}, or every video as a zip {all: true, dir?} -> {path, name, rel}")
def v_export(req, ctx):
    try:
        if req.get("all"):
            dest, n = videostore.export_all_zip(os.path.join(_dest_dir(req), time.strftime("reference-library-videos-%Y%m%d-%H%M.zip")))
            return {**ctx.ok("vexported", n=n, path=os.path.basename(dest)), **_file_out(dest)}
        dest = videostore.export_file(_vid(req), _dest_dir(req), fallback=_t(ctx, "video_default_name"))
        return {**ctx.ok("vdownload", path=os.path.basename(dest)), **_file_out(dest)}
    except ActionError:
        raise
    except Exception as e:
        return _fail(ctx, e)
