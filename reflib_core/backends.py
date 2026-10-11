"""Tagging backends. All share: load(), unload(), predict(paths) -> [{"scores": {tag_id: conf}, "minor": p}].
Heavy libraries (onnxruntime, torch, transformers, huggingface_hub) are imported lazily, only by the real backends.

  fake      deterministic, no download (tests / demo)
  wd        SmilingWolf WD-EVA02-Large tagger v3 (ONNX, Apache-2.0, ~1.3 GB): fast broad pass
  qwen      Qwen2.5-VL-7B-Instruct (Apache-2.0, ~16.6 GB bf16) with a JSON answer validated against the taxonomy
  wd+qwen   WD for what booru tags describe well, Qwen for the fine groups (body type, coverage, pose…)
  jev       jevimage (MIT, pinned 0.1.20): one frozen SigLIP2 encode, the taxonomy as typed questions
            (choice / score / noul / trained heads); in-process or a `jevimage serve` URL
  jev+qwen  recommended: Jev for every group, Qwen2.5-VL only for the fine groups where zero-shot is weak
  openai / gemini / grok   optional cloud classifiers (off by default), JSON-schema output, local fallback on refusal
"""
from __future__ import annotations
import hashlib, json, os, re
from typing import Callable, Dict, List, Optional
from . import taxonomy

MODELS = {
    "fake": {"label": "Fake (tests)", "size_gb": 0.0, "licence": "MIT", "repos": []},
    "wd": {"label": "WD-EVA02-Large tagger v3", "size_gb": 1.3, "licence": "Apache-2.0", "repos": ["SmilingWolf/wd-eva02-large-tagger-v3"]},
    "wd-small": {"label": "WD-ViT tagger v3 (small)", "size_gb": 0.4, "licence": "Apache-2.0", "repos": ["SmilingWolf/wd-vit-tagger-v3"]},
    "qwen": {"label": "Qwen2.5-VL-7B-Instruct", "size_gb": 16.6, "licence": "Apache-2.0", "repos": ["Qwen/Qwen2.5-VL-7B-Instruct"]},
    "wd+qwen": {"label": "WD-EVA02 + Qwen2.5-VL-7B (recommended)", "size_gb": 17.9, "licence": "Apache-2.0",
                "repos": ["SmilingWolf/wd-eva02-large-tagger-v3", "Qwen/Qwen2.5-VL-7B-Instruct"]},
}
MODELS.update({
    "jev": {"label": "Jev (jevimage 0.1.20, SigLIP2 so400m; server URL or own venv)", "size_gb": 4.5, "licence": "MIT (jevimage) + Apache-2.0 (SigLIP2)",
            "repos": ["google/siglip2-so400m-patch16-384"]},
    "jev+qwen": {"label": "Jev + Qwen2.5-VL-7B for fine groups (needs a Jev server)", "size_gb": 21.1, "licence": "MIT + Apache-2.0",
                 "repos": ["google/siglip2-so400m-patch16-384", "Qwen/Qwen2.5-VL-7B-Instruct"]},
    "openai": {"label": "OpenAI-compatible endpoint (cloud)", "size_gb": 0.0, "licence": "service terms", "repos": [], "cloud": True},
    "gemini": {"label": "Google Gemini (cloud)", "size_gb": 0.0, "licence": "service terms", "repos": [], "cloud": True},
    "grok": {"label": "xAI Grok (cloud)", "size_gb": 0.0, "licence": "service terms", "repos": [], "cloud": True},
})
BODY_MODELS = {"size_gb": 0.8, "repos": ["usyd-community/vitpose-base-simple", "ZhengPeng7/BiRefNet"]}   # body-shape pass
MINOR_THRESHOLD = 0.2
STORE_MIN = 0.15   # deliberately low: when in doubt, no body/nudity tags and a review flag


AGE_MID = {"age_18_24": 21.0, "age_25_34": 29.5, "age_35_44": 39.5, "age_45_54": 49.5, "age_55_64": 59.5, "age_65_plus": 70.0}


def age_estimate(scores: Dict[str, float]) -> Optional[Dict[str, float]]:
    """Weighted mean of the band midpoints with a ± from their spread (min ±4 years): an estimate, never exact.
    Adult bands only, so the estimate is always >= 18."""
    w = {k: float(scores.get(k, 0)) for k in AGE_MID if float(scores.get(k, 0)) > 0}
    tot = sum(w.values())
    if tot <= 0:
        return None
    m = sum(AGE_MID[k] * v for k, v in w.items()) / tot
    sd = (sum(v * (AGE_MID[k] - m) ** 2 for k, v in w.items()) / tot) ** 0.5
    return {"est": round(max(18.0, m), 1), "pm": round(max(4.0, sd + 3.0), 1)}


EXPLICIT_THRESHOLD = 0.5
# groups skipped when the explicit-content review flag is set (fine body shape and measurements)
BODY_SHAPE_GROUPS = {"body_type", "height_impression", "bust_impression", "hip_impression", "waist_definition", "build_scale",
                     "curvature", "muscle_tone", "leg_shape", "thigh_shape", "thigh_gap", "torso_proportion", "measurability"}


def finalize(scores: Dict[str, float], minor: float, source: str, minor_threshold: float = MINOR_THRESHOLD,
             body: Optional[Dict] = None, explicit: float = 0.0) -> Dict:
    """Exclusive groups keep one label; the safety rule drops every sensitive (body/nudity) tag when the person may
    be under 18 and flags the image for review."""
    best: Dict[str, tuple] = {}
    out: Dict[str, List] = {}
    for tid, c in scores.items():
        n = taxonomy.node(tid)
        if not n or n["kind"] != "tag" or c < STORE_MIN:   # keep the store small: the UI threshold starts at 0.35
            continue
        g = taxonomy.node(taxonomy.group_of(tid))
        if g and g.get("exclusive"):
            if g["id"] not in best or c > best[g["id"]][1]:
                best[g["id"]] = (tid, c)
        else:
            out[tid] = [round(float(c), 3), source]
    for tid, c in best.values():
        out[tid] = [round(float(c), 3), source]
    review = minor >= minor_threshold
    if review:
        out = {t: v for t, v in out.items() if not taxonomy.is_sensitive(t) and taxonomy.group_of(t) != "age_band"}
        out["appears_minor"] = [round(float(minor), 3), source]
        out["needs_review"] = [1.0, source]
        body = None   # the minor gate comes first: no body measurements either
    flagged = (not review) and explicit >= EXPLICIT_THRESHOLD
    if flagged:   # coarse review flag only: never described; fine body-shape / measurement tags are skipped
        out = {t: v for t, v in out.items() if taxonomy.group_of(t) not in BODY_SHAPE_GROUPS}
        out["explicit_content"] = [round(float(explicit), 3), source]
        out["needs_review"] = [1.0, source]
        body = None
    r = {"tags": out, "review": review or flagged}
    if flagged:
        r["explicit"] = True
    if body:
        r["body"] = body
    if not review:   # 1.5.1 numeric apparent age (estimated) from the adult band scores; never for flagged images
        a = age_estimate(scores)
        if a:
            r["age"] = a
    return r


