"""Pose + face similarity search (1.8.4+), shared by the classic explorer and the Galería through `sim_*` ilib actions.

Everything lives here; the hosts only route `sim_*` actions to handle() (see SIMILARITY_API.md for the contract).

* Models run in a separate process (simworker.py) started with the tagging-engine Python (setting "python"; default
  REFLIB_SIM_PYTHON, else the Python running WanGP). Lazy: the process starts on the first job / search and is stopped
  after IDLE_UNLOAD seconds without work, which frees the GPU. While WanGP generates (host busy()) the job waits.
* Index: <data>/similarity/ — meta.json (per image/video: persons / faces counts, size, error, video sampling fingerprint)
  + pose.npz (COCO-17 keypoints, float16) + face.npz (L2-normalised embeddings, float16; optional per-face `t` seconds
  for video faces). Separate files: existing library data are never touched.
  Saves are atomic (tmp + replace) every SAVE_EVERY images and at the end of a job.
* Videos (1.12.0-videofaces): kind=video items sampled at interval + scene cuts (see videosim.py); one result per
  video with best_t + segments. Settings: index_videos, video_interval_s, video_scene_detect, video_max_frames.
* Search: brute-force cosine in numpy over every indexed person / face (15k images = well under 100 ms).
* Result sets: a search returns an id ("sid"); the explorer shows it as a normal filter {"sim": sid} (imagelib hook),
  ordered by similarity unless another sort is picked, so nav history / selection / paging work unchanged.
"""
from __future__ import annotations
import base64, json, os, subprocess, sys, threading, time, uuid, zipfile
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from . import posesim
from . import videosim
from . import actions as _actions

BUSY: Callable[[], bool] = lambda: False   # set by the host (WanGP: "a generation is running" -> indexing waits)

VERSION = 1
SAVE_EVERY = 50
BATCH = 24   # 1.9.6-simperf: larger IPC batches so decode prefetch has work to overlap
IDLE_UNLOAD = 120.0
SYNC_EVERY = 60.0
RESULTS_KEEP = 30
# workers: decode/prefetch threads inside simworker (0 = auto from CPU count, typically 2..4)
DEFAULTS = {"python": "", "face_model": "arcface", "auto": True, "gpu": True, "models_dir": "", "w_pose": 0.5,
            "threshold": 0.0, "mirror": True, "limit": 1000, "workers": 0,
            # 1.12.0-videofaces: index kind=video (frame sample + scene cuts); pose on the same frames when cheap
            "index_videos": True, "video_interval_s": 2.0, "video_scene_detect": True, "video_max_frames": 60,
            "video_merge_gap_s": 4.0}
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


def _face_pack(vec, box=None, det=None, t=None, q=None):
    """In-memory multi-face record for one (item, face_model): embeddings + optional bbox/score/time/quality.

    box: (n, 4) float32 xywh normalised 0..1; NaN row = unknown (legacy entries without bbox).
    det: (n,) float32 detector score; NaN = unknown.
    t:   (n,) float32 seconds into the video; NaN = image / unknown (backward compatible).
    Face index within the item is the row order (0 = first / legacy sole face). For videos, rows from
    all sampled frames are concatenated in time order; face_i is unique per video item.
    """
    v = np.asarray(vec, np.float16)
    if v.ndim == 1:
        v = v.reshape(1, -1) if v.size else np.zeros((0, 0), np.float16)
    n = int(v.shape[0])
    if box is None:
        b = np.full((n, 4), np.nan, np.float32)
    else:
        b = np.asarray(box, np.float32).reshape(-1, 4)
        if b.shape[0] != n:
            b = np.full((n, 4), np.nan, np.float32)
    if det is None:
        s = np.full(n, np.nan, np.float32)
    else:
        s = np.asarray(det, np.float32).reshape(-1)
        if s.shape[0] != n:
            s = np.full(n, np.nan, np.float32)
    if t is None:
        tt = np.full(n, np.nan, np.float32)
    else:
        tt = np.asarray(t, np.float32).reshape(-1)
        if tt.shape[0] != n:
            tt = np.full(n, np.nan, np.float32)
    return {"vec": v, "box": b, "det": s, "t": tt, "q": _q_rows(q, n)}


Q_COLS = ("blur", "yaw", "trunc", "aligned")   # facequality: per-face quality inputs; NaN = unknown (pre-facequality)


def _q_rows(q, n):
    if q is not None:
        q = np.asarray(q, np.float32)
        if q.ndim == 2 and q.shape == (n, len(Q_COLS)):
            return q
    return np.full((n, len(Q_COLS)), np.nan, np.float32)


def _pack_q(pack, n):
    return _q_rows(pack.get("q") if isinstance(pack, dict) else None, n)


def _face_vec(pack):
    if pack is None:
        return None
    return pack["vec"] if isinstance(pack, dict) else pack  # legacy bare ndarray


def _face_n(pack) -> int:
    v = _face_vec(pack)
    return 0 if v is None else int(len(v))


