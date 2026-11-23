"""Control Image library picker — synthetic data only, no catalogs or personal files."""
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import inspect
import pytest
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "plugin.py").read_text()
TREE = ast.parse(SRC)

# Module-level helpers (no plugin storage).
mod_names = {"_direct_kind", "IMAGE_DIRECT_INPUTS", "IMAGE_KIND_INPUTS", "SAVE_AUDIO_INPUTS"}
# SAVE_AUDIO_INPUTS and WATCH must exist for _direct_kind to import — they're assigned earlier.
# Exec only the constants + helper by slicing the source between SAVE_VIDEO and the next def? Safer: compile those names from the tree.


def load_helpers():
    ns = {}
    # Pull top-level assignments and _direct_kind from the file without importing the plugin.
    wanted = []
    for n in TREE.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in {
                    "SAVE_AUDIO_INPUTS", "SAVE_VIDEO_INPUTS", "IMAGE_DIRECT_INPUTS", "IMAGE_KIND_INPUTS", "WATCH_IMAGES",
                }:
                    wanted.append(n)
        if isinstance(n, ast.FunctionDef) and n.name == "_direct_kind":
            wanted.append(n)
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "helpers", "exec"), ns)
    return ns


def test_direct_kind_images_videos_audio():
    ns = load_helpers()
    assert ns["_direct_kind"]("image_guide") == "image"
    assert ns["_direct_kind"]("image_mask") == "image"
    assert ns["_direct_kind"]("image_start") == "image"
    assert ns["_direct_kind"]("video_guide") == "video"
    assert ns["_direct_kind"]("audio_guide") == "audio"
    assert ns["_direct_kind"]("video_mask") == "video"


