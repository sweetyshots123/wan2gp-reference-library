"""Unit tests for reflib_core/faces.py with synthetic embeddings (no models, no library)."""
import json as json_mod
import os, sys, tempfile, threading
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import faces as F
from reflib_core.actions import ActionError


class Src:
    def __init__(self, data, model="arcface"):
        self.data, self.model = data, model
    def faces(self, m):
        ids, V = [], []
        for h, v in self.data.get(m, {}).items():
            ids += [F.fid(h, i, m) for i in range(len(v))]; V.append(v)
        return ids, F._norm(np.concatenate(V)) if V else np.zeros((0, 8), np.float32)
    def item(self, h, m):
        n = len(self.data.get(m, {}).get(h, ()))
        return {"w": 1000, "h": 1000, "n": n, "nbox": [[0.1, 0.1, 0.2, 0.2]] * n, "t": [None] * n, "kind": "image"}


class Tags:
    def __init__(self): self.t = {}
    def add(self, hs, tag): [self.t.setdefault(h, set()).add(tag) for h in hs]
    def remove(self, hs, tag): [self.t.get(h, set()).discard(tag) for h in hs]
    def rename(self, o, n):
        for s in self.t.values():
            if o in s: s.discard(o); s.add(n)
    def users(self, tag): return [h for h, s in self.t.items() if tag in s]


def synth(people=4, per=15, dim=64, noise=0.35, seed=0, model="arcface"):
    rng = np.random.default_rng(seed)
    C = F._norm(rng.normal(size=(people, dim)))
    data, truth = {}, {}
    for p in range(people):
        for k in range(per):
            h = "h%02d%03d" % (p, k)
            data[h] = (C[p] + noise * rng.normal(size=dim) / np.sqrt(dim)).reshape(1, -1).astype(np.float32)
            truth[F.fid(h, 0, model)] = p
    return {model: data}, truth


def mk(data, model="arcface"):
    d = tempfile.mkdtemp(); t = Tags()
    return F.Faces(d, Src(data, model), tagger=t), t, d


def test_cluster_purity_and_incremental():
    data, truth = synth()
    f, _, d = mk(data)
    st = f.run()
    assert st["clusters"] == 4, st
    for c in f.clusters()["clusters"].values():
        assert len({truth[x] for x in c["faces"]}) == 1
    # incremental: add a new face of person 0 -> joins existing cluster, no re-cluster
    data2, _ = synth(per=16)
    f.src.data["arcface"]["h00015"] = data2["arcface"]["h00015"]
    f._cache = {}
    st = f.run()
    assert st["clusters"] == 4 and st["total"] == 1
    # persisted
    g = F.Faces(d, f.src); assert len(g.clusters()["clusters"]) == 4


def test_assign_suggest_reject_tags():
    data, truth = synth()
    f, t, _ = mk(data)
    f.run()
    cid = next(k for k, c in f.clusters()["clusters"].items() if truth[c["faces"][0]] == 0)
    fs = list(f.clusters()["clusters"][cid]["faces"])
    r = f.assign_faces(name="Lucía", clusters=[cid])
    pid = r["person"]["id"]
    assert r["assigned"] == 15 and len(t.users("persona:Lucía")) == 15
    assert cid not in f.clusters()["clusters"]
    # move 3 faces back out and check suggestions find them first
    f.unassign(fs[:3])
    assert len(t.users("persona:Lucía")) == 12
    sug = f.suggest(pid, limit=5)
    assert {s["id"] for s in sug[:3]} == set(fs[:3]), sug
    assert all(truth[s["id"]] == 0 for s in sug)
    assert sug[0]["bbox"] == [100.0, 100.0, 200.0, 200.0] and sug[0]["box"] == [0.1, 0.1, 0.2, 0.2]
    f.reject(pid, [fs[0]])
    assert fs[0] not in {s["id"] for s in f.suggest(pid, limit=50, threshold=-1)}
    g = F.Faces(f.dir[:-6], f.src)   # rejection persisted
    assert fs[0] not in {s["id"] for s in g.suggest(pid, limit=50, threshold=-1)}
    f.assign_faces(pid=pid, faces=[fs[1]])   # confirm
    assert f.assign("arcface")[fs[1]] == pid
    c = F.Faces(f.dir[:-6], f.src).suggest(pid, method="centroid", limit=3)
    assert c and c[0]["id"] == fs[2]


