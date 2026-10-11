"""Body-shape analysis (adults only: callers run it only after the appears_minor gate passed).

Honest limits: one 2D photo has no absolute scale and no depth. What is measured is the visible silhouette WIDTH at
body landmarks, normalised by torso height (scale-free, the reliable part). Circumferences (bust / waist / hip / thigh,
"90-60-90") are ESTIMATES: width -> ellipse with a typical adult depth/width ratio (or a measured depth from a side
view), scaled by an assumed adult height (165 cm ± 7) or a user-entered height. They are stored as bands with an
uncertainty and shown as "estimado"; clothing, pose, lens and posture all move them.

Inputs are model-agnostic: a person mask (H×W bool), optional arm / skirt masks, and COCO-17 keypoints
{name: (x, y, conf)}. BodyParser (below) produces them locally with ViTPose (Apache-2.0) + SegFormer human parsing.
"""
from __future__ import annotations
import math, re
from typing import Dict, List, Optional, Tuple

DEFAULT_HEIGHT_CM, HEIGHT_SD_CM = 165.0, 7.0
SHOULDER_TO_HIP_OF_HEIGHT = 0.29          # shoulder line -> hip joints, fraction of stature (adult average)
DEPTH = {"bust": 0.72, "underbust": 0.70, "waist": 0.74, "high_hip": 0.72, "hip": 0.70, "thigh": 0.95, "knee": 0.95}
LEVELS = ["shoulder", "bust", "underbust", "waist", "high_hip", "hip", "thigh", "knee"]
NOT_MEASURABLE = {"measurable": False}


# ------------------------------------------------------------------ geometry
def runs(row) -> List[Tuple[int, int]]:
    """Contiguous True runs of one mask row as [start, end) pairs."""
    out, start = [], None
    for x, v in enumerate(row):
        if v and start is None:
            start = x
        elif not v and start is not None:
            out.append((start, x)); start = None
    if start is not None:
        out.append((start, len(row)))
    return out


def width_at(mask, y: float, cx: float) -> float:
    """Width of the run containing (or nearest to) the body centre line at row y."""
    y = int(round(min(max(y, 0), len(mask) - 1)))
    rs = runs(mask[y])
    if not rs:
        return 0.0
    for a, b in rs:
        if a <= cx < b:
            return float(b - a)
    a, b = min(rs, key=lambda r: min(abs(r[0] - cx), abs(r[1] - cx)))
    return float(b - a)


def span_at(mask, y: float, x0: float, x1: float) -> List[Tuple[int, int]]:
    y = int(round(min(max(y, 0), len(mask) - 1)))
    return [(a, b) for a, b in runs(mask[y]) if b > x0 and a < x1]


def _kp(k, name, min_conf=0.3):
    v = k.get(name)
    return (float(v[0]), float(v[1])) if v and (len(v) < 3 or v[2] >= min_conf) else None


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def ellipse_perimeter(width: float, depth: float) -> float:
    a, b = width / 2, depth / 2
    h = ((a - b) / (a + b)) ** 2 if a + b else 0
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


# ------------------------------------------------------------------ pose gate
def view_and_pose(k: Dict) -> Dict:
    ls, rs, lh, rh = (_kp(k, n) for n in ("left_shoulder", "right_shoulder", "left_hip", "right_hip"))
    if not (ls and rs and lh and rh):
        return {"ok": False, "reason": "torso keypoints not visible"}
    sm, hm = _mid(ls, rs), _mid(lh, rh)
    torso = hm[1] - sm[1]
    if torso <= 0:
        return {"ok": False, "reason": "not upright"}
    sw = _dist(ls, rs)
    lean = abs(hm[0] - sm[0]) / torso
    view = "front" if sw / torso >= 0.45 else "three_quarter" if sw / torso >= 0.28 else "side"
    nose = _kp(k, "nose")
    if view == "front" and nose and abs(nose[0] - sm[0]) > 0.35 * sw:
        view = "three_quarter"
    lk, rk, la, ra = (_kp(k, n) for n in ("left_knee", "right_knee", "left_ankle", "right_ankle"))
    legs = bool(lk and rk)
    standing = lean < 0.25
    if legs:
        for h, kn in ((lh, lk), (rh, rk)):
            dy = kn[1] - h[1]
            if dy <= 0.5 * torso * 0.6 or abs(kn[0] - h[0]) > 0.5 * dy:   # thighs roughly vertical and below the hips
                standing = False
    full = legs and bool(la and ra)
    return {"ok": True, "view": view, "standing": standing, "legs": legs, "full": full, "torso_px": torso,
            "shoulder_mid": sm, "hip_mid": hm, "knees": (lk, rk), "ankles": (la, ra), "lean": lean}


