"""1.11.1 exact video duplicates: python3 tests/test_dupes_video.py (needs ffmpeg on PATH; skipped otherwise)."""
import os, sys, tempfile, shutil, subprocess
if not shutil.which("ffmpeg"):
    print("skip: no ffmpeg"); raise SystemExit(0)
d = tempfile.mkdtemp(); os.environ["REFLIB_DATA_DIR"] = d
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import imagelib, dupes
src = os.path.join(tempfile.mkdtemp(), "vids"); os.makedirs(os.path.join(src, "sub"))
a = os.path.join(src, "clip.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", a], check=True)
shutil.copy(a, os.path.join(src, "sub", "clip_copy.mp4"))                       # identical bytes -> exact group
subprocess.run(["ffmpeg", "-v", "error", "-i", a, "-c:v", "libx264", "-crf", "35", os.path.join(src, "clip_reenc.mp4")], check=True)  # same picture, other bytes -> never grouped
imagelib.add_folder(src); imagelib.wait_scan(30) if hasattr(imagelib, "wait_scan") else None
dupes.scan(); s = dupes.wait(60); assert not s["errors"], s
g = dupes.groups()["groups"]
names = [sorted(r["name"] for r in x["rows"]) for x in g]
assert names == [["clip.mp4", "clip_copy.mp4"]], names
x = g[0]; r = x["rows"][0]
assert x["kind"] == "exact" and x.get("video") and r["video"] and (r["w"], r["h"]) == (320, 240) and r["codec"] == "h264" and r["fps"] == 25 and 1.9 <= r["dur"] <= 2.1, x
assert not any(y["kind"] == "near" for y in g)
print("ok test_dupes_video")
