// node tests/test_playback_rules.mjs
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "playback_rules.js"));
const P = globalThis.ReflibPlayback;
assert.equal(P.version, 1);
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
console.log("test_playback_rules: ok");