# ------------------------------------------------------------------ measurement
def measure_front(mask, k: Dict, arms=None, skirt=None, height_cm: Optional[float] = None, loose_clothing: bool = False) -> Dict:
    """Silhouette widths from a front / near-front, standing, half- or full-body image. Returns NOT_MEASURABLE
    (with a reason) for any other pose."""
    g = view_and_pose(k)
    if not g["ok"]:
        return dict(NOT_MEASURABLE, reason=g["reason"])
    if g["view"] != "front":
        return dict(NOT_MEASURABLE, reason=f"{g['view']} view", view=g["view"])
    if not g["standing"]:
        return dict(NOT_MEASURABLE, reason="not standing", view="front")
    body = [[bool(v) and not (arms is not None and arms[y][x]) for x, v in enumerate(r)] for y, r in enumerate(mask)] if arms is not None else mask
    T = g["torso_px"]
    sy, hy = g["shoulder_mid"][1], g["hip_mid"][1]
    cx = (g["shoulder_mid"][0] + g["hip_mid"][0]) / 2

    def widest(a, b):
        return max(width_at(body, sy + f * T, cx) for f in _frange(a, b))

    def narrowest(a, b):
        return min((width_at(body, sy + f * T, cx), f) for f in _frange(a, b))
    px = {"shoulder": width_at(body, sy + 0.06 * T, cx), "bust": widest(0.22, 0.38), "underbust": width_at(body, sy + 0.45 * T, cx)}
    px["waist"], wf = narrowest(0.55, 0.88)
    px["high_hip"] = width_at(body, sy + 0.92 * T, cx)
    px["hip"] = widest(1.0, 1.22)
    out = {"measurable": True, "view": "front", "full_body": g["full"], "px": {}, "torso_px": round(T, 1)}
    thigh = None
    if g["legs"]:
        lk, rk = g["knees"]
        ky = (lk[1] + rk[1]) / 2
        ty = hy + 0.5 * (ky - hy)
        x0, x1 = cx - px["hip"], cx + px["hip"]
        skirt_row = skirt is not None and any(skirt[int(ty)][int(max(0, x0)):int(min(len(skirt[0]), x1))])
        if not skirt_row:
            rs_t = span_at(body, ty, x0, x1)
            rs_k = span_at(body, ky, x0, x1)
            if len(rs_t) >= 2:
                legs2 = sorted(rs_t, key=lambda r: r[1] - r[0])[-2:]
                legs2.sort()
                gap = legs2[1][0] - legs2[0][1]
                tw = max(b - a for a, b in legs2)
            elif len(rs_t) == 1:
                gap, tw = 0, (rs_t[0][1] - rs_t[0][0]) / 2
            else:
                gap, tw = None, None
            kw = (sum(b - a for a, b in sorted(rs_k, key=lambda r: r[1] - r[0])[-2:]) / max(1, min(2, len(rs_k)))) if rs_k else None
            if tw:
                thigh = {"thigh": float(tw), "gap": float(max(0, gap)), "knee": float(kw) if kw else None}
    for k2, v in px.items():
        out["px"][k2] = round(v, 1)
    if thigh:
        out["px"].update({k2: round(v, 1) for k2, v in thigh.items() if v is not None})
    else:
        out["thigh_reason"] = "legs not visible" if not g["legs"] else "skirt / dress over the thighs"
    # proportions of stature (full body only)
    H = None
    if g["full"]:
        top = next((y for y, r in enumerate(mask) if any(r)), None)
        bot = max((y for y, r in enumerate(mask) if any(r)), default=None)
        if top is not None and bot:
            H = float(bot - top)
            la, ra = g["ankles"]
            ay = (la[1] + ra[1]) / 2
            out["prop"] = {"torso": round(T / H, 3), "leg": round((ay - hy) / H, 3)}
            lw, rw = _kp(k, "left_wrist"), _kp(k, "right_wrist")
            le, re_ = _kp(k, "left_elbow"), _kp(k, "right_elbow")
            arms_len = [(_dist(s, e) + _dist(e, w)) for s, e, w in ((_kp(k, "left_shoulder"), le, lw), (_kp(k, "right_shoulder"), re_, rw)) if s and e and w]
            if arms_len:
                out["prop"]["arm"] = round(max(arms_len) / H, 3)
    out["height_px"] = round(H, 1) if H else round(T / SHOULDER_TO_HIP_OF_HEIGHT, 1)
    out["scale_from"] = "stature" if H else "torso"
    out["loose_clothing"] = bool(loose_clothing)
    return derive(out, height_cm)