class Backend:
    name = "base"

    def __init__(self, cfg: Optional[Dict] = None):
        self.cfg = cfg or {}
        self.loaded = False

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False

    def predict(self, paths: List[str]) -> List[Dict]:
        raise NotImplementedError


def synth_silhouette(sh, bu, wa, hi, thigh=60, gap=10, knee=40, W=400, H=900, sy=200, T=240, legs=True):
    """A front silhouette mask + COCO keypoints with known widths (tests and the fake backend)."""
    cx = W // 2
    rows = [(sy - 80, 40), (sy, sh / 2), (sy + 0.30 * T, bu / 2), (sy + 0.72 * T, wa / 2), (sy + 1.1 * T, hi / 2), (sy + 1.2 * T, hi / 2 - 4)]
    m = [[False] * W for _ in range(H)]
    for y in range(sy - 80, int(sy + 1.2 * T)):
        for (y0, a), (y1, b) in zip(rows, rows[1:]):
            if y0 <= y <= y1:
                hw = a + (b - a) * (y - y0) / (y1 - y0)
                m[y][int(cx - hw):int(cx + hw)] = [True] * (int(cx + hw) - int(cx - hw))
                break
    ky = sy + 2 * T
    if legs:
        for y in range(int(sy + 1.2 * T), H - 20):
            t = min(1, (y - (sy + 1.2 * T)) / (ky - (sy + 1.2 * T)))
            w = thigh + (knee - thigh) * t
            g = gap / 2
            for a, b in ((cx - g - w, cx - g), (cx + g, cx + g + w)):
                m[y][int(a):int(b)] = [True] * (int(b) - int(a))
    hy = sy + T
    k = {"nose": (cx, sy - 50, .9), "left_shoulder": (cx - sh / 2 + 10, sy, .9), "right_shoulder": (cx + sh / 2 - 10, sy, .9),
         "left_hip": (cx - 40, hy, .9), "right_hip": (cx + 40, hy, .9)}
    if legs:
        k.update({"left_knee": (cx - 40, ky, .9), "right_knee": (cx + 40, ky, .9), "left_ankle": (cx - 40, H - 40, .9), "right_ankle": (cx + 40, H - 40, .9)})
    return m, k


class FakeBackend(Backend):
    """No model: image size -> format, mean colour -> garment colour, filename words naming tag ids (e.g.
    'hair_short-body_hourglass.png') -> those tags; 'minorcheck' in the name -> appears_minor. Benign test images only."""
    name = "fake"

    def predict(self, paths):
        from PIL import Image
        out = []
        ids = set(taxonomy.tag_ids())
        import time as _t
        for p in paths:
            if self.cfg.get("fake_delay"):
                _t.sleep(float(self.cfg["fake_delay"]))
            s: Dict[str, float] = {}
            with Image.open(p) as im:
                w, h = im.size
                r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
                hint = str(im.info.get("reflib_fake") or "")   # test images carry their tokens in a PNG text chunk
            s["portrait_format" if h > w * 1.05 else "landscape_format" if w > h * 1.05 else "square_format"] = 0.99
            s[max([("color_red", r - (g + b) / 2), ("color_green", g - (r + b) / 2), ("color_blue", b - (r + g) / 2),
                   ("color_black", 60 - max(r, g, b)), ("color_white", min(r, g, b) - 200)], key=lambda x: x[1])[0]] = 0.8
            base = (os.path.splitext(os.path.basename(p))[0] + " " + hint).lower()
            for word in re.split(r"[-\s.]+", base):
                if word in ids:
                    s[word] = 0.9
            jitter = int(hashlib.sha1(base.encode()).hexdigest()[:4], 16) / 65535
            s["photo_real"] = 0.6 + 0.3 * jitter
            if "failcheck" in base:
                raise RuntimeError("fake failure (test)")
            out.append({"scores": s, "minor": 0.9 if "minorcheck" in base else 0.01, "explicit": 0.9 if "explicitcheck" in base else 0.0})
        return out

    def body(self, path, height_cm=None):
        """Synthetic silhouette from a filename token like 'body170x170x110x180' (shoulder, bust, waist, hip px)."""
        from . import bodyshape
        from PIL import Image
        with Image.open(path) as im:
            hint = str(im.info.get("reflib_fake") or "")
        m = re.search(r"body(\d+)x(\d+)x(\d+)x(\d+)", (os.path.basename(path) + " " + hint).lower())
        if not m:
            return dict(bodyshape.NOT_MEASURABLE, reason="no person found")
        mask, kps = synth_silhouette(*[int(x) for x in m.groups()])
        return bodyshape.measure_front(mask, kps, height_cm=height_cm)


