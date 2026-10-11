"""1.5.3 paid cloud vision backends: Gemini 3.8 Flash, GPT-6.1 Sol, Claude Opus 5.5 / Sonnet 5.5.

All are OFF by default (per-backend enable toggle + the model selector). Shared rules, enforced in jobs.TagQueue:
  * never-cloud: an image whose known tags say `explicit_content` (Revisión › contenido explícito) or
    `appears_minor`, or that is in review, is NEVER uploaded; it is tagged locally. Images with no tags yet get a local
    fast pre-pass first, so this is decided before any upload.
  * Claude (Opus/Sonnet): clothed-only gate (coverage = clothed and no semi-nude/nude/topless/lingerie/swimwear tag).
  * refusals / safety blocks -> local fallback for that image, counted in the job report.
  * images: EXIF-transposed, downscaled to <= 1024 px, re-encoded as a fresh JPEG with no EXIF/GPS/XMP/ICC metadata.
  * keys: env (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY) or settings, masked, never logged.
Model ids verified 2026-10-11 against the providers' model pages; every id is editable in settings."""
from __future__ import annotations
import io, json, math, os, time
from typing import Dict, List, Optional, Tuple
from . import backends, taxonomy
from .backends import Backend, Refused, json_schema, parse_vlm, vlm_prompt

# ---------------------------------------------------------------------------- catalogue
CLOUD = {
    "gemini-3.8-flash": {"label": "Gemini 3.8 Flash (cloud, paid · recommended)", "provider": "google", "model_id": "gemini-3.8-flash",
                         "key_env": ("GEMINI_API_KEY", "REFLIB_GEMINI_API_KEY"), "key_field": "gemini_api_key", "batch": True},
    "gpt-6.1-sol": {"label": "GPT-6.1 Sol (cloud, paid · max quality)", "provider": "openai", "model_id": "gpt-6.1-sol",
                    "key_env": ("OPENAI_API_KEY", "REFLIB_OPENAI_API_KEY"), "key_field": "openai_api_key", "batch": True},
    "claude-opus-5-5": {"label": "Claude Opus 5.5 (cloud, paid · clothed photos only)", "provider": "anthropic", "model_id": "claude-opus-5-5",
                        "key_env": ("ANTHROPIC_API_KEY", "REFLIB_ANTHROPIC_API_KEY"), "key_field": "anthropic_api_key", "batch": False, "clothed_only": True},
    "claude-sonnet-5-5": {"label": "Claude Sonnet 5.5 (cloud, paid · clothed photos only)", "provider": "anthropic", "model_id": "claude-sonnet-5-5",
                          "key_env": ("ANTHROPIC_API_KEY", "REFLIB_ANTHROPIC_API_KEY"), "key_field": "anthropic_api_key", "batch": False, "clothed_only": True},
}
# USD per 1M tokens, Oct 2026 list prices (editable in settings: cloud_prices)
DEFAULT_PRICES = {
    "gemini-3.8-flash": {"in": 0.75, "out": 3.75, "cache": 0.075},
    "gpt-6.1-sol": {"in": 2.0, "out": 10.0, "cache": 0.10},
    "claude-opus-5-5": {"in": 4.0, "out": 20.0, "cache": 0.20},
    "claude-sonnet-5-5": {"in": 2.0, "out": 10.0, "cache": 0.10},
}
BATCH_DISCOUNT = 0.5
OUTPUT_TOKENS = 500
CLAUDE_CACHE_WRITE = 1.25   # x input price for the first (cache-writing) request
PRICE_WARNINGS = {"gemini-3.8-flash": "price_doubles_2027"}   # Google: list price doubles on 1 Jan 2027
POLICIES = {   # shown in settings + README
    "google": {"retention": "https://ai.google.dev/gemini-api/terms", "usage": "https://policies.google.com/terms/generative-ai/use-policy"},
    "openai": {"retention": "https://openai.com/enterprise-privacy/", "usage": "https://openai.com/policies/usage-policies/"},
    "anthropic": {"retention": "https://privacy.anthropic.com/", "usage": "https://www.anthropic.com/legal/aup"},
}
for _k, _v in CLOUD.items():
    backends.MODELS[_k] = {"label": _v["label"], "size_gb": 0.0, "licence": "service terms (paid)", "repos": [], "cloud": True, "paid": True}

