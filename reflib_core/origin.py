"""1.10.0 origin: every item is AI-generated ("ai") or real ("real"). One logic for the Media Library and the Galería.

Resolution, first match wins:
  1. manual override per item            (origin.json "items": {hash: "ai"|"real"})
  2. folder mark, nearest ancestor first  (origin.json "folders": {"<fid>|<rel>": "ai"|"real"}; "" rel = the watched folder),
     inherited by every subfolder and every new file, unless a deeper folder or the item overrides it
  3. auto: under a WanGP outputs folder (AI_DIRS, set by the host), a WanGP settings sidecar (<name>.json next to it, or
     <name>_settings.json), or a WanGP-style file name (…_seed123…, 2025-01-01-12h30m15s_…) -> "ai"; anything else "real".
Searchable as origin:ia / origin:real (alias origen:) in both UIs' search; filter key {"origins": ["ai"|"real"]}.
PNG text chunks are not read here (would mean opening every file on each catalog build); WanGP writes the settings json
or uses its own output folder / names, which covers its outputs."""
import json
import os
import re
import threading
from typing import Any, Dict, Iterable, List, Optional

from . import storage

VALUES = ("ai", "real")
AI_DIRS: List[str] = []          # host: WanGP save_path / image_save_path (absolute)
AI_DIRS_FN = None                 # or a callable returning them (plugin.py: _output_dirs)
_NAME_RE = re.compile(r"(^|[_\-. ])seed[_\-]?\d+|^\d{4}-\d{2}-\d{2}-\d{2}h\d{2}m\d{2}s", re.I)
_lock = threading.Lock()
_cache: Dict[str, Any] = {"key": None, "data": None}
_side: Dict[str, bool] = {}


def path() -> str:
    return os.path.join(storage.COLLECTIONS_DIR, "origin.json")


def load() -> Dict[str, Dict[str, str]]:
    p = path()
    try:
        st = os.stat(p); key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {"items": {}, "folders": {}}
    with _lock:
        if _cache["key"] == key:
            return _cache["data"]
    try:
        with open(p, "r", encoding="utf-8") as r:
            d = json.load(r)
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid origin.json: {e}")
        d = {}
    data = {k: {str(a): v for a, v in (d.get(k) or {}).items() if v in VALUES} if isinstance(d.get(k), dict) else {}
            for k in ("items", "folders")}
    with _lock:
        _cache.update(key=key, data=data)
    return data


def _save(data) -> None:
    os.makedirs(storage.COLLECTIONS_DIR, exist_ok=True)
    storage._atomic_write_json(path(), {"version": 1, **data})


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(p)).rstrip("\\/") if p else ""


def _auto(i: Dict[str, Any], ai_dirs: List[str]) -> bool:
    if i.get("virtual"):
        return False
    names = [i.get("name") or ""] + list(i.get("names") or ())
    if any(_NAME_RE.search(n) for n in names):
        return True
    for p in [i.get("path") or ""] + list(i.get("files") or ()):
        if not p:
            continue
        np_ = os.path.normcase(os.path.abspath(p))
        if any(np_.startswith(d + os.sep) for d in ai_dirs):
            return True
        if p not in _side:   # cached per path: one stat pair the first time a file is seen
            b = os.path.splitext(p)[0]
            _side[p] = os.path.isfile(b + ".json") or os.path.isfile(b + "_settings.json")
        if _side[p]:
            return True
    return False


def resolve(items: Iterable[Dict[str, Any]]) -> None:
    """Sets i["origin"] ("ai"|"real") and i["osrc"] ("item"|"folder"|"auto") on catalog items (in place, cheap)."""
    d = load()
    im, fm = d["items"], d["folders"]
    dirs = list(AI_DIRS)
    try:
        dirs += list(AI_DIRS_FN() or []) if AI_DIRS_FN else []
    except Exception:
        pass
    ai_dirs = [os.path.normcase(os.path.abspath(x)).rstrip("\\/") for x in dict.fromkeys(dirs) if x]
    for i in items:
        v = im.get(i["hash"])
        if v:
            i["origin"], i["osrc"] = v, "item"; continue
        fv = None
        if fm:
            best = -1
            for fid, rel in i.get("locs") or ():
                parts = rel.split("/") if rel else []
                for k in range(len(parts), -1, -1):
                    m = fm.get(fid + "|" + "/".join(parts[:k]))
                    if m:
                        if k > best:
                            best, fv = k, m
                        break
        if fv:
            i["origin"], i["osrc"] = fv, "folder"; continue
        i["origin"], i["osrc"] = ("ai" if _auto(i, ai_dirs) else "real"), "auto"


def set_items(hashes: Iterable[str], value: str) -> Dict[str, Any]:
    """value "ai" | "real" | "auto" (drop the override)."""
    hs = [h for h in dict.fromkeys(hashes) if re.match(r"^[0-9a-f]{64}$", str(h))]
    d = {k: dict(v) for k, v in load().items()}
    for h in hs:
        if value in VALUES:
            d["items"][h] = value
        else:
            d["items"].pop(h, None)
    _save(d)
    _refresh()
    return {"changed": len(hs), "hashes": hs}


def set_folder(fid: str, rel: str, value: str) -> Dict[str, Any]:
    rel = "/".join(p for p in str(rel or "").replace("\\", "/").split("/") if p and p not in (".", ".."))
    d = {k: dict(v) for k, v in load().items()}
    k = f"{fid}|{rel}"
    if value in VALUES:
        d["folders"][k] = value
    else:
        d["folders"].pop(k, None)
    _save(d)
    _refresh()
    return {"fid": fid, "rel": rel, "value": value if value in VALUES else "auto"}


