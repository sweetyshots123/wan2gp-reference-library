# 1.12.16 bench (from the slow-search diagnosis): python3 tests/bench_catalog_scan.py N_OLD N_NEW REPO
# Synthetic files in a temp dir; os.path.isfile slowed to 0.227 ms/file like a Google Drive folder; hashing 4 ms/file.
# 1.12.17: the scan is marked running (as the real scan worker does), so serving the previous catalog is exercised;
# prints how many rebuilds ran and how many requests were answered with the previous catalog.
import os, sys, time, threading, hashlib, random, tempfile, statistics as S
REPO=sys.argv[3]
root = tempfile.mkdtemp(prefix="rlbench_"); os.environ["REFLIB_DATA_DIR"] = os.path.join(root, "data")
sys.path.insert(0, REPO)
from reflib_core import storage, imagelib as L
src = os.path.join(root, "photos"); os.makedirs(src)
_isf=os.path.isfile
def slow_isfile(p):
    if str(p).startswith(src): time.sleep(0.000227)
    return _isf(p)
os.path.isfile=slow_isfile
N_OLD, N_NEW = int(sys.argv[1]), int(sys.argv[2])
words=["grome","img","screenshot","beach","portrait","cat"]
def mk(i):
    p=os.path.join(src,f"{random.choice(words)}_{i:06d}.png"); open(p,"wb").write(i.to_bytes(4,"little")*8); return p
files={}
fid="a"*32
for i in range(N_OLD):
    p=mk(i); st=os.stat(p); files[p]={"folder":fid,"size":st.st_size,"mtime":st.st_mtime,"hash":hashlib.sha256(p.encode()).hexdigest(),"first":time.time()}
os.makedirs(os.path.join(storage.PLUGIN_DIR,"folders"),exist_ok=True)
L._save_folders({"folders":[{"id":fid,"path":src,"recursive":True,"added":time.time()}],"files":files})
def tq():
    t=time.perf_counter(); L.query({"q":"grome"},0,120); return (time.perf_counter()-t)*1000
L.invalidate(); print("cold rebuild+query %.0f ms" % tq())
for i in range(N_OLD,N_OLD+N_NEW): mk(i)
_fh=storage._file_hash
storage._file_hash=lambda p:(time.sleep(0.004),_fh(p))[1]
done=threading.Event(); lat=[]
builds=[0]; served_prev=[0]
if hasattr(L, "_catalog_build"):
    _cb=L._catalog_build
    def _cb2(*a, **k):
        builds[0]+=1; return _cb(*a, **k)
    L._catalog_build=_cb2
_cat0=L.catalog
def _cat_count():
    with L._cat_lock:
        before=L._cat["data"]; fresh=L._cat["key"]==L._index_key()
    r=_cat0()
    if not fresh and r is before: served_prev[0]+=1
    return r
L.catalog=_cat_count
def scanner():
    L._set_scan(running=True)
    try:
        t=time.perf_counter(); L._scan_folder(L.load_folders()["folders"][0]); print("scan %.1fs"%(time.perf_counter()-t))
    finally:
        L._set_scan(running=False); done.set()
def client():
    while not done.is_set():
        lat.append(tq()); L.thumbs_for([],220); time.sleep(0.05)
th=[threading.Thread(target=scanner)]+[threading.Thread(target=client) for _ in range(3)]
[t.start() for t in th]; [t.join() for t in th]
print("rebuilds during scan %d, requests answered with the previous catalog %d" % (builds[0], served_prev[0]))
lat.sort(); print("queries during scan n=%d med %.0f p95 %.0f max %.0f ms" % (len(lat),S.median(lat),lat[int(len(lat)*.95)],lat[-1]))