NEVER_CLOUD = {"explicit_content", "appears_minor"}
CLAUDE_BLOCK = {"partially_clothed", "topless", "swimwear_only", "implied_nude", "nude", "lingerie_set", "one_piece_swimsuit",
                "explicit_content", "appears_minor", "needs_review"}


# ---------------------------------------------------------------------------- gating
def gate(name: str, tags, review: bool = False) -> Tuple[bool, str]:
    """(may upload?, reason). `tags` = the image's effective tag ids (manual + earlier local pass)."""
    t = set(tags or ())
    if review or t & NEVER_CLOUD:
        return False, "never_cloud"
    if CLOUD.get(name, {}).get("clothed_only"):
        if "clothed" not in t:
            return False, "not_clothed"
        if t & CLAUDE_BLOCK:
            return False, "not_clothed"
    return True, ""


# ---------------------------------------------------------------------------- image prep
def prep_image(path: str, max_side: int = 1024) -> Tuple[bytes, int, int]:
    """Orientation applied, downscaled, re-encoded from raw pixels: no EXIF (GPS), XMP, ICC or comments survive."""
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        clean = Image.frombytes("RGB", im.size, im.tobytes())   # pixels only: no info/exif/icc carried over
        buf = io.BytesIO(); clean.save(buf, "JPEG", quality=88, exif=b"", optimize=True)
    return buf.getvalue(), clean.size[0], clean.size[1]


def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode()


# ---------------------------------------------------------------------------- token accounting / estimate
def image_tokens(name: str, w: int = 1024, h: int = 1024) -> int:
    prov = CLOUD[name]["provider"]
    if prov == "google":     # 258 tokens per 768x768 tile (images <=384 px: 258)
        if w <= 384 and h <= 384:
            return 258
        return 258 * math.ceil(w / 768) * math.ceil(h / 768)
    if prov == "openai":     # high detail: fit 2048, short side 768, 170 per 512 tile + 85
        s = min(1.0, 2048 / max(w, h)); w2, h2 = w * s, h * s
        s = min(1.0, 768 / min(w2, h2)); w2, h2 = w2 * s, h2 * s
        return 85 + 170 * math.ceil(w2 / 512) * math.ceil(h2 / 512)
    return int(math.ceil(w * h / 750))   # anthropic


def prompt_tokens() -> int:
    return int(math.ceil((len(vlm_prompt()) + len(json.dumps(json_schema()))) / 3.6))


def prices(cfg: Optional[Dict] = None) -> Dict[str, Dict[str, float]]:
    p = {k: dict(v) for k, v in DEFAULT_PRICES.items()}
    for k, v in ((cfg or {}).get("cloud_prices") or {}).items():
        if k in p and isinstance(v, dict):
            for f in ("in", "out", "cache"):
                if v.get(f) not in (None, ""):
                    p[k][f] = float(v[f])
    return p


