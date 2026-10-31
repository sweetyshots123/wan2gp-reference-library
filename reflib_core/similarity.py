"""Pose + face similarity search (1.8.4+), shared by the classic explorer and the Galería through `sim_*` ilib actions.

Everything lives here; the hosts only route `sim_*` actions to handle() (see SIMILARITY_API.md for the contract).

* Models run in a separate process (simworker.py) started with the tagging-engine Python (setting "python"; default
  REFLIB_SIM_PYTHON, else the Python running WanGP). Lazy: the process starts on the first job / search and is stopped
  after IDLE_UNLOAD seconds without work, which frees the GPU. While WanGP generates (host busy()) the job waits.
* Index: <data>/similarity/ — meta.json (per image: persons / faces counts, size, error) + pose.npz (COCO-17 keypoints,
  float16) + face.npz (L2-normalised embeddings, float16). Separate files: existing library data are never touched.
  Saves are atomic (tmp + replace) every SAVE_EVERY images and at the end of a job.
* Search: brute-force cosine in numpy over every indexed person / face (15k images = well under 100 ms).
* Result sets: a search returns an id ("sid"); the explorer shows it as a normal filter {"sim": sid} (imagelib hook),
  ordered by similarity unless another sort is picked, so nav history / selection / paging work unchanged.
"""
from __future__ import annotations
import base64, json, os, subprocess, sys, threading, time, uuid, zipfile
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from . import posesim
from . import actions as _actions

BUSY: Callable[[], bool] = lambda: False   # set by the host (WanGP: "a generation is running" -> indexing waits)

VERSION = 1
SAVE_EVERY = 50
BATCH = 8
IDLE_UNLOAD = 120.0
SYNC_EVERY = 60.0
RESULTS_KEEP = 30
DEFAULTS = {"python": "", "face_model": "arcface", "auto": True, "gpu": True, "models_dir": "", "w_pose": 0.5,
            "threshold": 0.0, "mirror": True, "limit": 1000}
# Face recognisers the user can pick (Ajustes > Modelo de caras). Each keeps its own vectors (never mixed).
FACE_MODELS = {   # id -> file, aliases, dim, label, licence
    "arcface": {"file": "w600k_r50.onnx", "alias": ["buffalo_l/w600k_r50.onnx"], "dim": 512, "label": "ArcFace w600k_r50 (buffalo_l)",
                "license": "InsightFace: non-commercial research use only"},
    "glintr100": {"file": "glintr100.onnx", "alias": ["antelopev2/glintr100.onnx"], "dim": 512, "label": "ArcFace glintr100 (antelopev2, larger)",
                  "license": "InsightFace: non-commercial research use only"},
    "adaface": {"file": "adaface_ir_101.onnx", "alias": ["adaface/adaface_ir_101.onnx"], "dim": 512, "label": "AdaFace IR-101",
                "license": "AdaFace code MIT; weights trained on research face datasets (MS1M/WebFace): non-commercial research use only"},
    "sface": {"file": "face_recognition_sface_2021dec.onnx", "alias": ["sface.onnx"], "dim": 128, "label": "SFace (OpenCV zoo, fallback)",
              "license": "Apache-2.0"},
}
FACE_DIM = {k: v["dim"] for k, v in FACE_MODELS.items()}
MODEL_FILES = {   # name -> (url, size MB, licence)
    "yolox_l.onnx": ("https://huggingface.co/DeepBeepMeep/Wan2.1/resolve/main/pose/yolox_l.onnx", 217, "Apache-2.0 (YOLOX, DWPose)"),
    "dw-ll_ucoco_384.onnx": ("https://huggingface.co/DeepBeepMeep/Wan2.1/resolve/main/pose/dw-ll_ucoco_384.onnx", 134, "Apache-2.0 (DWPose / RTMPose)"),
    "face_detection_yunet_2023mar.onnx": ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", 0.2, "MIT (YuNet, OpenCV zoo)"),
    "w600k_r50.onnx": ("https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip", 174, "InsightFace buffalo_l: non-commercial research use"),
    "glintr100.onnx": ("https://huggingface.co/DIAMONIK7777/antelopev2/resolve/main/glintr100.onnx", 261, "InsightFace antelopev2: non-commercial research use"),
    "adaface_ir_101.onnx": ("https://huggingface.co/danelcsb/face/resolve/main/adaface_ir_101.onnx", 261, "AdaFace IR-101: research use (training data licence)"),
    "face_recognition_sface_2021dec.onnx": ("https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx", 37, "Apache-2.0 (SFace, OpenCV zoo)"),
}
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simworker.py")


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _atomic_npz(path, **arrays):
    tmp = path + ".tmp.npz"
    np.savez(tmp, **arrays)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------------------- index