def _norm_boxes(faces, w, h):
    """Worker boxes are pixel xywh in original image space; store normalised 0..1 (or NaN)."""
    n = len(faces)
    box = np.full((n, 4), np.nan, np.float32)
    det = np.full(n, np.nan, np.float32)
    q = np.full((n, len(Q_COLS)), np.nan, np.float32)
    iw, ih = float(w or 0), float(h or 0)
    for i, f in enumerate(faces):
        b = f.get("box")
        if b is not None and len(b) >= 4 and iw > 0 and ih > 0:
            box[i] = [float(b[0]) / iw, float(b[1]) / ih, float(b[2]) / iw, float(b[3]) / ih]
        if f.get("det") is not None:
            det[i] = float(f["det"])
        if isinstance(f.get("q"), (list, tuple)) and len(f["q"]) == 3:
            q[i, :3] = [float(x) for x in f["q"]]
        if f.get("al") is not None:
            q[i, 3] = float(f["al"])
    return box, det, q


def _face_times(faces):
    """Per-face video timestamps (seconds); NaN when the face comes from a still image."""
    n = len(faces)
    t = np.full(n, np.nan, np.float32)
    for i, f in enumerate(faces):
        if f.get("t") is not None:
            try:
                t[i] = float(f["t"])
            except (TypeError, ValueError):
                pass
    return t


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
        # 1.9.6-simperf: only rewrite npz files that changed (rewriting every face-*.npz each SAVE_EVERY
        # dominated wall time once the index grew past a few thousand images).
        self._dirty_pose = False
        self._dirty_faces: set = set()
        self._dirty_meta = False
        self._face_listeners: List[Callable] = []
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
                self.items[h] = {"p": np.zeros((0, 17, 3), np.float16), "faces": {}, "w": m.get("w", 0), "h": m.get("h", 0), "err": m.get("err", ""), "t": m.get("t", 0), "kind": m.get("kind", "image"), "v": m.get("v"), "pt": (np.asarray(m["pt"], np.float32) if isinstance(m.get("pt"), list) and m.get("pt") is not None else None)}
            files = [("pose.npz", "p", None)] + [("face-%s.npz" % fm, "f", fm) for fm in FACE_DIM]
            if self.face_model in FACE_DIM:
                files.append(("face.npz", "f", self.face_model))   # legacy file
            for name, key, fm in files:
                try:
                    with np.load(os.path.join(self.dir, name), allow_pickle=False) as z:
                        keys, own, vec = z["keys"], z["owner"], z["vec"]
                        model = z["model"] if "model" in z.files else None
                        # 1.9.6-simperf Personas: optional per-face bbox (xywh 0..1) + detector score.
                        # Absent in older npz -> NaN (legacy sole face = face_i 0 with null bbox).
                        box = z["box"] if "box" in z.files else None
                        det = z["det"] if "det" in z.files else None
                        # 1.12.0-videofaces: optional per-face timestamp (NaN for stills / legacy)
                        ft = z["t"] if "t" in z.files else None
                        qz = z["q"] if "q" in z.files else None
                except Exception:
                    continue
                if fm is not None:
                    if vec.ndim != 2 or vec.shape[1] != FACE_DIM[fm]:
                        continue
                    if model is not None:   # per-vector model id: drop anything that is not this file's model
                        keep = model == fm
                        own, vec = own[keep], vec[keep]
                        if box is not None:
                            box = box[keep]
                        if det is not None:
                            det = det[keep]
                        if ft is not None:
                            ft = ft[keep]
                        if qz is not None:
                            qz = qz[keep]
                order = np.argsort(own, kind="stable")
                own, vec = own[order], vec[order]
                if box is not None:
                    box = np.asarray(box, np.float32)[order]
                if det is not None:
                    det = np.asarray(det, np.float32)[order]
                if ft is not None:
                    ft = np.asarray(ft, np.float32)[order]
                if fm is not None and qz is not None and len(qz) == len(order):
                    qz = np.asarray(qz, np.float32)[order]
                else:
                    qz = None
                cuts = np.searchsorted(own, np.arange(len(keys) + 1))
                for k, h in enumerate(keys.tolist()):
                    if h in self.items:
                        if fm is None:
                            self.items[h]["p"] = vec[cuts[k]:cuts[k + 1]]
                            # pose times live in meta-side pt when present (loaded separately below)
                        elif fm in done.get(h, ()) and fm not in self.items[h]["faces"]:
                            sl = slice(cuts[k], cuts[k + 1])
                            n = int(cuts[k + 1] - cuts[k])
                            b = box[sl] if box is not None else np.full((n, 4), np.nan, np.float32)
                            d = det[sl] if det is not None else np.full(n, np.nan, np.float32)
                            tt = ft[sl] if ft is not None else np.full(n, np.nan, np.float32)
                            self.items[h]["faces"][fm] = _face_pack(vec[sl], b, d, tt, qz[sl] if qz is not None else None)
            self.rev += 1
            self._dirty_pose = False
            self._dirty_faces.clear()
            self._dirty_meta = False

    def save(self, force: bool = False):
        """Atomic incremental save. force=True rewrites every npz (final job save / migration).

        Otherwise only pose.npz and face-<model>.npz that received new vectors since the last save are
        rewritten, plus meta.json. Unused empty face-*.npz are left alone so a crash mid-job never loses
        already-committed vectors, and a new build can resume from the current meta + npz without reindex.
        """
        with self.lock:
            os.makedirs(self.dir, exist_ok=True)
            keys = list(self.items)
            todo = []
            if force or self._dirty_pose:
                todo.append(("pose.npz", None, (0, 17, 3)))
            dirty_fm = set(FACE_DIM) if force else set(self._dirty_faces)
            for m, d in FACE_DIM.items():
                if m not in dirty_fm:
                    continue
                # Never create a brand-new empty face-*.npz for an unused model; rewrite if it has
                # vectors or the file already exists (keeps resume / multi-model indexes intact).
                has_any = any(_face_n(self.items[h]["faces"].get(m)) for h in keys)
                path = os.path.join(self.dir, "face-%s.npz" % m)
                if has_any or os.path.isfile(path):
                    todo.append(("face-%s.npz" % m, m, (0, d)))
            for name, fm, shape in todo:
                vecs, own, boxes, dets, qs = [], [], [], [], []
                for k, h in enumerate(keys):
                    if fm is None:
                        v = self.items[h]["p"]
                        if v is not None and len(v):
                            vecs.append(v); own.append(np.full(len(v), k, np.int32))
                    else:
                        pack = self.items[h]["faces"].get(fm)
                        v = _face_vec(pack)
                        if v is not None and len(v):
                            vecs.append(v); own.append(np.full(len(v), k, np.int32))
                            if isinstance(pack, dict):
                                boxes.append(pack["box"]); dets.append(pack["det"])
                            else:
                                boxes.append(np.full((len(v), 4), np.nan, np.float32))
                                dets.append(np.full(len(v), np.nan, np.float32))
                            qs.append(_pack_q(pack, len(v)))
                n = sum(len(v) for v in vecs)
                extra = {}
                if fm is not None:
                    times = []
                    for k2, h2 in enumerate(keys):
                        pack2 = self.items[h2]["faces"].get(fm)
                        v2 = _face_vec(pack2)
                        if v2 is not None and len(v2):
                            if isinstance(pack2, dict) and "t" in pack2:
                                times.append(pack2["t"])
                            else:
                                times.append(np.full(len(v2), np.nan, np.float32))
                    extra["model"] = np.full(n, fm, dtype="<U16")
                    extra["box"] = np.concatenate(boxes).astype(np.float32) if boxes else np.zeros((0, 4), np.float32)
                    extra["det"] = np.concatenate(dets).astype(np.float32) if dets else np.zeros(0, np.float32)
                    extra["t"] = np.concatenate(times).astype(np.float32) if times else np.zeros(0, np.float32)
                    extra["q"] = np.concatenate(qs).astype(np.float32) if qs else np.zeros((0, len(Q_COLS)), np.float32)
                _atomic_npz(os.path.join(self.dir, name), keys=np.array(keys, dtype=str),
                            owner=np.concatenate(own) if own else np.zeros(0, np.int32),
                            vec=np.concatenate(vecs).astype(np.float16) if vecs else np.zeros(shape, np.float16), **extra)
            try:
                os.remove(os.path.join(self.dir, "face.npz"))   # legacy, now split per model
            except OSError:
                pass
            if force or self._dirty_meta or todo:
                def _meta_row(e):
                    row = {"np": int(len(e["p"])), "nf": {m: int(_face_n(v)) for m, v in e["faces"].items()},
                           "w": e.get("w", 0), "h": e.get("h", 0), "err": e.get("err", ""), "t": e.get("t", 0),
                           "kind": e.get("kind") or "image"}
                    if e.get("v"):
                        row["v"] = e["v"]
                    pt = e.get("pt")
                    if pt is not None and len(pt):
                        row["pt"] = [None if not np.isfinite(x) else round(float(x), 3) for x in np.asarray(pt, np.float32)]
                    return row
                _atomic_json(self.meta_path, {"version": VERSION, "face_models": sorted(FACE_DIM), "pose_model": "dwpose-body17",
                                              "items": {h: _meta_row(e) for h, e in self.items.items()}})
            self._dirty_pose = False
            self._dirty_faces.clear()
            self._dirty_meta = False

    def put(self, h: str, res: Dict[str, Any], face_model: str):
        with self.lock:
            e = self.items.get(h) or {"p": np.zeros((0, 17, 3), np.float16), "faces": {}}
            face_model = res.get("face_model") or face_model   # the model that really produced the vectors
            if not res.get("ok"):
                e.update(err=str(res.get("error") or "error")[:120], t=time.time())
            else:
                if "persons" in res:
                    raw_p = res["persons"] or []
                    e["p"] = np.asarray([p["kp"] for p in raw_p], np.float16).reshape(-1, 17, 3)
                    # per-person video timestamps (parallel to e["p"]); NaN / absent for stills
                    pt = np.full(len(raw_p), np.nan, np.float32)
                    for i, pr in enumerate(raw_p):
                        if pr.get("t") is not None:
                            try:
                                pt[i] = float(pr["t"])
                            except (TypeError, ValueError):
                                pass
                    e["pt"] = pt if len(raw_p) else None
                if "faces" in res:
                    D = FACE_DIM[face_model]
                    raw = res["faces"] or []
                    f = np.stack([np.frombuffer(base64.b64decode(x["emb"]), np.float16) for x in raw]) if raw else np.zeros((0, D), np.float16)
                    if f.ndim != 2 or f.shape[1] != D:
                        raise ValueError("face vector dim %s does not match %s" % (getattr(f, "shape", None), face_model))
                    bw, bh = res.get("w", 0), res.get("h", 0)
                    box, det, q = _norm_boxes(raw, bw, bh)
                    e["faces"][face_model] = _face_pack(f, box, det, _face_times(raw), q)
                    e.update(w=bw, h=bh, err="", t=time.time())
                else:
                    e.update(w=res.get("w", e.get("w", 0)), h=res.get("h", e.get("h", 0)), err="", t=time.time())
                if res.get("kind"):
                    e["kind"] = res["kind"]
                if res.get("v") is not None:
                    e["v"] = res["v"]
            self.items[h] = e
            self.rev += 1
            self._dirty_meta = True
            if "persons" in res or not res.get("ok"):
                self._dirty_pose = True
            if "faces" in res and face_model:
                self._dirty_faces.add(face_model)
                pack = e["faces"].get(face_model)
                if pack is not None and _face_n(pack):
                    self._notify_faces(h, face_model, pack)

    def face(self, h: str, fm: Optional[str] = None):
        """Embedding matrix (n, D) float16 for search; None if missing. Multi-face = multiple rows."""
        e = self.items.get(h)
        return None if not e else _face_vec(e["faces"].get(fm or self.active))

    def has(self, h: str, fm: Optional[str] = None) -> bool:
        e = self.items.get(h)
        return bool(e) and not e.get("err") and (fm or self.active) in e["faces"]

    def video_fresh(self, h: str, fingerprint: Dict[str, Any]) -> bool:
        """True when the video was indexed with the same mtime + sampling params (incremental skip)."""
        e = self.items.get(h)
        if not e or e.get("err") or e.get("kind") != "video":
            return False
        v = e.get("v") or {}
        try:
            return (float(v.get("mtime", -1)) == float(fingerprint.get("mtime", -2))
                    and float(v.get("interval_s", -1)) == float(fingerprint.get("interval_s", -2))
                    and bool(v.get("scene")) == bool(fingerprint.get("scene"))
                    and int(v.get("max_frames", -1)) == int(fingerprint.get("max_frames", -2)))
        except (TypeError, ValueError):
            return False

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
                f = _face_vec(e["faces"].get(self.active))
                if f is not None and len(f):
                    F.append(f); Fo.append(np.full(len(f), k, np.int32))
            D = FACE_DIM.get(self.active, 512)
            m = (keys, np.concatenate(P).astype(np.float32) if P else np.zeros((0, 17, 3), np.float32), np.concatenate(Po) if Po else np.zeros(0, np.int32),
                 np.concatenate(F).astype(np.float32) if F else np.zeros((0, D), np.float32), np.concatenate(Fo) if Fo else np.zeros(0, np.int32))
            self._mat = ((self.rev, self.active), m)
            return m

    def stats(self) -> Dict[str, int]:
        with self.lock:
            ok = [e for e in self.items.values() if not e.get("err")]
            return {"images": sum(1 for e in ok if (e.get("kind") or "image") != "video"),
                    "videos": sum(1 for e in ok if e.get("kind") == "video"),
                    "errors": sum(1 for e in self.items.values() if e.get("err")),
                    "persons": int(sum(len(e["p"]) for e in self.items.values())),
                    "faces": int(sum(_face_n(e["faces"].get(self.active)) for e in self.items.values())),
                    "faces_pending": sum(1 for h in self.items if self.needs_faces_only(h)), "face_model": self.active}

    # -------------------------------------------------------------------------------- Personas / face records
    def on_faces(self, callback: Callable) -> Callable[[], None]:
        """Subscribe to newly indexed faces. callback(records) where each record is
        {id, face_i, model, box, det, emb}. Returns an unsubscribe function.

        Designed for reflib_core/faces.py (clustering / person assignment) to update
        incrementally without re-reading the whole index after every batch.
        """
        self._face_listeners.append(callback)
        def _unsub():
            try:
                self._face_listeners.remove(callback)
            except ValueError:
                pass
        return _unsub

    def _notify_faces(self, h: str, fm: str, pack):
        v = _face_vec(pack)
        if v is None or not len(v):
            return
        box = pack["box"] if isinstance(pack, dict) else np.full((len(v), 4), np.nan, np.float32)
        det = pack["det"] if isinstance(pack, dict) else np.full(len(v), np.nan, np.float32)
        q = _pack_q(pack, len(v))
        recs = []
        tt = pack["t"] if isinstance(pack, dict) and "t" in pack else np.full(len(v), np.nan, np.float32)
        for i in range(len(v)):
            b = box[i]
            recs.append({
                "id": h,
                "face_i": i,
                "model": fm,
                "box": None if not np.isfinite(b).all() else [float(x) for x in b],
                "det": None if not np.isfinite(det[i]) else float(det[i]),
                "t": None if not np.isfinite(tt[i]) else float(tt[i]),
                "emb": np.asarray(v[i], np.float32),
                "q": q[i],
            })
        for cb in list(self._face_listeners):
            try:
                cb(recs)
            except Exception:
                pass

    def face_matrix(self, fm: Optional[str] = None) -> Dict[str, Any]:
        """Efficient dump of every face vector for Personas clustering / assignment.

        Returns a dict (all arrays length F, aligned):
          model: str — face model id
          ids: (F,) object — item hash per face
          face_i: (F,) int32 — 0-based index within that item (legacy sole face => 0)
          vec: (F, D) float32 — L2-normalised embeddings
          box: (F, 4) float32 — xywh normalised 0..1; NaN row if unknown (legacy)
          det: (F,) float32 — detector score; NaN if unknown
        Empty index => F=0 arrays with the right shapes.
        """
        fm = fm or self.active
        D = FACE_DIM.get(fm, 512)
        with self.lock:
            ids, fi, vecs, boxes, dets, times, qs = [], [], [], [], [], [], []
            for h, e in self.items.items():
                if e.get("err"):
                    continue
                pack = e["faces"].get(fm)
                v = _face_vec(pack)
                if v is None or not len(v):
                    continue
                n = len(v)
                ids.extend([h] * n)
                fi.append(np.arange(n, dtype=np.int32))
                vecs.append(np.asarray(v, np.float32))
                if isinstance(pack, dict):
                    boxes.append(pack["box"]); dets.append(pack["det"])
                    times.append(pack["t"] if "t" in pack else np.full(n, np.nan, np.float32))
                else:
                    boxes.append(np.full((n, 4), np.nan, np.float32))
                    dets.append(np.full(n, np.nan, np.float32))
                    times.append(np.full(n, np.nan, np.float32))
                qs.append(_pack_q(pack, n))
            if not vecs:
                return {"model": fm, "ids": np.array([], dtype=object), "face_i": np.zeros(0, np.int32),
                        "vec": np.zeros((0, D), np.float32), "box": np.zeros((0, 4), np.float32), "det": np.zeros(0, np.float32),
                        "t": np.zeros(0, np.float32), "q": np.zeros((0, len(Q_COLS)), np.float32)}
            return {"model": fm, "ids": np.asarray(ids, dtype=object), "face_i": np.concatenate(fi),
                    "vec": np.concatenate(vecs).astype(np.float32, copy=False),
                    "box": np.concatenate(boxes).astype(np.float32, copy=False),
                    "det": np.concatenate(dets).astype(np.float32, copy=False),
                    "t": np.concatenate(times).astype(np.float32, copy=False),
                    "q": np.concatenate(qs).astype(np.float32, copy=False)}