def measure_side(mask, k: Dict) -> Dict:
    """Depths (front-to-back) from a side view of the same person: replaces the assumed depth/width ratios."""
    g = view_and_pose(k)
    if not g["ok"] or g["view"] != "side" or not g["standing"]:
        return dict(NOT_MEASURABLE, reason="needs a standing side view")
    T, sy = g["torso_px"], g["shoulder_mid"][1]
    cx = (g["shoulder_mid"][0] + g["hip_mid"][0]) / 2
    d = {"bust": max(width_at(mask, sy + f * T, cx) for f in _frange(0.22, 0.38)),
         "waist": min(width_at(mask, sy + f * T, cx) for f in _frange(0.55, 0.88)),
         "hip": max(width_at(mask, sy + f * T, cx) for f in _frange(1.0, 1.22))}
    return {"measurable": True, "view": "side", "depth_norm": {k2: round(v / T, 4) for k2, v in d.items()}}


def combine_side(front: Dict, side: Dict, height_cm: Optional[float] = None) -> Dict:
    if not (front.get("measurable") and side.get("measurable")):
        return front
    f = dict(front)
    f["depth_norm"] = side["depth_norm"]
    f["views"] = ["front", "side"]
    return derive(f, height_cm)


def _frange(a, b, n=9):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


# ------------------------------------------------------------------ derived values, tags, estimates
def _soft(x, lo, hi):
    """0 at lo, 1 at hi (clamped), for confidences."""
    return max(0.0, min(1.0, (x - lo) / (hi - lo))) if hi != lo else float(x >= hi)


def derive(m: Dict, height_cm: Optional[float] = None) -> Dict:
    p, T = m["px"], m["torso_px"]
    m["norm"] = {k: round(v / T, 4) for k, v in p.items() if isinstance(v, (int, float))}
    b, w, h, s = p["bust"], p["waist"], p["hip"], p["shoulder"]
    r = {"waist_hip": round(w / h, 3), "waist_bust": round(w / b, 3), "shoulder_hip": round(s / h, 3), "bust_hip": round(b / h, 3)}
    if p.get("thigh"):
        r["thigh_hip"] = round(p["thigh"] / h, 3)
        if p.get("knee"):
            r["thigh_knee"] = round(p["thigh"] / p["knee"], 3)
        r["gap_hip"] = round(p.get("gap", 0) / h, 3)
    m["ratios"] = r
    wd = 1 - w / ((b + h) / 2)
    m["scores"] = {"waist_definition": round(max(0.0, wd), 3), "curvature": round(max(0.0, min(1.0, wd * 2.2 + abs(h - b) / h)), 3)}
    m["tags"] = shape_tags(m)
    return rescale(m, height_cm)


