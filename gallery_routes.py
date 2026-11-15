"""Galería: a second, very visual web UI for the same library (same process, same data, same actions).

Routes added to WanGP's FastAPI app (behind WanGP's login check when auth is on):
  GET  /reflib/gallery/...   the built Galería SPA (gallery/dist)
  POST /reflib/api           JSON body -> plugin.ilib(...)  (exactly the media-browser bridge: every action)
  GET  /reflib/face_thumb/<face id>.jpg?size=&margin=   cropped face (faces.face_thumb_path)
  POST /reflib/upload        multipart files -> plugin.ilib_upload(...) (import into the unassigned pool)
Nothing is duplicated: the Galería calls the same handler as the Media browser, so a change made in one UI is what
the other reads on its next query."""

import json
import os

GALLERY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gallery", "dist")
_installed = False
_plugin = None


def set_plugin(plugin) -> None:
    global _plugin
    _plugin = plugin


class _Req:   # minimal stand-in for gr.Request (ilib only reads request.client.host for "reveal")
    def __init__(self, request):
        self.client = getattr(request, "client", None)
        self.headers = getattr(request, "headers", {})


def mount(app, dependencies=None) -> None:
    from fastapi import APIRouter, Request, UploadFile, File, Form
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
    from starlette.concurrency import run_in_threadpool

    r = APIRouter(dependencies=dependencies or [])

    @r.post("/reflib/api")
    async def api(request: Request):
        if _plugin is None:
            return JSONResponse({"ok": False, "error": "Reference Library no está cargado"}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            body = {}
        out = await run_in_threadpool(_plugin.ilib, json.dumps(body), _Req(request))
        return Response(out, media_type="application/json")

    @r.post("/reflib/upload")
    async def upload(files: list[UploadFile] = File(...), meta: str = Form("{}")):
        import tempfile, shutil
        tmp = tempfile.mkdtemp(prefix="reflib_gal_")
        paths = []
        try:
            for f in files:
                p = os.path.join(tmp, os.path.basename(f.filename or "file"))
                with open(p, "wb") as w:
                    shutil.copyfileobj(f.file, w)
                paths.append(p)
            res = await run_in_threadpool(_plugin.ilib_upload, paths, meta)
            out = res[0] if isinstance(res, (tuple, list)) else res
            return Response(out if isinstance(out, str) else json.dumps(out), media_type="application/json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @r.get("/reflib/export/{rel:path}")
    async def export_file(rel: str):   # 1.9.5: downloads written by col_export / v_export (only inside their temp root)
        from .reflib_core import ioactions
        root = os.path.realpath(ioactions.EXPORT_ROOT)
        p = os.path.realpath(os.path.join(root, rel))
        if not p.startswith(root + os.sep) or not os.path.isfile(p):
            return Response("not found", status_code=404)
        return FileResponse(p, filename=os.path.basename(p))

    @r.get("/reflib/face_thumb/{name}")
    async def face_thumb(name: str, size: int = 160, margin: float = 0.4):   # 1.10.0: Personas face crops (both UIs)
        from .reflib_core import faces as _faces
        fid = name[:-4] if name.endswith(".jpg") else name
        try:
            p = await run_in_threadpool(_faces.face_thumb_path, fid, size, margin)
        except Exception:
            p = None
        if not p:
            return Response("not found", status_code=404)
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


    @r.get("/reflib/play/{digest}")
    async def play_media(digest: str, request: Request):
        """1.12.19: stream a browser-playable copy (cached H.264/AAC, or a growing fragmented MP4 while it builds)."""
        import asyncio, mimetypes
        from .reflib_core import imagelib, playable as _play
        digest = str(digest or "")
        # sync work (catalog, ffprobe, file checks) off the event loop: this route is polled while a copy is built
        src = await run_in_threadpool(imagelib.media_path, digest)
        if not src or not os.path.isfile(src) or imagelib.kind_of(src) in ("image", "audio"):
            return Response("not found", status_code=404)
        st = await run_in_threadpool(_play.ensure, digest, src, True)
        if st.get("play") == "failed":
            return JSONResponse({"ok": False, "error": st.get("error") or "transcode failed"}, status_code=415)
        if st.get("play") == "original":
            mt = mimetypes.guess_type(src)[0] or "video/mp4"
            return FileResponse(src, media_type=mt, filename=os.path.basename(src))
        # Wait until the cache has the first box (or is ready), so the <video> can start.
        deadline = asyncio.get_event_loop().time() + 45
        while asyncio.get_event_loop().time() < deadline:
            cur = await run_in_threadpool(_play.status, digest, src)
            if cur.get("play") == "failed":
                return JSONResponse({"ok": False, "error": cur.get("error") or "transcode failed"}, status_code=415)
            if cur.get("play") == "ready" and cur.get("path") and os.path.isfile(cur["path"]):
                return FileResponse(cur["path"], media_type="video/mp4",
                                    filename=_play.serve_name(digest, src),
                                    headers={"Cache-Control": "private, max-age=3600"})
            part = cur.get("part")
            if part and cur.get("play") == "preparing":
                try:   # open now: the part is removed once the remux to the final file is done
                    fh = open(part, "rb") if os.path.getsize(part) >= 256 else None
                except OSError:
                    fh = None
                if fh is not None:
                    return StreamingResponse(_grow_play(fh, digest, src, _play), media_type="video/mp4",
                                             headers={"Cache-Control": "no-store"})
            await asyncio.sleep(0.12)
        return Response("preparing", status_code=425)

    async def _grow_play(fh, digest, src, _play):
        import asyncio
        try:
            while True:
                chunk = fh.read(64 * 1024)
                if chunk:
                    yield chunk
                    continue
                cur = await run_in_threadpool(_play.status, digest, src)
                if cur.get("play") == "ready":
                    rest = fh.read()
                    if rest:
                        yield rest
                    break
                if cur.get("play") == "failed":
                    break
                await asyncio.sleep(0.12)
        finally:
            try:
                fh.close()
            except OSError:
                pass

    @r.get("/reflib/media-library")
    async def media_library_root():
        return RedirectResponse("/reflib/media-library/")

    @r.get("/reflib/media-library/")
    async def media_library_page():
        """1.12.7: standalone Media Library (same explorer JS, fetch bridge, no WanGP chrome)."""
        if _plugin is None:
            return Response("Reference Library no está cargado", status_code=503)
        # Prefer helpers already exported on the plugin module (set via set_plugin)
        mod = type(_plugin)
        # _plugin is an instance; helpers live on the package module
        import sys
        pkg = sys.modules.get(type(_plugin).__module__)
        build_js = getattr(pkg, "build_js", None)
        load_css = getattr(pkg, "load_css", None)
        PLUGIN_VERSION = getattr(pkg, "PLUGIN_VERSION", "")
        resolve_lang = getattr(pkg, "resolve_lang", lambda *a, **k: "en")
        load_settings = getattr(pkg, "load_settings", lambda: {})
        if not build_js or not load_css:
            return Response("build_js unavailable", status_code=500)
        lang = resolve_lang(load_settings().get("language") or "auto")
        title = "Media Library"
        css = load_css()
        js = build_js()
        html = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title} · Reference Library {PLUGIN_VERSION}</title>
<style>{css}</style>
</head>
<body>
<script>window.__REFLIB_STANDALONE__=true;window.__REFLIB_VERSION__={PLUGIN_VERSION!r};</script>
<script>{js}</script>
</body>
</html>"""
        return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    @r.get("/reflib/gallery")
    async def gallery_root():
        return RedirectResponse("/reflib/gallery/")

    @r.get("/reflib/gallery/{path:path}")
    async def gallery(path: str = ""):
        root = os.path.realpath(GALLERY_DIR)
        p = os.path.realpath(os.path.join(root, path or "index.html"))
        if not p.startswith(root) or not os.path.isfile(p):
            p = os.path.join(root, "index.html")
        if not os.path.isfile(p):
            return Response("Galería sin compilar: ejecuta `npm run build` en la carpeta gallery/ del plugin.", status_code=404)
        return FileResponse(p, headers={"Cache-Control": "no-cache"} if p.endswith(".html") else None)

    app.include_router(r)


def install() -> None:
    """Patch gradio's App.create_app (same pattern as WanGP's Deepy routes) so the routes exist on WanGP's app."""
    global _installed
    if _installed:
        return
    from gradio.routes import App
    original = App.create_app

    def create_app(*args, **kwargs):
        app = original(*args, **kwargs)
        deps = None
        try:
            from fastapi import Depends
            from gradio.routes import API_PREFIX
            try:
                from shared.utils.fastapi_routes import iter_app_routes
            except Exception:
                iter_app_routes = lambda a: a.routes
            check = next((rt.endpoint for rt in iter_app_routes(app) if getattr(rt, "path", None) == f"{API_PREFIX}/login_check"), None)
            deps = [Depends(check)] if check else None
        except Exception:
            deps = None
        try:
            mount(app, deps)
            print("[Reference Library] Galería: /reflib/gallery/ · Media Library: /reflib/media-library/")
        except Exception as e:
            print(f"[Reference Library] Galería no disponible: {e}")
        return app

    App.create_app = staticmethod(create_app)
    _installed = True
