"""1.12.22: find_binary falls back to a nearby ffmpeg_bins/; make_poster retries .ts at t=0."""
import os, shutil, subprocess, sys, tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
td = tempfile.mkdtemp(prefix="reflib-bins-")
os.environ.setdefault("REFLIB_DATA_DIR", td)

from reflib_core import media, storage

FFMPEG = shutil.which("ffmpeg")
need_ff = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")


@need_ff
def test_find_binary_uses_nearby_ffmpeg_bins(tmp_path, monkeypatch):
    """Even with no WanGP resolver and an empty PATH, a WanGP-style ffmpeg_bins/ next to the plugin root is used."""
    wgp = tmp_path / "Wan2GP"
    plug = wgp / "plugins" / "wan2gp-reference-library"
    bins = wgp / "ffmpeg_bins"
    bins.mkdir(parents=True)
    plug.mkdir(parents=True)
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    dest = bins / exe
    os.symlink(os.path.abspath(FFMPEG), dest)
    monkeypatch.setattr(media, "BINARY_RESOLVER", None)
    monkeypatch.setattr(storage, "PLUGIN_DIR", str(plug))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)
    found = media.find_binary("ffmpeg")
    assert found, "ffmpeg_bins fallback should find the binary"
    assert os.path.samefile(found, dest)


@need_ff
def test_make_poster_long_gop_ts(tmp_path):
    ts = tmp_path / "longgop.ts"
    dest = tmp_path / "p.jpg"
    r = subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=160x120:rate=25",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-g", "250", "-f", "mpegts", str(ts)],
        capture_output=True, timeout=30,
    )
    assert r.returncode == 0 and ts.is_file()
    assert media.make_poster(str(ts), str(dest))
    assert dest.is_file() and dest.stat().st_size > 0
