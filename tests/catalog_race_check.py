"""1.12.17 catalog races and regressions (from the 1.12.16 retest repros), synthetic temp folders only.
python3 tests/catalog_race_check.py            -> every case, each in its own process
python3 tests/catalog_race_check.py <case>     -> one case
Cases: forget / restore / remove_folder (an edit during indexing while an older rebuild is in flight: no request
after the edit may get the pre-edit catalog), late_landing (a build started before invalidate() never lands as
current), force_missing_a / force_missing_b ("forget missing" while the background re-check runs), sidecar_case."""
import hashlib, os, subprocess, sys, tempfile, threading, time

CASES = ["forget", "restore", "remove_folder", "late_landing", "force_missing_a", "force_missing_b", "sidecar_case", "sidecar_migration", "deleted_preview", "thumbs_budget", "fav_filter"]

if len(sys.argv) < 2:
    bad = []
    for c in CASES:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), c], capture_output=True, text=True, timeout=120)
        ok = r.returncode == 0
        print(("ok   " if ok else "FAIL ") + c + ("" if ok else "\n" + r.stdout + r.stderr))
        bad += [] if ok else [c]
    print("catalog_race_check: " + ("OK" if not bad else "FAILED " + ",".join(bad)))
    sys.exit(1 if bad else 0)

case = sys.argv[1]
ROOT = tempfile.mkdtemp(prefix="rl1217_")
os.environ["REFLIB_DATA_DIR"] = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import storage, imagelib as L, forget, origin   # noqa: E402
SRC = os.path.join(ROOT, "photos"); os.makedirs(SRC)
FID = "a" * 32


def mk(i, side=False):
    p = os.path.join(SRC, f"syn_{i:05d}.png")
    with open(p, "wb") as f:
        f.write(i.to_bytes(4, "little") * 8)
    if side:
        open(os.path.splitext(p)[0] + ".json", "w").close()
    return p


def setup(n=200):
    files = {}
    for i in range(n):
        p = mk(i, side=(i % 10 == 0)); st = os.stat(p)
        files[p] = {"folder": FID, "size": st.st_size, "mtime": st.st_mtime, "hash": hashlib.sha256(p.encode()).hexdigest(), "first": 1}
    os.makedirs(os.path.join(storage.PLUGIN_DIR, "folders"), exist_ok=True)
    L._save_folders({"folders": [{"id": FID, "path": SRC, "recursive": True, "added": 1}], "files": files})
    L.invalidate()
    return files


def scan_commit():
    d = L.load_folders(); p = mk(9001); st = os.stat(p)
    d["files"][p] = {"folder": FID, "size": st.st_size, "mtime": st.st_mtime, "hash": "f" * 64, "first": 2}
    time.sleep(0.02); L._save_folders(d)


def slow_builder(gate, started):
    orig = L.list_images
    def slow(*a, **k):
        r = orig(*a, **k); started.set(); gate.wait(5); return r
    return orig, slow


if case in ("forget", "restore", "remove_folder"):
    files = setup()
    p0 = sorted(files)[5]; h0 = files[p0]["hash"]
    if case == "restore":
        forget.forget([h0]); L.catalog()
    L.catalog()
    L._set_scan(running=True)
    scan_commit()
    gate, started = threading.Event(), threading.Event()
    orig, slow = slow_builder(gate, started)
    L.list_images = slow
    A = threading.Thread(target=L.catalog); A.start(); started.wait(5); L.list_images = orig   # rebuild A started BEFORE the edit
    if case == "forget":
        forget.forget([h0]); expect = False
    elif case == "restore":
        forget.restore(FID, [h0]); expect = True
    else:
        L.remove_folder(FID); L.invalidate(); expect = False   # the plugin invalidates after non-read-only actions
    gate2, started2 = threading.Event(), threading.Event()
    orig, slow2 = slow_builder(gate2, started2)
    L.list_images = slow2
    Q1 = threading.Thread(target=L.catalog); Q1.start(); time.sleep(0.05); gate.set(); A.join(); started2.wait(5)
    q2 = L.catalog()   # a request after the edit returned, while Q1 rebuilds
    gate2.set(); Q1.join(); L.list_images = orig
    L._set_scan(running=False)
    assert (h0 in q2["by_hash"]) == expect, f"{case}: a request after the edit got the pre-edit catalog"
    assert (h0 in L.catalog()["by_hash"]) == expect, f"{case}: final state"

