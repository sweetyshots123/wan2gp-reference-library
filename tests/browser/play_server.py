#!/usr/bin/env python3
"""Synthetic 1.12.19 play server: transcodes an mp4v fixture with reflib_core.playable
and streams GET /reflib/play/<hash> (finished cache or a growing fragmented MP4).
Never touches a real library — MEDIA and REFLIB_DATA_DIR come from the test runner.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("REFLIB_PLAY_ENCODER", "libx264")
# PLUGIN_DIR is read at storage import time
if "REFLIB_DATA_DIR" not in os.environ:
    raise SystemExit("REFLIB_DATA_DIR must be set (plugin-owned cache; never next to the fixture)")

from reflib_core import playable  # noqa: E402

MEDIA = Path(os.environ["MEDIA"])
SRC = MEDIA / "bad.mp4"
HASH = os.environ.get("PLAY_HASH", "mp4vfixture")
PORT = int(os.environ.get("PORT", "18919"))
PLAYBACK_JS = ROOT / "playback_rules.js"


def _state():
    playable.ensure(HASH, str(SRC), start=True)
    st = playable.status(HASH, str(SRC))
    play = st.get("play") or "failed"
    url = None if play == "failed" else f"/reflib/play/{HASH}"
    return {
        "ok": play != "failed",
        "play": play,
        "url": url,
        "rendering": play == "preparing",
        "codec": st.get("codec") or "",
        "progress": st.get("progress") or 0.0,
        "error": st.get("error"),
        "mode": st.get("mode") or "",
        "encoder": st.get("encoder") or playable.encoder_name(),
        "cache": playable.cache_dir(),
        "src": str(SRC),
        "path": st.get("path"),
    }


def _send_file(handler, path, ctype="video/mp4", extra=None, filename=None):
    path = Path(path)
    size = path.stat().st_size
    start, end = 0, size - 1
    rng = handler.headers.get("Range") or handler.headers.get("range")
    status = 200
    if rng:
        m = None
        try:
            unit, _, spec = rng.partition("=")
            if unit.strip() == "bytes":
                a, _, b = spec.partition("-")
                start = int(a or 0)
                end = int(b) if b else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    handler.send_response(416)
                    handler.send_header("Content-Range", f"bytes */{size}")
                    handler.end_headers()
                    return
                status = 206
        except ValueError:
            start, end, status = 0, size - 1, 200
    length = end - start + 1
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(length))
    handler.send_header("Accept-Ranges", "bytes")
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if filename:
        handler.send_header("Content-Disposition", f'inline; filename="{filename}"')
    for k, v in (extra or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    if handler.command == "HEAD":
        return
    with open(path, "rb") as fh:
        fh.seek(start)
        left = length
        while left > 0:
            chunk = fh.read(min(64 * 1024, left))
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            left -= len(chunk)


def _stream_part(handler, path, digest, src):
    handler.send_response(200)
    handler.send_header("Content-Type", "video/mp4")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if handler.command == "HEAD":
        return
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if chunk:
                try:
                    handler.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                continue
            cur = playable.status(digest, src)
            if cur.get("play") == "ready":
                rest = fh.read()
                if rest:
                    try:
                        handler.wfile.write(rest)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                return
            if cur.get("play") == "failed":
                return
            time.sleep(0.12)


PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>playable mp4v</title>
<style>
  body { font: 14px system-ui; background: #111; color: #eee; }
  video { width: 640px; max-width: 100%; background: #000; display: block; }
  .vprep, .vbad { margin-top: 8px; padding: 8px 12px; background: #222; border-radius: 8px; display: none; }
  .on { display: block; }
</style></head>
<body>
<video id="v" controls autoplay playsinline></video>
<div id="prep" class="vprep" role="status"></div>
<div id="bad" class="vbad" role="status"></div>
<pre id="log"></pre>
<script src="/playback_rules.js"></script>
<script>
const v = document.getElementById("v");
const prep = document.getElementById("prep");
const bad = document.getElementById("bad");
const log = document.getElementById("log");
const P = window.ReflibPlayback;
window.__play = { play: null, url: null, width: 0, ready: 0, err: null, notice: false, preparing: false };
function paint(s) {
  window.__play = {
    play: s && s.play, url: s && s.url, width: v.videoWidth || 0, ready: v.readyState || 0,
    err: v.error ? v.error.code : null,
    notice: !!(P && P.showUnplayable(s, v)),
    preparing: !!(P && P.showPreparing(s, v)),
    currentTime: v.currentTime || 0, duration: v.duration || 0,
  };
  const lab = P ? P.playLabels("es") : {};
  prep.textContent = lab.preparing || "Preparando vídeo…";
  bad.textContent = lab.unplayable || "";
  prep.classList.toggle("on", window.__play.preparing);
  bad.classList.toggle("on", window.__play.notice);
  log.textContent = JSON.stringify(window.__play);
}
if (P && P.watchPlay) {
  P.watchPlay(() => fetch("/media_url").then(r => r.json()), (s) => {
    if (s.url && v.getAttribute("src") !== s.url) {
      const keep = (v.currentTime || 0) > 0.05 ? { t: v.currentTime, paused: v.paused } : null;
      v.src = s.url;
      if (keep) {
        const on = () => {
          try { if (isFinite(keep.t)) v.currentTime = keep.t; } catch (e) {}
          if (!keep.paused) v.play().catch(() => {});
          v.removeEventListener("loadedmetadata", on);
        };
        v.addEventListener("loadedmetadata", on);
      }
      v.play().catch(() => {});
    }
    paint(s);
  }, v);
  const evs = P.UNPLAYABLE_EVENTS || ["error", "loadedmetadata", "playing", "canplay"];
  for (const e of evs) v.addEventListener(e, () => paint(P.playReply(window.__play)));
} else {
  fetch("/media_url").then(r => r.json()).then(s => { v.src = s.url; v.play().catch(() => {}); paint(s); });
}
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[play_server] " + (fmt % args) + "\n")

    def _json(self, obj, code=200):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _bytes(self, raw, ctype, code=200):
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path in ("/", "/index.html"):
            return self._bytes(PAGE, "text/html; charset=utf-8")
        if path == "/playback_rules.js":
            return _send_file(self, PLAYBACK_JS, "text/javascript; charset=utf-8")
        if path == "/media_url" or path == "/status":
            return self._json(_state())
        if path == "/health":
            return self._json({"ok": True, "src": str(SRC), "cache": playable.cache_dir()})
        if path.startswith("/reflib/play/"):
            digest = path.rsplit("/", 1)[-1]
            if digest != HASH or not SRC.is_file():
                self.send_response(404)
                self.end_headers()
                return
            src = str(SRC)
            st = playable.ensure(digest, src, start=True)
            if st.get("play") == "failed":
                return self._json({"ok": False, "error": st.get("error") or "transcode failed"}, 415)
            if st.get("play") == "original":
                mt = mimetypes.guess_type(src)[0] or "video/mp4"
                return _send_file(self, src, mt, filename=SRC.name)
            deadline = time.time() + 45
            while time.time() < deadline:
                cur = playable.status(digest, src)
                if cur.get("play") == "failed":
                    return self._json({"ok": False, "error": cur.get("error") or "transcode failed"}, 415)
                if cur.get("play") == "ready" and cur.get("path") and os.path.isfile(cur["path"]):
                    return _send_file(self, cur["path"], "video/mp4",
                                      extra={"Cache-Control": "private, max-age=3600"},
                                      filename=playable.serve_name(digest, src))
                if playable.part_ready(digest, src, 256):
                    part = playable.play_file(digest, src)
                    if part:
                        return _stream_part(self, part, digest, src)
                time.sleep(0.12)
            self.send_response(425)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b"preparing")
            return
        self.send_response(404)
        self.end_headers()


def main():
    if not SRC.is_file():
        raise SystemExit(f"missing fixture {SRC}")
    playable._reset_for_tests()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stdout.write(f"ready {PORT}\n")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