# booru tag (WD vocabulary) -> taxonomy ids
WD_MAP = {
    "close-up": "closeup", "portrait": "head_shoulders", "upper_body": "half_body", "cowboy_shot": "three_quarter_body", "full_body": "full_body",
    "from_above": "high_angle", "from_below": "low_angle", "dutch_angle": "dutch_angle",
    "standing": "standing", "sitting": "sitting", "lying": "lying", "on_back": "lying_on_back", "on_stomach": "lying_on_stomach", "on_side": "lying_on_side",
    "kneeling": "kneeling", "squatting": "squatting", "walking": "walking", "running": "running", "jumping": "jumping", "dancing": "dancing", "indian_style": "cross_legged", "crossed_legs": "cross_legged",
    "from_side": "side_view", "from_behind": "back_view", "looking_back": "back_view",
    "arms_up": "arms_up", "crossed_arms": "arms_crossed", "hands_on_hips": "hands_on_hips", "hand_in_own_hair": "hand_in_hair", "arms_behind_head": "hands_behind_head",
    "hand_on_own_face": "hand_on_face", "arms_behind_back": "hands_behind_back", "hands_in_pockets": "hands_in_pockets", "holding_phone": "holding_phone", "holding_cup": "holding_drink",
    "nude": "nude", "completely_nude": "nude", "topless": "topless", "bottomless": "bottomless", "underwear_only": "underwear_only", "convenient_censoring": "implied_nude",
    "t-shirt": "t_shirt", "crop_top": "crop_top", "tank_top": "tank_top", "blouse": "blouse", "collared_shirt": "shirt", "sweater": "sweater", "hoodie": "hoodie", "leotard": "bodysuit", "corset": "corset", "tube_top": "tube_top",
    "jeans": "jeans", "denim_shorts": "denim_shorts", "pants": "trousers", "leggings": "leggings", "shorts": "shorts", "skirt": "skirt", "miniskirt": "miniskirt", "pencil_skirt": "pencil_skirt", "pleated_skirt": "pleated_skirt", "long_skirt": "maxi_skirt",
    "dress": "dress", "short_dress": "mini_dress", "long_dress": "maxi_dress", "evening_gown": "evening_gown", "sundress": "sundress", "wedding_dress": "wedding_dress",
    "bikini": "bikini", "string_bikini": "string_bikini", "one-piece_swimsuit": "one_piece_swimsuit", "sarong": "sarong",
    "bra": "bra", "sports_bra": "sports_bra", "panties": "panties", "thong": "thong", "lingerie": "lingerie_set", "babydoll": "babydoll", "thighhighs": "stockings", "pantyhose": "stockings", "garter_belt": "garter_belt", "bathrobe": "robe", "nightgown": "nightgown", "pajamas": "nightgown",
    "jacket": "jacket", "leather_jacket": "leather_jacket", "denim_jacket": "denim_jacket", "coat": "coat", "trench_coat": "coat", "blazer": "blazer", "cardigan": "cardigan", "vest": "vest",
    "barefoot": "barefoot", "high_heels": "heels", "platform_footwear": "platform_heels", "boots": "boots", "ankle_boots": "ankle_boots", "thigh_boots": "knee_boots", "knee_boots": "knee_boots", "sneakers": "sneakers", "sandals": "sandals", "loafers": "flats",
    "hat": "hat", "baseball_cap": "hat", "scarf": "scarf", "belt": "belt", "handbag": "bag", "necklace": "necklace", "choker": "necklace", "earrings": "earrings", "bracelet": "bracelet", "watch": "watch", "ring": "ring", "gloves": "gloves", "hairband": "hair_accessory", "hair_ornament": "hair_accessory", "hair_bow": "hair_accessory",
    "striped": "striped", "floral_print": "floral", "polka_dot": "polka_dot", "plaid": "plaid", "leopard_print": "animal_print", "lace": "lace", "see-through": "sheer", "sequins": "sequins", "latex": "leather",
    "very_short_hair": "hair_very_short", "short_hair": "hair_short", "medium_hair": "hair_medium", "long_hair": "hair_long", "very_long_hair": "hair_very_long", "absurdly_long_hair": "hair_very_long",
    "black_hair": "hair_black", "brown_hair": "hair_brown", "blonde_hair": "hair_blonde", "red_hair": "hair_red", "orange_hair": "hair_red", "grey_hair": "hair_grey", "white_hair": "hair_grey", "pink_hair": "hair_dyed", "blue_hair": "hair_dyed", "purple_hair": "hair_dyed", "green_hair": "hair_dyed", "gradient_hair": "hair_ombre", "streaked_hair": "hair_ombre",
    "ponytail": "ponytail", "hair_bun": "bun", "single_hair_bun": "bun", "braid": "braid", "twintails": "pigtails", "bangs": "bangs", "wet_hair": "wet_hair", "messy_hair": "messy_hair", "wavy_hair": "hair_wavy", "curly_hair": "hair_curly", "straight_hair": "hair_straight",
    "muscular_female": "body_muscular", "toned": "body_athletic", "plump": "body_plus_size", "curvy": "body_curvy", "wide_hips": "hips_wide", "small_breasts": "bust_small", "medium_breasts": "bust_medium", "large_breasts": "bust_large",
    "dark_skin": "skin_6", "tan": "skin_4", "pale_skin": "skin_1", "tattoo": "tattoo", "arm_tattoo": "tattoo_arm", "leg_tattoo": "tattoo_leg", "back_tattoo": "tattoo_back", "nose_piercing": "piercing_nose", "navel_piercing": "piercing_navel", "ear_piercing": "piercing_ear", "piercing": "piercing", "freckles": "freckles", "mole": "beauty_mark",
    "smile": "smile", "laughing": "laughing", "grin": "smile", "expressionless": "neutral_expr", "serious": "neutral_expr", "one_eye_closed": "playful", "tongue_out": "playful", "sad": "sad", "surprised": "surprised",
    "looking_at_viewer": "gaze_camera", "looking_away": "gaze_away", "looking_to_the_side": "gaze_away", "looking_down": "gaze_down", "looking_up": "gaze_up", "closed_eyes": "eyes_closed",
    "makeup": "makeup_natural", "eyeshadow": "makeup_glam", "red_lips": "lips_red", "lipstick": "lips_nude", "glasses": "glasses", "sunglasses": "sunglasses",
    "indoors": "indoor", "outdoors": "outdoor", "bedroom": "bedroom", "bed": "bedroom", "bathroom": "bathroom", "bathtub": "bathroom", "shower_(place)": "bathroom", "couch": "living_room", "kitchen": "kitchen", "office": "office", "gym": "gym",
    "beach": "beach", "ocean": "beach", "pool": "pool", "street": "street", "city": "street", "forest": "nature", "nature": "nature", "garden": "nature", "mountain": "mountain", "car": "car", "car_interior": "car", "restaurant": "restaurant_bar", "bar_(place)": "restaurant_bar",
    "sunlight": "natural_light", "sunset": "golden_hour", "backlighting": "backlit", "neon_lights": "neon", "night": "night", "dark": "low_key",
    "simple_background": "bg_plain", "white_background": "bg_white", "black_background": "bg_dark", "blurry_background": "bg_blurred",
    "selfie": "style_selfie", "mirror": "mirror_selfie", "photorealistic": "photo_real", "realistic": "photo_real", "photo_(medium)": "photo_real", "monochrome": "black_white", "greyscale": "black_white",
    "solo": "solo", "1girl": "solo", "2girls": "two_people", "multiple_girls": "group", "no_humans": "no_people",
}
EXPLICIT_BOORU = ("sex",)   # generic activity tag of the taggers: only raises the coarse review flag
WD_MINOR = ("child", "loli", "shota", "aged_down", "toddler", "kindergarten_uniform", "elementary_school_uniform")


