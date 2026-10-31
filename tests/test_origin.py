"""1.10.0 origin: python3 tests/test_origin.py (no WanGP needed)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import storage, origin

d = tempfile.mkdtemp(); storage.COLLECTIONS_DIR = d
out = os.path.join(d, "outputs"); os.makedirs(out)
origin.AI_DIRS = [out]
def it(h, name, path, locs=()):
    return {"hash": h * 64, "name": name, "names": (name,), "path": path, "files": (path,), "locs": tuple(locs)}
open(os.path.join(d, "b.png"), "w").close(); open(os.path.join(d, "b.json"), "w").close()
items = [it("a", "foto.jpg", os.path.join(d, "foto.jpg"), [("f1", "viaje/2024")]),
         it("b", "b.png", os.path.join(d, "b.png")),
         it("c", "x.png", os.path.join(out, "x.png")),
         it("d", "2025-01-02-10h11m12s_seed42_test.mp4", "/z/y.mp4"),
         it("e", "img.jpg", "/z/img.jpg", [("f1", "viaje")])]
origin.resolve(items)
assert [i["origin"] for i in items] == ["real", "ai", "ai", "ai", "real"], [i["origin"] for i in items]
origin.set_folder("f1", "viaje", "ai"); origin.resolve(items)
assert items[0]["origin"] == "ai" and items[0]["osrc"] == "folder" and items[4]["origin"] == "ai"
origin.set_folder("f1", "viaje/2024", "real"); origin.resolve(items)
assert items[0]["origin"] == "real" and items[4]["origin"] == "ai"
origin.set_items(["e" * 64], "real"); origin.resolve(items)
assert items[4]["origin"] == "real" and items[4]["osrc"] == "item"
origin.set_items(["e" * 64], "auto"); origin.resolve(items)
assert items[4]["origin"] == "ai"
assert origin.parse_query("retrato origin:ia") == ("retrato", ["ai"])
assert origin.parse_query("origen:real") == ("", ["real"])
assert origin.folder_mark("f1", "viaje/2024/x") == {"own": None, "inherited": "real"}
print("origin ok")
