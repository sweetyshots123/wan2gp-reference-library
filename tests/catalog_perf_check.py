"""1.12.16 catalog: single flight, stale-while-indexing, no per-item stat, sidecars from the scan listing, folders index
parsed once, one catalog() per query, scan commits every ~10 s. Synthetic temp folders only.
python3 tests/catalog_perf_check.py  (pytest runs it in its own process via tests/test_catalog_perf.py)"""
import hashlib, os, sys, tempfile, threading, time
ROOT = tempfile.mkdtemp(prefix="rl1216_")
os.environ["REFLIB_DATA_DIR"] = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import storage, imagelib as L, forget, origin   # noqa: E402

SRC = os.path.join(ROOT, "photos"); os.makedirs(SRC)
FID = "a" * 32


def _mk(i, side=False):
    p = os.path.join(SRC, f"img_{i:05d}.png")
    with open(p, "wb") as f:
        f.write(i.to_bytes(4, "little") * 8)
    if side:
        open(os.path.splitext(p)[0] + ".json", "w").close()
    return p


def _setup(n=300):
    files = {}
    for i in range(n):
        p = _mk(i, side=(i % 10 == 0)); st = os.stat(p)
        files[p] = {"folder": FID, "size": st.st_size, "mtime": st.st_mtime, "hash": hashlib.sha256(p.encode()).hexdigest(), "first": 1}
    os.makedirs(os.path.join(storage.PLUGIN_DIR, "folders"), exist_ok=True)
    L._save_folders({"folders": [{"id": FID, "path": SRC, "recursive": True, "added": 1}], "files": files})
    L.invalidate()


class Count:
    """Counts os.path.isfile calls on the synthetic photos folder from the calling thread only."""
    def __init__(self):
        self.n = 0; self._orig = os.path.isfile; self.tid = threading.get_ident()
    def __enter__(self):
        def f(p):
            if threading.get_ident() == self.tid and str(p).startswith(SRC):
                self.n += 1
            return self._orig(p)
        os.path.isfile = f; return self
    def __exit__(self, *a):
        os.path.isfile = self._orig


_setup()


def test_single_flight_one_build_for_many_callers():
    L.invalidate()
    builds = [0]; orig = L.list_images
    def slow(*a, **k):
        builds[0] += 1; time.sleep(0.3); return orig(*a, **k)
    L.list_images = slow
    try:
        out = []
        th = [threading.Thread(target=lambda: out.append(L.catalog())) for _ in range(8)]
        [t.start() for t in th]; [t.join() for t in th]
    finally:
        L.list_images = orig
    assert builds[0] == 1, builds
    assert len({id(x) for x in out}) == 1 and len(out[0]["items"]) == 300


def test_stale_while_indexing_only_for_scan_changes():
    base = L.catalog()
    orig = L.list_images; started = threading.Event(); release = threading.Event()
    def slow(*a, **k):
        started.set(); release.wait(5); return orig(*a, **k)
    L._set_scan(running=True)
    try:
        d = L.load_folders(); p = _mk(9001); st = os.stat(p)
        d["files"][p] = {"folder": FID, "size": st.st_size, "mtime": st.st_mtime, "hash": "f" * 64, "first": 2}
        time.sleep(0.01); L._save_folders(d)   # a scan commit
        L.list_images = slow
        t = threading.Thread(target=L.catalog); t.start(); started.wait(5)
        t0 = time.perf_counter(); got = L.catalog(); dt = time.perf_counter() - t0
        assert got is base and dt < 0.2, "stale catalog served at once while the rebuild runs"
        release.set(); t.join()
        L.list_images = orig
        assert "f" * 64 in L.catalog()["by_hash"], "the rebuild lands"
        # a non-scan change (here the tags index) never serves stale data, even while indexing: it waits for a build
        base2 = L.catalog(); started.clear(); release.clear()
        d = L.load_folders(); d["files"][p]["first"] = 5; time.sleep(0.01); L._save_folders(d)
        L.list_images = slow
        t = threading.Thread(target=L.catalog); t.start(); started.wait(5)
        tp = L._tags_path(); os.makedirs(os.path.dirname(tp), exist_ok=True)
        import json
        with open(tp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "tags": {}}, f)
        threading.Timer(0.3, release.set).start()
        t0 = time.perf_counter(); got = L.catalog(); dt = time.perf_counter() - t0
        t.join(); L.list_images = orig
        assert got is not base2 and dt >= 0.25, ("tags change waited for a fresh catalog", dt)
    finally:
        L.list_images = orig; release.set(); L._set_scan(running=False)


