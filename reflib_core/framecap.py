"""Frame capture from library videos (Vidosser → wan2gp_media_hooks → imagelib.pool_add_bytes).

Both UIs (Media Library Gradio browser and Galería) must stay on the open video after a
capture: never navigate to the new frame. Feedback is a brief toast only. The browser
event ``vidosser:frame-saved`` (fired by Vidosser) plus ``frame_capture_rules.js``
(``ReflibFrameCapture``) encode the same contract for both UIs.
"""
from __future__ import annotations

from typing import Any, Dict


def save_result(res: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate a successful pool_add_bytes result for clients: stay on the video, do not navigate."""
    out = dict(res or {})
    out["stay"] = True
    out["navigate"] = False
    out.setdefault("source", "frame")
    return out