def estimate(name: str, n: int, cfg: Optional[Dict] = None, w: int = 1024, h: int = 1024, batch: Optional[bool] = None) -> Dict:
    cfg = cfg or {}
    pr = prices(cfg)[name]
    batch = bool(cfg.get("cloud_batch")) if batch is None else batch
    batch = batch and CLOUD[name]["batch"]
    P, I, T, O = prompt_tokens(), image_tokens(name, w, h), 40, OUTPUT_TOKENS
    per_nocache = ((P + I + T) * pr["in"] + O * pr["out"]) / 1e6
    per_cache = (P * pr["cache"] + (I + T) * pr["in"] + O * pr["out"]) / 1e6
    write = P * pr["in"] / 1e6 * (CLAUDE_CACHE_WRITE if CLOUD[name]["provider"] == "anthropic" else 1.0)
    disc = BATCH_DISCOUNT if batch else 1.0
    total_nocache = n * per_nocache * disc
    total_cache = ((max(0, n - 1) * per_cache + (write + (per_cache - P * pr["cache"] / 1e6))) * disc) if n else 0.0
    return {"model": name, "model_id": (cfg.get("cloud_models") or {}).get(name) or CLOUD[name]["model_id"], "images": n, "cloud": True, "paid": True,
            "image_px": [w, h], "image_tokens": I, "prompt_tokens": P, "text_tokens": T, "output_tokens": O,
            "price": pr, "batch": batch, "batch_discount": BATCH_DISCOUNT if batch else 0.0,
            "per_image_usd": round(per_cache * disc, 6), "per_image_nocache_usd": round(per_nocache * disc, 6),
            "usd": round(total_cache, 4), "usd_nocache": round(total_nocache, 4),
            "upload_mb": round(n * 0.18, 1), "warning": PRICE_WARNINGS.get(name, ""), "clothed_only": bool(CLOUD[name].get("clothed_only"))}


def usage_cost(name: str, u: Dict, cfg: Optional[Dict] = None, batch: bool = False) -> float:
    """Real cost from a normalised usage dict {input, cached, cache_write, output} (input excludes cached)."""
    pr = prices(cfg)[name]
    c = (u.get("input", 0) * pr["in"] + u.get("cached", 0) * pr["cache"] + u.get("cache_write", 0) * pr["in"] * CLAUDE_CACHE_WRITE
         + u.get("output", 0) * pr["out"]) / 1e6
    return c * (BATCH_DISCOUNT if batch else 1.0)


# ---------------------------------------------------------------------------- HTTP (patched in tests)
def http(method: str, url: str, body=None, headers: Optional[Dict] = None, key: Optional[str] = None, raw: bool = False, timeout: float = 180):
    import urllib.request, urllib.error
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    h = dict(headers or {})
    if not isinstance(body, bytes) and body is not None:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            return b if raw else json.loads(b.decode() or "{}")
    except urllib.error.HTTPError as e:
        msg = backends._mask(e.read().decode(errors="replace")[:400], key)
        import re
        if e.code in (400, 403, 451) and re.search(r"safety|policy|content|moderation|blocked|refus", msg, re.I):
            raise Refused(msg)
        raise RuntimeError(f"HTTP {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(backends._mask(str(e.reason), key)) from None


SYSTEM = ("You are an image cataloguing assistant for a private reference library of photos of adults. "
          "Classify the image strictly with the provided JSON schema; neutral, factual, no extra text. "
          "Set appears_minor=true if the person could be under 18, and explicit_activity=true for sexual activity "
          "(no further detail).\n\n")


class CloudBackend(Backend):
    name = ""
    cloud = True

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.usage = {"input": 0, "cached": 0, "cache_write": 0, "output": 0, "requests": 0}
        self.cost_usd = 0.0
        self.batch = bool(self.cfg.get("cloud_batch")) and CLOUD[self.name]["batch"]

    @property
    def model_id(self) -> str:
        return (self.cfg.get("cloud_models") or {}).get(self.name) or CLOUD[self.name]["model_id"]

    def key(self) -> str:
        c = CLOUD[self.name]
        k = self.cfg.get(c["key_field"]) or next((os.environ[e] for e in c["key_env"] if os.environ.get(e)), None)
        if not k:
            raise RuntimeError(f"no API key ({c['key_env'][0]})")
        return k

    def _account(self, u: Dict, batch: bool = False):
        for f in ("input", "cached", "cache_write", "output"):
            self.usage[f] += int(u.get(f) or 0)
        self.usage["requests"] += 1
        self.cost_usd += usage_cost(self.name, u, self.cfg, batch)

    def prompt(self) -> str:
        return SYSTEM + vlm_prompt()

    def predict(self, paths):
        return [self.predict_one(p) for p in paths]


# ---------------------------------------------------------------------------- Gemini
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_SAFETY = [{"category": c, "threshold": "BLOCK_NONE"} for c in
                 ("HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_DANGEROUS_CONTENT")]
GEMINI_BLOCK = ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "IMAGE_SAFETY", "SPII", "RECITATION")


