"""Shared action registry (1.8.5): one place where library features are callable by BOTH UIs.

Every feature module registers its actions here; ``plugin.ilib`` (the Media Library bridge, and the Galería's
``POST /reflib/api``) dispatches registered names before its legacy built-in ones, and the Gradio callbacks call the
same functions through :func:`call`. So a feature lives once, in reflib_core, and each UI only sends requests.

Registering a new action (e.g. from a new ``reflib_core/similarity.py``)::

    from . import actions

    @actions.action("sim_find", fast=True)          # fast=True: read-only + quick -> allowed on the unqueued channel
    def sim_find(req, ctx):
        ...                                          # req = the JSON request (dict), ctx = Ctx below
        return {"ok": True, "items": [...]}

and import the module once in ``reflib_core/actions_all.py`` (the only list to touch). Raise ``ActionError(key, **p)``
for a user-facing error: ``ctx`` turns the key into the UI language (plugin TEXT table) or, for keys it doesn't know,
shows the key/params as-is.

Long jobs: return ``{"ok": True, "job": id}`` from a start action and register a fast ``*_status`` action that returns
``{"ok": True, "job": {"done": n, "total": m, "running": bool, ...}}``; the Galería polls it to draw progress.
"""
from typing import Any, Callable, Dict, Optional

REGISTRY: Dict[str, Callable[[Dict[str, Any], "Ctx"], Dict[str, Any]]] = {}
FAST: set = set()
META: Dict[str, Dict[str, Any]] = {}


class ActionError(Exception):
    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key, self.params = key, params


class Ctx:
    """What an action may need from the host, without importing Gradio or the plugin."""

    def __init__(self, lang: str = "en", ok: Optional[Callable] = None, err: Optional[Callable] = None,
                 payload: Optional[Callable] = None, state: Optional[Dict[str, Any]] = None, request=None):
        self.lang = lang
        self._ok, self._err, self._payload = ok, err, payload
        self.state = state if state is not None else {}   # host-owned dict that survives between calls (undo tokens...)
        self.request = request

    def ok(self, key: str, **params) -> Dict[str, Any]:
        return self._ok(self.lang, key, **params) if self._ok else {"ok": True, "message": key, "toast": key, **params}

    def err(self, key: str, **params) -> Dict[str, Any]:
        return self._err(self.lang, key, **params) if self._err else {"ok": False, "error": key}

    def payload(self) -> Dict[str, Any]:
        """The library meta block (collections, counts...) both UIs refresh from after a write."""
        return {k: v for k, v in (self._payload(self.lang) if self._payload else {}).items() if k != "ok"}


def action(name: str, fast: bool = False, doc: str = ""):
    def deco(fn):
        if name in REGISTRY and REGISTRY[name] is not fn:
            raise ValueError(f"action {name!r} registered twice")
        REGISTRY[name] = fn
        META[name] = {"fast": fast, "doc": doc or (fn.__doc__ or "").strip().split("\n")[0]}
        if fast:
            FAST.add(name)
        return fn
    return deco


def has(name: str) -> bool:
    return name in REGISTRY


def call(name: str, req: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    try:
        return REGISTRY[name](req or {}, ctx)
    except ActionError as e:
        return ctx.err(e.key, **e.params)


def describe() -> Dict[str, Any]:
    return {k: dict(v) for k, v in sorted(META.items())}