def test_merge_split_rename_delete_undo():
    data, truth = synth()
    f, t, _ = mk(data)
    f.run()
    cs = list(f.clusters()["clusters"])
    a = f.assign_faces(name="Ana", clusters=[cs[0]])["person"]["id"]
    b = f.assign_faces(name="Bea", clusters=[cs[1]])["person"]["id"]
    p = f.merge_persons([b], a)
    assert p["count"] == 30 and "persona:Bea" not in set().union(*t.t.values())
    some = [x for x, q in f.assign("arcface").items() if q == a][:5]
    new = f.split(some, person=a)
    assert len(f.clusters()["clusters"][new]["faces"]) == 5 and f.person_obj(a)["count"] == 25
    m = f.merge_clusters([new, cs[2]]); assert len(f.clusters()["clusters"][m]["faces"]) == 20
    p = f.rename(a, "Ana María"); assert p["tag"] == "persona:Ana María" and len(t.users("persona:Ana María")) == 25
    f.set_cover(a, [x for x, q in f.assign("arcface").items() if q == a][3])
    tok = f.delete(a)
    assert not f.db["persons"] and not t.users("persona:Ana María")
    p = f.undo_delete(tok); assert p["count"] == 25 and len(t.users("persona:Ana María")) == 25
    try:
        f.merge_clusters([m]); assert False
    except ActionError as e:
        assert e.key == "faces_need_two"


def test_model_switch_and_errors():
    data, _ = synth()
    data2, _ = synth(model="sface", seed=0)
    f, t, _ = mk({**data, **data2})
    f.run()
    cid = list(f.clusters()["clusters"])[0]
    pid = f.assign_faces(name="X", clusters=[cid])["person"]["id"]
    f.src.model = "sface"; f._cache = {}
    assert f.person_obj(pid)["count"] == 0
    f.seed(t.users)
    assert f.person_obj(pid)["count"] == 15 and f.person_obj(pid)["seeded"]
    f.run(); assert len(f.clusters("sface")["clusters"]) == 3
    assert len(f.clusters("arcface")["clusters"]) == 3   # old model kept
    for bad, key in ((["zz"], "face_not_found"), (["h00000:0@arcface"], "faces_model_mismatch")):
        try:
            f.reject(pid, bad); assert False
        except ActionError as e:
            assert e.key == key
    try:
        f.rename("p_nope", "a"); assert False
    except ActionError as e:
        assert e.key == "person_not_found"


def test_scale_speed():
    import time
    data, _ = synth(people=300, per=40, dim=512, noise=0.5)
    f, _, _ = mk(data)
    t0 = time.time(); st = f.run(); dt = time.time() - t0
    assert 280 <= st["clusters"] <= 330, st
    assert dt < 20, dt
    print("12000 faces clustered in %.2fs -> %d clusters" % (dt, st["clusters"]))


def test_face_thumb_crop_cache_invalidate():
    from PIL import Image
    data, _ = synth(people=1, per=2)
    f, _, d = mk(data)
    img = os.path.join(d, "src.png")
    im = Image.new("RGB", (200, 200), (0, 0, 255)); im.paste((255, 0, 0), (20, 20, 60, 60)); im.save(img)   # face bbox 10,10,20,20 @100px -> 20..60 @200px
    src = lambda h: [img]
    fid = F.fid("h00000", 0, "arcface")
    p = f.thumb_file(fid, 64, 0.0, sources=src)
    with Image.open(p) as t:
        assert t.size == (64, 64) and t.getpixel((32, 32))[0] > 200, t.getpixel((32, 32))   # red face fills the crop
    assert f.thumb_file(fid, 64, 0.0, sources=src) == p          # cached
    os.utime(img, (os.path.getmtime(img) + 10,) * 2)
    p2 = f.thumb_file(fid, 64, 0.0, sources=src)
    assert p2 != p and not os.path.exists(p)                      # source changed -> new file, old removed
    f.src.item = lambda h, m: {"w": 100, "h": 100, "n": 1, "nbox": [None]}   # old index: no bbox -> whole image
    p3 = f.thumb_file(fid, 64, 0.4, sources=src)
    assert p3.endswith("_full.jpg")
    with Image.open(p3) as t:
        assert t.getpixel((60, 60))[2] > 200                      # blue background visible = whole image
    assert f.thumb_file(fid, 64, sources=lambda h: []) is None
    assert F.thumb_url(fid) == "/reflib/face_thumb/h00000%3A0%40arcface.jpg?size=160&margin=0.4"


