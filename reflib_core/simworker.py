"""Similarity model worker (1.9.6-simperf): a standalone script run in the tagging-engine Python (NOT WanGP's), spoken to over
stdin / stdout JSON lines. Needs only numpy, onnxruntime(-gpu) and opencv(-headless); never imports the plugin.

Models (all ONNX, lazy-loaded on the first request, CUDA when onnxruntime offers it):
  pose  DWPose: yolox_l.onnx (person boxes) + dw-ll_ucoco_384.onnx (RTMPose whole-body, COCO-133; body = first 17)
        Apache-2.0. The same files WanGP downloads to ckpts/pose/ (DeepBeepMeep/Wan2.1) are reused when present.
  face  YuNet (MIT, OpenCV zoo) detection + 5 landmarks, then ArcFace w600k_r50 (InsightFace buffalo_l, models
        for non-commercial research use) on the 112x112 aligned crop -> 512-d L2-normalised embedding.
        "sface" (OpenCV zoo SFace, Apache-2.0) is the permissive alternative recogniser (128-d).

Protocol: one JSON object per line.
  -> {"id": 1, "op": "analyse", "paths": [...], "pose": true, "face": true}
  <- {"id": 1, "ok": true, "results": [{"ok": true, "w": W, "h": H, "persons": [{"kp": [[x, y, c] * 17], "box": [x1, y1, x2, y2]}],
                                         "faces": [{"emb": "<base64 float16>", "box": [x, y, w, h], "det": 0.98}]}]}
  -> {"op": "info"} / {"op": "unload"} / {"op": "quit"}

1.9.6-simperf: decode prefetch thread pool, precomputed YOLOX grids, batched RTMPose + ArcFace, cv2 thread cap.
"""
import base64, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ARC_SRC = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)

def imread(path, max_side=1600):
    import cv2
    data = np.fromfile(path, dtype=np.uint8)   # unicode-safe on Windows
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cannot decode")
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1.0:
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return img, s


def _imread_safe(path):
    try:
        img, s = imread(path)
        return path, img, s, None
    except Exception as e:
        return path, None, 1.0, str(e)[:200]


def _providers(ort, want_gpu=True):
    av = ort.get_available_providers()
    return (["CUDAExecutionProvider"] if want_gpu and "CUDAExecutionProvider" in av else []) + ["CPUExecutionProvider"]


def _nms(b, s, thr):
    x1, y1, x2, y2 = b.T
    area = (x2 - x1 + 1) * (y2 - y1 + 1)
    order, keep = s.argsort()[::-1], []
    while order.size:
        i = order[0]; keep.append(i)
        w = np.maximum(0, np.minimum(x2[i], x2[order[1:]]) - np.maximum(x1[i], x1[order[1:]]) + 1)
        h = np.maximum(0, np.minimum(y2[i], y2[order[1:]]) - np.maximum(y1[i], y1[order[1:]]) + 1)
        ov = w * h / (area[i] + area[order[1:]] - w * h)
        order = order[1:][ov <= thr]
    return keep


