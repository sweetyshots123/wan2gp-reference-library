"""Galería: a second, very visual web UI for the same library (same process, same data, same actions).

Routes added to WanGP's FastAPI app (behind WanGP's login check when auth is on):
  GET  /reflib/gallery/...   the built Galería SPA (gallery/dist)
  POST /reflib/api           JSON body -> plugin.ilib(...)  (exactly the media-browser bridge: every action)
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
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
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
            print("[Reference Library] Galería: /reflib/gallery/")
        except Exception as e:
            print(f"[Reference Library] Galería no disponible: {e}")
        return app

    App.create_app = staticmethod(create_app)
    _installed = True