def _hf_file(repo: str, name: str, offline: bool, cache_dir: Optional[str]) -> str:
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo, name, local_files_only=offline, cache_dir=cache_dir)


class WDBackend(Backend):
    """WD tagger v3 through onnxruntime (CUDA provider when available). Input 448x448 BGR, white padding."""
    name = "wd"

    def __init__(self, cfg=None, repo="SmilingWolf/wd-eva02-large-tagger-v3"):
        super().__init__(cfg)
        self.repo = repo
        self.sess = None

    def load(self):
        import csv, onnxruntime as ort
        off, cache = bool(self.cfg.get("offline")), self.cfg.get("cache_dir")
        model = _hf_file(self.repo, "model.onnx", off, cache)
        with open(_hf_file(self.repo, "selected_tags.csv", off, cache), newline="", encoding="utf-8") as f:
            self.tags = [r["name"] for r in csv.DictReader(f)]
        prov = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
        if self.cfg.get("device") == "cpu":
            prov = ["CPUExecutionProvider"]
        self.sess = ort.InferenceSession(model, providers=prov)
        self.size = self.sess.get_inputs()[0].shape[1] or 448
        self.loaded = True

    def unload(self):
        self.sess = None
        self.loaded = False

    def _prep(self, path):
        import numpy as np
        from PIL import Image
        with Image.open(path) as im:
            if im.format == "JPEG":
                im.draft("RGB", (self.size * 2, self.size * 2))
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg.convert("RGB")
        s = max(im.size)
        sq = Image.new("RGB", (s, s), (255, 255, 255)); sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
        sq = sq.resize((self.size, self.size), Image.BICUBIC)
        return np.asarray(sq, dtype=np.float32)[:, :, ::-1]

    def raw(self, paths) -> List[Dict[str, float]]:
        import numpy as np
        x = np.stack([self._prep(p) for p in paths])
        probs = self.sess.run(None, {self.sess.get_inputs()[0].name: x})[0]
        return [{t: float(p) for t, p in zip(self.tags, row)} for row in probs]

    def predict(self, paths):
        out = []
        for booru in self.raw(paths):
            out.append(map_booru(booru))
        return out


def map_booru(booru: Dict[str, float]) -> Dict:
    s: Dict[str, float] = {}
    for bt, tid in WD_MAP.items():
        c = booru.get(bt, 0.0)
        if c > s.get(tid, 0.0):
            s[tid] = c
    if booru.get("rating:explicit", booru.get("explicit", 0)) > 0.5 and "nude" not in s:
        s["partially_clothed"] = 0.4
    clothed_hint = max([booru.get(k, 0) for k in ("shirt", "dress", "jacket", "pants", "skirt", "jeans", "sweater")] + [0])
    if clothed_hint > 0.5 and s.get("nude", 0) < 0.3:
        s["clothed"] = clothed_hint
    return {"scores": s, "minor": max([booru.get(k, 0.0) for k in WD_MINOR] + [0.0]),
            "explicit": max([booru.get(k, 0.0) for k in EXPLICIT_BOORU] + [0.0])}


# ---- local VLM with a JSON answer, validated against the taxonomy (unknown values are dropped) ----
VLM_GROUPS = ["shot", "angle", "body_pose", "body_orientation", "arms", "coverage", "tops", "bottoms", "dresses", "swimwear", "lingerie",
              "outerwear", "footwear", "garment_color", "garment_pattern", "hair_length", "hair_color", "hair_style", "hair_texture",
              "body_type", "height_impression", "skin_tone", "age_band", "expression", "gaze", "makeup", "eyewear", "place_type",
              "location", "lighting", "background", "photo_style", "medium", "people_count"]


def vlm_prompt(groups=VLM_GROUPS) -> str:
    lines = []
    for g in groups:
        n = taxonomy.node(g)
        opts = ", ".join(taxonomy.tags_in_group(g))
        lines.append(f'"{g}": {"one of" if n.get("exclusive") else "list of"} [{opts}] or null')
    return ("You label reference photos for an image library. Describe only what is visible, neutrally. "
            "Answer with ONE JSON object and nothing else, with these keys:\n" + "\n".join(lines) +
            '\n"appears_minor": true if the person could be under 18, else false\n"explicit_activity": true only if the image shows explicit sexual activity, else false (just the flag, never describe it)\n"confidence": 0.0-1.0 overall confidence')