def folder_mark(fid: str, rel: str) -> Dict[str, Optional[str]]:
    """-> {own: mark on this node or None, inherited: nearest ancestor's mark or None}"""
    fm = load()["folders"]
    parts = rel.split("/") if rel else []
    inh = None
    for k in range(len(parts) - 1, -1, -1):
        inh = fm.get(fid + "|" + "/".join(parts[:k]))
        if inh:
            break
    return {"own": fm.get(f"{fid}|{rel}"), "inherited": inh}


def _refresh() -> None:
    """Re-resolve the cached catalog in place (no full rebuild) and drop cached filter results."""
    from . import imagelib
    with imagelib._cat_lock:
        data = imagelib._cat.get("data")
        if data is None:
            return
        resolve(data["items"])
        data["origins"] = counts(data["items"])
        imagelib._cat.update(fkey=None, flist=None, lru=[])


def counts(items) -> Dict[str, int]:
    c = {"ai": 0, "real": 0}
    for i in items:
        c[i.get("origin") or "real"] += 1
    return c


_TOK = re.compile(r"(?:^|\s)(?:origin|origen):(ia|ai|real|ial|r)\b", re.I)


def parse_query(q: str):
    """'retrato origin:ia' -> ('retrato', ['ai']). Returns (rest, origins)."""
    want = []
    def sub(m):
        want.append("ai" if m.group(1).lower() in ("ia", "ai", "ial") else "real")
        return " "
    rest = _TOK.sub(sub, q or "")
    return " ".join(rest.split()), sorted(set(want))


# ---------------------------------------------------------------- shared actions (both UIs)
from .actions import ActionError, action  # noqa: E402

_LBL = {"ai": "IA", "real": "Real", "auto": "automático"}


def _hashes(req):
    from . import imagelib
    for k in ("sel", "selection"):   # Galería {sel} / Media Library {selection} ("all N matching" model)
        if isinstance(req.get(k), dict):
            return imagelib.resolve_selection(req[k])
    return imagelib.resolve_selection({"hashes": req.get("hashes") or []})


def _meta(ctx, out, req):
    if req.get("meta", True) and ctx._payload:
        out.update(ctx.payload())
    return out


@action("origin_info", fast=True, doc="Origin of a selection {sel|hashes} -> {ai, real, manual, value}")
def origin_info(req, ctx):
    from . import imagelib
    by = imagelib.catalog()["by_hash"]
    c = {"ai": 0, "real": 0}; manual = {"ai": 0, "real": 0}; auto = 0
    for h in _hashes(req):
        i = by.get(h)
        if not i:
            continue
        o = i.get("origin") or "real"
        c[o] += 1
        if i.get("osrc") == "item":
            manual[o] += 1
        else:
            auto += 1
    n = c["ai"] + c["real"]
    value = "auto" if auto == n else ("ai" if manual["ai"] == n else "real" if manual["real"] == n else "mixed")
    return {"ok": True, "n": n, "ai": c["ai"], "real": c["real"], "manual": manual, "value": value}


@action("origin_set", doc="Set the origin of items {sel|hashes, value: ai|real|auto}")
def origin_set(req, ctx):
    v = str(req.get("value") or "")
    if v not in VALUES + ("auto",):
        raise ActionError("bad_request")
    hs = _hashes(req)
    prev = {h: load()["items"].get(h) for h in hs}
    r = set_items(hs, v)
    msg = f"{r['changed']} elemento(s): origen {_LBL[v]}"
    undo = ctx.state.setdefault("origin_undo", {})
    import time as _t, uuid as _u
    tok = _u.uuid4().hex
    undo[tok] = {"at": _t.time(), "prev": prev}
    return _meta(ctx, {"ok": True, "message": msg, "toast": msg, "value": v, "changed": r["changed"], "undo_token": tok}, req)


@action("origin_undo", doc="Undo origin_set {undo_token}")
def origin_undo(req, ctx):
    ent = ctx.state.get("origin_undo", {}).pop(str(req.get("undo_token") or ""), None)
    if not ent:
        raise ActionError("undo_expired")
    groups: Dict[str, List[str]] = {}
    for h, v in ent["prev"].items():
        groups.setdefault(v or "auto", []).append(h)
    for v, hs in groups.items():
        set_items(hs, v)
    return _meta(ctx, {"ok": True, "message": "Origen restaurado", "toast": "Origen restaurado"}, req)


@action("origin_folder", doc="Mark a folder / subfolder {fid, rel, value: ai|real|auto}; inherited by its contents")
def origin_folder(req, ctx):
    v = str(req.get("value") or "")
    fid = str(req.get("fid") or "")
    if v not in VALUES + ("auto",) or not re.match(r"^[0-9a-f]{8,64}$", fid):
        raise ActionError("bad_request")
    r = set_folder(fid, str(req.get("rel") or ""), v)
    msg = "Carpeta marcada como IA" if v == "ai" else "Carpeta marcada como real" if v == "real" else "Carpeta: origen automático"
    return _meta(ctx, {"ok": True, "message": msg, "toast": msg, **r, **folder_mark(r["fid"], r["rel"])}, req)


@action("origin_folder_info", fast=True, doc="Origin mark of a folder node {fid, rel} -> {own, inherited}")
def origin_folder_info(req, ctx):
    return {"ok": True, **folder_mark(str(req.get("fid") or ""), str(req.get("rel") or ""))}
