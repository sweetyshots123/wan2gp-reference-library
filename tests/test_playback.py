"""reflib_core.playback: resume threshold + positions (no settings.json)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

td = tempfile.mkdtemp(prefix="reflib-pb-")
os.environ["REFLIB_DATA_DIR"] = td

from reflib_core import playback as pb
from reflib_core import actions

pb._reset_for_tests()

def test_default_min_without_file():
    pb._reset_for_tests()
    assert pb.get_min_s() == 300.0
    assert not os.path.isfile(pb._path())  # reading default must not create the file

def test_set_min_creates_playback_json_only():
    pb._reset_for_tests()
    assert pb.set_min_s(120) == 120.0
    assert os.path.isfile(pb._path())
    settings = os.path.join(td, "settings.json")
    assert not os.path.isfile(settings)
    pb._cache = None  # drop memory cache; keep file
    assert pb.get_min_s() == 120.0

def test_should_track_rules():
    assert pb.should_track(400, 60, 300) is True
    assert pb.should_track(200, 60, 300) is False
    assert pb.should_track(400, 2, 300) is False
    assert pb.should_track(400, 396, 300) is False
    assert pb.should_track(400, 390, 300) is False

def test_set_and_get_pos():
    pb._reset_for_tests()
    pb.set_min_s(300)
    h = "a" * 64
    r = pb.set_pos(h, 90, 400)
    assert r["tracked"] is True
    ent = pb.get(h)
    assert ent and abs(ent["t"] - 90) < 0.01
    r2 = pb.set_pos(h, 396, 400)
    assert r2.get("cleared")
    assert pb.get(h) is None

def test_actions_registered():
    assert actions.has("playback_get")
    assert actions.has("playback_set")
    assert actions.has("playback_settings")
    assert "playback_get" in actions.FAST
    assert "playback_settings" in actions.FAST
    ctx = actions.Ctx(lang="es")
    pb._reset_for_tests()
    out = actions.call("playback_settings", {}, ctx)
    assert out["ok"] and out["min_s"] == 300.0
    out2 = actions.call("playback_settings", {"min_m": 2}, ctx)
    assert out2["min_s"] == 120.0
    out3 = actions.call("playback_settings", {"min_m": 5}, ctx)
    assert out3["min_s"] == 300.0

if __name__ == "__main__":
    test_default_min_without_file()
    test_set_min_creates_playback_json_only()
    test_should_track_rules()
    test_set_and_get_pos()
    test_actions_registered()
    print("test_playback: ok")