def shape_tags(m: Dict) -> Dict[str, float]:
    """Neutral body-shape tags with confidences from the width ratios (the classic bust / waist / hip shape rules
    applied to frontal widths)."""
    r, n, sc = m["ratios"], m["norm"], m["scores"]
    wh, wb, sh, bh = r["waist_hip"], r["waist_bust"], r["shoulder_hip"], r["bust_hip"]
    t: Dict[str, float] = {"shape_measured": 0.95}
    cand = {
        "body_hourglass": min(_soft(0.80 - wh, 0, 0.10), _soft(0.80 - wb, 0, 0.10), 1 - _soft(abs(1 - bh), 0.05, 0.15)),
        "body_pear": min(_soft(1 / bh - 1, 0.03, 0.12), _soft(1 / sh - 1, 0.0, 0.10)),
        "body_inverted_triangle": max(_soft(sh - 1, 0.03, 0.15), _soft(bh - 1, 0.05, 0.15)),
        "body_rectangle": min(_soft(wh - 0.78, 0, 0.08), _soft(wb - 0.78, 0, 0.08), 1 - _soft(abs(1 - bh), 0.05, 0.12), 1 - _soft(wh - 0.92, 0, 0.05)),
        "body_apple": min(_soft(wh - 0.88, 0, 0.08), _soft(wb - 0.92, 0, 0.08)),
    }
    best = max(cand, key=cand.get)
    if cand[best] > 0.2:
        t[best] = round(0.45 + 0.45 * cand[best], 3)
    wd = sc["waist_definition"]
    t[("waist_very_defined" if wd >= 0.28 else "waist_defined" if wd >= 0.17 else "waist_straight")] = round(0.55 + 0.35 * min(1, abs(wd - 0.17) / 0.11 + 0.2), 3)
    t[("hips_wide" if sh <= 0.92 else "hips_narrow" if sh >= 1.08 else "hips_medium")] = round(0.5 + 0.4 * min(1, abs(sh - 1) / 0.12), 3)
    cv = sc["curvature"]
    t[("curves_high" if cv >= 0.55 else "curves_medium" if cv >= 0.3 else "curves_low")] = 0.7
    wn = n["waist"]   # waist width / torso height: the scale-free build cue
    t[("build_very_slim" if wn < 0.40 else "build_slim" if wn < 0.48 else "build_average" if wn < 0.58 else "build_full" if wn < 0.70 else "build_plus")] = 0.6
    if "thigh_hip" in r:
        th, gh = r["thigh_hip"], r["gap_hip"]
        t[("thigh_gap_none" if gh < 0.02 else "thigh_gap_slight" if gh < 0.06 else "thigh_gap_moderate" if gh < 0.12 else "thigh_gap_wide")] = round(0.6 + 0.3 * min(1, abs(gh - 0.06) / 0.06), 3)
        tk = r.get("thigh_knee", 1.6)
        t[("thigh_slim" if th < 0.40 and tk < 1.45 else "thigh_full" if th >= 0.52 else "thigh_curvy" if tk >= 1.75 else "thigh_athletic" if th >= 0.44 else "thigh_slim")] = 0.6
    else:
        t["thigh_not_measurable"] = 0.0
    pr = m.get("prop") or {}
    if "leg" in pr:
        t[("legs_long" if pr["leg"] >= 0.50 else "legs_short" if pr["leg"] < 0.44 else "legs_slender")] = 0.55
        ratio = pr["torso"] / pr["leg"]
        t[("torso_short" if ratio < 0.56 else "torso_long" if ratio > 0.66 else "torso_balanced")] = 0.55
    t.pop("thigh_not_measurable", None)
    return t


def rescale(m: Dict, height_cm: Optional[float] = None) -> Dict:
    """User height changed: rescale the 2D bands, then re-apply the mesh measurements (1.6.0)."""
    mesh = (m.get("mesh") or {}).get("raw")
    if m.get("mesh_only"):
        return merge_mesh(None, mesh, height_cm)
    base = {k: v for k, v in m.items() if k not in ("mesh", "source", "thigh_gap_cm")}
    r = _rescale2d(base, height_cm)
    return merge_mesh(r, mesh, height_cm) if mesh else r