def test_busy_and_translated_errors():
    data, _ = synth(people=1, per=3)
    f, _, _ = mk(data)
    old = F._F; F._F = f
    try:
        class C: lang = "es"
        f.st["running"] = True
        r = F._actions.call("face_reject", {"person": "p_x", "faces": []}, C())
        assert r["ok"] is False and r["code"] == "faces_busy" and "agrupando" in r["error"], r
        f.st["running"] = False
        r = F._actions.call("person_rename", {"person": "p_nope", "name": "a"}, C())
        assert r["code"] == "person_not_found" and r["error"] == "Persona no encontrada", r
        assert F._ok(C(), "face_assigned", n=2, name="Ana")["toast"] == "2 cara(s) asignada(s) a Ana"
    finally:
        F._F = old


def test_real_source_face_matrix_bbox_and_on_faces():
    """FaceSource over a minimal simperf-like index (face_matrix / on_faces / packs with box+det)."""
    import time
    data, _ = synth(people=2, per=4)
    V = data["arcface"]
    class Idx:
        active = "arcface"; rev = 0
        def __init__(self):
            self.items, self.cbs = {}, []
            for h, v in V.items():
                self.items[h] = {"w": 200, "h": 100, "faces": {"arcface": {"vec": v.astype(np.float16), "box": np.array([[0.25, 0.1, 0.2, 0.4]] * len(v), np.float32), "det": np.ones(len(v), np.float32)}}}
            h0 = next(iter(V)); self.items[h0]["faces"]["arcface"]["box"][:] = np.nan   # legacy row
        def face_matrix(self, fm=None):
            ids, fi, vec = [], [], []
            for h, e in self.items.items():
                p = e["faces"][fm]; ids += [h] * len(p["vec"]); fi += list(range(len(p["vec"]))); vec.append(p["vec"])
            return {"ids": np.array(ids, object), "face_i": np.array(fi, np.int32), "vec": np.concatenate(vec).astype(np.float32), "model": fm}
        def on_faces(self, cb):
            self.cbs.append(cb); return lambda: self.cbs.remove(cb)
    idx = Idx()
    f = F.Faces(tempfile.mkdtemp(), F.FaceSource(idx), tagger=Tags()); f.AUTO_DELAY = 0.05
    ids, M = f.src.faces("arcface")
    assert len(ids) == 8 and abs(float(np.linalg.norm(M[0])) - 1) < 1e-3
    h0, h1 = list(V)[:2]
    assert f.face_obj(F.fid(h0, 0, "arcface"), "arcface")["bbox"] is None
    o = f.face_obj(F.fid(h1, 0, "arcface"), "arcface")
    assert o["box"] == [0.25, 0.1, 0.2, 0.4] and o["bbox"] == [50.0, 10.0, 40.0, 40.0], o
    # on_faces -> debounced incremental clustering
    idx.cbs[0]([{"id": h1, "face_i": 0, "model": "arcface"}])
    for _ in range(100):
        if f.cl.get("arcface", {}).get("seen"): break
        time.sleep(0.02)
    assert len(f.clusters("arcface")["seen"]) == 8
    idx.rev += 1
    rng = np.random.default_rng(5)
    idx.items["new1"] = {"w": 10, "h": 10, "faces": {"arcface": {"vec": (V[h1] + 0.01 * rng.normal(size=V[h1].shape)).astype(np.float16), "box": np.full((1, 4), np.nan, np.float32), "det": np.ones(1, np.float32)}}}
    idx.cbs[0]([{"id": "new1", "face_i": 0, "model": "arcface"}])
    for _ in range(100):
        if len(f.clusters("arcface")["seen"]) == 9: break
        time.sleep(0.02)
    cl = f.clusters("arcface")["clusters"]
    assert any({F.fid("new1", 0, "arcface"), F.fid(h1, 0, "arcface")} <= set(c["faces"]) for c in cl.values())
    # face_min_size: a 10x10 px face (box 0.05 of 200x100 -> 10x5) is skipped
    idx.items[h1]["faces"]["arcface"]["box"][:] = [0.1, 0.1, 0.05, 0.05]; idx.rev += 1
    assert F.fid(h1, 0, "arcface") not in f._mat("arcface")["pos"]
    # re-index shrinking an item's rows drops stale assignments
    f.assign("arcface")[F.fid(h1, 3, "arcface")] = "p_x"
    idx.cbs[0]([{"id": h1, "face_i": 0, "model": "arcface"}])
    assert F.fid(h1, 3, "arcface") not in f.assign("arcface")
    f.close(); assert not idx.cbs