def gemini_schema() -> Dict:
    s = json_schema()
    for v in s["properties"].values():
        if isinstance(v.get("type"), list):
            v["type"], v["nullable"] = "string", True
            v["enum"] = [x for x in v["enum"] if x is not None]
    s.pop("additionalProperties", None)
    return s


class GeminiFlashBackend(CloudBackend):
    name = "gemini-3.8-flash"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.cache_name: Optional[str] = None
        self.base = (self.cfg.get("gemini_base") or GEMINI).rstrip("/")

    def ensure_cache(self, key) -> Optional[str]:
        """Context cache with the taxonomy prompt as system instruction (1 h TTL); best effort."""
        if self.cache_name or self.cfg.get("cloud_no_cache"):
            return self.cache_name
        try:
            r = http("POST", f"{self.base}/cachedContents", {"model": "models/" + self.model_id, "ttl": "3600s",
                     "systemInstruction": {"parts": [{"text": self.prompt()}]}}, {"x-goog-api-key": key}, key)
            self.cache_name = r.get("name")
        except Refused:
            raise
        except Exception:
            self.cache_name = None   # under the minimum size or unsupported: plain requests
        return self.cache_name

    def request(self, jpeg: bytes) -> Dict:
        body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": _b64(jpeg)}},
                                                        {"text": "Classify this image."}]}],
                "safetySettings": GEMINI_SAFETY,
                "generationConfig": {"temperature": 0, "maxOutputTokens": 2048, "responseMimeType": "application/json",
                                     "responseSchema": gemini_schema()}}
        if self.cache_name:
            body["cachedContent"] = self.cache_name
        else:
            body["systemInstruction"] = {"parts": [{"text": self.prompt()}]}
        return body

    @staticmethod
    def parse(r: Dict) -> Tuple[Dict, Dict]:
        if (r.get("promptFeedback") or {}).get("blockReason"):
            raise Refused(r["promptFeedback"]["blockReason"])
        cand = (r.get("candidates") or [{}])[0]
        if cand.get("finishReason") in GEMINI_BLOCK:
            raise Refused(cand["finishReason"])
        text = "".join(x.get("text", "") for x in ((cand.get("content") or {}).get("parts") or []) if not x.get("thought"))
        if not text.strip():
            raise Refused("empty answer")
        um = r.get("usageMetadata") or {}
        cached = int(um.get("cachedContentTokenCount") or 0)
        u = {"input": int(um.get("promptTokenCount") or 0) - cached, "cached": cached,
             "output": int(um.get("candidatesTokenCount") or 0) + int(um.get("thoughtsTokenCount") or 0)}
        return parse_vlm(text), u

    def predict_one(self, path):
        key = self.key()
        self.ensure_cache(key)
        jpeg, _, _ = prep_image(path)
        r = http("POST", f"{self.base}/models/{self.model_id}:generateContent", self.request(jpeg), {"x-goog-api-key": key}, key)
        out, u = self.parse(r)
        self._account(u)
        return out

    def batch_request(self, items: List[Tuple[str, bytes]]) -> Dict:
        return {"batch": {"display_name": "reflib-autotag", "input_config": {"requests": {"requests": [
            {"request": self.request(j), "metadata": {"key": k}} for k, j in items]}}}}

    def predict_batch(self, paths: List[str], poll_s: float = 30, timeout_s: float = 86400):
        """Batch API (50 % cheaper, up to 24 h). Returns per-path result or a Refused instance."""
        key = self.key()
        self.ensure_cache(key)
        items = [(str(i), prep_image(p)[0]) for i, p in enumerate(paths)]
        op = http("POST", f"{self.base}/models/{self.model_id}:batchGenerateContent", self.batch_request(items), {"x-goog-api-key": key}, key)
        name, t0 = op.get("name"), time.time()
        while not op.get("done"):
            if time.time() - t0 > timeout_s:
                raise RuntimeError("batch timeout")
            time.sleep(poll_s)
            op = http("GET", f"{self.base}/{name}", None, {"x-goog-api-key": key}, key)
        resp = ((op.get("response") or {}).get("inlinedResponses") or {}).get("inlinedResponses") or []
        out: List = [Refused("missing")] * len(paths)
        for i, x in enumerate(resp):
            idx = int((x.get("metadata") or {}).get("key", i))
            try:
                if x.get("error"):
                    raise Refused(str(x["error"])[:200])
                res, u = self.parse(x.get("response") or {})
                self._account(u, batch=True)
                out[idx] = res
            except Refused as e:
                out[idx] = e
        return out


