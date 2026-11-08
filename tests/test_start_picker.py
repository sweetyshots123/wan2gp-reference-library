"""Starting-image integration, no personal data or models.

Run with a Gradio/WanGP environment, e.g.
PYTHONPATH=/path/to/Wan2GP python tests/test_start_picker.py
Uses the installed core's actual AdvancedMediaGallery Add implementation, not a mock.
Extracts only the plugin methods under test to avoid loading plugin storage/settings.
"""
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

import gradio as gr
import inspect
import tempfile
import unittest
from PIL import Image
from shared.gradio.gallery import AdvancedMediaGallery

# AMG imports the full model stack only to read dimensions for its label. Stub that metadata helper,
# not AMG Add or Gradio: generation/diffusers dependencies are intentionally absent from this test.
metadata = ModuleType("shared.utils.utils")
metadata.get_video_info = lambda path: (0, 0, 0, 0)


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "plugin.py").read_text())
CLS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "ReferenceLibraryPlugin")
NAMES = {"_setup_start_target", "start_image_bridge", "amg"}


def harness(tmp_path):
    staged = []
    namespace = {"gr": gr, "json": json, "os": os,
                 "imagelib": SimpleNamespace(entry_for=lambda h: {"kind": "image"} if h == "image" else {"kind": "video"},
                                             media_path=lambda h: str(tmp_path / "source.png")),
                 "_stage_for_gallery": lambda paths: staged.extend(paths) or paths,
                 "tr": lambda lang, key: key}
    module = ast.Module(body=[ast.ClassDef(name="Harness", bases=[], keywords=[],
                                         body=[n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name in NAMES],
                                         decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "plugin_methods", "exec"), namespace)
    p = namespace["Harness"]()
    p.start_targets = {}
    p._amg = None
    Image.new("RGB", (8, 8), (30, 70, 90)).save(tmp_path / "source.png")
    with gr.Blocks():
        amg = AdvancedMediaGallery(media_mode="image", label="Starting images")
        amg.mount()
    extra = [None] + amg.get_toggable_elements()
    p._setup_start_target("generate", {"image_start": amg.gallery, "image_start_extra": extra})
    return p, amg, namespace, staged


def call(p, state, gallery, **overrides):
    req = {"id": "request", "hash": "image", "to": "image_start", "target": "generate:image_start"}
    req.update(overrides)
    with patch.dict("sys.modules", {"shared.utils.utils": metadata}):
        raw, gal, st = p.start_image_bridge("generate", json.dumps(req), gallery, state)
    return json.loads(raw), gal, st


def test_component_identity_and_missing_layout(tmp_path):
    p, amg, _, _ = harness(tmp_path)
    assert p.start_targets["generate"]["gallery"] is amg.gallery
    assert p.start_targets["generate"]["state"] is amg.state
    assert "reflib-start-generate" in amg.upload_btn.elem_classes
    p._setup_start_target("edit", {"image_start": amg.gallery, "image_start_extra": []})
    assert "edit" not in p.start_targets


def test_add_preserves_existing_after_selection(tmp_path):
    p, amg, _, staged = harness(tmp_path)
    state = {**amg.state.value, "items": ["existing-a", "existing-b"], "selected": 0}
    out, gal, new_state = call(p, state, ["existing-a", "existing-b"])
    assert out == {"ok": True, "id": "request", "target": "generate:image_start", "restored": ["image_start"]}
    assert gal["value"] == ["existing-a", str(tmp_path / "source.png"), "existing-b"]
    assert new_state["selected"] == 1
    assert state["items"] == ["existing-a", "existing-b"]  # input state not mutated
    assert len(staged) == 1


def test_add_to_empty_and_end(tmp_path):
    p, amg, _, _ = harness(tmp_path)
    out, gal, st = call(p, amg.state.value, [])
    assert out["ok"] and len(gal["value"]) == 1
    out, gal, st = call(p, {**amg.state.value, "selected": None}, ["old"])
    assert gal["value"][0] == "old" and len(gal["value"]) == 2


def test_wrong_kind_or_destination_never_writes(tmp_path):
    for req in ({"hash": "video"}, {"to": "image_refs"},
                {"target": "generate:image_refs"}, {"target": "edit:image_start"}):
        p, amg, _, staged = harness(tmp_path)
        out, gal, st = call(p, amg.state.value, ["keep"], **req)
        assert not out["ok"] and gal == gr.skip() and st == gr.skip() and not staged


def test_single_mode_never_replaces(tmp_path):
    p, amg, _, staged = harness(tmp_path)
    out, gal, st = call(p, {**amg.state.value, "single": True}, ["keep"])
    assert not out["ok"] and gal == gr.skip() and not staged


def test_missing_file_and_malformed_json(tmp_path):
    p, amg, ns, staged = harness(tmp_path)
    ns["imagelib"].media_path = lambda h: None
    out, gal, st = call(p, amg.state.value, ["keep"])
    assert not out["ok"] and not staged
    for raw in ("bad json", "[]", "null"):
        out, gal, st = p.start_image_bridge("generate", raw, ["keep"], amg.state.value)
        assert not json.loads(out)["ok"] and gal == gr.skip()


def test_bridge_reads_current_gallery_and_state_only():
    create = next(n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name == "create_ui")
    src = ast.get_source_segment((ROOT / "plugin.py").read_text(), create)
    assert 'inputs=[bridge_req, target["gallery"], target["state"]]' in src
    assert 'outputs=[bridge_resp, target["gallery"], target["state"]]' in src
    # Dedicated method does not call generation, history restores or Reference Images application.
    method = ast.unparse(next(n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name == "start_image_bridge"))
    assert "_on_add" in method and "_on_clear" not in method
    assert "apply_collection" not in method and "history_media" not in method


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
