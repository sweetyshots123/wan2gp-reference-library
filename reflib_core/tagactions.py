"""Global tag management as shared actions (1.8.6): rename, merge and delete a manual tag across the whole library,
used by the Media Library (Gradio) and the Galería. Personas are tags ("persona:<name>"), so the same actions rename or
delete a persona. Business logic lives in imagelib.rename_tag / delete_tag / set_tags."""
import time
import uuid

from . import imagelib, storage
from .actions import ActionError, action

UNDO_S = 5 * 60


def _done(ctx, out, req):
    if req.get("meta", True) and ctx._payload:
        out.update(ctx.payload())
    return out


@action("tag_info", fast=True, doc="Items carrying a tag {tag} -> {count}")
def tag_info(req, ctx):
    return {"ok": True, "tag": str(req.get("tag") or ""), "count": len(imagelib.tag_users(str(req.get("tag") or "")))}


@action("tag_rename", doc="Rename a tag everywhere {tag, to}; merges into `to` if it exists")
def tag_rename(req, ctx):
    old, new = str(req.get("tag") or ""), str(req.get("to") or "")
    if not imagelib.clean_tag(new):
        raise ActionError("tag_need_name")
    try:
        r = imagelib.rename_tag(old, new)
    except storage.StorageError:
        raise ActionError("tag_not_found", tag=old)
    key = "tag_merged" if r["merged"] else "tag_renamed"
    return _done(ctx, {**ctx.ok(key, old=old, tag=r["tag"], n=r["changed"]), "tag": r["tag"], "merged": r["merged"],
                       "changed": r["changed"], "hashes": r["hashes"]}, req)


@action("tag_merge", doc="Merge several tags into one {tags: [...], to}")
def tag_merge(req, ctx):
    srcs = [str(t) for t in req.get("tags") or [] if str(t).strip()]
    new = str(req.get("to") or "")
    if not srcs or not imagelib.clean_tag(new):
        raise ActionError("tag_need_name")
    total, hashes, target = 0, set(), imagelib.clean_tag(new)
    for t in srcs:
        if imagelib._fold(imagelib.clean_tag(t)) == imagelib._fold(target) and not imagelib.tag_users(t):
            continue
        try:
            r = imagelib.rename_tag(t, target)
        except storage.StorageError:
            continue
        target = r["tag"]; total += r["changed"]; hashes.update(r["hashes"])
    return _done(ctx, {**ctx.ok("tag_merged", old=", ".join(srcs), tag=target, n=len(hashes)), "tag": target,
                       "changed": len(hashes), "hashes": sorted(hashes)}, req)


@action("tag_delete", doc="Remove a tag from every item {tag} -> undo_token (5 min)")
def tag_delete(req, ctx):
    tag = str(req.get("tag") or "")
    try:
        r = imagelib.delete_tag(tag)
    except storage.StorageError:
        raise ActionError("tag_not_found", tag=tag)
    undo = ctx.state.setdefault("tag_undo", {})
    now = time.time()
    for k in [k for k, v in undo.items() if now - v["at"] > UNDO_S]:
        undo.pop(k, None)
    token = uuid.uuid4().hex
    undo[token] = {"at": now, "tag": r["tag"], "hashes": r["hashes"]}
    return _done(ctx, {**ctx.ok("tag_deleted", tag=r["tag"], n=r["changed"]), "tag": r["tag"], "changed": r["changed"],
                       "hashes": r["hashes"], "undo_token": token}, req)


@action("tag_undo_delete", doc="Put a deleted tag back {undo_token}")
def tag_undo_delete(req, ctx):
    ent = ctx.state.get("tag_undo", {}).pop(str(req.get("undo_token") or ""), None)
    if not ent or time.time() - ent["at"] > UNDO_S:
        raise ActionError("undo_expired")
    imagelib.set_tags(ent["hashes"], add=[ent["tag"]])
    return _done(ctx, {**ctx.ok("tag_restored", tag=ent["tag"], n=len(ent["hashes"])), "tag": ent["tag"],
                       "hashes": ent["hashes"]}, req)