def test_no_stale_when_not_indexing():
    L.catalog()
    d = L.load_folders(); p = _mk(9002); st = os.stat(p)
    d["files"][p] = {"folder": FID, "size": st.st_size, "mtime": st.st_mtime, "hash": "e" * 64, "first": 3}
    time.sleep(0.01); L._save_folders(d)
    assert "e" * 64 in L.catalog()["by_hash"], "outside a scan a change is always seen by the next call"


def test_key_only_scan_changes():
    k1 = L._index_key()
    k2 = tuple((a[0], 1, 2) if a[0] == L._folders_index() else a for a in k1)
    k3 = tuple((a[0], 1, 2) if a[0] == L._tags_path() else a for a in k1)
    assert L._only_scan_changed(k1, k2) and not L._only_scan_changed(k1, k3) and not L._only_scan_changed(None, k1)


def test_build_does_not_stat_watched_files_and_parses_index_once():
    L.invalidate()
    loads = [0]; orig = L.load_folders
    def cnt():
        loads[0] += 1; return orig()
    L.load_folders = cnt
    try:
        with Count() as c:
            cat = L.catalog()
    finally:
        L.load_folders = orig
    assert c.n == 0, f"{c.n} isfile calls on watched files during a rebuild"
    assert loads[0] == 1, loads
    assert len(cat["items"]) >= 300


def test_missing_from_background_recheck():
    p = os.path.join(SRC, "img_00007.png"); h = L.load_folders()["files"][p]["hash"]
    os.rename(p, p + ".gone")
    try:
        L.missing_recheck_now()
        assert L.catalog()["by_hash"][h]["missing"] is True
        assert h in forget.missing_hashes(), "forget-missing acts on the exact disk state"
    finally:
        os.rename(p + ".gone", p)
    L.missing_recheck_now()
    assert L.catalog()["by_hash"][h]["missing"] is False
    # non-folder items keep the direct check
    assert forget.is_missing({"path": "/nope/x.png", "files": ()}) is True
    assert forget.is_missing({"path": p, "files": ()}, known={p: 1}, gone=frozenset([p])) is True
    assert forget.is_missing({"path": p, "files": ()}, known={p: 1}) is False


def test_sidecars_from_scan_listing_no_stat():
    L._scan_folder(L.load_folders()["folders"][0])
    files = L.load_folders()["files"]
    flagged = {p for p, v in files.items() if v.get("side")}
    assert flagged == {p for p in files if os.path.isfile(os.path.splitext(p)[0] + ".json")} and len(flagged) == 30
    origin._side.clear(); origin._dir_names.clear(); L.invalidate()
    with Count() as c:
        cat = L.catalog()
    assert c.n == 0
    ai = {i["path"] for i in cat["items"] if i.get("origin") == "ai"}
    assert flagged <= ai and len(ai & set(files)) == 30
    # legacy entries (no "side" yet): one directory listing, not a stat pair per file
    origin._side.clear(); origin._dir_names.clear()
    lst = [0]; ol = os.listdir
    os.listdir = lambda d: (lst.__setitem__(0, lst[0] + 1), ol(d))[1]
    try:
        items = [{"hash": "1" * 64, "name": "img_00010.png", "names": (), "path": os.path.join(SRC, "img_00010.png"), "files": ()},
                 {"hash": "2" * 64, "name": "img_00011.png", "names": (), "path": os.path.join(SRC, "img_00011.png"), "files": ()}]
        with Count() as c:
            origin.resolve(items)
    finally:
        os.listdir = ol
    assert c.n == 0 and lst[0] == 1 and [i["origin"] for i in items] == ["ai", "real"]


def test_one_catalog_call_per_query():
    L.catalog()
    n = [0]; orig = L.catalog
    def cnt():
        n[0] += 1; return orig()
    L.catalog = cnt
    try:
        r = L.query({}, 0, 120)
    finally:
        L.catalog = orig
    assert len(r["items"]) == 120 and n[0] <= 6, n   # filtered() / counts + once for the page (1.12.15: +2 per item = 240 more)


def test_scan_commits_every_10s():
    assert L.SCAN_COMMIT_SECONDS >= 10


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
    print("catalog_perf_check: OK")
