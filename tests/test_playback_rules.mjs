// node tests/test_playback_rules.mjs
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "playback_rules.js"));
const P = globalThis.ReflibPlayback;
assert.equal(P.version, 2);
assert.equal(P.DEFAULT_MIN_S, 300);
assert.equal(P.shouldTrack(400, 60, 300), true);
assert.equal(P.shouldTrack(200, 60, 300), false);
assert.equal(P.shouldTrack(400, 2, 300), false);
assert.equal(P.shouldTrack(400, 396, 300), false);
assert.equal(P.fmt(65), "1:05");
assert.equal(P.fmt(3661), "1:01:01");
const es = P.offerLabels(90, "es");
assert.match(es.continue, /Seguir desde 1:30/);
assert.match(es.restart, /principio/);
const en = P.offerLabels(90, "en");
assert.match(en.continue, /Continue from 1:30/);
// 1.12.15 unplayable(): live state of the loaded <video>, never sticky (fake elements, no media)
{
  const P = globalThis.ReflibPlayback, V = (o) => ({ error: null, readyState: 0, videoWidth: 0, currentSrc: "", getAttribute: () => o.src ?? null, ...o });
  assert.equal(P.unplayable(null), false);
  assert.equal(P.unplayable(V({ src: "/m/a.mp4", currentSrc: "/m/a.mp4", error: { code: 4 } })), true, "unsupported source");
  assert.equal(P.unplayable(V({ src: "/m/a.mp4", currentSrc: "/m/a.mp4", error: { code: 3 } })), true, "decode error");
  assert.equal(P.unplayable(V({ src: "/m/a.mp4", currentSrc: "/m/a.mp4", error: { code: 2 } })), false, "network error is not a codec problem");
  assert.equal(P.unplayable(V({ src: "/m/a.mp4", currentSrc: "/m/a.mp4", error: { code: 1 } })), false, "aborted load");
  assert.equal(P.unplayable(V({ src: "/m/a.mp4", currentSrc: "/m/a.mp4", readyState: 1, videoWidth: 0 })), true, "metadata without a picture");
  assert.equal(P.unplayable(V({ src: "/m/a.mp4", currentSrc: "/m/a.mp4", readyState: 4, videoWidth: 320 })), false, "plays");
  assert.equal(P.unplayable(V({ src: "/m/b.webm", readyState: 0 })), false, "new load in progress (error reset by the browser)");
  assert.equal(P.unplayable(V({})), false, "no source");
  for (const e of ["error", "loadstart", "emptied", "loadedmetadata", "playing"]) assert.ok(P.UNPLAYABLE_EVENTS.includes(e), e);
}

// 1.12.19: preparing / failed vs the unplayable notice
{
  const P = globalThis.ReflibPlayback;
  const V = (o) => ({ error: null, readyState: 0, videoWidth: 0, currentSrc: "", getAttribute: () => o.src ?? null, ...o });
  const ok = V({ src: "/p.mp4", currentSrc: "/p.mp4", readyState: 4, videoWidth: 320 });
  const bad = V({ src: "/b.mp4", currentSrc: "/b.mp4", error: { code: 4 } });
  const sPrep = P.playReply({ play: "preparing", url: "/reflib/play/h", rendering: true, codec: "mpeg4", progress: 0.2 });
  const sFail = P.playReply({ play: "failed", error: "ffmpeg failed" });
  const sReady = P.playReply({ play: "ready", url: "/gradio/x" });
  const sOld = P.playReply({ url: "/m/a.mp4" });
  assert.equal(sPrep.preparing, true); assert.equal(sPrep.codec, "mpeg4");
  assert.equal(P.showPreparing(sPrep, null), true);
  assert.equal(P.showPreparing(sPrep, ok), false, "hide the banner once the stream is playing");
  assert.equal(P.showUnplayable(sPrep, bad), false, "no unsupported notice while converting");
  assert.equal(P.showUnplayable(sFail, ok), true);
  assert.equal(P.showUnplayable(sReady, ok), false);
  assert.equal(sOld.play, "original");
  const es = P.playLabels("es");
  assert.match(es.preparing, /Preparando vídeo/);
  assert.match(es.preparingTip, /original no se modifica/);
  const en = P.playLabels("en");
  assert.match(en.preparing, /Preparing video/);
}
console.log("test_playback_rules: ok");