def _rescale2d(m: Dict, height_cm: Optional[float] = None) -> Dict:
    """cm bands from the pixel widths: scale = stature / height_px; band = estimate ± uncertainty (relative)."""
    m = dict(m)
    user = bool(height_cm)
    Hcm = float(height_cm) if user else DEFAULT_HEIGHT_CM
    k = Hcm / m["height_px"]
    rel_h = 0.012 if user else HEIGHT_SD_CM / DEFAULT_HEIGHT_CM
    rel_p = 0.02 if m.get("scale_from") == "stature" else 0.08
    rel_d = 0.04 if m.get("depth_norm") else 0.08
    rel_c = 0.08 if m.get("loose_clothing") else 0.03
    rel = math.sqrt(rel_h ** 2 + rel_p ** 2 + rel_d ** 2 + rel_c ** 2)
    cm: Dict[str, List[float]] = {}
    for lv in ("bust", "underbust", "waist", "high_hip", "hip", "thigh"):
        wpx = m["px"].get(lv)
        if not wpx:
            continue
        if m.get("depth_norm") and lv in m["depth_norm"]:
            dpx = m["depth_norm"][lv] * m["torso_px"]
        else:
            dpx = wpx * DEPTH[lv]
        c = ellipse_perimeter(wpx * k, dpx * k)
        cm[lv] = [round(c, 1), round(c * (1 - rel)), round(c * (1 + rel))]
    for lv in ("shoulder",):
        if m["px"].get(lv):
            v = m["px"][lv] * k
            cm[lv + "_width"] = [round(v, 1), round(v * (1 - rel)), round(v * (1 + rel))]
    m["cm"] = cm
    m["height_cm"] = Hcm
    m["height_source"] = "user" if user else "assumed"
    m["uncertainty"] = round(rel, 3)
    m["estimated"] = True
    return m


MESH_FIT_REL = 0.04   # SAM 3D Body fit error on circumferences, relative (not verified on real photos; widened when 2D disagrees)


def merge_mesh(m: Optional[Dict], mesh: Optional[Dict], height_cm: Optional[float] = None) -> Optional[Dict]:
    """1.6.0: combine the 2D silhouette estimate with circumferences measured on the SAM 3D Body mesh.
    The mesh brings real depth (weight 2 against 1 for the 2D ellipse model); the band is the height uncertainty plus
    the fit error, widened by half the 2D/3D disagreement. Values stay "estimated". Without a measurable 2D estimate
    (side or seated pose) the mesh values are used alone, but no shape tags are derived from them."""
    if not mesh or not mesh.get("measurable"):
        return m
    user = bool(height_cm)
    tgt = float(height_cm) if user else DEFAULT_HEIGHT_CM
    k = tgt / float(mesh.get("height_cm") or tgt)          # the worker scaled to its own target; rescale here
    rel = math.sqrt((0.012 if user else HEIGHT_SD_CM / DEFAULT_HEIGHT_CM) ** 2 + MESH_FIT_REL ** 2)
    mc = {lv: v * k for lv, v in (mesh.get("cm") or {}).items() if isinstance(v, (int, float))}
    base = dict(m) if m and m.get("measurable") else {"measurable": True, "cm": {}, "ratios": {}, "tags": {}, "mesh_only": True,
                                                      "height_source": "user" if user else "assumed"}
    cm = dict(base.get("cm") or {})
    agree = {}
    for lv in ("bust", "underbust", "waist", "high_hip", "hip", "thigh"):
        if lv not in mc or mc[lv] <= 0:
            continue
        v = mc[lv]
        if lv in cm:
            mid, lo, hi = cm[lv]
            nm = (2 * v + mid) / 3
            spread = abs(v - mid) / 2
            cm[lv] = [round(nm, 1), round(min(nm * (1 - rel), nm - spread)), round(max(nm * (1 + rel), nm + spread))]
            agree[lv] = lo <= v <= hi
        else:
            cm[lv] = [round(v, 1), round(v * (1 - rel)), round(v * (1 + rel))]
    base["cm"] = cm
    if "thigh_gap" in mc:
        base["thigh_gap_cm"] = round(mc["thigh_gap"], 1)
    if base.get("mesh_only"):
        r = {}
        if cm.get("waist") and cm.get("hip"):
            r["waist_hip"] = round(cm["waist"][0] / cm["hip"][0], 3)
        if cm.get("waist") and cm.get("bust"):
            r["waist_bust"] = round(cm["waist"][0] / cm["bust"][0], 3)
        if cm.get("thigh") and cm.get("hip"):
            r["thigh_hip"] = round(cm["thigh"][0] / cm["hip"][0], 3)
        base["ratios"] = r
    base["mesh"] = {"model": mesh.get("model"), "cm": {lv: round(v, 1) for lv, v in mc.items()}, "agree": agree,
                    "raw": mesh}
    base["source"] = "sam3d+2d" if not base.get("mesh_only") else "sam3d"
    return base