elif case == "late_landing":
    files = setup(); L.catalog()
    gate, started = threading.Event(), threading.Event()
    orig, slow = slow_builder(gate, started)
    scan_commit(); L.list_images = slow
    A = threading.Thread(target=L.catalog); A.start(); started.wait(5); L.list_images = orig
    L.invalidate()                     # an edit that changes nothing in the key files
    gate.set(); A.join()
    with L._cat_lock:
        assert L._cat["key"] is None, "a build that started before invalidate() must not land as current"
        assert L._cat["data_epoch"] != L._cat["epoch"]
    assert L.catalog() is not None and L._cat["key"] == L._index_key()

elif case in ("force_missing_a", "force_missing_b"):
    files = setup(300); L.catalog()
    victim = sorted(files)[250]; h = files[victim]["hash"]
    orig = os.path.isfile
    def slow(p):
        if str(p).startswith(SRC):
            time.sleep(0.002)
        return orig(p)
    os.path.isfile = slow
    if case == "force_missing_b":
        os.remove(victim)                   # gone before the background pass reaches it
    L._miss["last"] = 0
    L._missing_recheck(list(L.load_folders()["files"]))   # background pass (~0.6 s)
    time.sleep(0.05)
    assert L._miss["running"], "background pass running"
    if case == "force_missing_a":
        os.remove(victim)                   # gone while the background pass runs
    mh = forget.missing_hashes()            # "Olvidar no encontrados": must wait, then check the disk itself
    os.path.isfile = orig
    assert h in mh, "the forced check found the deleted file"
    # a file that came back is not reported
    open(victim, "wb").write(b"back")
    assert h not in forget.missing_hashes()

elif case == "sidecar_case":
    import posixpath
    files = setup(20)
    p = os.path.join(SRC, "Foo_Bar.png"); open(p, "wb").write(b"x"); open(os.path.join(SRC, "foo_bar.JSON"), "w").close()
    q = os.path.join(SRC, "Other.png"); open(q, "wb").write(b"y")
    real = posixpath.normcase
    posixpath.normcase = lambda s: s.lower()   # Windows-like names (ntpath.normcase lower-cases)
    try:
        cand = {c[0]: c[3] for c in L._candidates({"path": SRC, "recursive": True}, with_stat=True)}
        origin._side.clear(); origin._dir_names.clear()
        items = [{"hash": "1" * 64, "name": "Foo_Bar.png", "names": (), "path": p, "files": ()},
                 {"hash": "2" * 64, "name": "Other.png", "names": (), "path": q, "files": ()}]
        origin.resolve(items)
    finally:
        posixpath.normcase = real
    assert cand[p] == 1 and cand[q] == 0, cand
    assert [i["origin"] for i in items] == ["ai", "real"], items
elif case == "sidecar_migration":
    import json
    for i in range(50):
        p = os.path.join(SRC, f"m_{i:03d}.png"); open(p, "wb").write(i.to_bytes(4, "little") * 8)
        if i % 5 == 0:
            open(os.path.join(SRC, f"m_{i:03d}.json"), "w").close()
    L.add_folder(SRC); L.rescan()
    idx = os.path.join(storage.PLUGIN_DIR, "folders", "index.json")
    d = json.load(open(idx))
    for v in d["files"].values():
        v.pop("side", None)                       # an index written by 1.12.15 (no flags)
    json.dump(d, open(idx, "w")); L.invalidate(); origin._side.clear(); origin._dir_names.clear()
    s0 = {p: (v["hash"], v["size"]) for p, v in d["files"].items()}
    ai = lambda: {os.path.basename(i["path"]): i.get("origin") for i in L.catalog()["items"]}
    assert sum(1 for o in ai().values() if o == "ai") == 10, "old index read fine"
    L.rescan(); d1 = json.load(open(idx))
    assert all("side" in v for v in d1["files"].values()) and sum(1 for v in d1["files"].values() if v["side"]) == 10
    assert {p: (v["hash"], v["size"]) for p, v in d1["files"].items()} == s0, "hashes/sizes unchanged"
    open(os.path.join(SRC, "m_001.json"), "w").close(); os.remove(os.path.join(SRC, "m_000.json"))
    L.rescan(); by = ai()
    assert by["m_001.png"] == "ai" and by["m_000.png"] == "real", "a sidecar added/removed later is seen in a long-lived process"

