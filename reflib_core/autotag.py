"""Auto-tag service: settings + TagStore + TagQueue + the catalog hook. One per data folder; hosts use this."""
from __future__ import annotations
import json, os, threading
from typing import Callable, Dict, List, Optional
from . import backends, bodyshape, cloud, imagelib, storage, taxonomy
from .jobs import TagQueue
from .tagstore import TagStore, effective

DEFAULTS = {"enabled": True, "model": "wd+qwen", "fallback_model": "wd", "threshold": 0.35, "thresholds": {},
            "batch": 4, "vram_gb": 24, "offline": False, "idle_unload_s": 120, "minor_threshold": backends.MINOR_THRESHOLD,
            "jev_encoder": "siglip2-so400m-384", "jev_url": "", "describer": "qwen", "jev_latest": False,
            "base_url": "", "cloud_model": "", "cloud_ok": False, "body_shape": True, "body_vlm_check": True,
            "default_height_cm": 0, "collection_heights": {},
            # 1.5.3 paid cloud backends: each off until its own toggle is on
            "cloud_enabled": {}, "cloud_models": {}, "cloud_batch": False, "cloud_batch_size": 200, "cloud_prices": {}}
SECRET = ("api_key", "openrouter_api_key", "jev_api_key", "gemini_api_key", "openai_api_key", "anthropic_api_key")


