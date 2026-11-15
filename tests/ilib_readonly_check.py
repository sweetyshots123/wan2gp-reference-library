"""1.12.18: read-only library actions must not drop the catalog (retest of 1.12.17: at_suggest / col_peek invalidated
it, so every search-box pause made the next query rebuild everything).
Also calls at_tax_list: being in ILIB_READONLY is not enough if _autotag still invalidates (1.12.18 retest). Synthetic temp library only.
Runs the REAL plugin.py `ilib` / `_autotag` methods (extracted with ast: no Gradio / WanGP needed) on the real core.
python3 tests/ilib_readonly_check.py [path/to/plugin.py]"""
import ast, hashlib, json, os, sys, tempfile, traceback
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "plugin.py")
TMP = tempfile.mkdtemp(prefix="rl1218_")
os.environ["REFLIB_DATA_DIR"] = os.path.join(TMP, "data")
sys.path.insert(0, ROOT)
from reflib_core import storage, imagelib as L   # noqa: E402

SRC = os.path.join(TMP, "photos"); os.makedirs(SRC)
files = {}
FID = "b" * 32
for i, name in enumerate(["animal_%03d.png", "antonio_%03d.png", "esther_%03d.png"] * 40):
    p = os.path.join(SRC, name % i)
    open(p, "wb").write(i.to_bytes(4, "little") * 8)
    st = os.stat(p)
    files[p] = {"folder": FID, "size": st.st_size, "mtime": st.st_mtime, "hash": hashlib.sha256(p.encode()).hexdigest(), "first": 1}
os.makedirs(os.path.join(storage.PLUGIN_DIR, "folders"), exist_ok=True)
L._save_folders({"folders": [{"id": FID, "path": SRC, "recursive": True, "added": 1}], "files": files})
L.invalidate()

tree = ast.parse(open(PLUGIN, encoding="utf-8").read())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ReferenceLibraryPlugin")
body = [n for n in cls.body if (isinstance(n, ast.FunctionDef) and n.name in ("ilib", "_autotag"))
        or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "ILIB_READONLY" for t in n.targets))]
mod = ast.Module(body=[ast.ClassDef(name="Harness", bases=[], keywords=[], body=body, decorator_list=[])], type_ignores=[])
ns = {"json": json, "traceback": traceback, "gr": SimpleNamespace(Request=object), "imagelib": L, "storage": storage,
      "LANGS": ("en", "es"), "TEXT": {"en": {}, "es": {}}, "tr": lambda lang, key, **k: key, "PLUGIN_VERSION": "test",
      "_actions": SimpleNamespace(has=lambda a: False), "autotag_service": lambda: SimpleNamespace(),
      "storage_error_text": lambda lang, e: str(e)}
# relative "from .reflib_core import …" inside the extracted methods needs a package; use the same modules from sys.path
for n in ast.walk(mod):
    if isinstance(n, ast.ImportFrom) and n.level == 1 and (n.module or "").startswith("reflib_core"):
        n.level = 0
from reflib_core import taxonomy as _tx_
ns["_taxonomy"] = _tx_
exec(compile(ast.fix_missing_locations(mod), "plugin_ilib", "exec"), ns)
H = ns["Harness"]
H._lang = lambda self, b=None: "es"
H._err = lambda self, lang, key: {"ok": False, "error": key}
H._ilib_payload = lambda self, lang: {"ok": True}
h = H()

builds = [0]
_cb = L._catalog_build
def counting(*a, **k):
    builds[0] += 1
    return _cb(*a, **k)
L._catalog_build = counting

def call(action, **kw):
    return json.loads(h.ilib(json.dumps(dict(kw, action=action, lang="es"))))

bad = []
call("query", f={}, offset=0, limit=50)
for action, kw in [("at_tax_list", {}), ("at_suggest", {"text": "an", "f": {}}), ("at_suggest", {"text": "est", "f": {}}),
                   ("col_peek", {"label": "nada"}), ("thumbs", {"hashes": []}), ("query", {"f": {}, "offset": 0, "limit": 50})]:
    e0, b0 = L._cat["epoch"], builds[0]
    r = call(action, **kw)
    call("query", f={}, offset=0, limit=50)   # the next query must not rebuild
    if L._cat["epoch"] != e0 or builds[0] != b0:
        bad.append(f"{action}: catalog dropped (epoch {e0}->{L._cat['epoch']}, rebuilds +{builds[0] - b0}) r={str(r)[:120]}")
# a write still invalidates (the check is not vacuous)
e0 = L._cat["epoch"]; call("some_write_action")   # not read-only -> invalidates
if L._cat["epoch"] == e0:
    bad.append("a non-read-only action did not invalidate (harness broken?)")
# audit: every action known to only read must be in ILIB_READONLY
RO = set(ns["Harness"].ILIB_READONLY)
for a in ("open", "query", "range", "sel_info", "index_of", "locate", "list", "thumbs", "preview", "browse", "scan_status",
          "at_status", "at_facets", "at_image", "at_suggest", "at_tax_list", "at_tax_export", "col_peek", "media_url", "media_dur",
          "media_src", "playback_get", "playback_settings", "virt_src", "virt_status", "mask_list", "mask_info", "resize_status",
          "forget_plan", "forget_missing_plan", "forget_status", "folder_excluded", "hist_list", "hist_get", "hist_find"):
    if a not in RO:
        bad.append("not read-only: " + a)
print("\n".join(bad) if bad else "ilib_readonly_check: OK")
sys.exit(1 if bad else 0)