def _per_image_argmax(owner: np.ndarray, scores: np.ndarray, n_images: int):
    """Best score per image + the global row index that produced it (-1 if none)."""
    best = np.zeros(n_images, np.float32)
    arg = np.full(n_images, -1, np.int32)
    if len(scores):
        # stable: first max wins unless a later score is strictly greater
        for i in range(len(scores)):
            o = int(owner[i]); sc = float(scores[i])
            if arg[o] < 0 or sc > best[o]:
                best[o] = sc; arg[o] = i
    return best, arg


def search(index: SimIndex, queries: List[Dict[str, np.ndarray]], mode: str = "both", w_pose: float = 0.5, threshold: float = 0.0,
           agg: str = "any", mirror: bool = True, limit: int = 1000, allowed: Optional[set] = None,
           merge_gap_s: float = 4.0) -> List[Dict[str, Any]]:
    """queries: [{"p": (n,17,3), "f": (m,D)}] (one per query photo). -> [{hash, score, pose, face, best_t?, segments?}] best first.

    Videos are already one index row (all frame faces under one hash); we attach best_t + segments from the
    winning face/pose row's timestamps. Images omit those fields (backward compatible).
    """
    keys, P, Po, F, Fo = index.matrices()
    N = len(keys)
    per_q, per_p, per_f = [], [], []
    # keep last query's per-row face/pose scores for best_t (aggregate any = max across queries)
    face_rows = np.zeros(len(F), np.float32)
    pose_rows = np.zeros(len(P), np.float32)
    for q in queries:
        sp = sf = None
        if mode in ("pose", "both"):
            rows = np.zeros(len(P), np.float32)
            for person in np.asarray(q.get("p") if q.get("p") is not None else np.zeros((0, 17, 3)), np.float32):
                rows = np.maximum(rows, posesim.pose_scores(person, P, mirror=mirror))
            pose_rows = np.maximum(pose_rows, rows)
            sp = posesim.per_image_max(Po, rows, N)
        if mode in ("face", "both"):
            qf = q.get("f")
            rows = posesim.face_scores(qf, F) if qf is not None and len(qf) and len(F) else np.zeros(len(F), np.float32)
            face_rows = np.maximum(face_rows, rows)
            sf = posesim.per_image_max(Fo, rows, N)
        per_q.append(posesim.combine(sp, sf, mode, w_pose)); per_p.append(sp); per_f.append(sf)
    if not per_q:
        return []
    tot = posesim.aggregate(per_q, agg)
    pp = posesim.aggregate([x for x in per_p if x is not None], agg) if mode != "face" else None
    ff = posesim.aggregate([x for x in per_f if x is not None], agg) if mode != "pose" else None
    _, face_arg = _per_image_argmax(Fo, face_rows, N) if len(F) else (None, np.full(N, -1, np.int32))
    _, pose_arg = _per_image_argmax(Po, pose_rows, N) if len(P) else (None, np.full(N, -1, np.int32))
    # per-item face times / pose times for video enrichment
    fm = index.face_matrix()
    # map global face row -> t
    face_t = fm.get("t")
    order = np.argsort(-tot, kind="stable")
    out = []
    for k in order:
        sc = float(tot[k])
        if sc <= 0 or sc < threshold:
            break
        h = keys[k]
        if allowed is not None and h not in allowed:
            continue
        row = {"hash": h, "score": round(sc, 4), "pose": None if pp is None else round(float(pp[k]), 4),
               "face": None if ff is None else round(float(ff[k]), 4)}
        e = index.items.get(h) or {}
        if e.get("kind") == "video":
            # best_t from the modality that contributed most (prefer face when mode is face/both and a face won)
            best_t = None
            match_times = []
            if mode != "pose" and face_arg[k] >= 0 and face_t is not None and face_arg[k] < len(face_t):
                tv = float(face_t[face_arg[k]])
                if np.isfinite(tv):
                    best_t = round(tv, 3)
                # segments: faces of this item whose score is within 10% of the item's face score (or >= threshold)
                item_face_score = float(ff[k]) if ff is not None else sc
                thr_seg = max(threshold, item_face_score * 0.9) if item_face_score > 0 else threshold
                for ri in range(len(Fo)):
                    if int(Fo[ri]) != k:
                        continue
                    if float(face_rows[ri]) >= thr_seg and face_t is not None and np.isfinite(face_t[ri]):
                        match_times.append(float(face_t[ri]))
            if best_t is None and mode != "face" and pose_arg[k] >= 0:
                pt = e.get("pt")
                if pt is not None and pose_arg[k] < len(Po):
                    # pose_arg is global row into P; map to local person index within item
                    # count how many pose rows belong to images before k
                    local = int(pose_arg[k] - int(np.searchsorted(Po, k)))
                    # simpler: enumerate persons of this item
                    # Po[pose_arg[k]] == k; local index = number of Po[:pose_arg[k]+1] equal to k - 1
                    local_i = int(np.sum(Po[:pose_arg[k] + 1] == k) - 1)
                    if 0 <= local_i < len(pt) and np.isfinite(pt[local_i]):
                        best_t = round(float(pt[local_i]), 3)
                        match_times.append(float(pt[local_i]))
                # also collect other pose hits
                if pt is not None and pp is not None:
                    thr_seg = max(threshold, float(pp[k]) * 0.9) if float(pp[k]) > 0 else threshold
                    local_i = 0
                    for ri in range(len(Po)):
                        if int(Po[ri]) != k:
                            continue
                        if float(pose_rows[ri]) >= thr_seg and local_i < len(pt) and np.isfinite(pt[local_i]):
                            match_times.append(float(pt[local_i]))
                        local_i += 1
            if best_t is not None:
                row["best_t"] = best_t
                row["kind"] = "video"
                row["segments"] = videosim.merge_segments(match_times or [best_t], merge_gap_s)
            else:
                row["kind"] = "video"
        out.append(row)
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
        self.st = {"running": False, "done": 0, "total": 0, "failed": 0, "waiting": "", "error": "", "per_image_ms": 0,
                   "videos_done": 0, "per_video_ms": 0, "video_frames": 0}
        self._sync_t = 0.0
        self._hint = 0.0

    # settings
    @property
    def settings_path(self):
        return os.path.join(self.dir, "settings.json")

    def settings(self) -> Dict[str, Any]:
        try:
            # 1.9.4: utf-8-sig — files written by PowerShell/other tools carry a BOM, which made json.load fail and
            # silently fall back to DEFAULTS (python="" -> WanGP's own interpreter instead of the configured venv).
            with open(self.settings_path, encoding="utf-8-sig") as fh:
                s = dict(DEFAULTS, **json.load(fh))
            self.st.pop("settings_error", None) if hasattr(self, "st") else None
            return s
        except FileNotFoundError:
            return dict(DEFAULTS)
        except Exception as e:
            if hasattr(self, "st"):
                self.st["settings_error"] = f"{self.settings_path}: {e}"
            return dict(DEFAULTS)

    def save_settings(self, upd: Dict[str, Any]) -> Dict[str, Any]:
        s = self.settings()
        for k, v in (upd or {}).items():
            if k in DEFAULTS:
                if k == "workers":
                    try:
                        s[k] = max(0, min(16, int(v)))
                    except (TypeError, ValueError):
                        s[k] = 0
                else:
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
                    for k, pack in e["faces"].items():
                        if k in done and _face_n(pack) >= 0:
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
                                                         "workers": int(s.get("workers") or 0),
                                                         "face_files": {k: [m["file"]] + m["alias"] for k, m in FACE_MODELS.items()}, "log": os.path.join(self.dir, "worker.log")}, self.log)
        self.last_used = time.time()
        return self.worker

    def stop_worker(self):
        w, self.worker = self.worker, None
        if w:
            w.stop()

    # Personas: thin pass-through so faces.py does not reach into SimIndex internals.
    def face_matrix(self, fm: Optional[str] = None) -> Dict[str, Any]:
        return self.index.face_matrix(fm or self.index.active)

    def on_faces(self, callback: Callable) -> Callable[[], None]:
        return self.index.on_faces(callback)

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

    def analyse_video(self, path: str, pose: bool = True) -> Dict[str, Any]:
        """Sample frames (interval + scene cuts), run the same batched worker, aggregate faces/persons with `t`."""
        s = self.settings()
        interval = float(s.get("video_interval_s") or videosim.INTERVAL_S)
        scene = bool(s.get("video_scene_detect", True))
        max_f = int(s.get("video_max_frames") or videosim.MAX_FRAMES)
        t0 = time.time()
        samp = videosim.sample_frames(path, interval_s=interval, scene_detect=scene, max_frames=max_f)
        try:
            if not samp.get("ok"):
                return {"ok": False, "error": samp.get("error") or "sample failed", "kind": "video",
                        "v": self._video_fingerprint(path)}
            if samp.get("warning"):
                self.log("[reflib] video sample %s: %s" % (os.path.basename(path), samp["warning"]))
            paths = samp["paths"]
            times = samp["times"]
            if not paths:
                return {"ok": False, "error": "no frames", "kind": "video", "v": self._video_fingerprint(path)}
            # ensure models, then batch-analyse frame JPEGs through the existing pipeline
            if self.missing_models():
                self.analyse([])  # triggers download path; ignore empty
            frame_res = self.analyse(paths, pose=pose) if paths else []
            faces, persons = [], []
            w = int(samp.get("w") or 0)
            h = int(samp.get("h") or 0)
            for fr, t in zip(frame_res, times):
                if not fr.get("ok"):
                    continue
                if not w:
                    w = int(fr.get("w") or 0); h = int(fr.get("h") or 0)
                for f in fr.get("faces") or []:
                    faces.append(dict(f, t=float(t)))
                for pr in fr.get("persons") or []:
                    persons.append(dict(pr, t=float(t)))
            fp = videosim.video_cache_key(samp["mtime"], interval, scene, max_f)
            fp["n_frames"] = len(paths)
            fp["duration"] = samp.get("duration")
            self.st["per_image_ms"] = int(1000 * (time.time() - t0))
            self.st["per_video_ms"] = self.st["per_image_ms"]
            self.st["video_frames"] = len(paths)
            return {"ok": True, "kind": "video", "w": w, "h": h, "faces": faces, "persons": persons, "v": fp,
                    "secs": round(time.time() - t0, 3)}
        finally:
            videosim.cleanup_sample(samp)

    # library
    def _path(self, item) -> Optional[str]:
        for p in (item.get("path"),) + tuple(item.get("files") or ()):
            if p and os.path.isfile(p):
                return p
        return None

    def image_hashes(self) -> List[str]:
        return [i["hash"] for i in self.catalog()["items"] if i.get("kind", "image") == "image" and not i.get("missing")]

    def video_hashes(self) -> List[str]:
        if not self.settings().get("index_videos", True):
            return []
        return [i["hash"] for i in self.catalog()["items"] if i.get("kind") == "video" and not i.get("missing")]

    def media_hashes(self) -> List[str]:
        """Images + (when index_videos) videos — what sim_index / search may cover."""
        return self.image_hashes() + self.video_hashes()

    def _video_fingerprint(self, path: str) -> Dict[str, Any]:
        s = self.settings()
        return videosim.video_cache_key(
            os.path.getmtime(path) if path and os.path.isfile(path) else 0.0,
            float(s.get("video_interval_s") or videosim.INTERVAL_S),
            bool(s.get("video_scene_detect", True)),
            int(s.get("video_max_frames") or videosim.MAX_FRAMES),
        )

    def _video_needs(self, h: str, path: Optional[str], force: bool = False) -> bool:
        if force:
            return True
        if not path:
            return False
        fp = self._video_fingerprint(path)
        if not self.index.has(h):
            return True
        return not self.index.video_fresh(h, fp)

    # jobs
    def enqueue(self, hashes: Optional[List[str]] = None, force: bool = False, faces_only: bool = False) -> Dict[str, Any]:
        imgs = set(self.image_hashes())
        vids = set(self.video_hashes())
        allh = list(imgs) + list(vids)
        hs = [h for h in (hashes if hashes is not None else allh) if h in imgs or h in vids]
        by = self.catalog()["by_hash"]
        if faces_only:   # "Calcular caras": the selected model only, pose untouched
            fo = [h for h in hs if self.index.needs_faces_only(h) or (force and self.index.has(h))]
            hs = []
        elif not force:
            fo = [h for h in hs if h in imgs and self.index.needs_faces_only(h)]
            img_new = [h for h in hs if h in imgs and not self.index.has(h)]
            vid_new = [h for h in hs if h in vids and self._video_needs(h, self._path(by.get(h) or {}), False)]
            # faces-only catch-up for videos already indexed under a previous face model
            fo += [h for h in hs if h in vids and self.index.needs_faces_only(h) and h not in vid_new]
            hs = img_new + vid_new
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

    @staticmethod
    def env_missing(err: str) -> bool:
        """1.9.4: one shared rule for 'the similarity Python env is not set up' (both UIs show their own wording for it)."""
        e = (err or "").lower()
        return any(k in e for k in ("no module named", "onnxruntime", "worker exited", "worker did not start", "dll load failed"))

    def status(self) -> Dict[str, Any]:
        self.maybe_sync()
        s = self.settings()
        st = self.index.stats()
        return dict(self.st, pending=len(self.pending), paused=self.paused, index=st,
                    library=len(self.image_hashes()), library_videos=len(self.video_hashes()),
                    videos_done=int(st.get("videos") or 0),
                    worker=bool(self.worker and self.worker.alive()), python=self.python(), face_model=self.index.active, face_model_setting=s["face_model"],
                    face_fallback=self.st.get("face_fallback", ""), face_models=self.face_models(),
                    missing_models=self.missing_models(), settings=s, env_missing=self.env_missing(self.st.get("error", "")))

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
                todo = [(h, self._path(by.get(h) or {}), (by.get(h) or {}).get("kind", "image")) for h in batch]
                fo = {h for h, _, _ in todo if h in self.face_only}
                # images (non-video) go through the batched path; videos one-by-one (sample then batch frames)
                img_todo = [(h, p) for h, p, k in todo if k != "video"]
                vid_todo = [(h, p) for h, p, k in todo if k == "video"]
                paths = [p for h, p in img_todo if p and h not in fo]
                fpaths = [p for h, p in img_todo if p and h in fo]
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
                for h, p in img_todo:
                    r = (next(r_face) if h in fo else next(r_full)) if p else {"ok": False, "error": "file not found"}
                    self.face_only.discard(h)
                    self.index.put(h, r, fm)
                    self.st["done"] += 1
                    self.st["failed"] += 0 if r.get("ok") else 1
                    n_since += 1
                for h, p in vid_todo:
                    try:
                        if not p:
                            r = {"ok": False, "error": "file not found", "kind": "video"}
                        else:
                            r = self.analyse_video(p, pose=(h not in fo))
                    except Exception as e:
                        r = {"ok": False, "error": str(e)[:200], "kind": "video"}
                        self.log("[reflib] video %s: %s" % (h[:12], r["error"]))
                    self.face_only.discard(h)
                    self.index.put(h, r, fm)
                    self.st["done"] += 1
                    self.st["failed"] += 0 if r.get("ok") else 1
                    self.st["videos_done"] = int(self.index.stats().get("videos") or 0)
                    n_since += 1
                if n_since >= SAVE_EVERY:
                    self.index.save(); n_since = 0
        finally:
            if n_since or self.index._dirty_meta or self.index._dirty_pose or self.index._dirty_faces:
                self.index.save(force=True)
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
        need = []
        for h in hashes:
            it = by.get(h) or {}
            p = self._path(it)
            if not p:
                continue
            if it.get("kind") == "video":
                if self._video_needs(h, p, False):
                    need.append((h, p, "video"))
            elif not self.index.has(h):
                need.append((h, p, "image"))
        if need:
            fm = self.index.active
            for h, pth, kind in need:
                if kind == "video":
                    self.index.put(h, self.analyse_video(pth), fm)
                else:
                    self.index.put(h, self.analyse([pth])[0], fm)
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
        allowed = set(self.media_hashes())
        res = search(self.index, qs, mode, s["w_pose"] if w_pose is None else float(w_pose), s["threshold"] if threshold is None else float(threshold),
                     agg, s["mirror"] if mirror is None else bool(mirror), int(limit or s["limit"]), allowed,
                     float(s.get("video_merge_gap_s") or videosim.MERGE_GAP_S))
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
        imagelib.SIMILARITY_ROW = _SVC.row
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
            return {"ok": False, "error": "engine", "detail": str(e)[:300], "env_missing": SimService.env_missing(str(e))}
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
