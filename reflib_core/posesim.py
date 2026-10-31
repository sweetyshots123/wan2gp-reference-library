"""Pose / face similarity maths (1.8.4). Pure numpy, no models, no I/O: unit-testable and shared by every UI.

Pose: COCO-17 body keypoints [x, y, conf] in image pixels. A joint counts when conf >= KP_MIN. Two poses are compared
only on the joints BOTH have: each side is centred on the mean of those joints and scaled to unit RMS radius, then
score = cosine of the flattened coordinates (= 1 - Procrustes distance / 2 without rotation), clipped to [0, 1], times
a coverage factor sqrt(common / joints of the query). So translation and scale never matter, missing joints are
ignored (but too few in common -> 0), and orientation matters (standing vs lying are different poses). mirror=True
also tries the left/right-flipped pose and keeps the better score.

Face: L2-normalised embeddings; score = cosine clipped to [0, 1] (ArcFace: same person typically >= 0.35-0.4).
"""
from __future__ import annotations
from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np

KP_MIN = 0.3
MIN_COMMON = 5
NJ = 17
FLIP = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]   # left <-> right
MODES = ("pose", "face", "both")
AGGS = ("any", "avg")


def as_kp(kp) -> np.ndarray:
    a = np.asarray(kp, dtype=np.float32).reshape(-1, NJ, 3)
    return a


def mirrored(kp: np.ndarray) -> np.ndarray:
    """Horizontal flip of (P,17,3) keypoints: x -> -x and left/right joints swapped (scale/translation free anyway)."""
    m = kp[:, FLIP].copy()
    m[..., 0] = -m[..., 0]
    return m


def normalize(kp) -> Tuple[np.ndarray, np.ndarray]:
    """(P,17,3) -> (coords (P,17,2) centred / unit RMS over each pose's own visible joints (0 elsewhere), mask (P,17))."""
    kp = as_kp(kp)
    m = kp[..., 2] >= KP_MIN
    xy = np.where(m[..., None], kp[..., :2], 0.0)
    n = np.maximum(m.sum(1, keepdims=True), 1)[..., None]
    c = xy.sum(1, keepdims=True) / n
    xy = np.where(m[..., None], xy - c, 0.0)
    r = np.sqrt((xy ** 2).sum((1, 2), keepdims=True) / n)
    return (xy / np.maximum(r, 1e-6)).astype(np.float32), m


def pose_scores(q, db, mirror: bool = False, min_common: int = MIN_COMMON) -> np.ndarray:
    """One query pose (17,3) against db (P,17,3) -> (P,) scores in [0, 1]. Re-normalises both on their common joints."""
    q = as_kp(q)[0]
    db = as_kp(db)
    if len(db) == 0:
        return np.zeros(0, np.float32)
    best = _pose_scores1(q, db, min_common)
    if mirror:
        best = np.maximum(best, _pose_scores1(mirrored(q[None])[0], db, min_common))
    return best


# 1.8.4: limb directions (COCO-17): pose = how the limbs point, independent of position, size and body proportions.
BONES = np.array([(5, 7), (7, 9), (6, 8), (8, 10),          # arms
                  (11, 13), (13, 15), (12, 14), (14, 16),   # legs
                  (5, 6), (11, 12), (5, 11), (6, 12),       # torso
                  (0, 5), (0, 6)], np.int64)                # head vs shoulders
BONE_W = np.array([1.0] * 8 + [0.35] * 6, np.float32)   # limbs decide; torso / head (almost always upright) count less
MIN_BONES = 4
SHARP = 6.0   # ((1 + cos) / 2) ** SHARP per limb: 0° -> 1, 20° -> 0.83, 45° -> 0.39, 90° -> 0.02


def _pose_scores1(q: np.ndarray, db: np.ndarray, min_common: int) -> np.ndarray:
    """Mean limb-direction agreement on the limbs both poses show, times sqrt(coverage of the query's limbs).
    min_common is kept for compatibility (joints); the rule is >= MIN_BONES common limbs."""
    a, b = BONES[:, 0], BONES[:, 1]
    vq = q[b, :2] - q[a, :2]                                            # (B,2)
    mq = (q[a, 2] >= KP_MIN) & (q[b, 2] >= KP_MIN) & (np.linalg.norm(vq, axis=1) > 1e-6)
    nq = int(mq.sum())
    if nq < MIN_BONES:
        return np.zeros(len(db), np.float32)
    vd = db[:, b, :2] - db[:, a, :2]                                    # (P,B,2)
    ld = np.linalg.norm(vd, axis=2)
    md = (db[:, a, 2] >= KP_MIN) & (db[:, b, 2] >= KP_MIN) & (ld > 1e-6)
    c = md & mq[None]
    n = c.sum(1).astype(np.float32)
    uq = vq / np.maximum(np.linalg.norm(vq, axis=1, keepdims=True), 1e-9)
    ud = vd / np.maximum(ld[..., None], 1e-9)
    cos = (ud * uq[None]).sum(2)                                        # (P,B)
    w = c * BONE_W[None]
    agree = ((1 + cos) / 2) ** SHARP * w
    s = agree.sum(1) / np.maximum(w.sum(1), 1e-9) * np.sqrt(w.sum(1) / float((BONE_W * mq).sum()))
    s[n < MIN_BONES] = 0
    return s.astype(np.float32)


def face_scores(q, db) -> np.ndarray:
    """q (D,) or (Q,D), db (F,D) -> (F,) best cosine over the query faces, clipped to [0, 1]."""
    db = np.asarray(db, dtype=np.float32)
    q = np.asarray(q, dtype=np.float32).reshape(-1, db.shape[1] if db.ndim == 2 and db.size else np.asarray(q).shape[-1])
    if db.size == 0 or q.size == 0:
        return np.zeros(len(db), np.float32)
    return np.clip((db @ q.T).max(1), 0, 1)


def per_image_max(owner: np.ndarray, scores: np.ndarray, n_images: int) -> np.ndarray:
    """Row scores (persons / faces) -> best score per image index (0 when the image has none)."""
    out = np.zeros(n_images, np.float32)
    if len(scores):
        np.maximum.at(out, owner, scores)
    return out


def combine(pose: Optional[np.ndarray], face: Optional[np.ndarray], mode: str, w_pose: float = 0.5) -> np.ndarray:
    if mode == "pose" or face is None:
        return pose
    if mode == "face" or pose is None:
        return face
    w = min(max(float(w_pose), 0.0), 1.0)
    return w * pose + (1 - w) * face


def aggregate(per_query: List[np.ndarray], agg: str = "any") -> np.ndarray:
    """Several query photos: 'any' = best match against any of them, 'avg' = mean over them."""
    if not per_query:
        return np.zeros(0, np.float32)
    st = np.stack(per_query)
    return st.max(0) if agg != "avg" else st.mean(0)
