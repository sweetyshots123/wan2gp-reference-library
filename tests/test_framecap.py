"""reflib_core.framecap.save_result annotates stay/navigate for both UIs."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from reflib_core import framecap

def test_save_result_stay():
    out = framecap.save_result({"ok": True, "name": "a.png", "hash": "h" * 64, "created": True})
    assert out["ok"] is True
    assert out["stay"] is True
    assert out["navigate"] is False
    assert out["source"] == "frame"
    assert out["name"] == "a.png"

if __name__ == "__main__":
    test_save_result_stay()
    print("test_framecap: ok")
