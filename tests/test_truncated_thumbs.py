"""1.12.5: truncated JPEGs either thumb successfully or fail once without spam."""
from __future__ import annotations
import io, os, tempfile, threading
from pathlib import Path

from PIL import Image, ImageFile

from reflib_core import imagelib


def _valid_jpeg(path: Path, size=(64, 48), color=(12, 34, 56)):
    im = Image.new("RGB", size, color)
    im.save(path, "JPEG", quality=90)


def _truncate(path: Path, keep_ratio: float = 0.35) -> None:
    data = path.read_bytes()
    path.write_bytes(data[: max(64, int(len(data) * keep_ratio))])


def test_truncated_jpeg_thumb_or_single_log(monkeypatch, capsys):
    ImageFile.LOAD_TRUNCATED_IMAGES = False  # ensure plugin restores/localizes
    with tempfile.TemporaryDirectory(prefix="rl-trunc-thumb-") as td:
        td = Path(td)
        monkeypatch.setattr(imagelib, "_thumbs_dir", lambda: str(td / ".thumbs"))
        # reset fail cache between tests
        imagelib._THUMB_FAIL.clear()
        src = td / "broken.jpg"
        _valid_jpeg(src)
        _truncate(src)

        uri1 = imagelib._img_data_uri(str(src), 64, str(td / ".thumbs" / "h1.jpg"))
        err1 = capsys.readouterr().out
        uri2 = imagelib._img_data_uri(str(src), 64, str(td / ".thumbs" / "h1.jpg"))
        err2 = capsys.readouterr().out

        # Either we recovered a thumbnail, or we logged exactly once and quieted afterwards.
        if uri1:
            assert uri1.startswith("data:image/jpeg;base64,")
            assert "thumbnail failed" not in err1
            assert err2 == ""
            assert (td / ".thumbs" / "h1.jpg").is_file()
        else:
            assert uri2 is None
            assert err1.count("thumbnail failed") == 1
            assert "truncated" in err1.lower() or "cannot identify" in err1.lower() or "thumbnail failed" in err1
            assert err2 == ""
            # negative cache persisted
            assert (td / ".thumbs" / "_fail_cache.json").is_file()

        # Flag must not stay enabled for the rest of the process.
        assert ImageFile.LOAD_TRUNCATED_IMAGES is False


def test_truncated_flag_restored_under_concurrency(monkeypatch):
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    with tempfile.TemporaryDirectory(prefix="rl-trunc-conc-") as td:
        td = Path(td)
        monkeypatch.setattr(imagelib, "_thumbs_dir", lambda: str(td / ".thumbs"))
        imagelib._THUMB_FAIL.clear()
        paths = []
        for i in range(8):
            p = td / f"t{i}.jpg"
            _valid_jpeg(p, color=(i * 10, 20, 30))
            if i % 2:
                _truncate(p, 0.3)
            paths.append(p)

        def work(p):
            imagelib._img_data_uri(str(p), 48, str(td / ".thumbs" / (p.stem + ".jpg")))

        threads = [threading.Thread(target=work, args=(p,)) for p in paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert ImageFile.LOAD_TRUNCATED_IMAGES is False


def test_rewritten_file_retries(monkeypatch, capsys):
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    with tempfile.TemporaryDirectory(prefix="rl-trunc-retry-") as td:
        td = Path(td)
        monkeypatch.setattr(imagelib, "_thumbs_dir", lambda: str(td / ".thumbs"))
        imagelib._THUMB_FAIL.clear()
        src = td / "flip.jpg"
        _valid_jpeg(src)
        _truncate(src, 0.2)
        # Force a hard failure path if truncated still loads: corrupt header enough
        raw = src.read_bytes()
        if len(raw) > 20:
            src.write_bytes(raw[:10] + b"\x00\x00\x00\x00" + raw[14:40])

        u1 = imagelib._img_data_uri(str(src), 32, str(td / ".thumbs" / "flip.jpg"))
        _ = capsys.readouterr()
        # rewrite with a good jpeg (mtime/size change)
        _valid_jpeg(src, color=(200, 10, 10))
        u2 = imagelib._img_data_uri(str(src), 32, str(td / ".thumbs" / "flip.jpg"))
        assert u2 and u2.startswith("data:image/jpeg;base64,")