def merge_vlm(m: Dict, vlm: Optional[Dict]) -> Dict:
    """Cross-check with a VLM's own estimate {"bust": cm, "waist": cm, "hip": cm, "shape": tag_id}: averages the cm
    midpoints (geometry weighted 2:1), widens the band when they disagree, and records agreement per value."""
    if not vlm or not m.get("measurable"):
        return m
    m = dict(m)
    m["cm"] = dict(m["cm"])
    agree = {}
    for lv in ("bust", "waist", "hip"):
        if lv in m["cm"] and isinstance(vlm.get(lv), (int, float)):
            mid, lo, hi = m["cm"][lv]
            v = float(vlm[lv])
            nm = (2 * mid + v) / 3
            spread = abs(mid - v) / 2
            m["cm"][lv] = [round(nm, 1), round(min(lo, nm - spread)), round(max(hi, nm + spread))]
            agree[lv] = lo <= v <= hi
    if vlm.get("shape"):
        agree["shape"] = vlm["shape"] in m.get("tags", {})
    m["vlm"] = {"values": {k: vlm[k] for k in ("bust", "waist", "hip", "shape") if k in vlm}, "agree": agree}
    return m


def flat(m: Optional[Dict]) -> Dict[str, float]:
    """Searchable numbers of one image: cm midpoints, ratios, proportions, scores."""
    if not m or not m.get("measurable"):
        return {}
    out = {k: v[0] for k, v in (m.get("cm") or {}).items()}
    out.update(m.get("ratios") or {})
    out.update({"prop_" + k: v for k, v in (m.get("prop") or {}).items()})
    out.update(m.get("scores") or {})
    out["height"] = m.get("height_cm")
    return out


# ------------------------------------------------------------------ search syntax
FIELDS = {
    "edad": "age", "age": "age",
    "waist": "waist", "cintura": "waist", "hip": "hip", "hips": "hip", "cadera": "hip", "caderas": "hip",
    "bust": "bust", "busto": "bust", "pecho": "bust", "underbust": "underbust", "bajopecho": "underbust",
    "highhip": "high_hip", "cadera_alta": "high_hip", "thigh": "thigh", "muslo": "thigh", "muslos": "thigh",
    "shoulders": "shoulder_width", "hombros": "shoulder_width", "height": "height", "altura": "height", "estatura": "height",
    "leg": "prop_leg", "pierna": "prop_leg", "torso": "prop_torso", "arm": "prop_arm", "brazo": "prop_arm",
    "curvature": "curvature", "curvatura": "curvature", "waistdef": "waist_definition", "definicion": "waist_definition",
}
RATIOS = {("waist", "hip"): "waist_hip", ("waist", "bust"): "waist_bust", ("shoulder", "hip"): "shoulder_hip",
          ("bust", "hip"): "bust_hip", ("thigh", "hip"): "thigh_hip", ("thigh", "knee"): "thigh_knee", ("gap", "hip"): "gap_hip"}
_ALIAS1 = {"cintura": "waist", "cadera": "hip", "caderas": "hip", "pecho": "bust", "busto": "bust", "hombro": "shoulder",
           "hombros": "shoulder", "muslo": "thigh", "rodilla": "knee", "hueco": "gap", "separacion": "gap"}