class AutoTagService:
    def __init__(self, data_dir: str, busy: Callable[[], bool] = lambda: False, log: Callable[[str], None] = print):
        self.dir = data_dir
        taxonomy.USER_PATH = os.path.join(data_dir, "user_taxonomy.json")
        taxonomy.reload()
        self.store = TagStore(data_dir)
        self._lock = threading.RLock()
        self._map = (None, {}, {})
        self.queue = TagQueue(self.store, self.paths_for, self.backend_cfg, busy=busy, on_results=imagelib.invalidate, log=log)
        imagelib.AUTOTAGS = self.auto_map
        imagelib.JOBSTATUS = self.queue.job_map

    # settings (secrets are stored but never returned to a UI or logged)
    @property
    def settings_path(self):
        return os.path.join(self.dir, "autotag_settings.json")

    def settings(self, with_secrets: bool = False) -> Dict:
        try:
            s = dict(DEFAULTS, **json.load(open(self.settings_path, encoding="utf-8")))
        except Exception:
            s = dict(DEFAULTS)
        if not with_secrets:
            for k in SECRET:
                s[k + "_set"] = bool(s.pop(k, None))
        return s

    def save_settings(self, upd: Dict) -> Dict:
        cur = self.settings(with_secrets=True)
        for k, v in (upd or {}).items():
            if k in DEFAULTS or k in SECRET:
                if k in SECRET and v in (None, "***"):
                    continue
                cur[k] = v
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.settings_path + ".tmp"
        json.dump(cur, open(tmp, "w", encoding="utf-8"), indent=1)
        os.replace(tmp, self.settings_path)
        self._map = (None, {}, {})
        imagelib.invalidate()
        return self.settings()

    def backend_cfg(self) -> Dict:
        s = self.settings(with_secrets=True)
        cfg = dict(s, cache_dir=os.path.join(self.dir, "models"), jev_heads_dir=os.path.join(self.dir, "models", "jev_heads"))
        if s.get("cloud_model"):
            cfg["model_name"] = s["cloud_model"]
        if s["model"] in cloud.CLOUD:
            cfg.pop("model_name", None)
            if os.environ.get("REFLIB_FAKE_CLOUD") == "1":   # E2E only: no network, synthetic usage
                cfg["fake_cloud"] = True
            if not (s.get("cloud_enabled") or {}).get(s["model"]):
                cfg["model"] = s["fallback_model"]   # paid backend: its own enable toggle
        elif backends.MODELS.get(s["model"], {}).get("cloud") and not s.get("cloud_ok"):
            cfg["model"] = s["fallback_model"]   # cloud needs an explicit opt-in
        return cfg

    def paths_for(self, hashes: List[str]) -> Dict[str, List[str]]:
        by = imagelib.catalog()["by_hash"]
        out = {}
        for h in hashes:
            i = by.get(h)
            if i:
                out[h] = [p for p in (i["path"],) + tuple(i["files"]) if p and os.path.isfile(p)][:1]
        return out

    def auto_map(self):
        try:
            st = os.stat(self.store.path)
            fk = (st.st_mtime_ns, st.st_size)
        except OSError:
            fk = None
        s = self.settings()
        key = (fk, taxonomy.REV[0], s["threshold"], json.dumps(s["thresholds"], sort_keys=True))
        if self._map[0] == key:
            return self._map
        m, bm = {}, {}
        for h, e in self.store.load().items():
            eff = effective(e, float(s["threshold"]), s["thresholds"])
            eff = {t: c for t, c in eff.items() if taxonomy.node(t)}   # deleted custom tags vanish (undo restores them)
            if eff:
                m[h] = frozenset(taxonomy.with_ancestors(eff))
            if e.get("body") and not e.get("review"):
                fb = bodyshape.flat(e["body"])
                if fb:
                    bm[h] = fb
            if not e.get("review") and "appears_minor" not in (e.get("tags") or {}):   # 1.5.1: searchable `edad 30-40`
                from .backends import AGE_MID
                band = [t for t in (eff or ()) if t in AGE_MID]
                age = (e.get("age") or {}).get("est")
                if band and (not age or not any(abs(AGE_MID[b] - age) <= 10 for b in band)):
                    age = AGE_MID[band[0]]   # a user-accepted band wins over a disagreeing numeric guess
                if age:
                    bm.setdefault(h, {})["age"] = float(age)
        self._map = (key, m, bm)
        return self._map

    # actions
    def enqueue(self, hashes, force=False):
        return self.queue.enqueue(hashes, force)

    def job_facets(self, f=None) -> Dict[str, int]:
        """1.5.4 "Estado del etiquetado" counts over the current filter (without its own jst part)."""
        ff = dict(f or {}); ff.pop("jst", None)
        items = imagelib.filtered(ff)["items"]
        _, jm = self.queue.job_map()
        tagged = self.auto_map()[1]
        c = {k: 0 for k in imagelib.JST_KEYS}
        for i in items:
            st = jm.get(i["hash"])
            if st:
                c[st] += 1
            elif i["hash"] not in tagged:
                c["never"] += 1
        return c

    def retry_failed(self):
        hs = self.queue.failed()
        return self.queue.enqueue(hs, force=True) if hs else {"queued": 0, "skipped": 0}

    def estimate(self, n: int) -> Dict:
        s = self.settings()
        m = s["model"]
        info = backends.MODELS.get(m, {})
        cache = os.path.join(self.dir, "models")
        dl = 0.0 if (backends.is_downloaded(m, cache) or (m.startswith("jev") and s.get("jev_url") and m == "jev")) else info.get("size_gb", 0)
        if s.get("body_shape") and m != "fake":
            try:
                from huggingface_hub import snapshot_download
                for r in backends.BODY_MODELS["repos"]:
                    snapshot_download(r, local_files_only=True, cache_dir=cache)
            except Exception:
                dl += backends.BODY_MODELS["size_gb"]
        out = {"model": m, "images": n, "download_gb": round(dl, 1), "cloud": bool(info.get("cloud"))}
        if m in cloud.CLOUD:
            out.update(cloud.estimate(m, n, s))
            out["enabled"] = bool((s.get("cloud_enabled") or {}).get(m))
            out["key_set"] = bool(s.get(cloud.CLOUD[m]["key_field"] + "_set") or any(os.environ.get(e) for e in cloud.CLOUD[m]["key_env"]))
            if not out["enabled"]:
                out.update(cloud=False, paid=False, local_instead=s["fallback_model"])
        elif m.startswith("openrouter"):
            out.update(backends.openrouter_estimate(m, n))
        elif info.get("cloud"):
            out.update(backends.cloud_estimate(m, n))
        return out

    def image_tags(self, h: str, lang: str = "en") -> Dict:
        e = self.store.get(h) or {}
        s = self.settings()
        eff = effective(e, float(s["threshold"]), s["thresholds"])
        rej, acc = set(e.get("rejected", [])), set(e.get("accepted", []))
        tags = []
        for tid, (c, src) in sorted((e.get("tags") or {}).items(), key=lambda kv: -kv[1][0]):
            tags.append({"id": tid, "label": taxonomy.label(tid, lang), "group": taxonomy.group_of(tid), "conf": round(c, 3),
                         "src": src, "shown": tid in eff, "rejected": tid in rej, "accepted": tid in acc})
        for tid in acc - set((e.get("tags") or {})):
            tags.append({"id": tid, "label": taxonomy.label(tid, lang), "group": taxonomy.group_of(tid), "conf": 1.0, "src": "manual",
                         "shown": True, "rejected": False, "accepted": True})
        return {"hash": h, "model": e.get("model"), "at": e.get("at"), "review": bool(e.get("review")), "tags": tags,
                "body": None if e.get("review") else e.get("body"),
                "age": None if e.get("review") else e.get("age"), "height_cm": e.get("height_cm")}

    def set_height(self, hashes, cm):
        n = self.store.set_height(hashes, cm)
        self._map = (None, {}, {})
        imagelib.invalidate()
        return n

    def set_collection_height(self, cid: str, cm):
        """A height for every image of a collection (e.g. one model's photo set): rescales their estimates."""
        hs = self.settings(with_secrets=True).get("collection_heights") or {}
        if cm:
            hs[cid] = float(cm)
        else:
            hs.pop(cid, None)
        self.save_settings({"collection_heights": hs})
        c = storage.get_collection(cid) or {}
        return self.set_height([i.get("hash") for i in c.get("images", []) if i.get("hash")], cm)

    def edit(self, h, tag_id, op):
        r = self.store.edit(h, tag_id, op)
        imagelib.invalidate()
        return r

    def training_examples(self) -> Dict[str, Dict[str, List[str]]]:
        """Accepted (human-confirmed) auto tags per exclusive group, as image paths: input for Jev heads."""
        ex: Dict[str, Dict[str, List[str]]] = {}
        data = self.store.load()
        paths = self.paths_for(list(data))
        for h, e in data.items():
            if e.get("review") or not paths.get(h):
                continue
            for tid in e.get("accepted", []):
                g = taxonomy.group_of(tid)
                if g and taxonomy.node(g).get("exclusive"):
                    ex.setdefault(g, {}).setdefault(tid, []).append(paths[h][0])
        return ex

    def training_examples_binary(self) -> Dict[str, Dict[str, List[str]]]:
        """Multi-label tags (shipped or custom): {tag: {"yes": accepted paths, "no": paths where it was removed}},
        the input for per-tag SigLIP2 heads ("Entrenar clasificadores")."""
        ex: Dict[str, Dict[str, List[str]]] = {}
        data = self.store.load()
        paths = self.paths_for(list(data))
        for h, e in data.items():
            if e.get("review") or not paths.get(h):
                continue
            for key, tids in (("yes", e.get("accepted", [])), ("no", e.get("rejected", []))):
                for tid in tids:
                    g = taxonomy.group_of(tid)
                    if taxonomy.node(tid) and not (g and taxonomy.node(g).get("exclusive")):
                        ex.setdefault(tid, {"yes": [], "no": []})[key].append(paths[h][0])
        return ex
