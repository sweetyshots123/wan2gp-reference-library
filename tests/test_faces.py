"""Unit tests for reflib_core/faces.py with synthetic embeddings (no models, no library)."""
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
        return {"w": 100, "h": 100, "n": n, "boxes": [[10, 10, 20, 20]] * n}


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
    assert sug[0]["bbox"] == [10, 10, 20, 20]
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


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
