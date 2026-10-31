"""1.12.1 shared virt_* actions (clips by in/out, crop, versions list): python3 tests/test_virtactions.py (needs ffmpeg)."""
import os, sys, tempfile, shutil, subprocess
if not shutil.which("ffmpeg"):
    print("skip: no ffmpeg"); raise SystemExit(0)
d = tempfile.mkdtemp(); os.environ["REFLIB_DATA_DIR"] = d
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import imagelib, actions, actions_all  # noqa: F401
src = os.path.join(tempfile.mkdtemp(), "vids"); os.makedirs(src)
v = os.path.join(src, "clip.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", v], check=True)
imagelib.add_folder(src); imagelib.wait_scan(30) if hasattr(imagelib, "wait_scan") else None
imagelib.SERVE_URL = lambda p: "/f=" + p
ctx = actions.Ctx("es", ok=lambda l, k, **p: {"ok": True, "message": k, **p}, err=lambda l, k, **p: {"ok": False, "error": k, **p})
call = lambda n, **r: actions.call(n, r, ctx)
h = next(i["hash"] for i in imagelib.catalog()["items"] if i.get("kind") == "video")
s = call("virt_src", hash=h)
assert s["ok"] and s["kind"] == "video" and not s["virtual"] and s["url"] == "/f=" + os.path.abspath(v) and s["orig_hash"] == h and 3.5 < s["duration"] < 4.5, s
assert call("virt_list", hash=h) == {"ok": True, "orig": h, "copies": []}
c = call("virt_create", hash=h, params={"start": 1, "end": 3}, name="tramo")
assert c["ok"] and c["message"] == "virt_created" and c["copy"]["dur"] == 2 and c["reload"], c
k = call("virt_create", hash=h, params={"rect": [0, 0, 160, 120]})
assert k["ok"] and k["copy"]["width"] == 160, k
l = call("virt_list", hash=c["hash"])   # from a copy: lists the original's versions
assert l["orig"] == h and sorted(x["hash"] for x in l["copies"]) == sorted([c["hash"], k["hash"]]), l
u = call("virt_update", hash=c["hash"], params={"start": 0.5, "end": 3})
assert u["ok"] and u["copy"]["dur"] == 2.5, u
s2 = call("virt_src", hash=c["hash"]); assert s2["virtual"] and s2["params"] == {"start": 0.5, "end": 3} and s2["orig_hash"] == h, s2
assert call("virt_create", hash=h, params={"start": 3, "end": 1})["error"] == "virt_bad"
assert call("virt_create", hash="nope", params={"start": 0, "end": 1})["error"] == "virt_no_orig"
assert call("virt_update", hash="nope", params={})["error"] == "err_image_missing"
assert call("virt_status", hash="nope") == {"ok": True, "state": "gone"}
assert call("virt_status", hash=c["hash"])["ok"]
# virtual copies never appear in duplicates
from reflib_core import dupes
assert not any(i.get("virtual") for i in dupes._candidates())
print("ok test_virtactions")