def test_status_counts_shown_groups_and_last_threshold():
    data, _ = synth(people=3, per=6)
    rng = np.random.default_rng(7)
    for k in range(5):   # 5 unrelated faces -> singletons, never shown in the panel
        data["arcface"]["solo%d" % k] = F._norm(rng.normal(size=(1, 64))).astype(np.float32)
    f, _, d = mk(data)
    f.run()
    s = f.status()
    assert s["clusters"] == 3 == f.list_clusters()["total"], s
    assert s["clusters_all"] >= 8 and s["min_cluster"] == 2
    assert abs(s["threshold"] - s["threshold_setting"]) < 1e-9
    # explicit threshold on a run is what status reports (and it persists)
    f.run(full=True, threshold=0.2)
    s = f.status()
    assert abs(s["threshold"] - 0.2) < 1e-9 and abs(s["threshold_setting"] - 0.2) > 1e-6, s
    assert abs(F.Faces(d, f.src).status()["threshold"] - 0.2) < 1e-9
    # naming a group removes it from the count
    f.run(full=True)
    c = f.list_clusters()["clusters"][0]["id"]
    f.assign_faces(name="Ana", clusters=[c])
    s = f.status()
    assert s["clusters"] == 2 == f.list_clusters()["total"] and s["persons"] == 1, s




def test_person_review_batch():
    """1.11.1 person_review = face_confirm(accept) + face_reject(reject) in one call."""
    data, truth = synth()
    f, t, _ = mk(data)
    old = F._F; F._F = f
    try:
        class C: lang = "es"
        f.run()
        cid = next(k for k, c in f.clusters()["clusters"].items() if truth[c["faces"][0]] == 0)
        fs = list(f.clusters()["clusters"][cid]["faces"])
        pid = f.assign_faces(name="Lucía", clusters=[cid])["person"]["id"]
        f.unassign(fs[:4])
        r = F._actions.call("person_review", {"person": pid, "accept": fs[:3], "reject": [fs[2], fs[3]], "meta": False}, C())
        assert r["ok"] and r["assigned"] == 2 and r["rejected"] == [fs[2], fs[3]] and r["accepted"] == fs[:2], r
        a = f.assign("arcface")
        assert a[fs[0]] == pid and a[fs[1]] == pid and fs[2] not in a and fs[3] not in a
        left = {s["id"] for s in f.suggest(pid, limit=50, threshold=-1)}
        assert fs[2] not in left and fs[3] not in left
        assert len(t.users("persona:Lucía")) == 13
        assert F._actions.call("person_review", {"person": "", "accept": fs[:1]}, C())["code"] == "person_not_found"
    finally:
        F._F = old


def test_facequality_helpers():
    s = dict(F.DEFAULTS)
    assert F.face_quality(0.95, 120, [200, 0.1, 0.0, 2], s)["ok"]
    q = F.face_quality(0.5, 120, [5, 0.9, 1.0, 2], s)
    assert not q["ok"] and {"low_det", "blurry", "profile", "truncated"} <= set(q["flags"]) and q["aligned"] == 2
    assert F.face_quality(None, None, None, s)["ok"]           # legacy faces: unknown never fails
    # strict clustering does not chain A - bridge - B
    rng = np.random.default_rng(0)
    a, b = F._norm(rng.normal(size=(1, 64))), F._norm(rng.normal(size=(1, 64)))
    A = F._norm(a + 0.15 * rng.normal(size=(6, 64))); B = F._norm(b + 0.15 * rng.normal(size=(6, 64)))
    br = F._norm((a + b))
    M = F._norm(np.vstack([A, br, B]))
    gs = F.strict_cluster(M, list(range(len(M))), [], 0.5, 3, 0.05)
    assert not any(set(g) & set(range(6)) and set(g) & set(range(7, 13)) for g in gs), gs
    # prototypes / suggest margin: a candidate closer to a rival person gets a negative margin
    P = A; others = F.prototypes(B, 2)
    sc, mg = F.suggest_scores(np.vstack([A[:1], B[:1]]), P, None, others, 2)
    assert mg[0] > 0 > mg[1]
    # remap by IoU
    mp = F.remap_by_iou({0: [0.1, 0.1, 0.2, 0.2], 1: [0.6, 0.6, 0.2, 0.2], 2: [0.0, 0.9, 0.05, 0.05]},
                        [[0.61, 0.6, 0.2, 0.2], [0.1, 0.11, 0.2, 0.2]])
    assert mp == {0: 1, 1: 0, 2: None}, mp