def parse_vlm(text: str, groups=VLM_GROUPS) -> Dict:
    """Constrained parse: first JSON object in the answer; values outside the group's options are ignored."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    conf = d.get("confidence")
    conf = min(1.0, max(0.0, float(conf))) if isinstance(conf, (int, float)) else 0.7
    s: Dict[str, float] = {}
    for g in groups:
        allowed = set(taxonomy.tags_in_group(g))
        v = d.get(g)
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str) and x in allowed:
                s[x] = conf
    minor = d.get("appears_minor")
    ex = d.get("explicit_activity")
    return {"explicit": 0.9 if ex is True or ex == "true" else 0.0,
            "scores": s, "minor": 0.9 if minor is True or minor == "true" else (0.5 if minor is None and d else 0.0 if d else 0.5)}


class QwenVLBackend(Backend):
    name = "qwen"

    def __init__(self, cfg=None, repo="Qwen/Qwen2.5-VL-7B-Instruct"):
        super().__init__(cfg)
        self.repo = repo
        self.model = self.proc = None

    def load(self):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        kw = {"local_files_only": bool(self.cfg.get("offline")), "cache_dir": self.cfg.get("cache_dir")}
        dev = "cuda" if torch.cuda.is_available() and self.cfg.get("device") != "cpu" else "cpu"
        mm = {0: f"{int(self.cfg.get('vram_gb') or 20)}GiB", "cpu": "64GiB"} if dev == "cuda" else None
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.repo, torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
            device_map="auto" if dev == "cuda" else None, max_memory=mm, **kw).eval()
        self.proc = AutoProcessor.from_pretrained(self.repo, min_pixels=256 * 28 * 28, max_pixels=768 * 28 * 28, **kw)
        self.loaded = True

    def unload(self):
        self.model = self.proc = None
        self.loaded = False
        try:
            import gc, torch
            gc.collect(); torch.cuda.empty_cache()
        except Exception:
            pass

    def describe(self, path: str, prompt: str, max_new_tokens: int = 400) -> str:
        import torch
        from PIL import Image
        img = Image.open(path).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
        text = self.proc.apply_chat_template(msgs, add_generation_prompt=True)
        inp = self.proc(text=[text], images=[img], return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            ids = self.model.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False)
        return self.proc.batch_decode(ids[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0]

    def predict(self, paths):
        return [parse_vlm(self.describe(p, vlm_prompt())) for p in paths]

    def body_estimate(self, path):
        return parse_body_vlm(self.describe(path, BODY_VLM_PROMPT, 80))


BODY_VLM_PROMPT = ("Estimate, for the adult in this photo, the approximate bust, waist and hip circumferences in cm "
                   "as a dressmaker would, and the body shape. Reply with JSON only: {\"bust\": number, \"waist\": number, "
                   "\"hip\": number, \"shape\": one of [body_hourglass, body_pear, body_apple, body_inverted_triangle, "
                   "body_rectangle]}. If the body is not clearly visible or the person could be under 18, reply {}.")


def parse_body_vlm(text: str) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        return None
    out = {k: float(d[k]) for k in ("bust", "waist", "hip") if isinstance(d.get(k), (int, float)) and 40 <= d[k] <= 200}
    if d.get("shape") in ("body_hourglass", "body_pear", "body_apple", "body_inverted_triangle", "body_rectangle"):
        out["shape"] = d["shape"]
    return out or None


class PipelineBackend(Backend):
    """WD for the broad pass, then the VLM; per tag the higher confidence wins, minor = max of both."""
    name = "wd+qwen"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.parts = [WDBackend(cfg), QwenVLBackend(cfg)]

    def load(self):
        for b in self.parts:
            b.load()
        self.loaded = True

    def unload(self):
        for b in self.parts:
            b.unload()
        self.loaded = False

    def predict(self, paths):
        res = [b.predict(paths) for b in self.parts]
        out = []
        for k in range(len(paths)):
            s: Dict[str, float] = {}
            for r in res:
                for t, c in r[k]["scores"].items():
                    s[t] = max(c, s.get(t, 0.0))
            out.append({"scores": s, "minor": max(r[k]["minor"] for r in res)})
        return out


def make_backend(name: str, cfg: Optional[Dict] = None) -> Backend:
    cfg = cfg or {}
    if name == "fake":
        return FakeBackend(cfg)
    if name == "wd":
        return WDBackend(cfg)
    if name == "wd-small":
        return WDBackend(cfg, "SmilingWolf/wd-vit-tagger-v3")
    if name == "qwen":
        return QwenVLBackend(cfg)
    if name == "wd+qwen":
        return PipelineBackend(cfg)
    raise ValueError(f"unknown model {name}")


def is_downloaded(name: str, cache_dir: Optional[str] = None) -> bool:
    if not MODELS.get(name, {}).get("repos"):
        return True
    try:
        from huggingface_hub import snapshot_download
        for r in MODELS[name]["repos"]:
            snapshot_download(r, local_files_only=True, cache_dir=cache_dir)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------- Jev (jevimage)
# The taxonomy maps onto Jev's typed questions: exclusive groups -> "choice", ordinal groups -> "score",
# multi-label tags -> "noul" (yes/no contrast pair), and groups with a trained head -> "head".
JEV_VERSION = "0.1.20"
ORDINAL = {"shot", "hair_length", "height_impression", "bust_impression", "hip_impression", "skin_tone", "age_band"}
# descriptive English captions, as the jevimage docs advise ("a photo of …", not bare words)
CAPTION = {
    "shot": "a {} photo of a person", "angle": "a photo of a person taken at {}", "orientation_img": "an image in {}",
    "body_pose": "a photo of a woman {}", "body_orientation": "a photo of a person seen in {}", "arms": "a photo of a woman with {}",
    "coverage": "a photo of a woman who is {}", "garment_color": "a person wearing {} clothes", "garment_pattern": "a person wearing a {} garment",
    "garment_fit": "a person wearing clothes that are {}", "hair_length": "a photo of a woman with {}", "hair_color": "a photo of a woman with {}",
    "hair_style": "a photo of a woman with {}", "hair_texture": "a photo of a woman with {}", "body_type": "a photo of a woman with a {} body type",
    "height_impression": "a photo of a woman who {}", "bust_impression": "a photo of a woman with a {}", "hip_impression": "a photo of a woman with {}",
    "skin_tone": "a photo of a person with {}", "age_band": "a photo of a woman who looks like a {}", "body_marks": "a photo of a person with a {}",
    "expression": "a photo of a person {}", "gaze": "a photo of a person {}", "makeup": "a photo of a woman wearing {}", "lips": "a photo of a woman wearing {}",
    "eyewear": "a photo of a person wearing {}", "place_type": "a photo taken {}", "location": "a photo taken in a {}", "lighting": "a photo with {}",
    "background": "a photo of a person with a {}", "photo_style": "a {}", "medium": "an image that is a {}", "color_grade": "a photo in {}",
    "people_count": "a photo of {}",
}
FINE_GROUPS = ["body_type", "coverage", "bust_impression", "hip_impression", "height_impression", "arms", "garment_fit", "photo_style", "age_band"]


def _caption(tid: str) -> str:
    g = taxonomy.group_of(tid)
    return CAPTION.get(g, "a photo showing {}").format(taxonomy.label(tid, "en"))


def jev_questions(heads: Optional[Dict[str, str]] = None) -> Dict[str, Dict]:
    """The whole taxonomy as Jev questions (≤ 64 per ask: callers chunk). Only leaf-level choice per group; parents
    come back through the hierarchy. heads: {group_id: head_name} for groups with a trained head."""
    q: Dict[str, Dict] = {}
    for g in taxonomy.groups():
        gid = g["id"]
        if gid == "safety":
            continue
        tags = sorted(taxonomy.tags_in_group(gid), key=list(taxonomy.load()["nodes"]).index)
        if heads and gid in heads:
            q[gid] = {"type": "head", "head": heads[gid]}
        elif g.get("exclusive") and gid in ORDINAL:
            order = list(taxonomy.load()["kids"].get(gid, []))   # taxonomy file order = low -> high
            q[gid] = {"type": "score", "criteria": [_caption(t) for t in order], "_ids": order}
        elif g.get("exclusive"):
            q[gid] = {"type": "choice", "criteria": {t: _caption(t) for t in tags}}
        else:
            for t in tags:
                q["n:" + t] = {"type": "noul", "criteria": {"true": _caption(t), "false": "a photo of a person"}}
    q["minor"] = {"type": "choice", "criteria": {"adult": "a photo of an adult woman", "minor": "a photo of a child or a teenager"}}
    q["person"] = {"type": "choice", "criteria": {"person": "a photograph of a real person",
                                                  "none": "an image with no real person: a drawing, a shape, an object or an empty scene"}}
    return q


SCENE_GROUPS = {"place_type", "location", "lighting", "background", "photo_style", "medium", "color_grade", "orientation_img", "people_count"}


def jev_answers_to_scores(questions: Dict[str, Dict], answers: Dict) -> Dict:
    s: Dict[str, float] = {}
    minor = 0.0
    for k, a in answers.items():
        q = questions.get(k) or {}
        a = dict(a)
        if k == "minor":
            minor = float((a.get("probabilities") or {}).get("minor", 0.0))
        elif a.get("type") in ("choice", "head"):
            if a.get("choice") and taxonomy.node(a["choice"]):
                s[a["choice"]] = float(a.get("confidence", max((a.get("probabilities") or {0: 0}).values())))
        elif a.get("type") == "score":
            ids = q.get("_ids") or []
            probs = a.get("probabilities") or {}
            if ids:
                i = min(len(ids) - 1, max(0, int(round(float(a.get("score", 0))))))
                s[ids[i]] = float(probs.get(str(i), 0.0)) + 0.5 * sum(float(probs.get(str(j), 0)) for j in (i - 1, i + 1) if 0 <= j < len(ids))
        elif a.get("type") == "noul" and k.startswith("n:"):
            s[k[2:]] = float(a.get("noul", 0.0))
    pa = (answers.get("person") or {}).get("probabilities") or {}
    if pa and float(pa.get("none", 0)) > 0.5:   # zero-shot answers every question even with nobody in the picture
        s = {t: c for t, c in s.items() if taxonomy.group_of(t) in SCENE_GROUPS}
        if taxonomy.node("no_people"):
            s["no_people"] = float(pa["none"])
        minor = 0.0
    return {"scores": s, "minor": minor}


class JevBackend(Backend):
    """jevimage in-process (`jevimage[local]`, needs transformers>=4.56) or a server (`jevimage serve`, or any
    jevimage-compatible URL) through the base install, which only needs pillow."""
    name = "jev"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.jev = None

    def load(self):
        import jevimage
        url = self.cfg.get("jev_url")
        if url:
            self.jev = jevimage.connect(url, api_key=self.cfg.get("jev_api_key") or os.environ.get("JEVIMAGE_API_KEY"))
        else:
            if self.cfg.get("offline"):
                os.environ["HF_HUB_OFFLINE"] = "1"
            self.jev = jevimage.load(self.cfg.get("jev_encoder") or "siglip2-so400m-384",
                                     heads_dir=self.cfg.get("jev_heads_dir"))
        self.loaded = True

    def unload(self):
        self.jev = None
        self.loaded = False
        try:
            import gc, torch
            gc.collect(); torch.cuda.empty_cache()
        except Exception:
            pass

    def heads(self) -> Dict[str, str]:
        try:
            names = {h.get("name") for h in self.jev.list_heads()}
        except Exception:
            return {}
        return {g["id"]: f"reflib_{g['id']}" for g in taxonomy.groups() if f"reflib_{g['id']}" in names}

    def predict(self, paths):
        qs = jev_questions(self.heads())
        clean = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in qs.items()}
        keys = list(clean)
        out = []
        for p in paths:
            ans = {}
            for i in range(0, len(keys), 64):   # Jev answers up to 64 questions per ask; the encode is cached
                ans.update(self.jev.ask(p, {k: clean[k] for k in keys[i:i + 64]}))
            out.append(jev_answers_to_scores(qs, ans))
        return out

    def train_heads(self, examples: Dict[str, Dict[str, List[str]]], min_per_class: int = 8) -> Dict[str, Dict]:
        """examples {group_id: {tag_id: [image paths]}} (from manual / accepted tags). Trains one linear head per
        exclusive group with ≥ 2 classes of ≥ min_per_class images; returns Jev's per-class report."""
        rep = {}
        for gid, by in examples.items():
            data = {t: ps for t, ps in by.items() if len(ps) >= min_per_class}
            if len(data) >= 2:
                h = self.jev.train(f"reflib_{gid}", data)
                rep[gid] = h.to_dict() if hasattr(h, "to_dict") else dict(h)
        return rep


