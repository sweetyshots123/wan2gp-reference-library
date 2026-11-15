"""1.12.19: browser-playable cache for codecs Chrome cannot decode (mp4v, …). Synthetic ffmpeg clips only."""
import os, sys, tempfile, time, subprocess, hashlib
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
td = tempfile.mkdtemp(prefix="reflib-play-")
os.environ["REFLIB_DATA_DIR"] = td
os.environ["REFLIB_PLAY_ENCODER"] = "libx264"
os.environ["REFLIB_PLAY_CACHE_MAX"] = str(32 * 1024 * 1024)

from reflib_core import playable as P
from reflib_core import storage, imagelib

FFMPEG = subprocess.run(["sh", "-c", "command -v ffmpeg"], capture_output=True).returncode == 0
FFPROBE = subprocess.run(["sh", "-c", "command -v ffprobe"], capture_output=True).returncode == 0
need_ff = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe required")


def _clip(path, codec, seconds=2, size="320x240", rate="30000/1001", audio=True, tag=None, container=None):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate={rate}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", codec]
    if tag:
        cmd += ["-tag:v", tag]
    cmd += ["-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-ac", "1", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [path]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    assert r.returncode == 0 and os.path.isfile(path) and os.path.getsize(path) > 0, r.stderr


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _isolate():
    prev = os.environ.get("REFLIB_DATA_DIR")
    os.environ["REFLIB_DATA_DIR"] = td
    os.environ["REFLIB_PLAY_ENCODER"] = "libx264"
    P._reset_for_tests()
    yield
    P._reset_for_tests()
    if prev is None:
        os.environ.pop("REFLIB_DATA_DIR", None)
    else:
        os.environ["REFLIB_DATA_DIR"] = prev


@need_ff
def test_probe_and_classify_mp4v():
    p = os.path.join(td, "mp4v.mp4")
    _clip(p, "mpeg4", tag="mp4v", size="800x600", rate="30000/1001")
    info = P.probe(p)
    assert info["vcodec"] == "mpeg4"
    assert info["width"] == 800 and info["height"] == 600
    assert abs(info["fps"] - 29.97) < 0.02
    assert info["pix_fmt"] == "yuv420p"
    assert P.classify(info) == "transcode"
    assert P.needs_convert(info)


@need_ff
def test_h264_mp4_is_original():
    p = os.path.join(td, "ok.mp4")
    _clip(p, "libx264")
    info = P.probe(p)
    assert info["vcodec"] == "h264"
    assert P.classify(info) == "original"


@need_ff
def test_h264_mkv_is_remux():
    src = os.path.join(td, "ok2.mp4")
    mkv = os.path.join(td, "ok2.mkv")
    _clip(src, "libx264")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c", "copy", mkv], capture_output=True, timeout=20)
    assert r.returncode == 0
    info = P.probe(mkv)
    assert info["vcodec"] == "h264"
    assert P.classify(info) == "remux"


def test_classify_table():
    assert P.classify({"vcodec": "mpeg4", "acodec": "aac", "ext": ".mp4"}) == "transcode"
    assert P.classify({"vcodec": "msmpeg4v3", "acodec": "", "ext": ".avi"}) == "transcode"
    assert P.classify({"vcodec": "mpeg2video", "acodec": "mp2", "ext": ".mpg"}) == "transcode"
    assert P.classify({"vcodec": "mpeg1video", "acodec": "", "ext": ".mpg"}) == "transcode"
    assert P.classify({"vcodec": "wmv3", "acodec": "wmav2", "ext": ".wmv"}) == "transcode"
    assert P.classify({"vcodec": "vc1", "acodec": "", "ext": ".mkv"}) == "transcode"
    assert P.classify({"vcodec": "hevc", "acodec": "aac", "ext": ".mp4"}) == "transcode"
    assert P.classify({"vcodec": "vp9", "acodec": "opus", "ext": ".webm"}) == "original"
    assert P.classify({"vcodec": "h264", "acodec": "aac", "ext": ".mp4"}) == "original"
    assert P.classify({"vcodec": "h264", "acodec": "aac", "ext": ".mkv"}) == "remux"
    assert P.classify({"vcodec": "h264", "acodec": "pcm_s16le", "ext": ".mkv"}) == "transcode"


@need_ff
def test_transcode_mp4v_plays_as_h264():
    src = os.path.join(td, "need.mp4")
    _clip(src, "mpeg4", tag="mp4v", seconds=1, size="160x120", rate="25")
    digest = _h("need")
    st0 = P.status(digest, src)
    assert st0["play"] == "preparing" and st0.get("idle")
    st = P.wait(digest, src, timeout=60)
    assert st["play"] == "ready", st
    assert st["path"] and os.path.isfile(st["path"])
    # cache lives under the plugin data dir, not next to the source
    assert os.path.commonpath([st["path"], td]) == td
    assert "cache" in st["path"].replace("\\", "/").split("/")
    assert os.path.dirname(os.path.abspath(st["path"])) != os.path.dirname(os.path.abspath(src))
    out = P.probe(st["path"])
    assert out["vcodec"] == "h264"
    # original untouched
    before = open(src, "rb").read()
    time.sleep(0.05)
    assert open(src, "rb").read() == before
    # second call is a cache hit (ready, no new job)
    st2 = P.ensure(digest, src)
    assert st2["play"] == "ready"
    assert st2["path"] == st["path"]


@need_ff
def test_single_flight():
    src = os.path.join(td, "flight.mp4")
    _clip(src, "mpeg4", tag="mp4v", seconds=2, size="160x120", rate="25")
    digest = _h("flight")
    a = P.ensure(digest, src)
    b = P.ensure(digest, src)
    assert a["play"] == "preparing" and b["play"] == "preparing"
    with P._lock:
        n = sum(1 for k in P._jobs if k.startswith(digest))
    assert n == 1
    st = P.wait(digest, src, timeout=60)
    assert st["play"] == "ready"


@need_ff
def test_remux_does_not_reencode():
    src = os.path.join(td, "remuxsrc.mp4")
    mkv = os.path.join(td, "remuxsrc.mkv")
    _clip(src, "libx264", seconds=1, size="160x120", rate="25")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c", "copy", mkv], check=True, timeout=20)
    digest = _h("remux")
    st = P.wait(digest, mkv, timeout=30)
    assert st["play"] == "ready", st
    assert st.get("mode") == "remux"
    info = P.probe(st["path"])
    assert info["vcodec"] == "h264"
    assert st["path"].endswith(".mp4")


@need_ff
def test_cache_eviction():
    os.environ["REFLIB_PLAY_CACHE_MAX"] = str(200_000)  # tight
    P._reset_for_tests()
    paths = []
    for i in range(3):
        src = os.path.join(td, f"ev{i}.mp4")
        _clip(src, "mpeg4", tag="mp4v", seconds=1, size="320x240", rate="15")
        d = _h(f"ev{i}")
        st = P.wait(d, src, timeout=60)
        assert st["play"] == "ready"
        paths.append(st["path"])
        time.sleep(0.05)
    P.evict(needed=0)
    # cap is small: at least the oldest finished file should have been dropped after later writes + evict
    existing = [p for p in paths if p and os.path.isfile(p)]
    assert len(existing) < 3 or sum(os.path.getsize(p) for p in existing) <= P.cache_max()
    os.environ["REFLIB_PLAY_CACHE_MAX"] = str(32 * 1024 * 1024)


@need_ff
def test_ensure_does_not_invalidate_catalog():
    # media_play / ensure must never bump the catalog epoch
    imagelib.invalidate()
    epoch = imagelib._cat.get("epoch")
    src = os.path.join(td, "cat.mp4")
    _clip(src, "mpeg4", tag="mp4v", seconds=1, size="160x120", rate="25")
    P.wait(_h("cat"), src, timeout=60)
    assert imagelib._cat.get("epoch") == epoch


def test_missing_file_fails():
    st = P.ensure("dead", os.path.join(td, "no-such.mp4"))
    assert st["play"] == "failed"
    assert st.get("error")


def test_encoder_forced_libx264():
    assert P.encoder_name() == "libx264"
    assert P.encoder()[0] == "libx264"
