"""Collection management as shared actions (1.8.5): moved out of the Gradio "Manage collections" callbacks so the
Media Library and the Galería run the same code. Messages come from the plugin's TEXT table via ``ctx``."""
import time
import uuid

from . import actions, imagelib, imagestore, storage
from .actions import ActionError, action

UNDO_S = 5 * 60


def _cid(req) -> str:
    cid = str(req.get("collection_id") or req.get("cid") or "")
    if not cid:
        raise ActionError("no_collection")
    return cid


def _index_of(col, req) -> int:
    """A collection image by position (Gradio manager) or by content hash (explorer / Galería)."""
    if req.get("hash"):
        h = str(req["hash"])
        for i, img in enumerate(col.get("images") or []):
            if str(img.get("hash") or "") == h:
                return i
        raise ActionError("not_found")
    return int(req.get("index", -1))


def _done(ctx, out, with_meta=True):
    imagelib.invalidate()
    if with_meta and ctx._payload:
        out.update(ctx.payload())
    return out


@action("col_rename", doc="Rename a collection {collection_id, name}")
def col_rename(req, ctx):
    cid, name = _cid(req), str(req.get("name") or "").strip()
    if not name:
        raise ActionError("need_name")
    try:
        col = storage.rename_collection(cid, name, fallback=req.get("fallback") or "Collection")
    except storage.StorageError:
        raise ActionError("not_found")
    return _done(ctx, {**ctx.ok("renamed_col", name=col["name"], _cid=col["id"]), "collection": {"id": col["id"], "name": col["name"]}}, req.get("meta", True))


@action("col_duplicate", doc="Copy a collection {collection_id, copy_suffix?}")
def col_duplicate(req, ctx):
    cid = _cid(req)
    try:
        col = storage.duplicate_collection(cid, copy_suffix=req.get("copy_suffix") or ("copia" if ctx.lang.startswith("es") else "copy"))
    except storage.StorageError:
        raise ActionError("not_found")
    return _done(ctx, {**ctx.ok("duplicated_col", name=col["name"], _cid=col["id"]), "collection": {"id": col["id"], "name": col["name"]}}, req.get("meta", True))


@action("col_delete", doc="Soft-delete a collection {collection_id} -> undo_token (5 min)")
def col_delete(req, ctx):
    cid = _cid(req)
    storage.purge_trash()
    try:
        col = storage.soft_delete(cid)
    except storage.StorageError:
        raise ActionError("not_found")
    token = uuid.uuid4().hex
    ctx.state[token] = {"id": col["id"], "name": col["name"], "time": time.time()}
    out = {**ctx.ok("deleted_undo_toast", name=col["name"], _cid=col["id"]), "undo_token": token, "undo_label": ctx.ok("undo").get("message", "Undo")}
    return _done(ctx, out, req.get("meta", True))


@action("col_undo_delete", doc="Restore a soft-deleted collection {undo_token}")
def col_undo_delete(req, ctx):
    token = req.get("undo_token")
    info = ctx.state.pop(token, None) if token else None
    if not info or info.get("kind") == "video" or time.time() - info["time"] > UNDO_S:
        raise ActionError("undo_expired")
    try:
        col = storage.restore_soft_deleted(info["id"])
    except storage.StorageError:
        raise ActionError("undo_expired")
    merged = imagestore.merge_after_restore(col["id"])
    if merged:
        col = storage.get_collection(col["id"])
        out = ctx.ok("restored_merged", name=col["name"], added=merged["added"], merged=merged["merged_name"], _cid=col["id"])
    else:
        out = ctx.ok("restored_col", name=col["name"], _cid=col["id"])
    out["collection"] = {"id": col["id"], "name": col["name"]}
    return _done(ctx, out, req.get("meta", True))


@action("col_cover", doc="Set a collection's cover {collection_id, hash | index}")
def col_cover(req, ctx):
    cid = _cid(req)
    try:
        col = storage.get_collection(cid)
        storage.set_cover(cid, _index_of(col, req))
    except storage.StorageError as e:
        return {"ok": False, "error": str(e)}
    return _done(ctx, ctx.ok("cover_set", _cid=cid), req.get("meta", True))


@action("col_move", doc="Move an image inside a collection {collection_id, hash | index, delta}")
def col_move(req, ctx):
    cid = _cid(req)
    try:
        col = storage.get_collection(cid)
        i = _index_of(col, req)
        col = storage.move_image(cid, i, int(req.get("delta") or 0))
    except storage.StorageError as e:
        return {"ok": False, "error": str(e)}
    d = int(req.get("delta") or 0)
    out = {"ok": True, "message": "", "changed": {"reason": "images", "id": cid}, "index": i + d if 0 <= i + d < len(col["images"]) else i}
    return _done(ctx, out, req.get("meta", False))


@action("actions_list", fast=True, doc="Registered shared actions and whether they are fast")
def actions_list(req, ctx):
    return {"ok": True, "actions": actions.describe()}