elif case == "deleted_preview":
    from PIL import Image
    files = setup(20); ps = sorted(files)[:3]
    for k, p in enumerate(ps):
        Image.new("RGB", (64, 48), (k * 60, 10, 10)).save(p, "PNG")
    d = L.load_folders()
    for p in ps:
        st = os.stat(p); d["files"][p].update(size=st.st_size, mtime=st.st_mtime)
    L._save_folders(d); L.invalidate(); L.catalog()
    h = d["files"][ps[0]]["hash"]; os.remove(ps[0])
    pv = L.preview(h)
    assert pv is None or not pv.get("src"), pv
    assert not L.thumbs_for([h]).get(h)
    assert L.media_path(h) is None
    assert L.preview(d["files"][ps[1]]["hash"])["src"], "an existing file still previews"
elif case == "thumbs_budget":   # 1.12.18 (retest D)
    from PIL import Image
    files = setup(12); ps = sorted(files)
    for k, p in enumerate(ps):
        Image.new("RGB", (64, 48), (k * 20, 10, 10)).save(p, "PNG")
    d = L.load_folders()
    for p in ps:
        st = os.stat(p); d["files"][p].update(size=st.st_size, mtime=st.st_mtime)
    L._save_folders(d); L.invalidate(); L.catalog()
    hs = [d["files"][p]["hash"] for p in ps]
    made = []
    real_make, real_cached = L._make_thumb, L._cached_thumb
    L._make_thumb = lambda h, c, size, by=None: (made.append(h), real_make(h, c, size, by=by))[1]
    L._queue_thumbs = lambda later: None   # keep the background worker out of the count
    # the budget counts from the start: slow cache reads alone spend it, so nothing is generated synchronously
    L._cached_thumb = lambda h: (time.sleep(0.03), real_cached(h))[1]
    pend = []
    L.thumbs_for(hs[:6], budget=0.1, pending=pend)
    assert made == [] and len(pend) == 6, ("first generation must respect the budget", made, pend)
    L._cached_thumb = real_cached
    # a thumbnail request never waits for a catalog rebuild
    builds = [0]; cb = L._catalog_build
    def counting(*a, **k):
        builds[0] += 1; import traceback as _tb; _tb.print_stack(limit=6) if os.environ.get("DBG") else None; return cb(*a, **k)
    L._catalog_build = counting
    L.invalidate()
    pend = []; out = L.thumbs_for(hs[6:8], budget=5, pending=pend)
    assert builds[0] == 0, "thumbs_for rebuilt the catalog"
    assert all(out[h] for h in hs[6:8]) and not pend, (out, pend)
    # a hash the stale catalog doesn't know yet is pending (retried), not "no source"
    unknown = "e" * 64
    pend = []; out = L.thumbs_for([unknown], budget=5, pending=pend)
    assert out[unknown] is None and pend == [unknown] and builds[0] == 0
    # without a budget (callers that need the answer now) the fresh catalog is still used
    L.thumbs_for([unknown]); assert builds[0] == 1
elif case == "fav_filter":   # 1.12.18: shared favourites filter (both UIs send f.fav)
    files = setup(30); hs = [files[p]["hash"] for p in sorted(files)]
    L.catalog()
    L.set_tags(hs[:4], add=["favorita"]); L.set_tags(hs[4:6], add=["Favorita"]); L.set_tags(hs[3:8], add=["playa"])
    tot = lambda f: L.query(f, 0, 100, 0)["total"]
    ids = lambda f: [i["hash"] for i in L.query(f, 0, 100, 0)["items"]]
    assert tot({"fav": True}) == 6, tot({"fav": True})
    assert ids({"fav": True}) == ids({"tags": ["favorita"]}), "same as the tag filter"
    assert tot({"fav": True, "tags": ["playa"]}) == 3, "combines with other tags (AND)"
    assert tot({"fav": False}) == 30 and tot({}) == 30
    assert L._clean_filter({"fav": True})["fav"] is True and L._clean_filter({})["fav"] is False
else:
    raise SystemExit("unknown case " + case)
print("ok", case)