class SimIndex:
    """Vectors per image hash. In memory: dict hash -> {"p": (n,17,3) f16, "f": (m,D) f16, "w", "h", "err"}."""

    def __init__(self, root: str):
        self.dir = root
        self.lock = threading.RLock()
        self.items: Dict[str, Dict[str, Any]] = {}
        self.face_model = ""     # legacy single-model meta (pre per-vector model ids)
        self.active = "arcface"  # face model whose vectors are searched / counted; others are kept but never mixed
        self.rev = 0
        self._mat = None
        self.load()

    @property
    def meta_path(self):
        return os.path.join(self.dir, "meta.json")

    def load(self):
        with self.lock:
            self.items = {}
            try:
                with open(self.meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:
                return
            self.face_model = meta.get("face_model", "")
            done = {}   # hash -> face models indexed (meta "nf" dict; legacy int = meta face_model)
            for h, m in (meta.get("items") or {}).items():
                nf = m.get("nf")
                done[h] = set(nf) if isinstance(nf, dict) else ({self.face_model} if self.face_model else set())
                self.items[h] = {"p": np.zeros((0, 17, 3), np.float16), "faces": {}, "w": m.get("w", 0), "h": m.get("h", 0), "err": m.get("err", ""), "t": m.get("t", 0)}
            files = [("pose.npz", "p", None)] + [("face-%s.npz" % fm, "f", fm) for fm in FACE_DIM]
            if self.face_model in FACE_DIM:
                files.append(("face.npz", "f", self.face_model))   # legacy file
            for name, key, fm in files:
                try:
                    with np.load(os.path.join(self.dir, name), allow_pickle=False) as z:
                        keys, own, vec = z["keys"], z["owner"], z["vec"]
                        model = z["model"] if "model" in z.files else None
                except Exception:
                    continue
                if fm is not None:
                    if vec.ndim != 2 or vec.shape[1] != FACE_DIM[fm]:
                        continue
                    if model is not None:   # per-vector model id: drop anything that is not this file's model
                        keep = model == fm
                        own, vec = own[keep], vec[keep]
                order = np.argsort(own, kind="stable")
                own, vec = own[order], vec[order]
                cuts = np.searchsorted(own, np.arange(len(keys) + 1))
                for k, h in enumerate(keys.tolist()):
                    if h in self.items:
                        if fm is None:
                            self.items[h]["p"] = vec[cuts[k]:cuts[k + 1]]
                        elif fm in done.get(h, ()) and fm not in self.items[h]["faces"]:
                            self.items[h]["faces"][fm] = vec[cuts[k]:cuts[k + 1]]
            self.rev += 1

    def save(self):
        with self.lock:
            os.makedirs(self.dir, exist_ok=True)
            keys = list(self.items)
            for name, fm, shape in [("pose.npz", None, (0, 17, 3))] + [("face-%s.npz" % m, m, (0, d)) for m, d in FACE_DIM.items()]:
                vecs, own = [], []
                for k, h in enumerate(keys):
                    v = self.items[h]["p"] if fm is None else self.items[h]["faces"].get(fm)
                    if v is not None and len(v):
                        vecs.append(v); own.append(np.full(len(v), k, np.int32))
                n = sum(len(v) for v in vecs)
                extra = {} if fm is None else {"model": np.full(n, fm, dtype="<U16")}   # model id per vector
                _atomic_npz(os.path.join(self.dir, name), keys=np.array(keys, dtype=str),
                            owner=np.concatenate(own) if own else np.zeros(0, np.int32),
                            vec=np.concatenate(vecs).astype(np.float16) if vecs else np.zeros(shape, np.float16), **extra)
            try:
                os.remove(os.path.join(self.dir, "face.npz"))   # legacy, now split per model
            except OSError:
                pass
            _atomic_json(self.meta_path, {"version": VERSION, "face_models": sorted(FACE_DIM), "pose_model": "dwpose-body17",
                                          "items": {h: {"np": int(len(e["p"])), "nf": {m: int(len(v)) for m, v in e["faces"].items()},
                                                        "w": e.get("w", 0), "h": e.get("h", 0), "err": e.get("err", ""), "t": e.get("t", 0)}
                                                    for h, e in self.items.items()}})

    def put(self, h: str, res: Dict[str, Any], face_model: str):
        with self.lock:
            e = self.items.get(h) or {"p": np.zeros((0, 17, 3), np.float16), "faces": {}}
            face_model = res.get("face_model") or face_model   # the model that really produced the vectors
            if not res.get("ok"):
                e.update(err=str(res.get("error") or "error")[:120], t=time.time())
            else:
                if "persons" in res:
                    e["p"] = np.asarray([p["kp"] for p in res["persons"]], np.float16).reshape(-1, 17, 3)
                if "faces" in res:
                    D = FACE_DIM[face_model]
                    f = np.stack([np.frombuffer(base64.b64decode(f["emb"]), np.float16) for f in res["faces"]]) if res["faces"] else np.zeros((0, D), np.float16)
                    if f.shape[1] != D:
                        raise ValueError("face vector dim %d does not match %s" % (f.shape[1], face_model))
                    e["faces"][face_model] = f
                e.update(w=res.get("w", 0), h=res.get("h", 0), err="", t=time.time())
            self.items[h] = e
            self.rev += 1

    def face(self, h: str, fm: Optional[str] = None):
        e = self.items.get(h)
        return None if not e else e["faces"].get(fm or self.active)

    def has(self, h: str, fm: Optional[str] = None) -> bool:
        e = self.items.get(h)
        return bool(e) and not e.get("err") and (fm or self.active) in e["faces"]

    def needs_faces_only(self, h: str, fm: Optional[str] = None) -> bool:
        """Pose done, faces missing for this model (e.g. after switching face model)."""
        e = self.items.get(h)
        return bool(e) and not e.get("err") and e.get("t", 0) > 0 and (fm or self.active) not in e["faces"]

    def matrices(self):
        """(keys, pose_kp (P,17,3) f32, pose_owner, face (F,D) f32, face_owner), cached per revision."""
        with self.lock:
            if self._mat and self._mat[0] == (self.rev, self.active):
                return self._mat[1]
            keys = list(self.items)
            P, Po, F, Fo = [], [], [], []
            for k, h in enumerate(keys):
                e = self.items[h]
                if len(e["p"]):
                    P.append(e["p"]); Po.append(np.full(len(e["p"]), k, np.int32))
                f = e["faces"].get(self.active)
                if f is not None and len(f):
                    F.append(f); Fo.append(np.full(len(f), k, np.int32))
            D = FACE_DIM.get(self.active, 512)
            m = (keys, np.concatenate(P).astype(np.float32) if P else np.zeros((0, 17, 3), np.float32), np.concatenate(Po) if Po else np.zeros(0, np.int32),
                 np.concatenate(F).astype(np.float32) if F else np.zeros((0, D), np.float32), np.concatenate(Fo) if Fo else np.zeros(0, np.int32))
            self._mat = ((self.rev, self.active), m)
            return m

    def stats(self) -> Dict[str, int]:
        with self.lock:
            return {"images": sum(1 for e in self.items.values() if not e.get("err")), "errors": sum(1 for e in self.items.values() if e.get("err")),
                    "persons": int(sum(len(e["p"]) for e in self.items.values())),
                    "faces": int(sum(len(e["faces"].get(self.active, ())) for e in self.items.values())),
                    "faces_pending": sum(1 for h in self.items if self.needs_faces_only(h)), "face_model": self.active}


def search(index: SimIndex, queries: List[Dict[str, np.ndarray]], mode: str = "both", w_pose: float = 0.5, threshold: float = 0.0,
           agg: str = "any", mirror: bool = True, limit: int = 1000, allowed: Optional[set] = None) -> List[Dict[str, Any]]:
    """queries: [{"p": (n,17,3), "f": (m,D)}] (one per query photo). -> [{hash, score, pose, face}] best first."""
    keys, P, Po, F, Fo = index.matrices()
    N = len(keys)
    per_q, per_p, per_f = [], [], []
    for q in queries:
        sp = sf = None
        if mode in ("pose", "both"):
            rows = np.zeros(len(P), np.float32)
            for person in np.asarray(q.get("p") if q.get("p") is not None else np.zeros((0, 17, 3)), np.float32):
                rows = np.maximum(rows, posesim.pose_scores(person, P, mirror=mirror))
            sp = posesim.per_image_max(Po, rows, N)
        if mode in ("face", "both"):
            qf = q.get("f")
            rows = posesim.face_scores(qf, F) if qf is not None and len(qf) and len(F) else np.zeros(len(F), np.float32)
            sf = posesim.per_image_max(Fo, rows, N)
        per_q.append(posesim.combine(sp, sf, mode, w_pose)); per_p.append(sp); per_f.append(sf)
    if not per_q:
        return []
    tot = posesim.aggregate(per_q, agg)
    pp = posesim.aggregate([x for x in per_p if x is not None], agg) if mode != "face" else None
    ff = posesim.aggregate([x for x in per_f if x is not None], agg) if mode != "pose" else None
    order = np.argsort(-tot, kind="stable")
    out = []
    for k in order:
        s = float(tot[k])
        if s <= 0 or s < threshold:
            break
        h = keys[k]
        if allowed is not None and h not in allowed:
            continue
        out.append({"hash": h, "score": round(s, 4), "pose": None if pp is None else round(float(pp[k]), 4), "face": None if ff is None else round(float(ff[k]), 4)})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------------------------------- worker process
class WorkerProc:
    def __init__(self, python: str, cfg: Dict[str, Any], log: Callable[[str], None] = print):
        self.python, self.cfg, self.log = python, cfg, log
        self.p: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.n = 0

    def start(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}   # a separate env: never WanGP's paths
        logp = self.cfg.get("log")
        err = open(logp, "w", encoding="utf-8") if logp else subprocess.DEVNULL
        try:
            self.p = subprocess.Popen([self.python, "-u", WORKER, json.dumps(self.cfg)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=err, text=True, encoding="utf-8", creationflags=flags, env=env)
        finally:
            if logp:
                err.close()
        line = self.p.stdout.readline()
        for _ in range(50):   # sitecustomize / banners printed before the worker redirects stdout
            if not line or line.strip().startswith("{"):
                break
            line = self.p.stdout.readline()
        if not line.strip().startswith("{"):
            self.stop()
            tail = ""
            try:
                with open(logp, encoding="utf-8", errors="replace") as fh:
                    tail = fh.read()[-300:].strip().splitlines()[-1]
            except Exception:
                pass
            raise RuntimeError("similarity worker did not start (python: %s) %s" % (self.python, tail))

    def call(self, req: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self.start()
            self.n += 1
            req = dict(req, id=self.n)
            self.p.stdin.write(json.dumps(req) + "\n"); self.p.stdin.flush()
            line = self.p.stdout.readline()
            if not line:
                self.stop()
                raise RuntimeError("similarity worker exited")
            return json.loads(line)

    def alive(self) -> bool:
        return self.p is not None and self.p.poll() is None

    def stop(self):
        p, self.p = self.p, None
        if p is not None:
            try:
                p.stdin.write('{"op": "quit"}\n'); p.stdin.flush(); p.wait(5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


# ---------------------------------------------------------------------------------------------------- service
class SimService:
    def __init__(self, data_dir: str, catalog: Callable[[], Dict], busy: Callable[[], bool] = lambda: False, log: Callable[[str], None] = print,
                 model_dirs: Optional[List[str]] = None):
        self.dir = os.path.join(data_dir, "similarity")
        self.catalog, self.busy, self.log = catalog, busy, log
        self.extra_dirs = model_dirs or []
        self.index = SimIndex(self.dir)
        self.face_only = set()
        self.index.active = self.settings()["face_model"]
        self.lock = threading.RLock()
        self.pending: List[str] = []
        self.paused = False
        self.cancel_flag = False
        self.thread: Optional[threading.Thread] = None
        self.worker: Optional[WorkerProc] = None
        self.last_used = 0.0
        self.results: Dict[str, Dict[str, Any]] = {}
        self.st = {"running": False, "done": 0, "total": 0, "failed": 0, "waiting": "", "error": "", "per_image_ms": 0}
        self._sync_t = 0.0
        self._hint = 0.0

    # settings
    @property
    def settings_path(self):
        return os.path.join(self.dir, "settings.json")

    def settings(self) -> Dict[str, Any]:
        try:
            with open(self.settings_path, encoding="utf-8") as fh:
                return dict(DEFAULTS, **json.load(fh))
        except Exception:
            return dict(DEFAULTS)

    def save_settings(self, upd: Dict[str, Any]) -> Dict[str, Any]:
        s = self.settings()
        for k, v in (upd or {}).items():
            if k in DEFAULTS:
                s[k] = type(DEFAULTS[k])(v) if not isinstance(DEFAULTS[k], bool) else bool(v)
        if s["face_model"] not in FACE_DIM:
            s["face_model"] = "arcface"
        old = self.settings()["face_model"]
        os.makedirs(self.dir, exist_ok=True)
        _atomic_json(self.settings_path, s)
        self.stop_worker()
        if s["face_model"] != old:
            self.st["face_fallback"] = ""
            self.index.active = s["face_model"]
            if self.index.items:
                self.enqueue()   # re-index faces only (pose vectors are model-independent)
        return s

    def python(self) -> str:
        return self.settings().get("python") or os.environ.get("REFLIB_SIM_PYTHON") or sys.executable

    def model_dirs(self) -> List[str]:
        s = self.settings()
        ds = [s.get("models_dir") or "", os.path.join(self.dir, "models")] + self.extra_dirs
        return [d for d in dict.fromkeys(ds) if d]

    def missing_models(self) -> List[str]:
        fm = self.settings()["face_model"]
        need = ["yolox_l.onnx", "dw-ll_ucoco_384.onnx", "face_detection_yunet_2023mar.onnx",
                FACE_MODELS["sface" if self.st.get("face_fallback") else fm]["file"]]
        return [n for n in need if not self.model_found(n)]

    def model_found(self, n: str) -> bool:
        alias = {"face_detection_yunet_2023mar.onnx": ["yunet.onnx"], **{m["file"]: m["alias"] for m in FACE_MODELS.values()}}
        return any(os.path.isfile(os.path.join(d, x)) for d in self.model_dirs() for x in [n, "pose/" + n] + alias.get(n, []))

    def face_models(self) -> List[Dict[str, Any]]:
        """Per-model status for the settings list: downloaded?, images with faces computed for it."""
        with self.index.lock:
            done = {k: 0 for k in FACE_MODELS}
            for e in self.index.items.values():
                if not e.get("err"):
                    for k in e["faces"]:
                        if k in done:
                            done[k] += 1
        return [{"id": k, "label": m["label"], "license": m["license"], "dim": m["dim"], "mb": MODEL_FILES[m["file"]][1],
                 "downloaded": self.model_found(m["file"]), "images": done[k]} for k, m in FACE_MODELS.items()]

    def download_models(self) -> List[str]:
        """Fetch missing weights into <data>/similarity/models (WanGP's ckpts/pose copies are reused when present)."""
        import urllib.request
        d = os.path.join(self.dir, "models"); os.makedirs(d, exist_ok=True)
        got = []
        for n in self.missing_models():
            url = MODEL_FILES[n][0]
            self.st["waiting"] = "download:" + n
            tmp = os.path.join(d, n + ".part")
            self.st["download"] = {"file": n, "done": 0, "total": int(MODEL_FILES[n][1] * 1e6)}
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as fh:   # chunked, progress in status
                self.st["download"]["total"] = int(r.headers.get("Content-Length") or self.st["download"]["total"])
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    fh.write(b); self.st["download"]["done"] += len(b)
            if url.endswith(".zip"):
                with zipfile.ZipFile(tmp) as z:
                    member = next(m for m in z.namelist() if m.endswith(n))
                    with z.open(member) as src, open(os.path.join(d, n), "wb") as dst:
                        dst.write(src.read())
                os.remove(tmp)
            else:
                os.replace(tmp, os.path.join(d, n))
            got.append(n)
        self.st["waiting"] = ""; self.st["download"] = None
        return got

    def _worker(self) -> WorkerProc:
        if self.worker is None:
            s = self.settings()
            self.worker = WorkerProc(self.python(), {"dirs": self.model_dirs(), "face_model": s["face_model"], "gpu": s["gpu"],
                                                         "face_files": {k: [m["file"]] + m["alias"] for k, m in FACE_MODELS.items()}, "log": os.path.join(self.dir, "worker.log")}, self.log)
        self.last_used = time.time()
        return self.worker

    def stop_worker(self):
        w, self.worker = self.worker, None
        if w:
            w.stop()

    def analyse(self, paths: List[str], pose: bool = True) -> List[Dict[str, Any]]:
        if self.missing_models():
            try:
                self.download_models()
            except Exception as e:   # ArcFace unavailable -> the worker falls back to SFace
                self.log("[reflib] similarity: model download failed: %s" % e)
                if "face_recognition_sface_2021dec.onnx" not in self.missing_models() or self.settings()["face_model"] == "sface":
                    raise
                self.st["face_fallback"] = "download: " + str(e)[:120]
                self.download_models()
        r = self._worker().call({"op": "analyse", "paths": paths, "pose": pose, "face": True})
        self.last_used = time.time()
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "worker error")
        if r.get("face_model") in FACE_DIM:
            self.index.active = r["face_model"]
            if r.get("face_fallback"):
                self.st["face_fallback"] = r["face_fallback"]
        n = max(1, len(paths))
        self.st["per_image_ms"] = int(1000 * float(r.get("secs") or 0) / n)
        return r["results"]

    # library
    def _path(self, item) -> Optional[str]:
        for p in (item.get("path"),) + tuple(item.get("files") or ()):
            if p and os.path.isfile(p):
                return p
        return None

    def image_hashes(self) -> List[str]:
        return [i["hash"] for i in self.catalog()["items"] if i.get("kind", "image") == "image" and not i.get("missing")]

    # jobs
    def enqueue(self, hashes: Optional[List[str]] = None, force: bool = False, faces_only: bool = False) -> Dict[str, Any]:
        allh = self.image_hashes()
        imgs = set(allh)
        hs = [h for h in (hashes if hashes is not None else allh) if h in imgs]
        if faces_only:   # "Calcular caras": the selected model only, pose untouched
            fo = [h for h in hs if self.index.needs_faces_only(h) or (force and self.index.has(h))]
            hs = []
        elif not force:
            fo = [h for h in hs if self.index.needs_faces_only(h)]
            hs = [h for h in hs if not self.index.has(h)]
        else:
            fo = []
        hs = hs + [h for h in fo if h not in hs]
        self.face_only.difference_update(set(hs) - set(fo))
        self.face_only.update(fo)
        with self.lock:
            seen = set(self.pending)
            new = [h for h in hs if h not in seen]
            self.pending.extend(new)
            self.st["total"] += len(new)
            self.cancel_flag = False
            self._ensure_thread()
        return {"queued": len(new), "pending": len(self.pending)}

    def _ensure_thread(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, name="reflib-similarity", daemon=True)
            self.thread.start()

    def pause(self, on: bool):
        self.paused = bool(on)

    def cancel(self):
        with self.lock:
            self.cancel_flag = True
            self.pending.clear()

    def status(self) -> Dict[str, Any]:
        self.maybe_sync()
        s = self.settings()
        return dict(self.st, pending=len(self.pending), paused=self.paused, index=self.index.stats(), library=len(self.image_hashes()),
                    worker=bool(self.worker and self.worker.alive()), python=self.python(), face_model=self.index.active, face_model_setting=s["face_model"],
                    face_fallback=self.st.get("face_fallback", ""), face_models=self.face_models(),
                    missing_models=self.missing_models(), settings=s)

    def maybe_sync(self):
        """Auto mode: new library images are queued (once indexing was started at least once)."""
        if time.time() - self._sync_t < SYNC_EVERY:
            return
        self._sync_t = time.time()
        if self.settings().get("auto") and self.index.items and not self.pending:
            try:
                self.enqueue()
            except Exception:
                pass

    def _run(self):
        by = None
        n_since = 0
        self.st.update(running=True, error="")
        try:
            while True:
                if self.cancel_flag:
                    break
                if self.paused or self.busy():
                    self.st["waiting"] = "paused" if self.paused else "busy"
                    time.sleep(0.5)
                    continue
                self.st["waiting"] = ""
                with self.lock:
                    batch, self.pending[:BATCH] = self.pending[:BATCH], []
                if not batch:
                    break
                by = self.catalog()["by_hash"]
                todo = [(h, self._path(by.get(h) or {})) for h in batch]
                fo = {h for h, _ in todo if h in self.face_only}
                paths = [p for h, p in todo if p and h not in fo]
                fpaths = [p for h, p in todo if p and h in fo]
                try:
                    r_full = iter(self.analyse(paths)) if paths else iter(())
                    r_face = iter(self.analyse(fpaths, pose=False)) if fpaths else iter(())
                except Exception as e:
                    self.st["error"] = str(e)[:200]
                    self.log("[reflib] similarity: " + self.st["error"])
                    with self.lock:
                        self.pending[:0] = batch
                    time.sleep(5)
                    if not (self.worker and self.worker.alive()) and "did not start" in self.st["error"]:
                        break
                    continue
                fm = self.index.active
                for h, p in todo:
                    r = (next(r_face) if h in fo else next(r_full)) if p else {"ok": False, "error": "file not found"}
                    self.face_only.discard(h)
                    self.index.put(h, r, fm)
                    self.st["done"] += 1
                    self.st["failed"] += 0 if r.get("ok") else 1
                    n_since += 1
                if n_since >= SAVE_EVERY:
                    self.index.save(); n_since = 0
        finally:
            if n_since:
                self.index.save()
            self.st.update(running=False, waiting="")
            if not self.pending:
                self.st.update(done=0, total=0, failed=0)
            threading.Thread(target=self._idle_unload, daemon=True).start()

    def _idle_unload(self):
        time.sleep(IDLE_UNLOAD + 1)
        if time.time() - self.last_used >= IDLE_UNLOAD and not (self.thread and self.thread.is_alive()):
            self.stop_worker()

    # search
    def _query_vectors(self, hashes: List[str], files: List[str]) -> List[Dict[str, np.ndarray]]:
        by = self.catalog()["by_hash"]
        need = [h for h in hashes if not self.index.has(h) and self._path(by.get(h) or {})]
        if need:
            res = self.analyse([self._path(by[h]) for h in need])
            fm = self.index.active
            for h, r in zip(need, res):
                self.index.put(h, r, fm)
            self.index.save()
        qs = []
        for h in hashes:
            e = self.index.items.get(h)
            if e and not e.get("err"):
                f = self.index.face(h)
                qs.append({"p": np.asarray(e["p"], np.float32), "f": None if f is None else np.asarray(f, np.float32)})
        if files:
            for r in self.analyse(files):
                if r.get("ok"):
                    qs.append({"p": np.asarray([p["kp"] for p in r.get("persons", [])], np.float32).reshape(-1, 17, 3),
                               "f": np.stack([np.frombuffer(base64.b64decode(f["emb"]), np.float16).astype(np.float32) for f in r["faces"]]) if r.get("faces") else None})
        return qs

    def run_search(self, hashes: List[str], files: List[str], mode="both", w_pose=None, threshold=None, agg="any", mirror=None, limit=None) -> Dict[str, Any]:
        s = self.settings()
        mode = mode if mode in posesim.MODES else "both"
        agg = agg if agg in posesim.AGGS else "any"
        t0 = time.time()
        hashes = list(hashes or [])[:50]
        qs = self._query_vectors(hashes, files)
        tq = time.time() - t0
        info = {"queries": len(qs), "persons": sum(len(q["p"]) for q in qs), "faces": sum(0 if q["f"] is None else len(q["f"]) for q in qs)}
        if not qs:
            return {"ok": False, "error": "no_query", **info}
        t1 = time.time()
        allowed = set(self.image_hashes())
        res = search(self.index, qs, mode, s["w_pose"] if w_pose is None else float(w_pose), s["threshold"] if threshold is None else float(threshold),
                     agg, s["mirror"] if mirror is None else bool(mirror), int(limit or s["limit"]), allowed)
        ts = time.time() - t1
        sid = "s" + uuid.uuid4().hex[:10]
        params = {"mode": mode, "agg": agg, "hashes": list(hashes)[:50], "files": len(files)}
        with self.lock:
            self.results[sid] = {"scores": {r["hash"]: r["score"] for r in res}, "rows": {r["hash"]: r for r in res}, "params": params, "t": time.time()}
            for k in sorted(self.results, key=lambda k: self.results[k]["t"])[:-RESULTS_KEEP]:
                del self.results[k]
        return {"ok": True, "sid": sid, "n": len(res), "top": res[:20], "params": params, "ms": {"query": int(tq * 1000), "search": int(ts * 1000)}, **info}

    def scores(self, sid: str) -> Optional[Dict[str, float]]:
        r = self.results.get(sid)
        return r["scores"] if r else None

    def row(self, sid: str, h: str) -> Optional[Dict[str, Any]]:
        r = self.results.get(sid)
        return r["rows"].get(h) if r else None

    def info(self, h: str) -> Dict[str, Any]:
        e = self.index.items.get(h)
        if not e:
            return {"indexed": False}
        return {"indexed": not e.get("err"), "error": e.get("err", ""), "w": e.get("w"), "h": e.get("h"),
                "persons": [{"kp": np.round(np.asarray(p, np.float32), 1).tolist()} for p in e["p"]],
                "faces": int(len(e["f"])) if e.get("f") is not None else 0}


# ---------------------------------------------------------------------------------------------------- host glue
_SVC: Optional[SimService] = None


def service(data_dir: Optional[str] = None, **kw) -> SimService:
    """The process-wide service. The first call wires the imagelib "sim" filter hook."""
    global _SVC
    if _SVC is None:
        from . import imagelib, storage
        dd = data_dir or os.path.dirname(storage.COLLECTIONS_DIR)
        dirs = kw.pop("model_dirs", None) or [os.path.join(os.getcwd(), "ckpts", "pose"), os.path.join(os.getcwd(), "ckpts")]
        kw.setdefault("busy", lambda: BUSY())
        _SVC = SimService(dd, imagelib.catalog, model_dirs=dirs, **kw)
        imagelib.SIMILARITY = _SVC.scores
    return _SVC


def _save_drops(svc: SimService, files) -> List[str]:
    """Dropped query photos ({"name", "data": base64 or data URL}) -> temp files (deleted after the search)."""
    out = []
    d = os.path.join(svc.dir, "tmp"); os.makedirs(d, exist_ok=True)
    for f in (files or [])[:12]:
        data = str((f or {}).get("data") or "")
        data = data.split(",", 1)[1] if data.startswith("data:") else data
        try:
            raw = base64.b64decode(data)
        except Exception:
            continue
        if not raw or len(raw) > 40 * 1024 * 1024:
            continue
        p = os.path.join(d, uuid.uuid4().hex + os.path.splitext(str(f.get("name") or ".jpg"))[1][:6])
        open(p, "wb").write(raw)
        out.append(p)
    return out


def handle(action: str, req: Dict[str, Any], hashes: List[str]) -> Dict[str, Any]:
    """Every `sim_*` ilib action. Returns a JSON-able dict ({"ok": ...}); errors are codes the UIs translate."""
    svc = service()
    if action == "sim_status":
        return {"ok": True, "sim": svc.status()}
    if action == "sim_index":   # "Calcular poses y caras": all=true -> whole library (only what is missing unless force)
        r = svc.enqueue(None if req.get("all") else hashes, force=bool(req.get("force")), faces_only=bool(req.get("faces_only")))
        return {"ok": True, **r, "sim": svc.status()}
    if action == "sim_pause":
        svc.pause(req.get("paused", True))
        return {"ok": True, "sim": svc.status()}
    if action == "sim_cancel":
        svc.cancel()
        return {"ok": True, "sim": svc.status()}
    if action == "sim_settings":
        s = svc.save_settings(req.get("settings") or {}) if isinstance(req.get("settings"), dict) else svc.settings()
        return {"ok": True, "settings": s}
    if action == "sim_info":
        return {"ok": True, "info": svc.info(str(req.get("hash") or "")), "row": svc.row(str(req.get("sid") or ""), str(req.get("hash") or ""))}
    if action == "sim_search":
        tmp = _save_drops(svc, req.get("files"))
        try:
            return svc.run_search(hashes, tmp, req.get("mode") or "both", req.get("w_pose"), req.get("threshold"), req.get("agg") or "any",
                                  req.get("mirror"), req.get("limit"))
        except Exception as e:
            return {"ok": False, "error": "engine", "detail": str(e)[:300]}
        finally:
            for p in tmp:
                try:
                    os.remove(p)
                except OSError:
                    pass
    return {"ok": False, "error": "bad request"}


READONLY = ("sim_status", "sim_info", "sim_search", "sim_index", "sim_pause", "sim_cancel", "sim_settings")   # no library data change
FAST = ("sim_status", "sim_info")
DOCS = {"sim_status": "Index / job / per-face-model status (fast)", "sim_info": "Models + licences; {hash, sid} -> per-item score row (fast)",
        "sim_search": "Find similar {hashes|selection, files[], mode, w_pose, threshold, agg, mirror} -> {sid, n}; then query with filter {sim: sid}",
        "sim_index": "Start/extend the background job {all|hashes, force, faces_only}", "sim_pause": "Pause/resume the job {paused}",
        "sim_cancel": "Stop the job", "sim_settings": "Read / update settings {settings:{face_model, gpu, auto, ...}}"}


def _register(name):
    @_actions.action(name, fast=name in FAST, doc=DOCS[name])
    def _act(req, ctx):
        h = req.get("hashes")
        return handle(name, req, [str(x) for x in h] if isinstance(h, list) else [])
    return _act


for _n in READONLY:
    _register(_n)
