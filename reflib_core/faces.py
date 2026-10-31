"""Personas (1.10.0): iPhone-Photos-style people built on the face embeddings of `sim_index`.

Contract: FACES_API.md. numpy only. Storage: <data>/faces/persons.json (source of truth, atomic + .bak) and
clusters-<model>.json (rebuildable cache). Face data never leaves the machine. Both UIs (Media Library
reflib_faces.js, Galería Personas page) only call the face_* / person_* actions registered at the bottom.
"""
from __future__ import annotations
import json, os, re, shutil, threading, time, unicodedata, uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from . import actions as _actions
from .actions import ActionError

VERSION = 1
UNDO_S = 5 * 60
THRESH = {"arcface": 0.42, "glintr100": 0.40, "adaface": 0.40, "sface": 0.50}
DEFAULTS = {"face_auto_cluster": True, "face_cluster_threshold": None, "face_suggest_threshold": None, "face_min_cluster": 2, "face_min_size": 40}
# facequality: quality gate (faces failing it stay searchable but are left out of clustering, centroids and
# suggestions, and are flagged), strict clustering and multi-prototype suggestions. Defaults tuned on LFW.
QDEFAULTS = {"face_q_min_det": 0.80, "face_q_min_blur": 25.0, "face_q_max_yaw": 0.60, "face_q_skip_trunc": True,
             "face_link_k": 3, "face_link_margin": 0.05, "face_proto_k": 4, "face_suggest_margin": 0.05}
DEFAULTS.update(QDEFAULTS)
_FID = re.compile(r"^([0-9A-Za-z_\-]+):(\d+)@([a-z0-9_]+)$")


def fid(h: str, n: int, model: str) -> str:
    return "%s:%d@%s" % (h, n, model)


def parse_fid(f: str) -> Optional[Tuple[str, int, str]]:
    m = _FID.match(str(f or ""))
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).strip().lower()) if not unicodedata.combining(c))


def _atomic_json(path: str, obj, bak: bool = False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if bak and os.path.isfile(path):
        shutil.copy2(path, path + ".bak")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
        fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, path)


def face_quality(det, px, q, s: Dict[str, Any]) -> Dict[str, Any]:
    """Quality of one face. det: detector score; px: min(bbox w, h) in source pixels; q: [blur, yaw, trunc, aligned]
    (NaN = unknown, e.g. faces indexed before facequality: unknown inputs never fail the gate).
    -> {score 0..1, ok, flags:[low_det|small|blurry|profile|truncated], aligned:int|None}"""
    q = list(q) if q is not None else []
    q += [float("nan")] * (4 - len(q))
    blur, yaw, trunc, al = (float(x) if x is not None else float("nan") for x in q[:4])
    fin = lambda x: x is not None and np.isfinite(x)
    flags = []
    if fin(det) and det < float(s["face_q_min_det"]):
        flags.append("low_det")
    if fin(px) and px < float(s.get("face_min_size") or 0):
        flags.append("small")
    if fin(blur) and blur < float(s["face_q_min_blur"]):
        flags.append("blurry")
    if fin(yaw) and yaw > float(s["face_q_max_yaw"]):
        flags.append("profile")
    if fin(trunc) and trunc > 0.5 and s.get("face_q_skip_trunc", True):
        flags.append("truncated")
    parts = [min(1.0, max(0.0, (det - 0.5) / 0.5)) if fin(det) else 1.0,
             min(1.0, px / 112.0) if fin(px) else 1.0,
             min(1.0, blur / 150.0) if fin(blur) else 1.0,
             1.0 - min(1.0, yaw) if fin(yaw) else 1.0,
             0.7 if fin(trunc) and trunc > 0.5 else 1.0]
    return {"score": round(float(np.prod(parts)), 3), "ok": not flags, "flags": flags,
            "aligned": int(al) if fin(al) else None}


def box_iou(a, b) -> float:
    if not a or not b:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    i = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    u = a[2] * a[3] + b[2] * b[3] - i
    return i / u if u > 0 else 0.0


def remap_by_iou(old: Dict[int, Any], new: List[Any], min_iou: float = 0.5) -> Dict[int, Optional[int]]:
    """Greedy best-IoU matching of old face rows (face_i -> bbox xywh 0..1) onto the re-indexed rows of the same item.
    Old faces without a bbox (legacy) keep their row when it still exists; unmatched -> None."""
    pairs = sorted(((box_iou(b, nb), i, j) for i, b in old.items() if b for j, nb in enumerate(new) if nb), reverse=True)
    mp: Dict[int, Optional[int]] = {}
    used = set()
    for v, i, j in pairs:
        if v < min_iou:
            break
        if i not in mp and j not in used:
            mp[i] = j; used.add(j)
    for i, b in old.items():
        if i not in mp:
            mp[i] = i if (not b and i < len(new) and i not in used) else None
    return mp


def strict_cluster(M: np.ndarray, todo: List[int], groups: List[List[int]], th: float, k: int = 3, margin: float = 0.05) -> List[List[int]]:
    """No-chaining clustering. A face joins the best group whose centroid is >= th AND that has at least
    min(k, size) members >= th - margin; otherwise it starts a new group. Then groups are merged only when their
    AVERAGE pairwise similarity (average linkage, not centroid-to-centroid) is >= th. `groups` (rows of M) are
    extended in place and returned."""
    th_m = th - margin
    S = [M[g].sum(0) for g in groups]
    for i in todo:
        v = M[i]
        best = -1
        if S:
            C = np.stack(S); C = C / np.maximum(np.linalg.norm(C, axis=1, keepdims=True), 1e-8)
            sc = C @ v
            for j in np.argsort(-sc):
                if sc[j] < th:
                    break
                g = groups[j]
                if int((M[g] @ v >= th_m).sum()) >= min(k, len(g)):
                    best = int(j); break
        if best < 0:
            groups.append([i]); S.append(v.copy())
        else:
            groups[best].append(i); S[best] = S[best] + v
    # average-linkage merge among groups whose centroids are close
    while len(groups) > 1:
        C = np.stack([x / max(np.linalg.norm(x), 1e-8) for x in S])
        G = C @ C.T; np.fill_diagonal(G, -1)
        a_s, b_s = np.nonzero(np.triu(G >= th))
        best, pair = th, None
        for a, b in zip(a_s.tolist(), b_s.tolist()):
            avg = float((M[groups[a]] @ M[groups[b]].T).mean())
            if avg >= best:
                best, pair = avg, (a, b)
        if pair is None:
            break
        a, b = pair
        groups[a] += groups[b]; S[a] = S[a] + S[b]
        del groups[b]; del S[b]
    return groups