def test_recompute_keeps_assignments():
    data, truth = synth(people=2, per=6)
    f, _, d = mk(data)
    f.run()
    c = list(f.clusters()["clusters"])[0]
    f.assign_faces(name="Ana", clusters=[c])
    before = dict(f.assign("arcface"))
    hs = f.recompute_plan()
    assert set(hs) == {F.parse_fid(x)[0] for x in before} and f.db["remap"]["arcface"]
    f._remap_pending(set(hs), "arcface")   # same boxes -> identity mapping
    assert f.assign("arcface") == before and not f.db["remap"]["arcface"]


class VSrc(Src):
    """Src where hashes starting with 'v' are videos: one face row per sampled frame (t = row index)."""
    def item(self, h, m):
        it = Src.item(self, h, m)
        if h.startswith("v"):
            it.update(kind="video", t=[float(i) for i in range(it["n"])])
        else:
            it.update(kind="image", t=[None] * it["n"])
        return it


def test_video_suggestion_ids_review_expand_and_no_resuggest():
    """1.12.2 A/B: a deduped video suggestion carries every merged face id; accepting / rejecting it via
    person_review applies to all its frames; other frames of a decided video are never re-suggested."""
    rng = np.random.default_rng(3)
    A, B = F._norm(rng.normal(size=(2, 64)))
    near = lambda c, k: (c + 0.25 * rng.normal(size=(k, 64)) / 8).astype(np.float32)
    data = {"arcface": {**{"a%02d" % i: near(A, 1) for i in range(6)},
                        "vA1": near(A, 5), "vA2": near(A, 4),
                        "vMix": np.vstack([near(A, 2), near(B, 2)])}}
    d = tempfile.mkdtemp(); t = Tags()
    f = F.Faces(d, VSrc(data), tagger=t)
    old = F._F; F._F = f
    try:
        class C: lang = "es"
        pid = f.assign_faces(name="Ana", faces=[F.fid("a%02d" % i, 0, "arcface") for i in range(6)])["person"]["id"]
        sug = f.suggest(pid, limit=20)
        v1 = next(x for x in sug if x["hash"] == "vA1")
        assert sorted(v1["ids"]) == [F.fid("vA1", i, "arcface") for i in range(5)], v1
        assert sum(1 for x in sug if x["hash"] == "vA1") == 1
        mix = next(x for x in sug if x["hash"] == "vMix")
        assert set(mix["ids"]) == {F.fid("vMix", 0, "arcface"), F.fid("vMix", 1, "arcface")}, mix
        # accept the representative only -> all 5 frames of vA1 assigned; reject vA2 rep -> all 4 rejected
        r = F._actions.call("person_review", {"person": pid, "accept": [v1["id"]],
                                              "reject": [next(x["id"] for x in sug if x["hash"] == "vA2")], "meta": False}, C())
        assert r["ok"] and r["assigned"] == 5 and r["n_rejected"] == 4 and "toast" not in r, r
        a = f.assign("arcface")
        assert all(a.get(F.fid("vA1", i, "arcface")) == pid for i in range(5))
        assert len(f.db["reject"]["arcface"][pid]) == 4
        # face_assign / face_reject expand too; B's frames of vMix are never pulled in
        F._actions.call("face_assign", {"person": pid, "faces": [mix["id"]], "meta": False}, C())
        assert {F.fid("vMix", 0, "arcface"), F.fid("vMix", 1, "arcface")} <= set(f.assign("arcface"))
        assert F.fid("vMix", 2, "arcface") not in f.assign("arcface") and F.fid("vMix", 3, "arcface") not in f.assign("arcface")
        # B: decided videos are not re-suggested (even other frames left unassigned)
        f.unassign([F.fid("vA1", 4, "arcface")])
        f.db["reject"]["arcface"][pid] = f.db["reject"]["arcface"][pid][:2]
        hs = {x["hash"] for x in f.suggest(pid, limit=20, threshold=-1)}
        assert not hs & {"vA1", "vA2", "vMix"}, hs
    finally:
        F._F = old


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)


