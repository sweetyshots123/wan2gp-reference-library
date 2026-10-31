"""1.12.1 virtual copies (clips by in/out, crop/resolution) as shared actions: the Media Library and the Galería call
the same virt_* code (moved unchanged from plugin.py ``_virtual``). Deleting a copy keeps using the library's
``delete`` / ``delete_all`` flow (originals are never touched, one undo token)."""
import os

from . import imagelib
from .actions import action

def _url(p: str) -> str:
    f = getattr(imagelib, "SERVE_URL", None)   # set by the host (plugin.py _serve_url: Gradio-served URL of one library file)
    return f(p) if f else ""


def _guard(fn):
    def run(req, ctx):
        from . import virtuals as _vc
        try:
            return fn(req, ctx, _vc)
        except _vc.VirtualError as e:
            msg = str(e)
            if msg in ("original missing",):
                return {**ctx.err("virt_broken"), "broken": True}
            if msg == "original not in the library":
                return ctx.err("virt_no_orig")
            return ctx.err("virt_bad", e=msg)
    run.__doc__ = fn.__doc__
    return run


@action("virt_src", fast=True, doc="Editor source {hash}: the ORIGINAL's file + facts, and the copy's params")
@_guard
def a_src(req, ctx, _vc):
    h = str(req.get("hash") or "")
    ent = imagelib.entry_for(h) or {}
    c = _vc.by_hash(h) if ent.get("virtual") else None
    if ent.get("virtual") and not c:
        return ctx.err("err_image_missing")
    if c:
        src = _vc.source_path(c)
        if not src:
            return {**ctx.err("virt_broken"), "broken": True}
        kind, name, params, ohash = c["kind"], c["name"], c.get("params") or {}, (c.get("orig") or {}).get("hash")
    else:
        src = next((q for q in [ent.get("path")] + list(ent.get("files") or []) if q and os.path.isfile(q)), None) if ent else None
        if not src:
            return ctx.err("err_image_missing")
        kind, name, params, ohash = ("video" if ent.get("kind") == "mask" else ent.get("kind") or "image"), ent.get("name") or os.path.basename(src), {}, h   # a mask is a video
    facts = _vc.original_facts(src, kind)
    if c and _vc.refresh_facts(c["id"], facts):   # 1.6.7: heal a duration stored as 0 by 1.6.6
        imagelib.invalidate()
    return {"ok": True, "kind": kind, "name": os.path.splitext(name)[0] if not c else name, "path": os.path.abspath(src),
            "url": _url(src), "params": params, "virtual": bool(c), "orig_hash": ohash, **facts}


@action("virt_create", doc="New virtual copy {hash, params:{rect?, start?, end?}, name?}")
@_guard
def a_create(req, ctx, _vc):
    c = _vc.create(str(req.get("hash") or ""), req.get("params") if isinstance(req.get("params"), dict) else None, name=req.get("name"), lang=ctx.lang)
    imagelib.invalidate()
    out = ctx.ok("virt_created", name=c["name"])
    out.update(hash=c["hash"], copy=_vc.describe(c), reload=True, quiet=True)
    return out


@action("virt_update", doc="Change a virtual copy {hash, params, name?}")
@_guard
def a_update(req, ctx, _vc):
    c = _vc.by_hash(str(req.get("hash") or ""))
    if not c:
        return ctx.err("err_image_missing")
    c = _vc.update(c["id"], req.get("params") if isinstance(req.get("params"), dict) else None, name=req.get("name"))
    imagelib.invalidate()
    out = ctx.ok("virt_updated", name=c["name"])
    out.update(hash=c["hash"], copy=_vc.describe(c), reload=True, quiet=True)
    return out


@action("virt_status", fast=True, doc="Render state of a copy {hash} -> {state, url?}")
@_guard
def a_status(req, ctx, _vc):
    c = _vc.by_hash(str(req.get("hash") or ""))
    if not c:
        return {"ok": True, "state": "gone"}
    st = _vc.render_async(c["id"])
    out = {"ok": True, "state": st.get("state"), "error": st.get("error")}
    if st.get("state") == "ready":
        out["url"] = _url(st["path"])
    return out


@action("virt_list", fast=True, doc="1.12.1 versions of a media item {hash} (an original, or one of its copies) -> {orig, copies:[describe]}")
@_guard
def a_list(req, ctx, _vc):
    h = str(req.get("hash") or "")
    c = _vc.by_hash(h)
    orig = ((c.get("orig") or {}).get("hash") if c else h) or h
    return {"ok": True, "orig": orig, "copies": [_vc.describe(x) for x in _vc.copies_of(orig)]}
