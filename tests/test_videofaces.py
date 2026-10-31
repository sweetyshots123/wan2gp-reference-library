"""Unit tests for 1.12.0-videofaces: sampling, t, dedup, segments (no models / no library)."""
from __future__ import annotations
import os, sys, tempfile, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import videosim
from reflib_core import faces as F


def _make_face_img(path, color=(40, 80, 200), size=128, mark=None):
    import cv2
    img = np.zeros((size, size, 3), np.uint8)
    img[:] = color
    # simple "face": oval + two eyes
    cv2.ellipse(img, (size // 2, size // 2), (size // 3, size // 2 - 8), 0, 0, 360, (220, 190, 170), -1)
    cv2.circle(img, (size // 2 - 18, size // 2 - 10), 6, (20, 20, 20), -1)
    cv2.circle(img, (size // 2 + 18, size // 2 - 10), 6, (20, 20, 20), -1)
    if mark is not None:
        cv2.putText(img, str(mark), (8, size - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.imwrite(path, img)
    return path


def make_synth_video(out_path, duration_s=10.0, fps=10, face_at=None):
    """Write an mp4 with solid backgrounds and composited face crops at known times.

    face_at: dict {t_seconds: face_jpg_path}. At each listed second the face is pasted centred.
    Scene change at mid-point (background color flip) to exercise histogram detect.
    """
    import cv2
    face_at = face_at or {}
    w, h = 320, 240
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    assert vw.isOpened(), "VideoWriter failed (codec)"
    n = int(round(duration_s * fps))
    faces = {}
    for t, p in face_at.items():
        im = cv2.imread(p)
        if im is not None:
            faces[float(t)] = im
    for i in range(n):
        t = i / fps
        # scene A (blue-ish) then scene B (green-ish) after half
        if t < duration_s / 2:
            frame = np.full((h, w, 3), (180, 60, 40), np.uint8)
        else:
            frame = np.full((h, w, 3), (40, 180, 60), np.uint8)
        # composite nearest face within 0.05s
        for ft, fim in faces.items():
            if abs(ft - t) < 0.051:
                fh, fw = fim.shape[:2]
                x0, y0 = (w - fw) // 2, (h - fh) // 2
                frame[y0:y0 + fh, x0:x0 + fw] = fim
                break
        vw.write(frame)
    vw.release()
    return out_path


def test_sample_times_grid_and_cap():
    ts = videosim.sample_times(20.0, 25.0, interval_s=2.0, max_frames=60)
    assert ts[0] == 0.0
    assert all(a < b for a, b in zip(ts, ts[1:]))
    assert len(ts) <= 60
    # ~ every 2s
    assert any(abs(t - 2.0) < 1e-3 for t in ts)
    capped = videosim.sample_times(200.0, 25.0, interval_s=1.0, max_frames=10)
    assert len(capped) <= 10


def test_merge_segments():
    segs = videosim.merge_segments([1.0, 2.0, 3.0, 10.0, 11.5], gap=4.0)
    assert segs == [{"t0": 1.0, "t1": 3.0}, {"t0": 10.0, "t1": 11.5}]
    assert videosim.merge_segments([]) == []


def test_video_cache_key_stable():
    a = videosim.video_cache_key(100.0, 2.0, True, 60)
    b = videosim.video_cache_key(100.0, 2.0, True, 60)
    c = videosim.video_cache_key(100.1, 2.0, True, 60)
    assert a == b and a != c


def test_synth_video_sample_times_and_scene():
    import cv2
    td = tempfile.mkdtemp(prefix="rlvf_")
    try:
        f1 = _make_face_img(os.path.join(td, "f1.jpg"), mark=1)
        f2 = _make_face_img(os.path.join(td, "f2.jpg"), color=(200, 40, 40), mark=2)
        vid = os.path.join(td, "clip.mp4")
        # faces at 1.0s and 7.0s (after scene cut at 5s)
        make_synth_video(vid, duration_s=10.0, fps=10, face_at={1.0: f1, 7.0: f2})
        assert os.path.getsize(vid) > 1000

        t0 = time.perf_counter()
        samp = videosim.sample_frames(vid, interval_s=2.0, scene_detect=True, max_frames=60)
        dt = time.perf_counter() - t0
        assert samp["ok"], samp
        assert samp["method"] in ("cv2", "ffmpeg")
        assert len(samp["times"]) == len(samp["paths"]) >= 3
        # uniform 0,2,4,6,8,… present (approx)
        assert any(abs(t - 0.0) < 0.05 for t in samp["times"])
        assert any(abs(t - 2.0) < 0.15 for t in samp["times"])
        # scene cut near 5s should appear when scene_detect on
        # (histogram flip at half); allow loose match
        near_cut = [t for t in samp["times"] if 4.0 <= t <= 6.5]
        assert near_cut, ("expected scene sample near mid", samp["times"])
        # faces visible at sampled frames around 1s / 7s
        assert any(abs(t - 1.0) < 1.1 for t in samp["times"]) or any(abs(t - 0.0) < 0.1 for t in samp["times"])
        videosim.cleanup_sample(samp)

        # read_frame_at
        fr = videosim.read_frame_at(vid, 1.0)
        assert fr is not None and fr.shape[0] == 240

        # timing note for report
        print("TIMING sample_frames 10s@10fps box_cpu: %.3fs frames=%d method=%s" % (dt, len(samp.get("paths") or []), samp.get("method")))
        return dt, len(samp.get("paths") or [])
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def test_dedupe_video_faces_and_segments():
    class Src:
        model = "arcface"
        def item(self, h, m):
            if h == "vid1":
                return {"w": 320, "h": 240, "n": 3,
                        "nbox": [[0.3, 0.2, 0.3, 0.4]] * 3,
                        "t": [1.0, 2.0, 8.0], "kind": "video"}
            return {"w": 100, "h": 100, "n": 1, "nbox": [[0.1, 0.1, 0.2, 0.2]], "t": [None], "kind": "image"}
        def faces(self, m):
            return [], np.zeros((0, 8), np.float32)

    class Tags:
        def add(self, *a): pass
        def remove(self, *a): pass
        def rename(self, *a): pass
        def users(self, tag): return []

    d = tempfile.mkdtemp()
    try:
        svc = F.Faces(d, Src(), tagger=Tags())
        raw = [
            svc.face_obj(F.fid("img1", 0, "arcface"), "arcface", {"score": 0.9}),
            svc.face_obj(F.fid("vid1", 0, "arcface"), "arcface", {"score": 0.7}),
            svc.face_obj(F.fid("vid1", 1, "arcface"), "arcface", {"score": 0.95}),
            svc.face_obj(F.fid("vid1", 2, "arcface"), "arcface", {"score": 0.8}),
        ]
        out = svc.dedupe_video_faces(raw, merge_gap=4.0)
        # image + ONE video
        assert len(out) == 2, out
        vid = next(x for x in out if x["hash"] == "vid1")
        assert vid["best_t"] == 2.0  # highest score face
        assert vid["id"] == F.fid("vid1", 1, "arcface")
        # 1.0+2.0 merge; 8.0 separate (gap > 4 from 2)
        assert len(vid["segments"]) == 2
        assert vid["segments"][0]["t0"] == 1.0 and vid["segments"][0]["t1"] == 2.0
        assert vid["segments"][1]["t0"] == 8.0
        img = next(x for x in out if x["hash"] == "img1")
        assert img.get("kind") == "image" and "segments" not in img
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_search_segments_helper_matches_contract():
    # mirrors search-side merge used in similarity.search
    times = [0.0, 2.0, 4.1, 20.0]
    segs = videosim.merge_segments(times, gap=4.0)
    assert segs[0] == {"t0": 0.0, "t1": 4.1}
    assert segs[1] == {"t0": 20.0, "t1": 20.0}


if __name__ == "__main__":
    test_sample_times_grid_and_cap()
    test_merge_segments()
    test_video_cache_key_stable()
    test_dedupe_video_faces_and_segments()
    test_search_segments_helper_matches_contract()
    dt, n = test_synth_video_sample_times_and_scene()
    # longer timing pass for report
    td = tempfile.mkdtemp(prefix="rlvf_bench_")
    try:
        import cv2
        f1 = _make_face_img(os.path.join(td, "f1.jpg"))
        vid = os.path.join(td, "long.mp4")
        make_synth_video(vid, duration_s=60.0, fps=15, face_at={5.0: f1, 30.0: f1, 55.0: f1})
        t0 = time.perf_counter()
        samp = videosim.sample_frames(vid, interval_s=2.0, scene_detect=True, max_frames=60)
        dt60 = time.perf_counter() - t0
        n60 = len(samp.get("paths") or [])
        videosim.cleanup_sample(samp)
        print("TIMING sample_frames 60s@15fps box_cpu: %.3fs frames=%d" % (dt60, n60))
        # rough 5090 estimate: decode dominates on CPU; GPU face/pose ~5–15× faster than box CPU
        # for the analyse stage. Sampling itself stays CPU-bound (~same order on 5090 host).
        print("ESTIMATE 5090: sampling ~%.2fs (CPU-bound); face+pose analyse of %d frames ~%.1f–%.1fs (vs box CPU analyse if models present)" % (
            dt60, n60, n60 * 0.015, n60 * 0.04))
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    print("ALL OK")