class JevQwenBackend(PipelineBackend):
    """Jev answers every group; Qwen2.5-VL re-reads only the fine groups (body type, coverage…) and wins there."""
    name = "jev+qwen"

    def __init__(self, cfg=None):
        Backend.__init__(self, cfg)
        self.parts = [JevBackend(cfg), QwenVLBackend(cfg)]

    def predict(self, paths):
        a, b = (x.predict(paths) for x in self.parts)
        out = []
        for ja, qa in zip(a, b):
            s = dict(ja["scores"])
            fine = {t for g in FINE_GROUPS for t in taxonomy.tags_in_group(g)}
            for t in list(s):
                if t in fine and any(x in fine and taxonomy.group_of(x) == taxonomy.group_of(t) for x in qa["scores"]):
                    del s[t]
            for t, c in qa["scores"].items():
                s[t] = max(c, s.get(t, 0.0))
            out.append({"scores": s, "minor": max(ja["minor"], qa["minor"])})
        return out


# ---------------------------------------------------------------------------- cloud (optional, off by default)
class Refused(Exception):
    """The service declined or filtered the image (some refuse nudity): the job falls back to the local backend."""


def json_schema(groups=VLM_GROUPS) -> Dict:
    props = {}
    for g in groups:
        opts = taxonomy.tags_in_group(g)
        if taxonomy.node(g).get("exclusive"):
            props[g] = {"type": ["string", "null"], "enum": opts + [None]}
        else:
            props[g] = {"type": "array", "items": {"type": "string", "enum": opts}}
    props["appears_minor"] = {"type": "boolean"}
    props["explicit_activity"] = {"type": "boolean"}
    props["confidence"] = {"type": "number"}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _mask(text: str, key: Optional[str]) -> str:
    return text.replace(key, "***") if key else text


