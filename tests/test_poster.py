"""1.12.2 poster frame: ~10% / >=1 s in, skipping black frames; open_file command. python3 tests/test_poster.py"""
import os, sys, shutil, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflib_core import media, reveal
assert media.poster_times(0) == [0.0]
assert media.poster_times(20)[0] == 2.0 and media.poster_times(4)[0] == 1.0 and media.poster_times(0.6)[0] == 0.3
assert reveal.open_command("C:\\a b\\v.mp4", "win32") == ["explorer.exe", "C:\\a b\\v.mp4"] and reveal.open_command("/x/v.mp4", "linux") == ["xdg-open", "/x/v.mp4"]
if shutil.which("ffmpeg"):
    d = tempfile.mkdtemp(); v = os.path.join(d, "b.mp4"); out = os.path.join(d, "p.jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=160x120:d=1.5,format=yuv420p", "-f", "lavfi", "-i", "testsrc=s=160x120:d=3",
                    "-filter_complex", "[0][1]concat=n=2:v=1", "-pix_fmt", "yuv420p", v], check=True)
    assert media.make_poster(v, out)
    try:
        import cv2
        assert cv2.imread(out).mean() > 40, "black poster"
    except ImportError:
        pass
print("ok test_poster")
