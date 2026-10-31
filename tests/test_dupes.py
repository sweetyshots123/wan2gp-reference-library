"""1.11.0 duplicates: python3 tests/test_dupes.py (no WanGP needed; uses Pillow + numpy)."""
import os, sys, tempfile, shutil
d = tempfile.mkdtemp(); os.environ["REFLIB_DATA_DIR"] = d
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from reflib_core import imagelib, dupes, forget
src = os.path.join(tempfile.mkdtemp(), "fotos"); os.makedirs(os.path.join(src, "sub"))
rng = np.random.default_rng(1)
def pic(seed):
    r = np.random.default_rng(seed); a = r.integers(0, 255, (12, 16, 3), dtype=np.uint8)
    return Image.fromarray(a).resize((1600, 1200), Image.BICUBIC)
big = pic(1); big.save(os.path.join(src, "big.jpg"), quality=95)
big.resize((800, 600)).save(os.path.join(src, "small.jpg"), quality=80)          # near dup, smaller
shutil.copy(os.path.join(src, "big.jpg"), os.path.join(src, "sub", "big_copy.jpg"))  # exact copy (same hash)
pic(2).save(os.path.join(src, "other.jpg")); pic(3).save(os.path.join(src, "other2.png"))
# D: same size + same pHash but different bytes (pd_soldier_0/_1 case) -> 'near', never 'Idénticos'
_t = np.array(pic(4)); _t.copy().astype(np.uint8); Image.fromarray(_t).save(os.path.join(src, "tw_0.png"))
_t[0, 0] = (_t[0, 0].astype(int) ^ 1).astype(np.uint8); Image.fromarray(_t).save(os.path.join(src, "tw_1.png"))
imagelib.add_folder(src); imagelib.wait_scan(30) if hasattr(imagelib, "wait_scan") else None
recycled = []
forget.RECYCLER = lambda ps: ([os.remove(p) or recycled.append(p) for p in ps], {})[1]
dupes.scan(); s = dupes.wait(60)
assert s["hashed"] == 6 and not s["errors"], s
g = dupes.groups()
tw = next(x for x in g["groups"] if {r["name"] for r in x["rows"]} == {"tw_0.png", "tw_1.png"})
assert tw["kind"] == "near" and tw["dist"] == 0 and not tw["same_item"], tw
g["groups"] = [x for x in g["groups"] if x is not tw]
kinds = sorted(x["kind"] for x in g["groups"]); assert kinds == ["exact", "near"], [(x["kind"], [r["name"] for r in x["rows"]]) for x in g["groups"]]
near = next(x for x in g["groups"] if x["kind"] == "near"); ex = next(x for x in g["groups"] if x["kind"] == "exact")
k = near["rows"][near["keep"]]; sm = near["rows"][near["smallest"]]
assert (k["w"], k["h"]) == (1600, 1200) and (sm["w"], sm["h"]) == (800, 600) and k["mp"] == 1.92 and k["fmt"] == "JPEG" and k["bytes"] > 0, near
assert ex["same_item"] and len(ex["rows"]) == 2
# incremental: nothing new to hash
dupes.scan(); assert dupes.wait(30)["total"] == 0
# resolve near: tags move to the keeper, the delete is left to the existing flow
small_h = sm["hash"]; imagelib.set_tags([small_h], add=["favorito", "persona:Ana"])
# C: resolve only plans; cancelling the dialog afterwards must leave the tags untouched
r = dupes.resolve(k["hash"], [small_h])
assert r["drop"] == [small_h] and r["tags"] == ["favorito", "persona:Ana"], r
assert not {"favorito", "persona:Ana"} & set(imagelib.catalog()["by_hash"][k["hash"]].get("tags") or ())
assert {"favorito", "persona:Ana"} <= set(imagelib.catalog()["by_hash"][small_h]["tags"])
t = dupes.transfer(k["hash"], r["tags"])   # what the UI runs after the delete succeeded
assert t["tags_moved"] == 2 and {"favorito", "persona:Ana"} <= set(imagelib.catalog()["by_hash"][k["hash"]]["tags"])
try:
    dupes.resolve("nope", []); raise SystemExit("dup_not_found not raised")
except dupes.ActionError as e:
    assert e.key == "dup_not_found"
# exact: never all copies, then recycle one through forget.recycle + rescan
try:
    dupes.resolve(k["hash"], [], copies=[x["path"] for x in ex["rows"]]); raise SystemExit("keep-one not enforced")
except dupes.ActionError as e:
    assert e.key == "dup_keep_one"
cp = os.path.join(src, "sub", "big_copy.jpg")
# A: through the action entry with the host's sanitizing (plugin.py pops client `paths` from every action)
from reflib_core import actions as _act
req = {"action": "dup_resolve", "keep": k["hash"], "drop": [], "copies": [cp]}; req.pop("paths", None); req.pop("dir", None)
r = dupes.a_resolve(req, None); assert r["recycled"] == 1 and recycled == [cp], r
_pl = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin.py"), encoding="utf-8").read()
assert 'req.pop("paths", None)' in _pl and '"dup_not_found"' in _pl
imagelib.wait_scan(30)
assert not any(x["kind"] == "exact" for x in dupes.groups()["groups"])
# threshold 0 -> resized copy no longer counts unless identical pHash
print("thr0 groups", len(dupes.groups(0)["groups"]))
# flat / solid images are too low-contrast for perceptual hashing and must not match each other
import tempfile as _tf
from PIL import Image as _I
_d = _tf.mkdtemp(); _a, _b = os.path.join(_d, "a.png"), os.path.join(_d, "b.png")
_I.new("RGB", (64, 48), (200, 30, 80)).save(_a); _I.new("RGB", (64, 48), (170, 170, 160)).save(_b)
ha, hb = dupes.hashes_of(_a), dupes.hashes_of(_b)
assert ha["s"] < dupes.FLAT_STD and hb["s"] < dupes.FLAT_STD, (ha, hb)
assert dupes.hashes_of(os.path.join(_d, "a.png"))["s"] == ha["s"]
print("dupes ok")