def _decode_workers(cfg):
    """workers setting: 0 / unset = auto from CPU count (sane default 2..4)."""
    w = int(cfg.get("workers") or 0)
    if w > 0:
        return max(1, min(16, w))
    n = os.cpu_count() or 4
    return max(2, min(4, n // 2 or 2))


class Pose:
    def __init__(self, det, pose, gpu=True):
        import onnxruntime as ort
        pv = _providers(ort, gpu)
        self.det = ort.InferenceSession(det, providers=pv)
        self.pose = ort.InferenceSession(pose, providers=pv)
        self._det_in = self.det.get_inputs()[0].name
        self._pose_in = self.pose.get_inputs()[0].name
        # Precompute YOLOX 640 grids once (was rebuilt every boxes() call).
        S = 640
        grids, strides = [], []
        for st in (8, 16, 32):
            xv, yv = np.meshgrid(np.arange(S // st), np.arange(S // st))
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((grids[-1].shape[0], 1), st))
        self._g = np.concatenate(grids)
        self._st = np.concatenate(strides)
        self._S = S

    def boxes(self, img):
        import cv2
        S = self._S
        r = min(S / img.shape[0], S / img.shape[1])
        pad = np.full((S, S, 3), 114, np.uint8)
        pad[:int(img.shape[0] * r), :int(img.shape[1] * r)] = cv2.resize(img, (int(img.shape[1] * r), int(img.shape[0] * r)))
        x = np.ascontiguousarray(pad.transpose(2, 0, 1), np.float32)[None]
        out = self.det.run(None, {self._det_in: x})[0][0]
        g, st = self._g, self._st
        xy = (out[:, :2] + g) * st; wh = np.exp(out[:, 2:4]) * st
        sc = out[:, 4] * out[:, 5]   # objectness x "person"
        m = sc > 0.3
        if not m.any():
            return np.zeros((0, 4), np.float32), np.zeros(0, np.float32)
        b = np.concatenate([xy[m] - wh[m] / 2, xy[m] + wh[m] / 2], 1) / r
        keep = _nms(b, sc[m], 0.45)
        return b[keep], sc[m][keep]

    def _affine_crop(self, img, box):
        import cv2
        W, H = 288, 384
        x1, y1, x2, y2 = box
        c = np.array([(x1 + x2) / 2, (y1 + y2) / 2]); s = np.array([x2 - x1, y2 - y1]) * 1.25
        s = np.array([s[0], s[0] / (W / H)]) if s[0] > s[1] * W / H else np.array([s[1] * W / H, s[1]])
        k = W / s[0]
        M = np.array([[k, 0, W / 2 - k * c[0]], [0, k, H / 2 - k * c[1]]], np.float32)
        crop = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR)
        x = (crop.astype(np.float32) - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
        x = np.ascontiguousarray(x.transpose(2, 0, 1), np.float32)
        return x, k, c, W, H

    def keypoints(self, img, box):
        x, k, c, W, H = self._affine_crop(img, box)
        sx, sy = self.pose.run(None, {self._pose_in: x[None]})
        sx, sy = sx[0, :17], sy[0, :17]
        px, py = sx.argmax(1) / 2.0, sy.argmax(1) / 2.0
        conf = np.minimum(sx.max(1), sy.max(1))
        kx = (px - W / 2) / k + c[0]; ky = (py - H / 2) / k + c[1]
        return np.stack([kx, ky, np.clip(conf, 0, 1)], 1)

    def keypoints_batch(self, img, boxes):
        """Batched RTMPose (dynamic batch axis). Falls back to one-by-one on failure."""
        if not len(boxes):
            return []
        if len(boxes) == 1:
            return [self.keypoints(img, boxes[0])]
        try:
            crops, meta = [], []
            for box in boxes:
                x, k, c, W, H = self._affine_crop(img, box)
                crops.append(x); meta.append((k, c, W, H))
            batch = np.stack(crops, 0)
            sx, sy = self.pose.run(None, {self._pose_in: batch})
            out = []
            for i, (k, c, W, H) in enumerate(meta):
                a, b = sx[i, :17], sy[i, :17]
                px, py = a.argmax(1) / 2.0, b.argmax(1) / 2.0
                conf = np.minimum(a.max(1), b.max(1))
                kx = (px - W / 2) / k + c[0]; ky = (py - H / 2) / k + c[1]
                out.append(np.stack([kx, ky, np.clip(conf, 0, 1)], 1))
            return out
        except Exception:
            return [self.keypoints(img, b) for b in boxes]

    def __call__(self, img, scale, max_people=6):
        b, sc = self.boxes(img)
        order = np.argsort(-(b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]))[:max_people] if len(b) else []
        if not len(order):
            return []
        boxes = [b[i] for i in order]
        kps = self.keypoints_batch(img, boxes)
        out = []
        for i, kp, bi in zip(order, kps, boxes):
            kp = kp.copy()
            kp[:, :2] /= scale
            out.append({"kp": np.round(kp, 3).tolist(), "box": np.round(bi / scale, 1).tolist(), "score": round(float(sc[i]), 3)})
        return out


class Face:
    def __init__(self, yunet, rec, kind="arcface", gpu=True):
        import cv2, onnxruntime as ort
        self.kind = kind
        self.det = cv2.FaceDetectorYN.create(yunet, "", (320, 320), 0.7, 0.3, 50)
        if kind == "sface":
            self.sf = cv2.FaceRecognizerSF.create(rec, "")
            self.rec = None
        else:
            self.rec = ort.InferenceSession(rec, providers=_providers(ort, gpu))
            self._rec_in = self.rec.get_inputs()[0].name

    def _align(self, img, f):
        import cv2
        lm = f[4:14].reshape(5, 2).astype(np.float32)
        M, _ = cv2.estimateAffinePartial2D(lm, ARC_SRC, method=cv2.LMEDS)
        crop = cv2.warpAffine(img, M, (112, 112), borderValue=0)
        px = crop if self.kind == "adaface" else cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        return (px.astype(np.float32) - 127.5) / 127.5

    def embed(self, img, f):
        import cv2
        if self.kind == "sface":
            return self.sf.feature(self.sf.alignCrop(img, f)).reshape(-1)
        x = self._align(img, f)
        return np.asarray(self.rec.run(None, {self._rec_in: x.transpose(2, 0, 1)[None]})[0]).reshape(-1)

    def embed_batch(self, img, faces):
        """Batched ArcFace/AdaFace/glintr (dynamic batch). SFace stays serial (OpenCV API)."""
        if self.kind == "sface" or not faces:
            return [self.embed(img, f) for f in faces]
        if len(faces) == 1:
            return [self.embed(img, faces[0])]
        try:
            batch = np.stack([self._align(img, f).transpose(2, 0, 1) for f in faces], 0)
            out = np.asarray(self.rec.run(None, {self._rec_in: batch})[0])
            return [out[i].reshape(-1) for i in range(len(faces))]
        except Exception:
            return [self.embed(img, f) for f in faces]

    def __call__(self, img, scale, max_faces=8, min_px=24):
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, fs = self.det.detect(img)
        cand = []
        for f in (fs if fs is not None else [])[:max_faces]:
            if min(f[2], f[3]) < min_px:
                continue
            cand.append(f)
        embs = self.embed_batch(img, cand)
        out = []
        for f, e in zip(cand, embs):
            e = np.asarray(e, np.float32)
            e /= (np.linalg.norm(e) + 1e-9)
            out.append({"emb": base64.b64encode(e.astype(np.float16).tobytes()).decode("ascii"),
                        "box": [round(float(v) / scale, 1) for v in f[:4]], "det": round(float(f[14]), 3)})
        return out


class Worker:
    def __init__(self, cfg):
        self.cfg, self.pose, self.face = cfg, None, None
        self.face_kind, self.fallback = "", ""
        self._pool = None

    def _find(self, names):
        for d in self.cfg.get("dirs") or []:
            for n in names:
                p = os.path.join(d, n)
                if os.path.isfile(p):
                    return p
        raise FileNotFoundError("model not found: " + names[0])

    def _ensure_pool(self):
        if self._pool is None:
            nw = _decode_workers(self.cfg)
            # Only cap OpenCV when the decode pool is actually parallel; otherwise YuNet /
            # warpAffine benefit from OpenCV's own threads on a quiet GPU box.
            if nw > 1:
                try:
                    import cv2
                    cv2.setNumThreads(1)
                except Exception:
                    pass
            self._pool = ThreadPoolExecutor(max_workers=nw, thread_name_prefix="simdec")

    def load(self, pose, face):
        gpu = self.cfg.get("gpu", True)
        if pose and self.pose is None:
            self.pose = Pose(self._find(["yolox_l.onnx", "pose/yolox_l.onnx"]), self._find(["dw-ll_ucoco_384.onnx", "pose/dw-ll_ucoco_384.onnx"]), gpu)
        if face and self.face is None:
            kind = self.cfg.get("face_model", "arcface")
            yunet = self._find(["face_detection_yunet_2023mar.onnx", "yunet.onnx"])
            files = self.cfg.get("face_files") or {"arcface": ["w600k_r50.onnx", "buffalo_l/w600k_r50.onnx"]}
            sface = files.get("sface") or ["face_recognition_sface_2021dec.onnx", "sface.onnx"]
            if kind != "sface":
                try:   # selected model (ArcFace by default); SFace only if it cannot load
                    self.face = Face(yunet, self._find(files.get(kind) or files["arcface"]), kind, gpu)
                    if kind == "adaface" or kind == "glintr100":   # probe once so a bad export falls back now, not mid-job
                        self.face.embed(np.zeros((160, 160, 3), np.uint8), np.array([40, 40, 80, 80, 60, 70, 100, 70, 80, 90, 65, 105, 95, 105, 1], np.float32))
                    self.face_kind = kind
                    return
                except Exception as e:
                    self.fallback = kind + ": " + str(e)[:160]
                    sys.stderr.write("[simworker] %s failed, falling back to SFace: %s\n" % (kind, e))
            self.face = Face(yunet, self._find(sface), "sface", gpu)
            self.face_kind = "sface"

    def analyse(self, path, pose=True, face=True):
        img, s = imread(path)
        r = {"ok": True, "w": int(img.shape[1] / s), "h": int(img.shape[0] / s)}
        if pose:
            r["persons"] = self.pose(img, s)
        if face:
            r["faces"] = self.face(img, s)
        return r

    def analyse_many(self, paths, pose=True, face=True):
        """Decode with a small prefetch window, then run models in order (sessions stay on this thread).

        Submitting the whole batch at once fights ORT for CPU/RAM when decode is cheap (local SSD)
        and under live WanGP contention; a window of size=workers keeps 1..N images decoding ahead.
        """
        if not paths:
            return []
        if len(paths) == 1:
            try:
                return [self.analyse(paths[0], pose, face)]
            except Exception as e:
                return [{"ok": False, "error": str(e)[:200]}]
        nw = _decode_workers(self.cfg)
        # workers=1 → sequential (no pool); useful when decode is free / GPU saturated.
        if nw <= 1:
            out = []
            for p in paths:
                try:
                    out.append(self.analyse(p, pose, face))
                except Exception as e:
                    out.append({"ok": False, "error": str(e)[:200]})
            return out
        self._ensure_pool()
        window = max(2, nw)   # keep about one decode-ahead per worker
        res, i, n = [], 0, len(paths)
        pending = []   # [(path, Future)]
        while i < n or pending:
            while len(pending) < window and i < n:
                p = paths[i]; i += 1
                pending.append((p, self._pool.submit(_imread_safe, p)))
            path, fut = pending.pop(0)
            _p, img, s, err = fut.result()
            if err is not None or img is None:
                res.append({"ok": False, "error": err or "cannot decode"})
                continue
            try:
                r = {"ok": True, "w": int(img.shape[1] / s), "h": int(img.shape[0] / s)}
                if pose:
                    r["persons"] = self.pose(img, s)
                if face:
                    r["faces"] = self.face(img, s)
                res.append(r)
            except Exception as e:
                res.append({"ok": False, "error": str(e)[:200]})
        return res

    def handle(self, req):
        op = req.get("op")
        if op == "info":
            import onnxruntime as ort
            return {"ok": True, "providers": ort.get_available_providers(), "loaded": {"pose": self.pose is not None, "face": self.face is not None},
                    "workers": _decode_workers(self.cfg)}
        if op == "unload":
            self.pose = self.face = None
            if self._pool is not None:
                self._pool.shutdown(wait=False, cancel_futures=True)
                self._pool = None
            return {"ok": True}
        if op == "analyse":
            pose, face = bool(req.get("pose", True)), bool(req.get("face", True))
            t = time.time()
            self.load(pose, face)
            res = self.analyse_many(req.get("paths") or [], pose, face)
            return {"ok": True, "results": res, "secs": round(time.time() - t, 3), "face_model": self.face_kind, "face_fallback": self.fallback}
        return {"ok": False, "error": "unknown op"}


def main():
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    w = Worker(cfg)
    out = sys.stdout
    sys.stdout = sys.stderr   # stray prints from libraries never corrupt the protocol
    out.write(json.dumps({"ready": True}) + "\n"); out.flush()
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except Exception:
            continue
        if req.get("op") == "quit":
            break
        try:
            resp = w.handle(req)
        except Exception as e:
            resp = {"ok": False, "error": (type(e).__name__ + ": " + str(e))[:300]}
        resp["id"] = req.get("id")
        out.write(json.dumps(resp) + "\n"); out.flush()


if __name__ == "__main__":
    main()
