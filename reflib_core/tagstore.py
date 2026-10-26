"""Auto-tag storage, separate from manual tags. Format (see FORMAT.md), file <data_dir>/autotags.json:
{"format": "reflib-autotags", "version": 1,
 "images": {sha256: {"tags": {tag_id: [confidence, source]}, "model": str, "at": unix_ts,
                     "review": bool, "rejected": [tag_id], "accepted": [tag_id]}}}"""
from __future__ import annotations
import json, os, threading, time
from typing import Dict, Iterable, Optional
from . import taxonomy

FORMAT, VERSION = "reflib-autotags", 1


class TagStore:
    def __init__(self, data_dir: str):
        self.dir = data_dir
        self._lock = threading.RLock()
        self._cache = None   # (mtime_ns, data)

    @property
    def path(self) -> str:
        return os.path.join(self.dir, "autotags.json")

    def load(self) -> Dict[str, Dict]:
        try:
            st = os.stat(self.path)
        except OSError:
            return {}
        if self._cache and self._cache[0] == (st.st_mtime_ns, st.st_size):
            return self._cache[1]
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            data = d.get("images", {}) if isinstance(d, dict) and d.get("version", 1) <= VERSION else {}
        except (OSError, ValueError):
            data = {}
        self._cache = ((st.st_mtime_ns, st.st_size), data)
        return data

    def _save(self, data: Dict[str, Dict]) -> None:
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"format": FORMAT, "version": VERSION, "images": data}, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, self.path)
        self._cache = None

    def set_results(self, results: Dict[str, Dict], model: str) -> None:
        """results {hash: {"tags": {id: [conf, src]}, "review": bool}}; accept/remove edits survive a re-run."""
        with self._lock:
            data = dict(self.load())
            for h, r in results.items():
                old = data.get(h) or {}
                data[h] = {"tags": r["tags"], "model": model, "at": time.time(), "review": bool(r.get("review")),
                           "rejected": old.get("rejected", []), "accepted": old.get("accepted", [])}
                if r.get("body"):
                    data[h]["body"] = r["body"]
                if r.get("age") and not r.get("review"):
                    data[h]["age"] = r["age"]
                if old.get("height_cm"):
                    data[h]["height_cm"] = old["height_cm"]
            self._save(data)

    def pop(self, hashes: Iterable[str]) -> Dict[str, Dict]:
        """1.7.1: remove these images' auto tags; returns what was removed (for undo)."""
        with self._lock:
            data = dict(self.load())
            out = {h: data.pop(h) for h in list(hashes) if h in data}
            if out:
                self._save(data)
            return out

    def restore(self, entries: Dict[str, Dict]) -> int:
        with self._lock:
            data = dict(self.load())
            n = 0
            for h, e in (entries or {}).items():
                if h not in data and isinstance(e, dict):
                    data[h] = e; n += 1
            if n:
                self._save(data)
            return n

    def done_for(self, hashes: Iterable[str], model: str) -> set:
        d = self.load()
        return {h for h in hashes if h in d and d[h].get("model") == model}

    def set_height(self, hashes: Iterable[str], cm: Optional[float]) -> int:
        """User-entered height (cm) per image: rescales the body estimates (stored with the image, survives re-runs)."""
        from . import bodyshape
        with self._lock:
            data = dict(self.load())
            n = 0
            for h in hashes:
                e = dict(data.get(h) or {"tags": {}, "model": "manual", "at": time.time(), "review": False})
                if cm:
                    e["height_cm"] = float(cm)
                else:
                    e.pop("height_cm", None)
                if e.get("body") and e["body"].get("measurable"):
                    e["body"] = bodyshape.rescale(e["body"], e.get("height_cm"))
                data[h] = e
                n += 1
            self._save(data)
            return n

    def get(self, h: str) -> Optional[Dict]:
        return self.load().get(h)

    def edit(self, h: str, tag_id: str, op: str) -> Dict:
        """op: accept | remove | restore."""
        if not taxonomy.node(tag_id):
            raise ValueError("unknown tag")
        with self._lock:
            data = dict(self.load())
            e = dict(data.get(h) or {"tags": {}, "model": "manual", "at": time.time(), "review": False})
            acc, rej = set(e.get("accepted", [])), set(e.get("rejected", []))
            if op == "accept" and (e.get("review") or "appears_minor" in (e.get("tags") or {})) and (
                    taxonomy.is_sensitive(tag_id) or taxonomy.group_of(tag_id) == "age_band"):
                raise ValueError("flagged for review: no body, nudity or age tags")   # the minor gate also binds manual edits
            if op == "accept":
                acc.add(tag_id); rej.discard(tag_id)
            elif op == "remove":
                rej.add(tag_id); acc.discard(tag_id)
            elif op == "restore":
                rej.discard(tag_id)
            else:
                raise ValueError("bad op")
            e["accepted"], e["rejected"] = sorted(acc), sorted(rej)
            if tag_id == "appears_minor" and op == "remove":
                e["review"] = False
            data[h] = e
            self._save(data)
            return e


def effective(e: Optional[Dict], threshold: float = 0.35, thresholds: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Visible auto tags of one image: {id: conf} over the (per-group) threshold, minus removed, plus accepted (1.0)."""
    if not e:
        return {}
    out: Dict[str, float] = {}
    rej = set(e.get("rejected", []))
    for tid, cs in (e.get("tags") or {}).items():
        tid = taxonomy.ALIASES.get(tid, tid)
        th = (thresholds or {}).get(taxonomy.group_of(tid) or "", threshold)
        if cs[0] >= th and tid not in rej:
            out[tid] = cs[0]
    for tid in e.get("accepted", []):
        out[taxonomy.ALIASES.get(tid, tid)] = 1.0
    return out