# ---------------------------------------------------------------------------- OpenAI GPT-6.1 Sol
OPENAI = "https://api.openai.com/v1"


class GPTSolBackend(CloudBackend):
    name = "gpt-6.1-sol"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.base = (self.cfg.get("openai_base") or OPENAI).rstrip("/")

    def request(self, jpeg: bytes) -> Dict:
        # static prefix first (system prompt) so automatic prompt caching hits; prompt_cache_key pins routing
        return {"model": self.model_id, "temperature": 0, "max_completion_tokens": 2048, "prompt_cache_key": "reflib-taxonomy-v1",
                "messages": [{"role": "system", "content": self.prompt()},
                             {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _b64(jpeg), "detail": "high"}},
                                                          {"type": "text", "text": "Classify this image."}]}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "reflib_tags", "strict": True, "schema": json_schema()}}}

    @staticmethod
    def parse(r: Dict) -> Tuple[Dict, Dict]:
        ch = (r.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        if msg.get("refusal") or ch.get("finish_reason") == "content_filter" or not msg.get("content"):
            raise Refused(msg.get("refusal") or ch.get("finish_reason") or "empty answer")
        us = r.get("usage") or {}
        cached = int((us.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        return parse_vlm(msg["content"]), {"input": int(us.get("prompt_tokens") or 0) - cached, "cached": cached,
                                           "output": int(us.get("completion_tokens") or 0)}

    def predict_one(self, path):
        key = self.key()
        r = http("POST", self.base + "/chat/completions", self.request(prep_image(path)[0]), {"Authorization": f"Bearer {key}"}, key)
        out, u = self.parse(r)
        self._account(u)
        return out

    def batch_jsonl(self, items: List[Tuple[str, bytes]]) -> bytes:
        return "".join(json.dumps({"custom_id": k, "method": "POST", "url": "/v1/chat/completions", "body": self.request(j)}) + "\n"
                       for k, j in items).encode()

    def predict_batch(self, paths: List[str], poll_s: float = 30, timeout_s: float = 86400):
        key = self.key()
        auth = {"Authorization": f"Bearer {key}"}
        jsonl = self.batch_jsonl([(str(i), prep_image(p)[0]) for i, p in enumerate(paths)])
        bnd = "reflibBoundary7"
        form = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n--{bnd}\r\n"
                f"Content-Disposition: form-data; name=\"file\"; filename=\"reflib.jsonl\"\r\nContent-Type: application/jsonl\r\n\r\n").encode() + jsonl + f"\r\n--{bnd}--\r\n".encode()
        f = http("POST", self.base + "/files", form, dict(auth, **{"Content-Type": f"multipart/form-data; boundary={bnd}"}), key)
        b = http("POST", self.base + "/batches", {"input_file_id": f["id"], "endpoint": "/v1/chat/completions", "completion_window": "24h"}, auth, key)
        t0 = time.time()
        while b.get("status") not in ("completed", "failed", "expired", "cancelled"):
            if time.time() - t0 > timeout_s:
                raise RuntimeError("batch timeout")
            time.sleep(poll_s)
            b = http("GET", self.base + "/batches/" + b["id"], None, auth, key)
        out: List = [Refused("missing")] * len(paths)
        if b.get("output_file_id"):
            raw = http("GET", self.base + f"/files/{b['output_file_id']}/content", None, auth, key, raw=True)
            for line in raw.decode().splitlines():
                if not line.strip():
                    continue
                x = json.loads(line)
                idx = int(x.get("custom_id", 0))
                try:
                    res, u = self.parse(((x.get("response") or {}).get("body")) or {})
                    self._account(u, batch=True)
                    out[idx] = res
                except Refused as e:
                    out[idx] = e
        return out


# ---------------------------------------------------------------------------- Anthropic Claude (clothed only)
ANTHROPIC = "https://api.anthropic.com/v1"


class ClaudeBackend(CloudBackend):
    name = "claude-opus-5-5"
    TOOL = "record_tags"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.base = (self.cfg.get("anthropic_base") or ANTHROPIC).rstrip("/")

    def request(self, jpeg: bytes) -> Dict:
        return {"model": self.model_id, "max_tokens": 4096,
                "system": [{"type": "text", "text": self.prompt(), "cache_control": {"type": "ephemeral"}}],
                "tools": [{"name": self.TOOL, "description": "Record the taxonomy tags for the image.",
                           "input_schema": json_schema(), "strict": True, "cache_control": {"type": "ephemeral"}}],
                "tool_choice": {"type": "auto"},
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(jpeg)}},
                    {"type": "text", "text": f"Classify this image by calling {self.TOOL} once."}]}]}

    @classmethod
    def parse(cls, r: Dict) -> Tuple[Dict, Dict]:
        if r.get("stop_reason") == "refusal" or r.get("type") == "error":
            raise Refused(str(r.get("stop_reason") or r.get("error"))[:200])
        blocks = r.get("content") or []
        tool = next((b for b in blocks if b.get("type") == "tool_use" and b.get("name") == cls.TOOL), None)
        if tool:
            text = json.dumps(tool.get("input") or {})
        else:
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if "{" not in text:
                raise Refused("no tool call")
        us = r.get("usage") or {}
        return parse_vlm(text), {"input": int(us.get("input_tokens") or 0), "cached": int(us.get("cache_read_input_tokens") or 0),
                                 "cache_write": int(us.get("cache_creation_input_tokens") or 0), "output": int(us.get("output_tokens") or 0)}

    def predict_one(self, path):
        key = self.key()
        r = http("POST", self.base + "/messages", self.request(prep_image(path)[0]),
                 {"x-api-key": key, "anthropic-version": "2023-06-01"}, key)
        out, u = self.parse(r)
        self._account(u)
        return out


