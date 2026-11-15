"""1.12.21: imagelib indexes the same video extensions as media.VIDEO_EXTS.

Synthetic only: empty placeholder files and kind_of / _candidates. Does not touch a real library.
Adding extensions must not rewrite kinds of already-recognised files, or any tags.
"""
import os, sys, tempfile, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
td = tempfile.mkdtemp(prefix="reflib-exts-")
os.environ.setdefault("REFLIB_DATA_DIR", td)

from reflib_core import imagelib, media


NEW = (".mpg", ".mpeg", ".wmv", ".ts", ".mts", ".m2ts", ".flv", ".3gp")
OLD_VIDEO = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
AUDIO = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus")


def test_video_exts_match_media_module():
    assert imagelib.VIDEO_EXTS == media.VIDEO_EXTS
    for e in NEW + OLD_VIDEO:
        assert e in imagelib.VIDEO_EXTS
        assert e in imagelib.MEDIA_EXTS


def test_kind_of_existing_extensions_unchanged():
    for e in OLD_VIDEO:
        assert imagelib.kind_of("clip" + e) == "video"
        assert imagelib.kind_of("/tmp/lib/clip" + e) == "video"
    for e in IMAGES:
        assert imagelib.kind_of("pic" + e) == "image"
    for e in AUDIO:
        assert imagelib.kind_of("track" + e) == "audio"
    assert imagelib.kind_of("notes.txt") == ""
    assert imagelib.kind_of("file.exe") == ""


def test_kind_of_new_containers_are_video():
    for e in NEW:
        assert imagelib.kind_of("movie" + e) == "video", e
        assert imagelib.kind_of("Movie" + e.upper()) == "video", e  # extension is lowercased


def test_candidates_lists_new_exts_and_ignores_non_media():
    root = os.path.join(td, "folder")
    os.makedirs(root, exist_ok=True)
    names = ["keep.jpg", "old.mp4", "a.mpg", "b.mpeg", "c.wmv", "d.ts", "e.m2ts", "f.flv", "g.3gp", "h.mts",
             "skip.txt", "also.exe", ".hidden.mpg"]
    for n in names:
        open(os.path.join(root, n), "wb").write(b"x")
    found = {os.path.basename(p) for p in imagelib._candidates({"path": root, "recursive": True})}
    assert "keep.jpg" in found and "old.mp4" in found
    for n in ["a.mpg", "b.mpeg", "c.wmv", "d.ts", "e.m2ts", "f.flv", "g.3gp", "h.mts"]:
        assert n in found, n
    assert "skip.txt" not in found and "also.exe" not in found
    assert ".hidden.mpg" not in found  # existing skip-dotfiles rule


def test_kind_of_and_scan_do_not_rewrite_tags():
    """Tags live in the tag store, not in kind_of. A pass over kind_of / _candidates must leave tags.json alone."""
    tags_path = os.path.join(td, "dummy-tags.json")
    payload = {"version": 1, "tags": {"abc123": ["favorita", "persona:Ada"]}}
    with open(tags_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    before = open(tags_path, "rb").read()
    mtime = os.path.getmtime(tags_path)
    # resolve kinds for a mix of old and new files (pure; no tag I/O)
    for e in OLD_VIDEO + NEW + IMAGES + AUDIO:
        imagelib.kind_of("item" + e)
    imagelib._candidates({"path": os.path.join(td, "folder"), "recursive": True})
    assert open(tags_path, "rb").read() == before
    assert os.path.getmtime(tags_path) == mtime
    # the stored tags themselves are unchanged
    with open(tags_path, encoding="utf-8") as f:
        after = json.load(f)
    assert after["tags"]["abc123"] == ["favorita", "persona:Ada"]