def _fold(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


_NUM = r"(\d+(?:[.,]\d+)?)"


def parse_query(q: str) -> Tuple[List[Tuple[str, float, float]], List[str], str]:
    """Split a search string into numeric conditions [(field, lo, hi)], tag terms ["cadera ancha"] and leftover text.
    Supports: cintura<65, waist>=60, cadera 90-100, ratio cintura/cadera<0.72, 90-60-90 ±5, cadera:ancha."""
    s = _fold(q)
    conds: List[Tuple[str, float, float]] = []
    terms: List[str] = []

    def num(x):
        return float(x.replace(",", "."))

    def add(field, op, a, b=None):
        a = num(a)
        if op in ("<", "<="):
            conds.append((field, -1e9, a))
        elif op in (">", ">="):
            conds.append((field, a, 1e9))
        elif op == "-":
            conds.append((field, min(a, num(b)), max(a, num(b))))
        else:
            tol = max(0.5, a * 0.03) if a > 5 else 0.02
            conds.append((field, a - tol, a + tol))

    m = re.search(rf"\b(\d{{2,3}})-(\d{{2,3}})-(\d{{2,3}})(?:\s*(?:±|\+-|\+/-)\s*{_NUM})?", s)
    if m:
        tol = num(m.group(4)) if m.group(4) else 3.0
        for f, v in zip(("bust", "waist", "hip"), m.groups()[:3]):
            conds.append((f, float(v) - tol, float(v) + tol))
        s = s.replace(m.group(0), " ")
    for m in list(re.finditer(rf"\bratio\s+([a-z_]+)\s*/\s*([a-z_]+)\s*(<=|>=|<|>|=)\s*{_NUM}", s)):
        a, b = _ALIAS1.get(m.group(1), m.group(1)), _ALIAS1.get(m.group(2), m.group(2))
        key = RATIOS.get((a, b))
        if key:
            add(key, m.group(3), m.group(4))
            s = s.replace(m.group(0), " ")
    for m in list(re.finditer(rf"\b([a-z_]+)\s*(<=|>=|<|>|=)\s*{_NUM}", s)):
        f = FIELDS.get(m.group(1))
        if f:
            add(f, m.group(2), m.group(3))
            s = s.replace(m.group(0), " ")
    for m in list(re.finditer(rf"\b([a-z_]+)\s+{_NUM}\s*-\s*{_NUM}\b", s)):
        f = FIELDS.get(m.group(1))
        if f:
            add(f, "-", m.group(2), m.group(3))
            s = s.replace(m.group(0), " ")
    for m in list(re.finditer(r"\b([a-z_]+):([a-z_]+)\b", s)):
        terms.append(f"{m.group(1)} {m.group(2)}".replace("_", " "))
        s = s.replace(m.group(0), " ")
    return conds, terms, " ".join(s.split())


def matches(nums: Dict[str, float], conds) -> bool:
    for f, lo, hi in conds:
        v = nums.get(f)
        if v is None or not (lo <= v <= hi):
            return False
    return True


# ------------------------------------------------------------------ local models (lazy; GPU on the PC)
POSE_REPO = "usyd-community/vitpose-base-simple"        # ViTPose-B, Apache-2.0, 0.34 GB, transformers >= 4.48
SEG_REPO, SEG_REV = "ZhengPeng7/BiRefNet", "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"   # MIT, 0.44 GB, pinned (remote code)
# (SegFormer "clothes" human parsing was considered: its licence is "other" / research data, so it is not used.)


def arm_mask(shape, k: Dict, torso_px: float):
    """Arms from the keypoints (thick shoulder-elbow-wrist segments), so they are not counted in the torso widths."""
    H, W = shape
    r = max(3.0, 0.085 * torso_px)
    m = [[False] * W for _ in range(H)]
    for side in ("left", "right"):
        pts = [_kp(k, f"{side}_{j}") for j in ("shoulder", "elbow", "wrist")]
        for n_seg, (a, b) in enumerate(zip(pts, pts[1:])):
            if not (a and b):
                continue
            if n_seg == 0:   # start below the armpit: the shoulder joint and the bust line belong to the torso
                a = (a[0] + 0.35 * (b[0] - a[0]), a[1] + 0.35 * (b[1] - a[1]))
            x0, x1 = int(max(0, min(a[0], b[0]) - r)), int(min(W - 1, max(a[0], b[0]) + r))
            y0, y1 = int(max(0, min(a[1], b[1]) - r)), int(min(H - 1, max(a[1], b[1]) + r))
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1.0
            for y in range(y0, y1 + 1):
                row = m[y]
                for x in range(x0, x1 + 1):
                    t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
                    if (x - a[0] - t * dx) ** 2 + (y - a[1] - t * dy) ** 2 <= r * r:
                        row[x] = True
    return m


class BodyParser:
    """Silhouette (BiRefNet) + COCO keypoints (ViTPose) for one image; load()/unload() follow the tagger's GPU rules."""

    def __init__(self, device: Optional[str] = None, cache_dir: Optional[str] = None, offline: bool = False):
        self.device, self.cache_dir, self.offline = device, cache_dir, offline
        self.m = None

    def load(self):
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageSegmentation, VitPoseForPoseEstimation
        dev = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        kw = {"cache_dir": self.cache_dir, "local_files_only": self.offline}
        seg = AutoModelForImageSegmentation.from_pretrained(SEG_REPO, revision=SEG_REV, trust_remote_code=True, **kw)
        self.m = {"dev": dev, "pp": AutoImageProcessor.from_pretrained(POSE_REPO, **kw),
                  "pose": VitPoseForPoseEstimation.from_pretrained(POSE_REPO, **kw).to(dev).eval(),
                  "seg": seg.to(dev).eval().half() if dev == "cuda" else seg.eval()}

    def unload(self):
        self.m = None
        try:
            import gc, torch
            gc.collect(); torch.cuda.empty_cache()
        except Exception:
            pass

    def parse(self, path: str, max_side: int = 768) -> Optional[Dict]:
        import numpy as np, torch
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.thumbnail((max_side, max_side))
        W, H = im.size
        m = self.m
        x = torch.from_numpy(np.asarray(im.resize((1024, 1024)), dtype=np.float32) / 255.0).permute(2, 0, 1)
        x = ((x - torch.tensor([0.485, 0.456, 0.406])[:, None, None]) / torch.tensor([0.229, 0.224, 0.225])[:, None, None])[None]
        x = x.to(m["dev"], dtype=next(m["seg"].parameters()).dtype)
        with torch.inference_mode():
            pred = m["seg"](x)[-1].sigmoid().float()
            pred = torch.nn.functional.interpolate(pred, size=(H, W), mode="bilinear", align_corners=False)[0, 0].cpu().numpy()
        person = pred > 0.5
        if person.sum() < 0.02 * W * H:
            return None
        ys, xs = np.where(person)
        box = [[float(xs.min()), float(ys.min()), float(xs.max() - xs.min()), float(ys.max() - ys.min())]]
        with torch.inference_mode():
            inp = m["pp"](im, boxes=[box], return_tensors="pt").to(m["dev"])
            out = m["pose"](**inp)
            res = m["pp"].post_process_pose_estimation(out, boxes=[box])[0][0]
        names = ["nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder", "right_shoulder", "left_elbow",
                 "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"]
        kps = {n: (float(p[0]), float(p[1]), float(s)) for n, p, s in zip(names, res["keypoints"].tolist(), res["scores"].tolist())}
        mask = person.tolist()
        g = view_and_pose(kps)
        arms = arm_mask((H, W), kps, g["torso_px"]) if g.get("ok") else None
        return {"mask": mask, "arms": arms, "kps": kps}

    def analyse(self, path: str, height_cm: Optional[float] = None, loose: bool = False, skirt: bool = False) -> Dict:
        """skirt=True (the tagger saw a skirt / dress): thigh values are marked not measurable."""
        r = self.parse(path)
        if not r:
            return dict(NOT_MEASURABLE, reason="no person found")
        m = measure_front(r["mask"], r["kps"], r["arms"], None, height_cm, loose)
        if skirt and m.get("measurable") and "thigh" in m.get("px", {}):
            for k in ("thigh", "gap", "knee"):
                m["px"].pop(k, None)
            m["thigh_reason"] = "skirt / dress over the thighs"
            m = derive(m, height_cm)
        return m