class ClaudeSonnetBackend(ClaudeBackend):
    name = "claude-sonnet-5-5"


class FakeCloudBackend(CloudBackend):
    """E2E only (cfg fake_cloud): behaves like a paid backend without network. Files whose name contains 'refuse'
    (or whose PNG hint says 'refuse') are refused; usage is synthetic so the report shows a real-cost line."""
    name = "gemini-3.8-flash"

    def predict_one(self, path):
        prep_image(path)
        from PIL import Image
        with Image.open(path) as im:
            hint = str(im.info.get("reflib_fake", ""))
        if "refuse" in os.path.basename(path).lower() or "refuse" in hint:
            raise Refused("SAFETY")
        time.sleep(float(self.cfg.get("fake_cloud_delay") or 0.2))
        out = backends.FakeBackend(self.cfg).predict([path])[0]
        self._account({"input": 300, "cached": prompt_tokens(), "output": 420})
        return out


CLASSES = {"gemini-3.8-flash": GeminiFlashBackend, "gpt-6.1-sol": GPTSolBackend,
           "claude-opus-5-5": ClaudeBackend, "claude-sonnet-5-5": ClaudeSonnetBackend}
_make_prev = backends.make_backend


def make_backend(name, cfg=None):
    cfg = cfg or {}
    if name in CLASSES:
        if cfg.get("fake_cloud"):
            b = FakeCloudBackend(cfg); b.name = name
            return b
        return CLASSES[name](cfg)
    return _make_prev(name, cfg)


backends.make_backend = make_backend