def test_assign_skips_obsolete_faces():
    """1.12.9: naming a group with stale face ids (left the matrix after reindex) assigns the live ones
    and prunes the dead — never face_not_found on the whole group."""
    data, _ = synth(people=1, per=6)
    f, t, _ = mk(data)
    f.run()
    cid = list(f.clusters()["clusters"])[0]
    live = list(f.clusters()["clusters"][cid]["faces"])
    # inject an obsolete id into the cluster (hash gone from the matrix)
    stale = "deadhash:0@arcface"
    f.clusters()["clusters"][cid]["faces"] = live + [stale]
    r = f.assign_faces(name="Lucía", clusters=[cid])
    assert r["assigned"] == len(live)
    assert r["skipped"] == 1
    assert stale in r["skipped_ids"]
    assert stale not in (f.clusters().get("clusters") or {})
    # all-obsolete → clear error, no person created, clusters untouched (1.12.10 BUG-A)
    f2, _, d2 = mk(data)
    f2.run()
    cid2 = list(f2.clusters()["clusters"])[0]
    before_cl = json_mod.dumps(f2.clusters(), sort_keys=True)
    before_persons = dict(f2.db["persons"])
    f2.clusters()["clusters"][cid2]["faces"] = [stale]
    try:
        f2.assign_faces(name="X_all_obsolete", clusters=[cid2])
        assert False
    except ActionError as e:
        assert e.key == "face_all_obsolete"
    assert "X_all_obsolete" not in {p["name"] for p in f2.db["persons"].values()}
    assert f2.db["persons"] == before_persons
    # in-memory cluster still holds the stale id we planted (no prune on all-obsolete)
    assert stale in f2.clusters()["clusters"][cid2]["faces"]


def test_match_persons_fold_prefix_substring():
    data, _ = synth(people=1, per=3)
    f, _, _ = mk(data)
    f.run()
    f.assign_faces(name="María José", clusters=[list(f.clusters()["clusters"])[0]])
    # rebuild a second person via new_person
    f.new_person("Mario")
    f.new_person("Ana")
    m = f.match_persons("mar", 10)
    names = [x["name"] for x in m]
    assert names[0] in ("María José", "Mario")
    assert "Ana" not in names
    assert [x["name"] for x in f.match_persons("josé", 5)] == ["María José"]
    # fold-equal resolve via find
    assert f.find_person("maria jose") == f.find_person("María José")


def test_assign_all_obsolete_no_person_no_prune():
    """1.12.10 BUG-A: all-obsolete assign must not create a person or prune/save."""
    data, _ = synth(people=1, per=4)
    f, _, d = mk(data)
    f.run()
    cid = list(f.clusters()["clusters"])[0]
    stale = "deadhash:0@arcface"
    f.clusters()["clusters"][cid]["faces"] = [stale]
    n_before = len(f.db["persons"])
    cl_path = os.path.join(d, "faces", "clusters-arcface.json")
    # snapshot disk after run()
    disk_before = open(cl_path, encoding="utf-8").read() if os.path.isfile(cl_path) else None
    try:
        f.assign_faces(name="Ghost", clusters=[cid])
        assert False, "expected face_all_obsolete"
    except ActionError as e:
        assert e.key == "face_all_obsolete"
    assert len(f.db["persons"]) == n_before
    assert not any(p["name"] == "Ghost" for p in f.db["persons"].values())
    assert stale in f.clusters()["clusters"][cid]["faces"]
    if disk_before is not None:
        assert open(cl_path, encoding="utf-8").read() == disk_before


def test_atomic_json_unique_tmp(tmp_path=None):
    """1.12.10: _atomic_json uses a unique temp name (not path+'.tmp' fixed)."""
    import inspect
    src = inspect.getsource(F._atomic_json)
    assert "mkstemp" in src
    d = tempfile.mkdtemp()
    path = os.path.join(d, "persons.json")
    F._atomic_json(path, {"version": 1, "persons": {}})
    assert os.path.isfile(path)
    assert not os.path.isfile(path + ".tmp")  # fixed name must not linger
    F._atomic_json(path, {"version": 1, "persons": {"p": {"name": "A"}}}, bak=True)
    assert os.path.isfile(path + ".bak")