def prototypes(P: np.ndarray, k: int = 4, iters: int = 15) -> np.ndarray:
    """Centroid + up to k k-means centroids (cosine, deterministic init: farthest-point) of confirmed faces."""
    c = _norm(P.sum(0, keepdims=True))
    k = max(0, min(int(k), len(P) // 5))
    if k < 2:
        return c
    idx = [int(np.argmax(P @ c[0]))]
    for _ in range(k - 1):
        idx.append(int(np.argmin((P @ P[idx].T).max(1))))
    C = P[idx].copy()
    for _ in range(iters):
        a = (P @ C.T).argmax(1)
        C = _norm(np.stack([P[a == j].sum(0) if (a == j).any() else C[j] for j in range(len(C))]))
    return np.vstack([c, C])


def suggest_scores(X: np.ndarray, P: np.ndarray, neg: Optional[np.ndarray] = None, others: Optional[np.ndarray] = None,
                   k: int = 4) -> Tuple[np.ndarray, np.ndarray]:
    """score = max similarity to the person's prototypes (centroid + k-means); margin = score - max(similarity to the
    person's rejected faces, to other persons' prototypes). Returns (score, margin)."""
    sc = (X @ prototypes(P, k).T).max(1)
    rival = np.full(len(X), -1.0, np.float32)
    for R in (neg, others):
        if R is not None and len(R):
            rival = np.maximum(rival, (X @ R.T).max(1))
    return sc, sc - rival


def _norm(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, np.float32)
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.maximum(n, 1e-8)


class FaceSource:
    """Adapter over simperf's SimService/SimIndex face records (SIMILARITY_API.md "Face records"):
    faces(model) via face_matrix(), per-face bbox (xywh 0..1, None when unknown) via the in-memory pack,
    on_faces() for incremental clustering. Tests pass a fake with the same methods."""

    def __init__(self, index, service=None):
        self.index = index
        self.svc = service if service is not None and hasattr(service, "face_matrix") else index

    @property
    def model(self) -> str:
        return self.index.active

    def faces(self, model: str) -> Tuple[List[str], np.ndarray]:
        fm = self.svc.face_matrix(model)
        ids = [fid(h, int(i), model) for h, i in zip(fm["ids"], fm["face_i"])]
        from .similarity import FACE_DIM
        V = np.asarray(fm["vec"], np.float32)
        return ids, (_norm(V) if len(ids) else np.zeros((0, FACE_DIM.get(model, 512)), np.float32))

    def on_faces(self, cb):
        return self.svc.on_faces(cb)

    def item(self, h: str, model: str) -> Dict[str, Any]:
        e = self.index.items.get(h) or {}
        pack = (e.get("faces") or {}).get(model)
        vec = pack.get("vec") if isinstance(pack, dict) else pack
        n = 0 if vec is None else len(vec)
        box = pack.get("box") if isinstance(pack, dict) else None
        det = pack.get("det") if isinstance(pack, dict) else None
        qq = pack.get("q") if isinstance(pack, dict) else None
        nb = [None] * n
        if box is not None and len(box) == n:
            nb = [None if not np.all(np.isfinite(b[:4])) else [round(float(x), 5) for x in b[:4]] for b in box]
        dd = [float(det[i]) if det is not None and i < len(det) and np.isfinite(det[i]) else None for i in range(n)]
        qs = [[float(x) for x in qq[i]] if qq is not None and i < len(qq) else None for i in range(n)]
        return {"w": e.get("w", 0) or 0, "h": e.get("h", 0) or 0, "n": n, "nbox": nb, "det": dd, "q": qs}


def _px(nb, w, hh):
    return [round(nb[0] * w, 1), round(nb[1] * hh, 1), round(nb[2] * w, 1), round(nb[3] * hh, 1)] if nb and w and hh else None


class Faces:
    def __init__(self, data_dir: str, source, settings: Callable[[], Dict[str, Any]] = lambda: {},
                 save_settings: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
                 tagger=None):
        self.dir = os.path.join(data_dir, "faces")
        self.src, self._settings, self._save_settings = source, settings, save_settings
        self.tagger = tagger   # object with add(hashes, tag), remove(hashes, tag), rename(old, new)
        self.lock = threading.RLock()
        self.st = {"running": False, "done": 0, "total": 0}
        self.rev = 0
        self._cache: Dict[str, Any] = {}
        self.undo: Dict[str, Any] = {}
        self.db = self._load_json("persons.json") or {"version": VERSION, "persons": {}, "assign": {}, "reject": {}}
        # simperf on_faces(): new faces -> debounced incremental run() (only unseen faces are clustered)
        self._auto_timer = None
        self._unsub = source.on_faces(self._on_faces) if hasattr(source, "on_faces") else None
        for k in ("persons", "assign", "reject"):
            self.db.setdefault(k, {})
        self.cl: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ storage
    def _load_json(self, name):
        try:
            with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def _save_db(self):
        _atomic_json(os.path.join(self.dir, "persons.json"), self.db, bak=True)
        self.rev += 1

    AUTO_DELAY = 4.0

    def _on_faces(self, records) -> None:
        try:
            self._remap_pending({str(r.get("id")) for r in records or [] if r.get("model") == self.src.model}, self.src.model)
            if not self.settings().get("face_auto_cluster", True):
                return
            if not any(r.get("model") == self.src.model for r in records or []):
                return
            self._drop_stale({str(r.get("id")) for r in records if r.get("model") == self.src.model}, self.src.model)
            if True:
                if self._auto_timer is not None:
                    self._auto_timer.cancel()
                t = threading.Timer(self.AUTO_DELAY, self._auto_run)
                t.daemon = True
                self._auto_timer = t
                t.start()
        except Exception:
            pass

    # ------------------------------------------------------------------ facequality: recompute faces, keep people
    def recompute_plan(self, hashes=None, m: Optional[str] = None) -> List[str]:
        """Before re-indexing faces (new alignment / quality fields): remember the bbox of every assigned or rejected
        face of `hashes` (default: every item with one) in persons.json "remap"; when the item comes back from the
        worker, _remap_pending() maps old face rows to new ones by bbox IoU, so person assignments survive."""
        m = m or self.src.model
        with self.lock:
            used = {}
            for f in list(self.assign(m)) + [f for fs in (self.db["reject"].get(m) or {}).values() for f in fs]:
                p = parse_fid(f)
                if p:
                    used.setdefault(p[0], set()).add(p[1])
            hs = [h for h in (hashes if hashes is not None else list(used))]
            rm = self.db.setdefault("remap", {}).setdefault(m, {})
            for h in hs:
                if h in used and h not in rm:
                    it = self.src.item(h, m)
                    rm[h] = {str(i): it["nbox"][i] for i in used[h] if i < len(it["nbox"])}
            self._save_db()
            return hs

    def _remap_pending(self, hashes, m) -> int:
        rm = (self.db.get("remap") or {}).get(m) or {}
        todo = [h for h in hashes if h in rm]
        if not todo:
            return 0
        n = 0
        with self.lock:
            for h in todo:
                old = rm.pop(h)
                new = self.src.item(h, m)["nbox"]
                mp = remap_by_iou({int(k): v for k, v in old.items()}, new)
                n += self._apply_remap(h, m, mp)
            self._save_db()
            self.rev += 1
        return n

    def _apply_remap(self, h, m, mp) -> int:
        """mp: old face_i -> new face_i (None = no match: assignment / rejection dropped)."""
        def tr(f):
            p = parse_fid(f)
            if not p or p[0] != h or p[1] not in mp:
                return f
            return None if mp[p[1]] is None else fid(h, mp[p[1]], m)
        a = self.assign(m)
        moved = {f: a.pop(f) for f in [f for f in a if tr(f) != f]}
        for f, pid in moved.items():
            g = tr(f)
            if g:
                a[g] = pid
        for pid, fs in (self.db["reject"].get(m) or {}).items():
            self.db["reject"][m][pid] = [g for g in (tr(f) for f in fs) if g]
        return len(moved)

    def _drop_stale(self, hashes, m) -> None:
        """Re-indexed items: drop assignments / rejections that point past the item's new face count."""
        with self.lock:
            n = {h: self.src.item(h, m)["n"] for h in hashes}
            ch = False
            for f in [f for f in self.assign(m) if parse_fid(f) and parse_fid(f)[0] in n and parse_fid(f)[1] >= n[parse_fid(f)[0]]]:
                del self.assign(m)[f]; ch = True
            for pid, fs in (self.db["reject"].get(m) or {}).items():
                keep = [f for f in fs if not (parse_fid(f) and parse_fid(f)[0] in n and parse_fid(f)[1] >= n[parse_fid(f)[0]])]
                if len(keep) != len(fs):
                    self.db["reject"][m][pid] = keep; ch = True
            if ch:
                self._save_db()

    def _auto_run(self) -> None:
        self._auto_timer = None
        if self.st.get("running"):
            return self._on_faces([{"model": self.src.model}])   # try again after the running job
        try:
            self.run()
        except Exception as e:
            print("[Reference Library] faces: auto-cluster failed: %s" % e)

    def close(self) -> None:
        if self._auto_timer is not None:
            self._auto_timer.cancel()
        if self._unsub:
            self._unsub()

    def clusters(self, model: Optional[str] = None) -> Dict[str, Any]:
        m = model or self.src.model
        if m not in self.cl:
            c = self._load_json("clusters-%s.json" % m) or {}
            self.cl[m] = {"version": VERSION, "threshold": c.get("threshold"), "seen": list(c.get("seen") or []),
                          "clusters": dict(c.get("clusters") or {})}
        return self.cl[m]

    def _save_cl(self, m):
        _atomic_json(os.path.join(self.dir, "clusters-%s.json" % m), self.clusters(m))
        self.rev += 1

    # ------------------------------------------------------------------ settings
    def settings(self) -> Dict[str, Any]:
        s = dict(DEFAULTS); s.update({k: v for k, v in (self._settings() or {}).items() if k in DEFAULTS and v is not None})
        m = self.src.model
        if s["face_cluster_threshold"] is None:
            s["face_cluster_threshold"] = THRESH.get(m, 0.42)
        if s["face_suggest_threshold"] is None:
            s["face_suggest_threshold"] = round(s["face_cluster_threshold"] - 0.05, 3)
        return s

    # ------------------------------------------------------------------ data helpers
    def _mat(self, m: str):
        rev = getattr(getattr(self.src, "index", None), "rev", None)
        ms = int(self.settings().get("face_min_size") or 0)
        if rev is not None and self._cache.get("key", (None,))[0:3] == (m, rev, ms):
            return self._cache
        ids, M = self.src.faces(m)
        if ms > 0 and len(ids):   # skip tiny faces when their bbox and the image size are known
            keep = []
            for i, f in enumerate(ids):
                h, n, _ = parse_fid(f)
                it = self.src.item(h, m)
                b = it["nbox"][n] if n < len(it["nbox"]) else None
                keep.append(not (b and it["w"] and it["h"]) or min(b[2] * it["w"], b[3] * it["h"]) >= ms)
            if not all(keep):
                k = np.array(keep)
                ids, M = [f for f, x in zip(ids, keep) if x], M[k]
        key = (m, rev, ms, len(ids), id(M) if rev is None else 0, self._qkey())
        if self._cache.get("key") != key:
            self._cache = {"key": key, "ids": ids, "M": M, "pos": {f: i for i, f in enumerate(ids)}}
            self._cache["good"] = self._good(ids, m)
        return self._cache

    # ------------------------------------------------------------------ facequality helpers
    def _qkey(self):
        s = self.settings()
        return tuple(s.get(k) for k in sorted(QDEFAULTS))

    def quality(self, f: str, m: str) -> Dict[str, Any]:
        h, n, _ = parse_fid(f)
        it = self.src.item(h, m)
        b = it["nbox"][n] if n < len(it["nbox"]) else None
        px = min(b[2] * it["w"], b[3] * it["h"]) if b and it["w"] and it["h"] else None
        det = (it.get("det") or [None] * (n + 1))[n] if n < len(it.get("det") or []) else None
        q = (it.get("q") or [None] * (n + 1))[n] if n < len(it.get("q") or []) else None
        return face_quality(det, px, q, self.settings())

    def _good(self, ids, m) -> np.ndarray:
        return np.array([self.quality(f, m)["ok"] for f in ids], bool) if len(ids) else np.zeros(0, bool)

    def assign(self, m) -> Dict[str, str]:
        return self.db["assign"].setdefault(m, {})

    def _person(self, pid) -> Dict[str, Any]:
        p = self.db["persons"].get(str(pid or ""))
        if not p:
            raise ActionError("person_not_found", person=pid)
        return p

    # ------------------------------------------------------------------ face thumbnails
    def thumb_file(self, fid: str, size: int = 160, margin: float = 0.4, sources=None) -> Optional[str]:
        """Square JPEG of one face (bbox + margin), cached in data/faces/thumbs/ keyed by face id, model, size, margin
        and source mtime (a changed source gets a new file). No bbox (old index) -> centred whole-image square.
        `sources(hash) -> [paths]` (default: imagelib catalog). None = no readable source."""
        pf = parse_fid(fid)
        if not pf:
            raise ActionError("face_not_found", id=str(fid))
        h, n, m = pf
        size = max(32, min(1024, int(size or 160)))
        margin = max(0.0, min(2.0, float(margin if margin is not None else 0.4)))
        if sources is None:
            from . import imagelib
            sources = lambda hh: imagelib.paths_for_hashes([hh]).get(hh) or []
        src = next((x for x in sources(h) if x and os.path.isfile(x)), None)
        if not src:
            return None
        mt = int(os.path.getmtime(src))
        it = self.src.item(h, m)
        box = it["nbox"][n] if n < len(it["nbox"]) else None
        key = f"{h}_{n}_{m}_{size}_{int(round(margin * 100))}_{mt}{'' if box else '_full'}"
        d = os.path.join(self.dir, "thumbs")
        out = os.path.join(d, key + ".jpg")
        if os.path.isfile(out):
            return out
        from PIL import Image, ImageOps
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            W, H = im.size
            if box:
                x, y, w, hh = box[0] * W, box[1] * H, box[2] * W, box[3] * H   # xywh 0..1 -> pixels of this file
                side = min(max(w, hh) * (1 + margin), W, H)
                cx, cy = x + w / 2, y + hh / 2
            else:
                side, cx, cy = min(W, H), W / 2, H / 2
            l = max(0, min(W - side, cx - side / 2)); t = max(0, min(H - side, cy - side / 2))
            crop = im.crop((int(l), int(t), int(l + side), int(t + side))).resize((size, size), Image.LANCZOS)
        os.makedirs(d, exist_ok=True)
        for old in os.listdir(d):   # drop stale variants of this face/size (older source mtime)
            if old.startswith(f"{h}_{n}_{m}_{size}_") and old != key + ".jpg":
                try:
                    os.remove(os.path.join(d, old))
                except OSError:
                    pass
        tmp = out + ".tmp"
        crop.save(tmp, "JPEG", quality=86)
        os.replace(tmp, out)
        return out

    def face_obj(self, f: str, m: str, extra=None) -> Dict[str, Any]:
        h, n, _ = parse_fid(f)
        it = self.src.item(h, m)
        o = {"id": f, "hash": h, "n": n, "model": m, "box": it["nbox"][n] if n < len(it["nbox"]) else None,
             "bbox": _px(it["nbox"][n], it["w"], it["h"]) if n < len(it["nbox"]) else None,
             "w": it["w"], "h": it["h"], "thumb": thumb_url(f)}
        o.update(self._qfields(f, m))
        pid = self.assign(m).get(f)
        if pid:
            o["person"] = pid
        if extra:
            o.update(extra)
        return o

    def _qfields(self, f, m) -> Dict[str, Any]:
        q = self.quality(f, m)
        return {"quality": {"score": q["score"], "ok": q["ok"], "flags": q["flags"]}, "aligned": q["aligned"]}

    def _check(self, faces, m) -> List[str]:
        pos = self._mat(m)["pos"]
        out = []
        for f in faces or []:
            p = parse_fid(f)
            if not p:
                raise ActionError("face_not_found", id=f)
            if p[2] != m:
                raise ActionError("faces_model_mismatch", id=f)
            if f not in pos:
                raise ActionError("face_not_found", id=f)
            out.append(f)
        return list(dict.fromkeys(out))

    def _cl_of(self, m) -> Dict[str, str]:
        return {f: cid for cid, c in self.clusters(m)["clusters"].items() for f in c["faces"]}

    # ------------------------------------------------------------------ clustering
    def run(self, full: bool = False, threshold: Optional[float] = None) -> Dict[str, Any]:
        try:
            return self._run(full, threshold)
        finally:
            if self.st.get("running"):
                self.st = {**self.st, "running": False}

    def _run(self, full: bool = False, threshold: Optional[float] = None) -> Dict[str, Any]:
        with self.lock:
            m = self.src.model
            s = self.settings()
            th = float(threshold if threshold is not None else s["face_cluster_threshold"])
            c = self.mat = self._mat(m)
            ids, M, pos = c["ids"], c["M"], c["pos"]
            cl = self.clusters(m)
            asg = self.assign(m)
            if full or (cl["threshold"] is not None and abs(cl["threshold"] - th) > 1e-6):
                cl["clusters"], cl["seen"] = {}, []
            cl["threshold"] = th
            # drop vanished / assigned faces from clusters
            for cid in list(cl["clusters"]):
                fs = [f for f in cl["clusters"][cid]["faces"] if f in pos and f not in asg]
                if fs:
                    cl["clusters"][cid]["faces"] = fs
                else:
                    del cl["clusters"][cid]
            seen = set(cl["seen"]) & set(pos)
            todo = [f for f in ids if f not in seen and f not in asg]
            self.st = {"running": True, "done": 0, "total": len(todo)}
            self._cluster_into(cl, M, pos, todo, th, c.get("good"), s)
            cl["seen"] = sorted(seen | set(todo))
            self._save_cl(m)
            self.st = {"running": False, "done": len(todo), "total": len(todo)}
            return self.status()

    def _cluster_into(self, cl, M, pos, todo, th, good, s) -> None:
        """facequality: strict (no chaining) clustering of `todo` into cl["clusters"]; low-quality faces are skipped
        (they stay searchable, are flagged, and are never grouped)."""
        if good is not None and len(good):
            todo = [f for f in todo if good[pos[f]]]
        cids, groups = [], []
        for k, v in cl["clusters"].items():
            g = [pos[f] for f in v["faces"] if good is None or not len(good) or good[pos[f]]]
            if g:
                cids.append(k); groups.append(g)
        first = {g[0]: (k, len(g)) for k, g in zip(cids, groups)}
        groups = strict_cluster(M, [pos[f] for f in todo], groups, th, int(s["face_link_k"]), float(s["face_link_margin"]))
        ids = self.mat["ids"]
        out = {}
        for g in groups:   # keep the id of the biggest previous group a group contains (stable ids across runs)
            ks = [first[i] for i in g if i in first]
            cid = max(ks, key=lambda x: x[1])[0] if ks else "c_" + uuid.uuid4().hex[:12]
            out[cid] = {"faces": [ids[i] for i in g]}
        cl["clusters"] = out
        self.st["done"] = len(todo)

    def status(self) -> Dict[str, Any]:
        m = self.src.model
        c = self._mat(m)
        asg = self.assign(m)
        cl = self.clusters(m)
        s = self.settings()
        ms = int(s["face_min_cluster"])
        # only groups the panel can show (>= face_min_cluster faces); singletons are reported apart
        shown = sum(1 for v in cl["clusters"].values() if len(v["faces"]) >= ms)
        th = cl.get("threshold")   # threshold of the last clustering run (may be an explicit one)
        return {"model": m, **self.st, "faces": len(c["ids"]), "unassigned": sum(1 for f in c["ids"] if f not in asg),
                "clusters": shown, "clusters_all": len(cl["clusters"]), "min_cluster": ms,
                "persons": len(self.db["persons"]), "rev": self.rev,
                "threshold": float(th) if th is not None else s["face_cluster_threshold"],
                "threshold_setting": s["face_cluster_threshold"]}

    def _cover(self, faces: List[str], m: str) -> Optional[str]:
        """Face closest to the group centroid (most typical face)."""
        c = self._mat(m)
        idx = [c["pos"][f] for f in faces if f in c["pos"]]
        if not idx:
            return None
        V = c["M"][idx]
        return faces[int((V @ _norm(V.sum(0))).argmax())] if len(idx) == len(faces) else [f for f in faces if f in c["pos"]][int((V @ _norm(V.sum(0))).argmax())]

    def list_clusters(self, offset=0, limit=50, min_size=None, faces_per=6):
        m = self.src.model
        ms = int(min_size if min_size is not None else self.settings()["face_min_cluster"])
        cs = sorted(((k, v["faces"]) for k, v in self.clusters(m)["clusters"].items() if len(v["faces"]) >= ms),
                    key=lambda x: (-len(x[1]), x[0]))
        out = []
        for k, fs in cs[offset:offset + limit]:
            cov = self._cover(fs, m)
            out.append({"id": k, "size": len(fs), "cover": self.face_obj(cov, m) if cov else None,
                        "faces": [self.face_obj(f, m) for f in fs[:faces_per]]})
        return {"total": len(cs), "clusters": out}

    # ------------------------------------------------------------------ persons
    def person_obj(self, pid: str) -> Dict[str, Any]:
        p = self._person(pid)
        m = self.src.model
        fs = [f for f, q in self.assign(m).items() if q == pid]
        cov = (p.get("cover") or {}).get(m)
        if cov not in fs:
            cov = self._cover(fs, m) if fs else None
        return {"id": pid, "name": p["name"], "tag": "persona:" + p["name"], "count": len(fs),
                "items": len({parse_fid(f)[0] for f in fs}), "cover": self.face_obj(cov, m) if cov else None,
                **({"seeded": True} if p.get("seeded", {}).get(m) else {})}

    def find_person(self, name: str) -> Optional[str]:
        f = _fold(name)
        return next((k for k, p in self.db["persons"].items() if _fold(p["name"]) == f), None)

    def new_person(self, name: str) -> str:
        name = str(name or "").strip()
        if not name:
            raise ActionError("person_need_name")
        pid = self.find_person(name)
        if pid:
            return pid
        pid = "p_" + uuid.uuid4().hex[:12]
        self.db["persons"][pid] = {"name": name, "created": time.time(), "cover": {}}
        return pid

    def _tag(self, op, hashes, *a):
        if self.tagger and hashes:
            getattr(self.tagger, op)(sorted(hashes), *a)

    def assign_faces(self, pid=None, name=None, clusters=(), faces=()) -> Dict[str, Any]:
        with self.lock:
            m = self.src.model
            if not pid:
                pid = self.new_person(name)
            p = self._person(pid)
            cl = self.clusters(m)["clusters"]
            fs = []
            for cid in clusters or []:
                if cid not in cl:
                    raise ActionError("cluster_not_found", cluster=cid)
                fs += cl[cid]["faces"]
            fs = self._check(list(fs) + list(faces or []), m)
            asg = self.assign(m)
            prev = {f: asg.get(f) for f in fs}
            for f in fs:
                asg[f] = pid
            rej = self.db["reject"].get(m, {}).get(pid)
            if rej:
                self.db["reject"][m][pid] = [f for f in rej if f not in set(fs)]
            for cid in list(cl):
                cl[cid]["faces"] = [f for f in cl[cid]["faces"] if f not in set(fs)]
                if not cl[cid]["faces"]:
                    del cl[cid]
            self._save_db(); self._save_cl(m)
            hashes = {parse_fid(f)[0] for f in fs}
            self._tag("add", hashes, "persona:" + p["name"])
            for q in {q for q in prev.values() if q and q != pid}:
                self._retag_after_remove(q, {parse_fid(f)[0] for f, x in prev.items() if x == q})
            return {"person": self.person_obj(pid), "assigned": len(fs), "hashes": sorted(hashes)}

    def _retag_after_remove(self, pid, hashes):
        p = self.db["persons"].get(pid)
        if not p:
            return
        still = {parse_fid(f)[0] for mm in self.db["assign"].values() for f, q in mm.items() if q == pid}
        self._tag("remove", set(hashes) - still, "persona:" + p["name"])

    def unassign(self, faces) -> Dict[str, Any]:
        with self.lock:
            m = self.src.model
            fs = self._check(faces, m)
            asg = self.assign(m)
            by: Dict[str, set] = {}
            for f in fs:
                q = asg.pop(f, None)
                if q:
                    by.setdefault(q, set()).add(parse_fid(f)[0])
            cl = self.clusters(m)
            cl["seen"] = [f for f in cl["seen"] if f not in set(fs)]
            self._save_db(); self._save_cl(m)
            for q, hs in by.items():
                self._retag_after_remove(q, hs)
            return {"n": sum(len(v) for v in by.values()), "hashes": sorted(set().union(*by.values())) if by else []}

    def suggest(self, pid, method="proto", limit=40, threshold=None) -> List[Dict[str, Any]]:
        self._person(pid)
        m = self.src.model
        c = self._mat(m)
        asg = self.assign(m)
        mine = [c["pos"][f] for f, q in asg.items() if q == pid and f in c["pos"]]
        if not mine:
            return []
        th = float(threshold if threshold is not None else self.settings()["face_suggest_threshold"])
        rej = set(self.db["reject"].get(m, {}).get(pid, []))
        cand = [i for i, f in enumerate(c["ids"]) if f not in asg and f not in rej]
        if not cand:
            return []
        return self._suggest_ranked(pid, m, c, asg, mine, cand, rej, method, limit, th)

    def _suggest_ranked(self, pid, m, c, asg, mine, cand, rej, method, limit, th) -> List[Dict[str, Any]]:
        """facequality: candidates must pass the quality gate; score = max over the person's prototypes (centroid +
        k-means of confirmed good faces; "nn" = every confirmed face, "centroid" = centroid only); margin = score minus
        the best similarity to this person's rejected faces and to other persons' prototypes. Kept when
        score >= th and margin >= face_suggest_margin; ranked by margin, then score."""
        s = self.settings()
        good = c.get("good")
        ok = (lambda i: bool(good[i])) if good is not None and len(good) else (lambda i: True)
        cand = [i for i in cand if ok(i)]
        P_idx = [i for i in mine if ok(i)] or mine
        if not cand:
            return []
        M = c["M"]; P, X = M[P_idx], M[cand]
        neg = M[[c["pos"][f] for f in rej if f in c["pos"]]] if rej else None
        others = []
        for q in self.db["persons"]:
            if q != pid:
                oi = [c["pos"][f] for f, w in asg.items() if w == q and f in c["pos"] and ok(c["pos"][f])]
                if oi:
                    others.append(prototypes(M[oi], int(s["face_proto_k"])))
        others = np.vstack(others) if others else None
        if method == "nn":
            sc = (X @ P.T).max(1)
            rival = np.full(len(X), -1.0, np.float32)
            for R in (neg, others):
                if R is not None and len(R):
                    rival = np.maximum(rival, (X @ R.T).max(1))
            mg = sc - rival
        else:
            sc, mg = suggest_scores(X, P, neg, others, 0 if method == "centroid" else int(s["face_proto_k"]))
        keep = np.nonzero((sc >= th) & (mg >= float(s["face_suggest_margin"])))[0]
        order = keep[np.lexsort((-sc[keep], -mg[keep]))]
        return [self.face_obj(c["ids"][cand[k]], m, {"score": round(float(sc[k]), 4), "margin": round(float(mg[k]), 4)})
                for k in order[:max(1, int(limit))]]

    def reject(self, pid, faces) -> int:
        with self.lock:
            self._person(pid)
            m = self.src.model
            fs = self._check(faces, m)
            r = self.db["reject"].setdefault(m, {}).setdefault(pid, [])
            n = 0
            for f in fs:
                if f not in r:
                    r.append(f); n += 1
            self._save_db()
            return n

    def unreject(self, pid, faces=None) -> int:
        with self.lock:
            self._person(pid)
            r = self.db["reject"].setdefault(self.src.model, {}).get(pid, [])
            keep = [f for f in r if faces is not None and f not in set(faces)]
            self.db["reject"][self.src.model][pid] = keep
            self._save_db()
            return len(r) - len(keep)

    def merge_clusters(self, cids) -> str:
        with self.lock:
            m = self.src.model
            cl = self.clusters(m)["clusters"]
            if len(set(cids)) < 2:
                raise ActionError("faces_need_two")
            for k in cids:
                if k not in cl:
                    raise ActionError("cluster_not_found", cluster=k)
            into = cids[0]
            for k in cids[1:]:
                if k != into:
                    cl[into]["faces"] += cl.pop(k)["faces"]
            self._save_cl(m)
            return into

    def merge_persons(self, pids, into) -> Dict[str, Any]:
        with self.lock:
            if len(set(pids) | {into}) < 2:
                raise ActionError("faces_need_two")
            tgt = self._person(into)
            for q in pids:
                if q == into:
                    continue
                src = self._person(q)
                for mm in self.db["assign"].values():
                    for f, x in list(mm.items()):
                        if x == q:
                            mm[f] = into
                for mm in self.db["reject"].values():
                    if q in mm:
                        mm.setdefault(into, [])
                        mm[into] += [f for f in mm.pop(q) if f not in mm[into]]
                del self.db["persons"][q]
                if self.tagger:
                    self.tagger.rename("persona:" + src["name"], "persona:" + tgt["name"])
            self._save_db()
            return self.person_obj(into)

    def split(self, faces, cluster=None, person=None) -> str:
        with self.lock:
            m = self.src.model
            fs = self._check(faces, m)
            if not fs:
                raise ActionError("face_not_found", id="")
            cl = self.clusters(m)
            if person:
                self._person(person)
                self.unassign([f for f in fs if self.assign(m).get(f) == person])
            elif cluster:
                if cluster not in cl["clusters"]:
                    raise ActionError("cluster_not_found", cluster=cluster)
            for cid in list(cl["clusters"]):
                cl["clusters"][cid]["faces"] = [f for f in cl["clusters"][cid]["faces"] if f not in set(fs)]
                if not cl["clusters"][cid]["faces"]:
                    del cl["clusters"][cid]
            new = "c_" + uuid.uuid4().hex[:12]
            cl["clusters"][new] = {"faces": fs}
            cl["seen"] = sorted(set(cl["seen"]) | set(fs))
            self._save_cl(m)
            return new

    def rename(self, pid, name) -> Dict[str, Any]:
        with self.lock:
            p = self._person(pid)
            name = str(name or "").strip()
            if not name:
                raise ActionError("person_need_name")
            other = self.find_person(name)
            if other and other != pid:
                return self.merge_persons([pid], other)
            old = p["name"]; p["name"] = name
            self._save_db()
            if self.tagger and old != name:
                self.tagger.rename("persona:" + old, "persona:" + name)
            return self.person_obj(pid)

    def delete(self, pid, keep_tag=False) -> str:
        with self.lock:
            p = self._person(pid)
            snap = {"person": dict(p), "assign": {m: {f: q for f, q in mm.items() if q == pid} for m, mm in self.db["assign"].items()},
                    "reject": {m: list(mm.get(pid, [])) for m, mm in self.db["reject"].items()}, "keep_tag": keep_tag}
            hashes = {parse_fid(f)[0] for mm in snap["assign"].values() for f in mm}
            for mm in self.db["assign"].values():
                for f in [f for f, q in mm.items() if q == pid]:
                    del mm[f]
            for mm in self.db["reject"].values():
                mm.pop(pid, None)
            del self.db["persons"][pid]
            for m in self.cl:
                self.cl[m]["seen"] = [f for f in self.cl[m]["seen"] if parse_fid(f)[0] not in hashes]
            self._save_db()
            if not keep_tag:
                self._tag("remove", hashes, "persona:" + p["name"])
            tok = uuid.uuid4().hex
            now = time.time()
            for k in [k for k, v in self.undo.items() if now - v["at"] > UNDO_S]:
                del self.undo[k]
            self.undo[tok] = {"at": now, "pid": pid, "hashes": sorted(hashes), **snap}
            return tok

    def undo_delete(self, tok) -> Dict[str, Any]:
        with self.lock:
            u = self.undo.pop(str(tok or ""), None)
            if not u or time.time() - u["at"] > UNDO_S:
                raise ActionError("undo_expired")
            pid = u["pid"]
            self.db["persons"][pid] = u["person"]
            for m, mm in u["assign"].items():
                self.db["assign"].setdefault(m, {}).update(mm)
            for m, r in u["reject"].items():
                if r:
                    self.db["reject"].setdefault(m, {})[pid] = r
            self._save_db()
            if not u["keep_tag"]:
                self._tag("add", set(u["hashes"]), "persona:" + u["person"]["name"])
            return self.person_obj(pid)

    def set_cover(self, pid, face):
        with self.lock:
            p = self._person(pid)
            m = self.src.model
            f = self._check([face], m)[0]
            if self.assign(m).get(f) != pid:
                raise ActionError("face_not_found", id=face)
            p.setdefault("cover", {})[m] = f
            self._save_db()
            return self.person_obj(pid)

    def seed(self, tag_users: Callable[[str], List[str]]):
        """Model switch: persons with no faces for the active model get the single face of items carrying their tag."""
        with self.lock:
            m = self.src.model
            asg = self.assign(m)
            have = set(asg.values())
            ch = False
            for pid, p in self.db["persons"].items():
                if pid in have:
                    continue
                for h in tag_users("persona:" + p["name"]):
                    if self.src.item(h, m)["n"] == 1:
                        f = fid(h, 0, m)
                        if f not in asg:
                            asg[f] = pid; ch = True
                            p.setdefault("seeded", {})[m] = True
            if ch:
                self._save_db()

    def for_items(self, hashes) -> Dict[str, Any]:
        m = self.src.model
        out = {}
        for h in hashes[:200]:
            it = self.src.item(h, m)
            out[h] = {"w": it["w"], "h": it["h"], "model": m, "faces": [self.face_obj(fid(h, i, m), m) for i in range(it["n"])]}
        cmap = self._cl_of(m)
        for v in out.values():
            for f in v["faces"]:
                if f["id"] in cmap:
                    f["cluster"] = cmap[f["id"]]
        return out


# ---------------------------------------------------------------------------------------------------- host glue
_F: Optional[Faces] = None


class _ImagelibTagger:
    def add(self, hashes, tag):
        from . import imagelib
        imagelib.set_tags(hashes, add=[tag])

    def remove(self, hashes, tag):
        from . import imagelib
        imagelib.set_tags(hashes, remove=[tag])

    def rename(self, old, new):
        from . import imagelib, storage
        try:
            imagelib.rename_tag(old, new)
        except storage.StorageError:
            pass


def service() -> Faces:
    global _F
    if _F is None:
        from . import similarity
        svc = similarity.service()
        def save(upd):   # merge face_* keys into similarity/settings.json without restarting the sim worker
            with svc.lock:
                try:
                    with open(svc.settings_path, encoding="utf-8-sig") as fh:
                        cur = json.load(fh)
                except Exception:
                    cur = {}
                cur.update(upd)
                _atomic_json(svc.settings_path, cur)
            return cur
        _F = Faces(os.path.dirname(svc.dir), FaceSource(svc.index, svc), settings=svc.settings, save_settings=save,
                   tagger=_ImagelibTagger())
    return _F


def _svc() -> Faces:
    f = service()
    if not f._mat(f.src.model)["ids"] and not f.db["persons"]:
        pass
    return f


def _need_index(f: Faces):
    if not f._mat(f.src.model)["ids"]:
        raise ActionError("faces_no_index")


def _meta(ctx, out, req):
    if req.get("meta", True) and getattr(ctx, "_payload", None):
        out.update(ctx.payload())
    return out


def _model_seed(f: Faces):
    if f.db["persons"] and f._cache.get("seeded") != f.src.model:
        try:
            from . import imagelib
            f.seed(imagelib.tag_users)
        except Exception:
            pass
        f._cache["seeded"] = f.src.model


FACE_TEXT = {
    "en": {"face_assigned": "{n} face(s) assigned to {name}",
           "faces_no_index": "No face vectors for the active face model yet. Run \"Compute faces\" first.",
           "faces_busy": "Faces are being grouped right now. Try again in a moment.",
           "face_not_found": "Face not found: {id}", "cluster_not_found": "Group not found",
           "person_not_found": "Person not found", "person_need_name": "Type a name first",
           "faces_model_mismatch": "That face belongs to another face model",
           "faces_need_two": "Pick at least two to merge", "undo_expired": "Too late to undo"},
    "es": {"face_assigned": "{n} cara(s) asignada(s) a {name}",
           "faces_no_index": "Aún no hay caras calculadas para el modelo de caras activo. Usa \"Calcular caras\" primero.",
           "faces_busy": "Se están agrupando las caras ahora mismo. Inténtalo de nuevo en un momento.",
           "face_not_found": "Cara no encontrada: {id}", "cluster_not_found": "Grupo no encontrado",
           "person_not_found": "Persona no encontrada", "person_need_name": "Escribe un nombre primero",
           "faces_model_mismatch": "Esa cara pertenece a otro modelo de caras",
           "faces_need_two": "Elige al menos dos para unir", "undo_expired": "Ya no se puede deshacer"},
}
# writes refused (faces_busy) while a clustering job holds the lock, instead of stalling the action queue
BUSY_WRITES = {"face_assign", "face_confirm", "face_unassign", "face_reject", "face_unreject", "face_merge", "face_split",
               "person_rename", "person_delete", "person_undo_delete", "person_set_cover", "face_settings"}


THUMB_ROUTE = "/reflib/face_thumb/"


def thumb_url(fid: str, size: int = 160, margin: float = 0.4) -> str:
    from urllib.parse import quote
    return f"{THUMB_ROUTE}{quote(str(fid), safe='')}.jpg?size={int(size)}&margin={margin:g}"


def face_thumb_path(fid: str, size=160, margin=0.4) -> Optional[str]:
    """Used by the HTTP route (gallery_routes.py): path of the cached face JPEG, or None."""
    return service().thumb_file(fid, size, margin)


def ftext(lang, key, **p):
    t = FACE_TEXT.get(str(lang or "en")[:2], FACE_TEXT["en"]).get(key) or FACE_TEXT["en"].get(key, key)
    try:
        return t.format(**p)
    except (KeyError, IndexError):
        return t


def _ok(ctx, key, **p):
    t = ftext(getattr(ctx, "lang", "en"), key, **p)
    return {"ok": True, "message": t, "toast": t, "code": key}


def A(name, **kw):
    """actions.action + translated face errors ({ok:false, error:<text>, code:<key>}) + faces_busy guard."""
    def deco(fn):
        def run(req, ctx):
            try:
                if name in BUSY_WRITES and _svc().st.get("running"):
                    raise ActionError("faces_busy")
                return fn(req, ctx)
            except ActionError as e:
                if e.key not in FACE_TEXT["en"]:
                    raise
                return {"ok": False, "error": ftext(getattr(ctx, "lang", "en"), e.key, **e.params), "code": e.key, **{("face" if k == "id" else k): v for k, v in e.params.items()}}
        run.__name__, run.__doc__ = fn.__name__, fn.__doc__
        return _actions.action(name, **kw)(run)
    return deco


@A("face_status", fast=True, doc="Personas: clustering progress / counts (fast)")
def a_status(req, ctx):
    return {"ok": True, "faces": _svc().status()}


@A("face_cluster_run", doc="Group unnamed faces {full?, threshold?} (incremental)")
def a_run(req, ctx):
    f = _svc(); _need_index(f); _model_seed(f)
    if f.st.get("running"):
        raise ActionError("faces_busy")
    th = req.get("threshold")
    t = threading.Thread(target=f.run, kwargs={"full": bool(req.get("full")), "threshold": float(th) if th is not None else None}, daemon=True)
    t.start(); t.join(float(req.get("wait", 2.0)))
    return {"ok": True, "job": True, "faces": f.status()}


@A("face_clusters", fast=True, doc="Unnamed face clusters {offset, limit, min_size, faces_per}")
def a_clusters(req, ctx):
    f = _svc()
    return {"ok": True, **f.list_clusters(int(req.get("offset", 0)), int(req.get("limit", 50)), req.get("min_size"), int(req.get("faces_per", 6)))}


@A("face_cluster_faces", fast=True, doc="Faces of one cluster {cluster, offset, limit}")
def a_cluster_faces(req, ctx):
    f = _svc(); m = f.src.model
    c = f.clusters(m)["clusters"].get(str(req.get("cluster") or ""))
    if not c:
        raise ActionError("cluster_not_found", cluster=req.get("cluster"))
    o, l = int(req.get("offset", 0)), int(req.get("limit", 200))
    return {"ok": True, "total": len(c["faces"]), "faces": [f.face_obj(x, m) for x in c["faces"][o:o + l]]}


@A("face_for_item", fast=True, doc="Faces (bbox, person, cluster) of {hash} or {hashes}")
def a_for_item(req, ctx):
    hs = req.get("hashes") if isinstance(req.get("hashes"), list) else [req.get("hash")]
    return {"ok": True, "items": _svc().for_items([str(h) for h in hs if h])}


@A("face_assign", doc="Clusters / faces -> person {person|name, clusters, faces}; adds persona:<Name>")
def a_assign(req, ctx):
    f = _svc()
    r = f.assign_faces(req.get("person"), req.get("name"), req.get("clusters") or [], req.get("faces") or [])
    return _meta(ctx, {**_ok(ctx, "face_assigned", n=r["assigned"], name=r["person"]["name"]), **r}, req)


@A("face_confirm", doc="'Is this also X?' yes {person, faces}")
def a_confirm(req, ctx):
    if not req.get("person"):
        raise ActionError("person_not_found", person="")
    return a_assign({**req, "name": None, "clusters": []}, ctx)


@A("face_unassign", doc="Remove faces from their person {faces}")
def a_unassign(req, ctx):
    r = _svc().unassign(req.get("faces") or [])
    return _meta(ctx, {"ok": True, **r}, req)


@A("face_suggest", fast=True, doc="Unassigned faces like a person {person, method nn|centroid, limit, threshold}")
def a_suggest(req, ctx):
    f = _svc(); _model_seed(f)
    th = req.get("threshold")
    return {"ok": True, "person": req.get("person"), "faces": f.suggest(req.get("person"), req.get("method") or "proto", int(req.get("limit", 40)),
                                                                         float(th) if th is not None else None)}


@A("face_reject", doc="'Is this also X?' no {person, faces}; never suggested again")
def a_reject(req, ctx):
    return {"ok": True, "n": _svc().reject(req.get("person"), req.get("faces") or [])}


@A("face_unreject", doc="Forget rejections {person, faces?}")
def a_unreject(req, ctx):
    fs = req.get("faces")
    return {"ok": True, "n": _svc().unreject(req.get("person"), fs if isinstance(fs, list) else None)}


@A("face_merge", doc="Merge {clusters:[..]} or {persons:[..], into}")
def a_merge(req, ctx):
    f = _svc()
    if req.get("persons"):
        into = req.get("into") or req["persons"][0]
        return _meta(ctx, {"ok": True, "person": f.merge_persons(list(req["persons"]), into)}, req)
    return {"ok": True, "cluster": f.merge_clusters(list(req.get("clusters") or []))}


@A("face_split", doc="Move faces to a new cluster {cluster|person, faces}")
def a_split(req, ctx):
    return _meta(ctx, {"ok": True, "cluster": _svc().split(req.get("faces") or [], req.get("cluster"), req.get("person"))}, req)


@A("person_list", fast=True, doc="Personas {offset, limit}")
def a_plist(req, ctx):
    f = _svc(); _model_seed(f)
    ps = sorted((f.person_obj(k) for k in f.db["persons"]), key=lambda p: (-p["count"], _fold(p["name"])))
    o, l = int(req.get("offset", 0)), int(req.get("limit", 200))
    return {"ok": True, "total": len(ps), "persons": ps[o:o + l]}


@A("person_get", fast=True, doc="One person and its faces {person, offset, limit}")
def a_pget(req, ctx):
    f = _svc(); m = f.src.model
    p = f.person_obj(req.get("person"))
    fs = [x for x, q in f.assign(m).items() if q == p["id"]]
    o, l = int(req.get("offset", 0)), int(req.get("limit", 200))
    return {"ok": True, "person": p, "total": len(fs), "faces": [f.face_obj(x, m) for x in fs[o:o + l]]}


@A("person_rename", doc="Rename a person and its persona: tag {person, name}")
def a_prename(req, ctx):
    return _meta(ctx, {"ok": True, "person": _svc().rename(req.get("person"), req.get("name"))}, req)


@A("person_delete", doc="Forget a person (never deletes images) {person, keep_tag} -> undo_token")
def a_pdel(req, ctx):
    return _meta(ctx, {"ok": True, "undo_token": _svc().delete(req.get("person"), bool(req.get("keep_tag")))}, req)


@A("person_undo_delete", doc="Restore a deleted person {undo_token}")
def a_pundo(req, ctx):
    return _meta(ctx, {"ok": True, "person": _svc().undo_delete(req.get("undo_token"))}, req)


@A("person_set_cover", doc="Cover face of a person {person, face}")
def a_pcover(req, ctx):
    return {"ok": True, "person": _svc().set_cover(req.get("person"), req.get("face"))}


@A("face_recompute", doc="Re-index faces (new alignment + quality) keeping person assignments by bbox IoU {hashes?}")
def a_recompute(req, ctx):
    f = _svc()
    hs = req.get("hashes") if isinstance(req.get("hashes"), list) else None
    from . import similarity
    svc = similarity.service()
    plan = f.recompute_plan(hs)
    target = hs if hs is not None else None   # None = every library image
    r = svc.enqueue(target, force=True, faces_only=True)
    return {"ok": True, "remap_items": len(plan), **r}


@A("face_settings", doc="Read / update face clustering settings {settings}")
def a_settings(req, ctx):
    f = _svc()
    s = req.get("settings")
    if isinstance(s, dict) and f._save_settings:
        f._save_settings({k: v for k, v in s.items() if k in DEFAULTS})
    return {"ok": True, "settings": f.settings()}


@A("face_thumb", fast=True, doc="Face thumbnail {id | hash+n[+model], size=160, margin=0.4, data?} -> {url, cached, data?}")
def a_thumb(req, ctx):
    f = _svc()
    fid = req.get("id")
    if not fid and req.get("hash"):
        fid = f"{req['hash']}:{int(req.get('n', 0))}@{req.get('model') or f.src.model}"
    size, margin = int(req.get("size") or 160), float(req.get("margin") if req.get("margin") is not None else 0.4)
    p = f.thumb_file(fid, size, margin)
    if not p:
        raise ActionError("face_not_found", id=str(fid))
    out = {"ok": True, "id": fid, "url": thumb_url(fid, size, margin)}
    if req.get("data"):
        import base64
        with open(p, "rb") as fh:
            out["data"] = "data:image/jpeg;base64," + base64.b64encode(fh.read()).decode()
    return out