def _post(url: str, body: Dict, headers: Dict, key: Optional[str], timeout: float = 120) -> Dict:
    import urllib.request, urllib.error
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        msg = _mask(e.read().decode(errors="replace")[:400], key)
        if e.code in (400, 403, 451) and re.search(r"safety|policy|content|moderation|blocked|refus", msg, re.I):
            raise Refused(msg)
        raise RuntimeError(f"HTTP {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(_mask(str(e.reason), key)) from None


def _b64(path: str, max_side: int = 1024):
    import base64, io
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB"); im.thumbnail((max_side, max_side))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode(), len(buf.getvalue())


class OpenAICompatBackend(Backend):
    """Any OpenAI-compatible /chat/completions endpoint with response_format json_schema (OpenAI, xAI Grok,
    local servers like vLLM / LM Studio / llama.cpp). Key from cfg or env, never logged."""
    name = "openai"
    DEFAULT_URL, KEY_ENV, DEFAULT_MODEL = "https://api.openai.com/v1", ("REFLIB_OPENAI_API_KEY", "OPENAI_API_KEY"), "gpt-4.1-mini"

    def _key(self):
        return self.cfg.get("api_key") or next((os.environ[k] for k in self.KEY_ENV if os.environ.get(k)), None)

    def predict(self, paths):
        key = self._key()
        if not key and not self.cfg.get("base_url", "").startswith(("http://127.", "http://localhost")):
            raise RuntimeError(f"no API key ({self.KEY_ENV[0]})")
        url = (self.cfg.get("base_url") or self.DEFAULT_URL).rstrip("/") + "/chat/completions"
        out = []
        for p in paths:
            data, _ = _b64(p)
            body = {"model": self.cfg.get("model_name") or self.DEFAULT_MODEL, "temperature": 0,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": vlm_prompt()},
                                                              {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}}]}],
                    "response_format": {"type": "json_schema", "json_schema": {"name": "reflib_tags", "strict": True, "schema": json_schema()}}}
            r = _post(url, body, {"Authorization": f"Bearer {key}"} if key else {}, key)
            ch = (r.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            if msg.get("refusal") or ch.get("finish_reason") == "content_filter" or not msg.get("content"):
                raise Refused(msg.get("refusal") or ch.get("finish_reason") or "empty answer")
            out.append(parse_vlm(msg["content"]))
        return out


class GrokBackend(OpenAICompatBackend):
    name = "grok"
    DEFAULT_URL, KEY_ENV, DEFAULT_MODEL = "https://api.x.ai/v1", ("REFLIB_XAI_API_KEY", "XAI_API_KEY"), "grok-4"


class GeminiBackend(Backend):
    """Google Gemini generateContent with responseMimeType application/json + responseSchema."""
    name = "gemini"

    def predict(self, paths):
        key = self.cfg.get("api_key") or os.environ.get("REFLIB_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("no API key (GEMINI_API_KEY)")
        model = self.cfg.get("model_name") or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        schema = json_schema()
        for v in schema["properties"].values():   # Gemini's OpenAPI subset: nullable instead of type lists
            if isinstance(v.get("type"), list):
                v["type"], v["nullable"] = "string", True
                v["enum"] = [x for x in v["enum"] if x is not None]
        schema.pop("additionalProperties", None)
        out = []
        for p in paths:
            data, _ = _b64(p)
            body = {"contents": [{"parts": [{"text": vlm_prompt()}, {"inline_data": {"mime_type": "image/jpeg", "data": data}}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": schema}}
            r = _post(url, body, {"x-goog-api-key": key}, key)
            if (r.get("promptFeedback") or {}).get("blockReason"):
                raise Refused(r["promptFeedback"]["blockReason"])
            cand = (r.get("candidates") or [{}])[0]
            if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "IMAGE_SAFETY"):
                raise Refused(cand["finishReason"])
            parts = ((cand.get("content") or {}).get("parts") or [{}])
            text = "".join(x.get("text", "") for x in parts)
            if not text:
                raise Refused("empty answer")
            out.append(parse_vlm(text))
        return out


CLOUD_PRICE_USD_PER_IMAGE = {"openai": 0.002, "gemini": 0.001, "grok": 0.004}   # rough defaults, editable in settings


def cloud_estimate(name: str, n_images: int, price: Optional[float] = None, avg_upload_kb: float = 180.0) -> Dict:
    p = CLOUD_PRICE_USD_PER_IMAGE.get(name, 0.003) if price is None else price
    return {"images": n_images, "usd": round(n_images * p, 2), "upload_mb": round(n_images * avg_upload_kb / 1024, 1)}


_make_base = make_backend


def make_backend(name: str, cfg: Optional[Dict] = None) -> Backend:   # noqa: F811
    cfg = cfg or {}
    extra = {"jev": JevBackend, "jev+qwen": JevQwenBackend, "openai": OpenAICompatBackend, "grok": GrokBackend, "gemini": GeminiBackend}
    if name in extra:
        return extra[name](cfg)
    return _make_base(name, cfg)


# ---------------------------------------------------------------------------- OpenRouter (optional, off by default)
OPENROUTER = "https://openrouter.ai/api"
JEV_MODEL_PINNED, JEV_MODEL_LATEST = "typesafe/jev-1.13", "~typesafe/jev-latest"
JEV_PRICE_PER_M_INPUT = 0.042   # USD, output free (openrouter.ai/typesafe/jev-1.13, checked 2026-10-10)


def _or_key(cfg) -> str:
    k = cfg.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("no API key (OPENROUTER_API_KEY)")
    return k


class _CostMixin:
    cost_usd = 0.0

    def _add_cost(self, r: Dict):
        try:
            self.cost_usd += float((r.get("usage") or {}).get("cost") or 0)
        except Exception:
            pass


class JevRouterBackend(OpenAICompatBackend, _CostMixin):
    """(a) OpenRouter `typesafe/jev-router`: image + strict JSON schema over chat/completions. The router picks the
    underlying model per request, so cost and refusal behaviour vary; real cost comes from usage.cost."""
    name = "openrouter-router"
    DEFAULT_URL, KEY_ENV, DEFAULT_MODEL = OPENROUTER + "/v1", ("OPENROUTER_API_KEY",), "typesafe/jev-router"

    def __init__(self, cfg=None):
        cfg = dict(cfg or {})
        cfg.setdefault("api_key", cfg.get("openrouter_api_key"))
        cfg["base_url"] = cfg.get("openrouter_base") and cfg["openrouter_base"] + "/v1" or self.DEFAULT_URL
        cfg["model_name"] = cfg.get("router_model") or self.DEFAULT_MODEL
        super().__init__(cfg)
        self.cost_usd = 0.0

    def predict(self, paths):
        global _post
        orig = _post

        def tap(url, body, headers, key, timeout=120):
            r = orig(url, body, headers, key, timeout)
            self._add_cost(r)
            return r
        _post = tap
        try:
            return super().predict(paths)
        finally:
            _post = orig


DESCRIBE_PROMPT = ("Describe the main person in this photo for an image catalogue, neutrally and factually, as short "
                   "English phrases: framing and camera angle; pose, body orientation, arms; clothing coverage and each "
                   "visible garment with colour and pattern; hair length, colour, style, texture; body build and height "
                   "impression; skin tone; apparent age (say clearly if the person could be under 18); expression, gaze, "
                   "makeup, tattoos, piercings, glasses; setting, background, lighting; photo style. No speculation.")


def decision_questions(groups: Optional[List[str]] = None) -> Dict[str, Dict]:
    """Taxonomy -> Decisions API questions: exclusive groups -> choice (ordinal -> score), multi-label tags -> noul."""
    q: Dict[str, Dict] = {}
    for k, v in jev_questions().items():
        g = k[2:] if k.startswith("n:") else k
        if groups and taxonomy.group_of(g) not in groups and g not in groups and k != "minor":
            continue
        v = dict(v)
        if v["type"] == "noul":
            tid = k[2:]
            v["instructions"] = f"Based on the description, does the photo show {taxonomy.label(tid, 'en')}?"
            v["criteria"] = {"true": "The description says it: " + _caption(tid) + ".",
                             "false": "The description does not mention it or contradicts it."}
        elif k == "minor":
            v["instructions"] = "Could the person described be under 18?"
            v = {"type": "noul", "instructions": v["instructions"],
                 "criteria": {"true": "The description suggests a child or a teenager, or is unsure.",
                              "false": "The description clearly says an adult."}}
        else:
            v["instructions"] = f"Which best matches the photo ({taxonomy.label(k, 'en')})?"
            if v["type"] == "choice":
                v["criteria"] = dict(v["criteria"], **{"_none": "The description does not say."})
        q[k.replace(":", "__")] = v
    return q


class JevCascadeBackend(Backend, _CostMixin):
    """(b) local describer -> text `state` -> OpenRouter Jev 1.13 Decisions API answers the taxonomy as typed decisions.
    The image never leaves the PC; only the description does. Describer: cfg describer = qwen | wd | fake."""
    name = "openrouter-jev"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.cost_usd = 0.0
        self.describer = None
        self.input_tokens = 0

    def load(self):
        d = self.cfg.get("describer") or "qwen"
        self.describer = make_backend(d, self.cfg)
        self.describer.load()
        self.loaded = True

    def unload(self):
        if self.describer:
            self.describer.unload()
        self.loaded = False

    def describe(self, path: str) -> Dict:
        d = self.describer
        if hasattr(d, "describe"):
            return {"description": d.describe(path, DESCRIBE_PROMPT)}
        pr = d.predict([path])[0]   # a tagger describer: its tags as phrases
        top = sorted(pr["scores"].items(), key=lambda kv: -kv[1])[:40]
        return {"description": "; ".join(_caption(t) for t, c in top if c >= 0.3), "local_minor_risk": round(pr["minor"], 3)}

    def predict(self, paths):
        key = _or_key(self.cfg)
        model = JEV_MODEL_LATEST if self.cfg.get("jev_latest") else (self.cfg.get("jev_model") or JEV_MODEL_PINNED)
        url = (self.cfg.get("openrouter_base") or OPENROUTER) + "/alpha/decisions"
        qs = decision_questions()
        keys = list(qs)
        out = []
        for p in paths:
            state = self.describe(p)
            ans = {}
            for i in range(0, len(keys), 64):
                r = _post(url, {"model": model, "state": state, "questions": {k: qs[k] for k in keys[i:i + 64]}},
                          {"Authorization": f"Bearer {key}"}, key)
                if r.get("error"):
                    raise Refused(str(r["error"])[:200])
                self._add_cost(r)
                self.input_tokens += int((r.get("usage") or {}).get("input_tokens") or 0)
                ans.update(r.get("answers") or {})
            plain = {}
            for k, a in ans.items():
                k2 = k.replace("__", ":")
                if a.get("type") == "choice" and a.get("choice") == "_none":
                    continue
                if k2 == "minor":
                    plain["minor"] = {"type": "choice", "probabilities": {"minor": a.get("noul", 0)}}
                else:
                    plain[k2] = a
            res = jev_answers_to_scores({k.replace("__", ":"): v for k, v in jev_questions().items()}, plain)
            res["minor"] = max(res["minor"], float(state.get("local_minor_risk") or 0))
            out.append(res)
        return out


def openrouter_estimate(name: str, n_images: int) -> Dict:
    if name == "openrouter-jev":
        toks = len(json.dumps(decision_questions())) / 3.6 + 3 * 400   # questions + a ~400-token description in each of 3 requests
        return {"images": n_images, "usd": round(n_images * toks * JEV_PRICE_PER_M_INPUT / 1e6, 4),
                "tokens_per_image": int(toks), "upload_mb": 0.0, "note": "images stay local; only text is sent"}
    return dict(cloud_estimate("grok", n_images), note="jev-router picks the model per request: price varies, real cost from usage.cost")


MODELS.update({
    "openrouter-router": {"label": "OpenRouter Jev Router (cloud, image upload)", "size_gb": 0.0, "licence": "service terms", "repos": [], "cloud": True},
    "openrouter-jev": {"label": "Local description + OpenRouter Jev 1.13 decisions (cloud, text only)", "size_gb": 15.5,
                       "licence": "service terms + local describer", "repos": ["Qwen/Qwen2.5-VL-7B-Instruct"], "cloud": True},
})
_make_v2 = make_backend


def make_backend(name: str, cfg: Optional[Dict] = None) -> Backend:   # noqa: F811
    if name == "openrouter-router":
        return JevRouterBackend(cfg or {})
    if name == "openrouter-jev":
        return JevCascadeBackend(cfg or {})
    return _make_v2(name, cfg)
