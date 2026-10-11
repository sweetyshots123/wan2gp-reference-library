"""Tolerant client for Prompt Library's optional API (``sys.modules["wan2gp_prompt_library_api"]``).

Looked up lazily at every call (never at import: plugin load order is not guaranteed). Every function degrades to
"not available" instead of raising, so Reference Library keeps working alone.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

MODULE_NAME = "wan2gp_prompt_library_api"


def api():
    mod = sys.modules.get(MODULE_NAME)
    if mod is None:
        return None
    try:
        if int(getattr(mod, "API_VERSION", 0) or 0) < 1:
            return None
    except (TypeError, ValueError):
        return None
    return mod if callable(getattr(mod, "list_prompts", None)) else None


def available() -> bool:
    return api() is not None


def can_write() -> bool:
    mod = api()
    return bool(mod and callable(getattr(mod, "set_collection_prompts", None)))


def _title(p: Dict[str, Any]) -> str:
    for key in ("title", "name", "label"):
        if p.get(key):
            return str(p[key])
    text = str(p.get("text") or p.get("prompt") or "").strip()
    return (text[:60] + "…") if len(text) > 60 else (text or str(p.get("id")))


def _norm(p: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(p, dict) or not p.get("id"):
        return None
    cols = p.get("collections")
    return {"id": str(p["id"]), "title": _title(p),
            "collections": [str(c) for c in cols] if isinstance(cols, (list, tuple)) else None}


def list_prompts() -> List[Dict[str, Any]]:
    """[{id, title, collections|None}] sorted by title; [] if unavailable."""
    mod = api()
    if not mod:
        return []
    try:
        items = [n for n in (_norm(p) for p in (mod.list_prompts() or [])) if n]
    except Exception as e:
        print(f"[Reference Library] Prompt Library list_prompts failed: {e}")
        return []
    return sorted(items, key=lambda p: p["title"].lower())


def prompts_for_collection(cid: str) -> List[Dict[str, Any]]:
    """Linked prompts [{id, title}] in Prompt Library's order. Accepts ids or dicts from the API; falls back to the
    ``collections`` field of list_prompts() when prompts_for_collection is missing."""
    mod = api()
    if not mod or not cid:
        return []
    by_id = {p["id"]: p for p in list_prompts()}
    fn = getattr(mod, "prompts_for_collection", None)
    try:
        if callable(fn):
            raw = fn(cid) or []
            out = []
            for item in raw:
                pid = str(item.get("id")) if isinstance(item, dict) else str(item)
                if not pid or pid in (o["id"] for o in out):
                    continue
                p = by_id.get(pid) or (_norm(item) if isinstance(item, dict) else None)
                if p:
                    out.append({"id": p["id"], "title": p["title"]})
            return out
        return [{"id": p["id"], "title": p["title"]} for p in by_id.values() if cid in (p.get("collections") or [])]
    except Exception as e:
        print(f"[Reference Library] Prompt Library prompts_for_collection failed: {e}")
        return []


def set_collection_prompts(cid: str, prompt_ids: List[str]) -> Tuple[bool, str]:
    mod = api()
    if not mod or not callable(getattr(mod, "set_collection_prompts", None)):
        return False, "unavailable"
    try:
        res = mod.set_collection_prompts(cid, [str(p) for p in (prompt_ids or [])])
    except Exception as e:
        return False, str(e) or e.__class__.__name__
    if res is False or (isinstance(res, dict) and res.get("ok") is False):
        return False, str((res or {}).get("error") if isinstance(res, dict) else "failed")
    return True, ""