def _tag_harness():
    pytest.importorskip("gradio")
    import gradio as gr
    CLS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "ReferenceLibraryPlugin")
    fn = next(n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name == "_tag_image_pick")
    ns = {"gr": gr}
    module = ast.Module(body=[ast.ClassDef(name="Harness", bases=[], keywords=[], body=[fn], decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "tag", "exec"), ns)
    return ns["Harness"](), gr


def test_tag_control_image_only():
    p, gr = _tag_harness()
    with gr.Blocks():
        guide = gr.Image(label="Control Image")
        editor = gr.ImageEditor()
    p._tag_image_pick("generate", {"image_guide": guide, "image_mask_guide": editor})
    assert "reflib-ipick" in guide.elem_classes
    assert "reflib-ipick-image_guide-generate" in guide.elem_classes
    # ImageEditor is not tagged
    cl = editor.elem_classes or []
    assert "reflib-ipick" not in cl
    p._tag_image_pick("edit", {"image_guide": None})  # missing component is skipped


def _strip_relative_imports(fn):
    fn = ast.parse(ast.unparse(fn)).body[0]
    fn.body = [n for n in fn.body if not (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("reflib_core") or (isinstance(n, ast.ImportFrom) and n.level))]
    return fn


def test_history_media_sets_control_image(tmp_path):
    """hash/to for image_guide stages one file and updates the Image, not a gallery."""
    pytest.importorskip("gradio")
    import gradio as gr
    CLS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "ReferenceLibraryPlugin")
    fn = _strip_relative_imports(next(n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name == "history_media"))
    src_path = tmp_path / "synth-guide.png"
    src_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    staged = []
    helpers = load_helpers()
    ns = {
        "gr": gr, "json": json, "os": os, "traceback": __import__("traceback"),
        "imagelib": SimpleNamespace(
            entry_for=lambda h: {"kind": "image"} if h == "img" else {"kind": "video"},
            media_path=lambda h: str(src_path) if h in ("img", "vid") else None,
        ),
        "_stage_for_gallery": lambda paths: staged.extend(paths) or list(paths),
        "_stage_video": lambda path, name: path,
        "tr": lambda lang, key, **k: key,
        "_direct_kind": helpers["_direct_kind"],
        "_h": SimpleNamespace(get=lambda eid: None, paths=lambda *a: []),
    }
    module = ast.Module(body=[ast.ClassDef(name="Harness", bases=[], keywords=[], body=[fn], decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "hist", "exec"), ns)
    plugin = ns["Harness"]()
    with gr.Blocks():
        guide = gr.Image(label="Control Image")
        video = gr.Video()
    plugin.vtargets = {"generate": {"video": video}}
    plugin._hist_comps = {"generate": [("image_guide", guide), ("video_guide", video)]}
    raw, upd_guide, upd_video = plugin.history_media("generate", json.dumps({
        "id": "r1", "hash": "img", "to": "image_guide", "lang": "en",
    }))
    out = json.loads(raw)
    assert out["ok"] is True, out
    assert out["restored"] == ["image_guide"]
    value = upd_guide["value"] if isinstance(upd_guide, dict) else getattr(upd_guide, "value", upd_guide)
    if isinstance(value, dict):
        value = value.get("value") or value.get("path")
    assert str(value) == str(src_path)
    def _is_skip(v):
        if v is None or v == gr.skip() or v is gr.skip():
            return True
        name = type(v).__name__
        if name in ("Skip", "LiteralValue"):
            return True
        if isinstance(v, dict) and v.get("__type__") in {"skip", "generic_update"} and v.get("__value") is None and not v.get("value"):
            return "skip" in str(v).lower() or v.get("__type__") == "skip"
        return "skip" in str(v).lower() and "value" not in str(v).lower()
    assert _is_skip(upd_video), repr(upd_video)
    staged.clear()
    raw, a, b = plugin.history_media("generate", json.dumps({"id": "r2", "hash": "vid", "to": "image_guide"}))
    assert json.loads(raw)["ok"] is False
    assert not staged


def test_setup_tags_control_image_without_video_guide():
    """Z-Image in image mode may have no video_guide; the button and history path must still be wired."""
    pytest.importorskip("gradio")
    import gradio as gr
    CLS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "ReferenceLibraryPlugin")
    names = {"_tag_image_pick", "_register_image_hist", "_hist_tabs", "_hist_targets", "_setup_video_target"}
    fns = [n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name in names]
    helpers = load_helpers()
    ns = {
        "gr": gr,
        "WATCH_VIDEOS": ("video_guide", "video_guide2", "video_guide3", "video_source"),
        "WATCH_IMAGES": ("image_start", "image_end", "image_refs", "image_guide"),
        "AUDIO_TARGETS": ("audio_guide", "audio_guide2", "audio_guide3"),
        "load_settings": lambda: {"video_bar": True, "show_edit_bar": True},
        "SAVE_AUDIO_INPUTS": helpers["SAVE_AUDIO_INPUTS"],
    }
    module = ast.Module(body=[ast.ClassDef(name="Harness", bases=[], keywords=[], body=fns, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "setup", "exec"), ns)
    plugin = ns["Harness"]()
    plugin.vtargets = {}
    plugin._image_hist = {}
    plugin._extra_comps = {}
    plugin._hist_comps = {}
    plugin.save_targets = {}
    plugin.insert_after = lambda *a, **k: None
    with gr.Blocks():
        guide = gr.Image(label="Control Image")
        start = gr.Gallery()
    plugin._setup_video_target("generate", {"image_guide": guide, "image_start": start})
    assert "generate" not in plugin.vtargets
    assert "reflib-ipick" in guide.elem_classes
    assert "reflib-ipick-image_guide-generate" in guide.elem_classes
    assert "generate" in plugin._hist_tabs()
    names_found = [n for n, _ in plugin._hist_targets("generate")]
    assert "image_guide" in names_found
    assert "video_guide" not in names_found


if __name__ == "__main__":
    def run(fn):
        if not inspect.signature(fn).parameters:
            return fn()
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    suite = unittest.TestSuite(unittest.FunctionTestCase(lambda f=f: run(f), description=name)
                               for name, f in list(globals().items()) if name.startswith("test_"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
