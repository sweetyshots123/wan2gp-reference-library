"""Background auto-tag queue: one worker thread, batches, progress, pause / cancel, yields to a host "busy" check
(e.g. WanGP generating: the model is unloaded and the job waits), unloads the model after an idle period.
Host-agnostic: the host passes callables, nothing here imports a UI or WanGP."""
from __future__ import annotations
import threading, time, traceback
from typing import Callable, Dict, Iterable, List, Optional
from . import backends, taxonomy, cloud
from .tagstore import TagStore, effective


def json_src(r) -> str:
    try:
        return " ".join(sorted({str(v[1]) for v in (r or {}).get("tags", {}).values()}))
    except Exception:
        return ""


class TagQueue:
    def __init__(self, store: TagStore, resolve_paths: Callable[[List[str]], Dict[str, List[str]]],
                 settings: Callable[[], Dict], busy: Callable[[], bool] = lambda: False,
                 on_results: Callable[[], None] = lambda: None, log: Callable[[str], None] = print):
        self.store, self.resolve_paths, self.settings, self.busy, self.on_results, self.log = store, resolve_paths, settings, busy, on_results, log
        self.lock = threading.RLock()
        self.pending: List[str] = []
        self.backend: Optional[backends.Backend] = None
        self.backend_key = None
        self.fallback: Optional[backends.Backend] = None
        self.body_parser = None
        self._last_scores = None
        self.paused = False
        self.cancel_flag = False
        self.thread: Optional[threading.Thread] = None
        self.last_used = 0.0
        self.st = {"running": False, "done": 0, "total": 0, "skipped": 0, "failed": 0, "refused": 0, "review": 0, "gated": 0, "cloud_sent": 0, "notes": [],
                   "waiting": "", "model": "", "loaded": False, "error": ""}
        # 1.5.4 per-image job status: live overlay (queued / processing) over the persisted last result (done / failed / local)
        self.jst: Dict[str, str] = {}
        self.jlast: Dict[str, str] = {}
        self.jrev = 0
        self.jpath = getattr(store, "dir", None) and __import__("os").path.join(store.dir, "job_status.json")
        try:
            import json as _j
            self.jlast = dict(_j.load(open(self.jpath, encoding="utf-8")).get("images") or {})
        except Exception:
            self.jlast = {}
        threading.Thread(target=self._idle_watch, name="reflib-autotag-idle", daemon=True).start()

    # ---- 1.5.4 job status ----
    def _set(self, hs, st):
        with self.lock:
            for h in hs:
                if st in ("queued", "processing"):
                    self.jst[h] = st
                else:
                    self.jst.pop(h, None)
                    self.jlast[h] = st
            self.jrev += 1

    def _persist(self):
        if not self.jpath:
            return
        import json as _j, os as _o
        try:
            tmp = self.jpath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _j.dump({"version": 1, "images": self.jlast}, f, separators=(",", ":"))
            _o.replace(tmp, self.jpath)
        except Exception:
            pass

    def job_status(self, h: str) -> Optional[str]:
        return self.jst.get(h) or self.jlast.get(h)

    def job_map(self):
        """(rev, {hash: status}) — live overlay over the last persisted status."""
        with self.lock:
            m = dict(self.jlast); m.update(self.jst)
            return self.jrev, m

    def counts(self) -> Dict[str, int]:
        c = {"queued": 0, "processing": 0, "done": 0, "failed": 0, "local": 0}
        for v in self.job_map()[1].values():
            c[v] = c.get(v, 0) + 1
        return c

    def failed(self) -> List[str]:
        return [h for h, v in self.job_map()[1].items() if v == "failed"]

    # ---- public ----
    def status(self) -> Dict:
        with self.lock:
            return dict(self.st, queued=len(self.pending), paused=self.paused, jrev=self.jrev, jcounts=self.counts(), loaded=bool(self.backend and self.backend.loaded),
                        cost_usd=round(float(getattr(self.backend, "cost_usd", 0.0) or 0.0), 6))

    def enqueue(self, hashes: Iterable[str], force: bool = False) -> Dict:
        cfg = self.settings()
        model = cfg.get("model", "fake")
        hashes = list(dict.fromkeys(hashes))
        done = set() if force else self.store.done_for(hashes, model)   # only new / changed (= new hash) images
        new = [h for h in hashes if h not in done]
        with self.lock:
            have = set(self.pending)
            add = [h for h in new if h not in have]
            self.pending.extend(add)
            self._set(add, "queued")
            if not self.st["running"]:
                self.st.update(running=True, done=0, total=0, skipped=0, failed=0, refused=0, review=0, gated=0, cloud_sent=0, notes=[], error="", report=None)
                if self.backend is not None and hasattr(self.backend, "usage"):   # per-job cost report
                    self.backend.cost_usd = 0.0
                    self.backend.usage = {k: 0 for k in self.backend.usage}
                self.cancel_flag = False
                self.thread = threading.Thread(target=self._run, name="reflib-autotag", daemon=True)
                self.thread.start()
            self.st["total"] += len(add)
            self.st["skipped"] += len(hashes) - len(add)
        return {"queued": len(add), "skipped": len(hashes) - len(add)}

    def pause(self, on: bool = True):
        self.paused = bool(on)

    def cancel(self):
        with self.lock:
            for h in self.pending:
                self.jst.pop(h, None)
            self.jrev += 1
            self.pending.clear()
            self.cancel_flag = True
            self.paused = False

    def unload(self):
        with self.lock:
            for b in (self.backend, self.fallback):
                if b and b.loaded:
                    b.unload()
            if self.body_parser is not None:
                self.body_parser.unload()
            self.st["loaded"] = False

    def wait(self, timeout: float = 60) -> Dict:
        t0 = time.time()
        while time.time() - t0 < timeout and self.status()["running"]:
            time.sleep(0.05)
        return self.status()

    # ---- worker ----
    def _get_backend(self, cfg):
        key = (cfg.get("model"), tuple(sorted((k, str(v)) for k, v in cfg.items() if k not in ("threshold", "batch"))))
        if self.backend is None or self.backend_key != key:
            if self.backend and self.backend.loaded:
                self.backend.unload()
            self.backend = backends.make_backend(cfg.get("model", "fake"), cfg)
            self.backend_key = key
        if not self.backend.loaded:
            self.backend.load()
        return self.backend

    def _local_fallback(self, cfg):
        name = cfg.get("fallback_model") or "fake"
        if self.fallback is None or self.fallback.name != name:
            self.fallback = backends.make_backend(name, dict(cfg, model=name))
        if not self.fallback.loaded:
            self.fallback.load()
        return self.fallback

    def _gate(self) -> bool:
        """Wait while paused or while the host is busy (unloading the model to give the GPU back). False = cancelled."""
        unloaded = False
        while True:
            if self.cancel_flag:
                return False
            if self.paused:
                self.st["waiting"] = "paused"
            elif self.busy():
                self.st["waiting"] = "host_busy"
                if not unloaded:
                    self.unload(); unloaded = True
            else:
                self.st["waiting"] = ""
                return True
            time.sleep(0.3)

    def _run(self):
        try:
            while True:
                if not self._gate():
                    break
                cfg = self.settings()
                with self.lock:
                    bs = int(cfg.get("cloud_batch_size") or 200) if (cfg.get("model") in cloud.CLOUD and cfg.get("cloud_batch")) else int(cfg.get("batch") or 4)
                    batch = self.pending[:max(1, bs)]
                if not batch:
                    break
                self._set(batch, "processing")
                paths = self.resolve_paths(batch)
                ok = [(h, paths[h][0]) for h in batch if paths.get(h)]
                results = {}
                if ok:
                    self.st["model"] = cfg.get("model", "")
                    try:
                        be = self._get_backend(cfg)
                        self.st["loaded"] = True
                        preds = []
                        if getattr(be, "cloud", False) and be.name in cloud.CLOUD:
                            preds = self._cloud_preds(be, ok, cfg)
                        else:
                          for h, p in ok:   # per image, so one refusal only falls back for that image
                            try:
                                preds.append((h, be.predict([p])[0], be.name))
                            except backends.Refused:
                                self.st["refused"] += 1
                                preds.append((h, self._local_fallback(cfg).predict([p])[0], (cfg.get("fallback_model") or "fake") + " (fallback)"))
                        for h, pr, src in preds:
                            mt = float(cfg.get("minor_threshold") or backends.MINOR_THRESHOLD)
                            body = None
                            if cfg.get("body_shape", True) and pr["minor"] < mt and pr.get("explicit", 0.0) < backends.EXPLICIT_THRESHOLD:   # adults only: the minor gate comes first
                                self._last_scores = pr["scores"]
                                body = self._body(be, dict(ok)[h], cfg, h)
                                if body and body.get("measurable"):
                                    for t, c in body["tags"].items():   # geometry wins over zero-shot for its own groups
                                        g = taxonomy.group_of(t)
                                        for o in [x for x in pr["scores"] if taxonomy.group_of(x) == g and x != t]:
                                            if taxonomy.node(g).get("exclusive"):
                                                pr["scores"].pop(o)
                                        pr["scores"][t] = max(c, pr["scores"].get(t, 0))
                                elif body and body.get("reason") != "no person found":
                                    pr["scores"]["shape_not_measurable"] = 0.9
                                else:
                                    body = None
                            r = backends.finalize(pr["scores"], pr["minor"], src, mt, body=body, explicit=float(pr.get("explicit", 0.0)))
                            results[h] = r
                            self.st["review"] += int(r["review"])
                    except Exception as e:
                        self.st["error"] = str(e)[:300]
                        self.log(f"[Reference Library] auto-tag failed: {self.st['error']}")
                        self.st["failed"] += len(batch)
                        self._set(batch, "failed"); self._persist()
                        with self.lock:
                            self.pending = [h for h in self.pending if h not in batch]
                        if "API key" in str(e) or "No module" in str(e) or "local_files_only" in str(e) or "offline" in str(e).lower():
                            self.pending.clear()
                        continue
                if results:
                    self.store.set_results(results, cfg.get("model", "fake"))
                    self.on_results()
                for h in batch:
                    r = results.get(h)
                    src = json_src(r)
                    self._set([h], "failed" if r is None else ("local" if ("(local" in src or "fallback" in src) else "done"))
                self._persist()
                with self.lock:
                    self.pending = [h for h in self.pending if h not in batch]
                    self.st["done"] += len(batch)
                    self.st["failed"] += len(batch) - len(ok)
                self.last_used = time.time()
        except Exception:
            self.st["error"] = traceback.format_exc(limit=2)[-300:]
        finally:
            with self.lock:
                self.st["running"] = False
                self.st["waiting"] = ""
                if getattr(self.backend, "cloud", False):
                    self.st["report"] = self.report()
                self.last_used = time.time()

    def _note(self, h, why):
        if len(self.st["notes"]) < 200:
            self.st["notes"].append({"hash": h, "note": why})

    def _known_tags(self, h, cfg):
        e = self.store.get(h) or {}
        tags = set(effective(e, float(cfg.get("threshold") or 0.35), cfg.get("thresholds") or {})) if e else set()
        tags |= set(e.get("accepted") or [])
        return tags, bool(e.get("review")), bool(e)

    def _cloud_preds(self, be, ok, cfg):
        """1.5.3 gate in front of every paid cloud backend: explicit / minor / review never leave the PC; Claude only
        sees clothed photos. Untagged images get the local fast pass first (its result is reused if gated)."""
        fbname = (cfg.get("fallback_model") or "fake")
        mt = float(cfg.get("minor_threshold") or backends.MINOR_THRESHOLD)
        send, preds = [], {}
        for h, p in ok:
            tags, review, known = self._known_tags(h, cfg)
            local = None
            need = not known or not tags or (cloud.CLOUD[be.name].get("clothed_only") and not (tags & set(taxonomy.tags_in_group("coverage"))))
            if need:
                local = self._local_fallback(cfg).predict([p])[0]
                r = backends.finalize(dict(local["scores"]), local["minor"], fbname, mt, explicit=float(local.get("explicit", 0.0)))
                tags |= set(r["tags"]); review = review or bool(r["review"])
            allowed, why = cloud.gate(be.name, tags, review)
            if allowed:
                send.append((h, p))
            else:
                self.st["gated"] += 1
                self._note(h, why)
                preds[h] = (local or self._local_fallback(cfg).predict([p])[0], fbname + " (local: " + why + ")")
        if send:
            self.st["cloud_sent"] += len(send)
            if be.batch and len(send) > 1 and hasattr(be, "predict_batch"):
                res = be.predict_batch([p for _, p in send])
            else:
                res = []
                for _, p in send:
                    try:
                        res.append(be.predict([p])[0])
                    except backends.Refused as e:
                        res.append(e)
            for (h, p), r in zip(send, res):
                if isinstance(r, Exception):
                    self.st["refused"] += 1
                    self._note(h, "refused")
                    preds[h] = (self._local_fallback(cfg).predict([p])[0], fbname + " (fallback: refused)")
                else:
                    preds[h] = (r, be.name)
        return [(h,) + preds[h] for h, _ in ok]

    def report(self) -> Dict:
        be = self.backend
        return {"model": self.st.get("model"), "done": self.st["done"], "cloud_sent": self.st["cloud_sent"], "gated": self.st["gated"],
                "refused": self.st["refused"], "failed": self.st["failed"], "review": self.st["review"],
                "cost_usd": round(float(getattr(be, "cost_usd", 0.0) or 0.0), 6), "usage": dict(getattr(be, "usage", {}) or {}),
                "notes": list(self.st["notes"][:50])}

    def _body(self, be, path, cfg, h):
        from . import bodyshape
        try:
            hcm = (self.store.get(h) or {}).get("height_cm") or cfg.get("default_height_cm") or None
            parts = getattr(be, "parts", [be])
            fake = next((x for x in parts if hasattr(x, "body")), None)
            if fake is not None:
                m = fake.body(path, hcm)
            else:
                if self.body_parser is None:
                    self.body_parser = bodyshape.BodyParser(cache_dir=cfg.get("cache_dir"), offline=bool(cfg.get("offline")))
                if self.body_parser.m is None:
                    self.body_parser.load()
                sc = set((self._last_scores or {}))
                skirt = bool(sc & set(taxonomy.descendants("dresses")) | sc & set(taxonomy.descendants("skirt")) | sc & {"skirt"})
                loose = bool(sc & {"loose_fit"})
                m = self.body_parser.analyse(path, hcm, loose=loose, skirt=skirt)
            vlm = next((x for x in parts if hasattr(x, "body_estimate")), None)
            if m.get("measurable") and vlm is not None and cfg.get("body_vlm_check", True):
                m = bodyshape.merge_vlm(m, vlm.body_estimate(path))
            return m
        except Exception as e:
            self.log(f"[Reference Library] body shape skipped: {str(e)[:200]}")
            return None

    def _idle_watch(self):
        while True:
            time.sleep(5)
            try:
                idle = float(self.settings().get("idle_unload_s") or 120)
                if not self.st["running"] and self.backend and self.backend.loaded and time.time() - self.last_used > idle:
                    self.unload()
            except Exception:
                pass
